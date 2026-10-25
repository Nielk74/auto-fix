"""Triage decisions, suite comparison, test history, metrics, settings and health checks."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from test_jobs import post, write_config

from auto_fix import health, history
from auto_fix.config import LLMConfig, load_settings
from auto_fix.dashboard import serve
from auto_fix.jobs import JobError
from auto_fix.llm import RepairModel
from auto_fix.schedules import ScheduleStore
from auto_fix.triage import TriageStore, active


def seed(root, name, status, *, day=20, tests=("math.add",), reason="", base=None, final=None):
    folder = root / "runs" / name
    folder.mkdir(parents=True)
    result = {
        "status": status,
        "reason": reason,
        "failure": {"build_type": "Cpp_Tests", "tests": [{"name": test} for test in tests]},
        "baseline": {"report": base or {"passed": ["math.sub"], "failed": list(tests)}},
        "verification": {"report": final or {"passed": list(tests), "failed": []}},
    }
    (folder / "result.json").write_text(json.dumps(result), encoding="utf-8")
    events = [
        {"node": "collect_context", "time": f"2026-10-{day:02d}T10:00:00+00:00"},
        {"node": "model_call", "ok": False, "time": f"2026-10-{day:02d}T10:01:00+00:00"},
        {"node": "verify", "time": f"2026-10-{day:02d}T10:05:00+00:00"},
    ]
    (folder / "events.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )
    return folder


def test_a_decision_takes_a_run_out_of_attention_until_reopened_or_the_snooze_ends(tmp_path):
    seed(tmp_path, "tc-1", "ready")
    seed(tmp_path, "tc-2", "blocked", day=21)
    store = TriageStore(tmp_path)
    assert history.run_page(tmp_path)["attention_total"] == 2
    record = store.update("runs/tc-1", "reject", "ana", note="Changes the public contract")
    assert record["state"] == "rejected" and record["notes"][0]["text"].startswith("Changes")
    page = history.run_page(tmp_path)
    assert [run["name"] for run in page["attention"]] == ["tc-2"]
    assert [run["name"] for run in history.run_page(tmp_path, status="triaged")["runs"]] == ["tc-1"]
    store.update("runs/tc-1", "reopen", "ana")
    assert history.run_page(tmp_path)["attention_total"] == 2
    now = datetime(2026, 10, 25, tzinfo=UTC)
    snoozed = store.update("runs/tc-2", "snooze", "ana", until="2026-10-27", at=now)
    assert active(snoozed, now) and not active(snoozed, now + timedelta(days=3))
    store.update("runs/tc-2", "rate", "ana", rating="bad", note="Hides the bug")
    assert store.get("runs/tc-2")["rating"]["value"] == "bad"


@pytest.mark.parametrize(
    "action, fields",
    [
        ("note", {}),
        ("rate", {"rating": "meh"}),
        ("snooze", {"until": ""}),
        ("snooze", {"until": "2020-01-01"}),
        ("explode", {}),
    ],
)
def test_triage_rejects_incomplete_decisions(tmp_path, action, fields):
    with pytest.raises(JobError):
        TriageStore(tmp_path).update("runs/tc-1", action, "ana", **fields)


def test_comparison_names_fixed_remaining_and_newly_broken_tests(tmp_path):
    seed(
        tmp_path,
        "tc-1",
        "blocked",
        tests=("a", "b"),
        base={"passed": ["c", "d"], "failed": ["a", "b"]},
        final={"passed": ["a", "d"], "failed": ["b", "c"]},
    )
    detail = history.run_detail(tmp_path, "runs/tc-1")
    assert detail["comparison"]["fixed"] == ["a"]
    assert detail["comparison"]["still_failing"] == ["b"]
    assert detail["comparison"]["regressions"] == ["c"]
    assert detail["summary"]["regressions"] == 1


def test_detail_lists_each_build_check_with_its_logs(tmp_path):
    run = seed(tmp_path, "tc-1", "ready")
    for label in ("baseline-0123456789ab", "attempt-1-ba9876543210"):
        (run / "evidence" / label).mkdir(parents=True)
        (run / "evidence" / label / "test.log").write_text("ok\n", encoding="utf-8")
    labels = {item["label"] for item in history.run_detail(tmp_path, "runs/tc-1")["builds"]}
    assert labels == {"baseline", "attempt-1"}
    files = history.run_detail(tmp_path, "runs/tc-1")["builds"][0]["files"]
    assert files[0]["path"].startswith("evidence/") and files[0]["path"].endswith("test.log")


def test_test_history_counts_fixes_and_failures_that_did_not_reproduce(tmp_path):
    seed(tmp_path, "tc-1", "ready", day=20)
    seed(tmp_path, "tc-2", "blocked", day=21, reason="failures were not reproduced after rebase")
    seed(tmp_path, "tc-3", "blocked", day=22, tests=("math.mul",))
    index = history.failing_tests(tmp_path)
    assert [row["name"] for row in index["tests"]] == ["math.mul", "math.add"]
    add = index["tests"][1]
    assert (add["runs"], add["fixed"], add["not_reproduced"]) == (2, 1, 1)
    assert add["last"]["name"] == "tc-2" and add["first_seen"].startswith("2026-10-20")
    assert history.failing_tests(tmp_path, q="MUL")["total"] == 1
    runs = history.runs_for_test(tmp_path, "math.add")["runs"]
    assert [run["name"] for run in runs] == ["tc-2", "tc-1"]


def test_metrics_report_fix_rate_durations_tokens_and_failed_calls(tmp_path):
    ready = seed(tmp_path, "tc-1", "ready", day=20)
    seed(tmp_path, "tc-2", "blocked", day=21)
    seed(tmp_path, "tc-3", "ready", day=1)
    (ready / "model-calls").mkdir()
    call = {"usage": {"prompt_tokens": 1200, "completion_tokens": 300}}
    (ready / "model-calls" / "01-repair.json").write_text(json.dumps(call), encoding="utf-8")
    found = history.metrics(tmp_path, days=7, now=datetime(2026, 10, 22, tzinfo=UTC))
    total = found["total"]
    assert total["runs"] == 2 and total["fix_rate"] == 0.5
    assert total["median_duration"] == 300 and total["median_time_to_candidate"] == 300
    assert (total["tokens_in"], total["tokens_out"]) == (1200, 300)
    assert (total["model_calls"], total["failed_model_calls"]) == (2, 2)
    assert [row["key"] for row in found["workflows"]] == ["bt:Cpp_Tests"]
    assert len(found["daily"]) == 7 and found["daily"][4] == {"date": "2026-10-20", "ready": 1}
    with pytest.raises(ValueError):
        history.metrics(tmp_path, days=0)


def test_history_sorts_by_duration_and_age(tmp_path):
    seed(tmp_path, "tc-1", "ready", day=20)
    seed(tmp_path, "tc-2", "ready", day=21)
    assert [r["name"] for r in history.run_page(tmp_path, sort="started")["runs"]] == [
        "tc-1",
        "tc-2",
    ]
    with pytest.raises(ValueError):
        history.run_page(tmp_path, sort="name")


def test_settings_show_token_variables_by_name_never_their_values(tmp_path, monkeypatch):
    monkeypatch.setenv("UNUSED_TOKEN", "super-secret-value")
    described = health.describe(load_settings(write_config(tmp_path)))
    assert described["llm"]["token_env"] == "UNUSED_TOKEN" and described["llm"]["token_set"]
    assert "super-secret-value" not in json.dumps(described)


def test_health_reports_status_codes_missing_tokens_and_unreachable_services(tmp_path, monkeypatch):
    settings = load_settings(write_config(tmp_path))
    monkeypatch.delenv("UNUSED_TOKEN", raising=False)
    assert all(not item["ok"] for item in health.check(settings))
    monkeypatch.setenv("UNUSED_TOKEN", "token-value")

    def handler(request):
        assert request.headers["authorization"] == "Bearer token-value"
        if request.url.path.endswith("/models"):
            raise httpx.ConnectError("refused")
        code = 401 if "projects" in request.url.path else 200
        return httpx.Response(code, text="server body must not leak")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        checks = {item["name"]: item for item in health.check(settings, client)}
    assert checks["TeamCity"]["ok"] and checks["TeamCity"]["detail"] == "HTTP 200"
    assert checks["Bitbucket"]["detail"] == "HTTP 401 (token rejected)"
    assert checks["Model endpoint"]["detail"] == "Unreachable (ConnectError)"
    assert not checks["Git repository"]["ok"]
    assert "server body" not in json.dumps(checks)


def test_schedule_preview_lists_upcoming_runs_without_saving(tmp_path):
    store = ScheduleStore(tmp_path)
    data = {"name": "Nightly", "kind": "demo", "params": {}, "time": "02:00", "frequency": "daily"}
    upcoming = store.preview(data, at=datetime(2026, 10, 24, tzinfo=UTC))
    assert len(upcoming) == 5 and upcoming[0] == "2026-10-25T00:00:00+00:00"
    assert store.all() == []
    with pytest.raises(JobError):
        store.preview({**data, "time": "25:00"})


def test_truncated_model_output_is_kept_for_inspection(monkeypatch):
    monkeypatch.setenv("MODEL_TOKEN", "token")
    answer = {"finish_reason": "length", "message": {"content": '{"summary": "cut'}}
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"choices": [answer]}))
    config = LLMConfig(url="https://model.internal/v1", token_env="MODEL_TOKEN", model="qwen")
    model = RepairModel(config, httpx.Client(transport=transport))
    with pytest.raises(ValueError, match="finish_reason: length"):
        model.propose({})
    assert model.last_raw == '{"summary": "cut'


@pytest.fixture
def controlled(tmp_path):
    seed(tmp_path / "state", "tc-1", "ready")
    server = serve(tmp_path / "state", "127.0.0.1", 0, config=write_config(tmp_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    with urllib.request.urlopen(base + "/") as response:
        page = response.read().decode()
    token = page.split('name="auto-fix-token" content="', 1)[1].split('"', 1)[0]
    yield base, token
    server.shutdown()
    server.server_close()


def read(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read())


def test_dashboard_serves_tests_metrics_settings_and_triage(controlled):
    base, token = controlled
    assert read(base + "/api/tests")["tests"][0]["name"] == "math.add"
    assert read(base + "/api/tests?name=math.add")["runs"][0]["name"] == "tc-1"
    assert "total" in read(base + "/api/metrics?days=30")
    settings = read(base + "/api/settings")
    assert settings["config"]["teamcity"]["build_types"] == ["Cpp_Tests"]
    _, done = post(base + "/api/runs/triage", {"run": "runs/tc-1", "action": "dismiss"}, token)
    assert done["triage"]["state"] == "dismissed"
    assert read(base + "/api/runs")["attention_total"] == 0
    assert read(base + "/api/run?id=runs%2Ftc-1")["summary"]["triage"]["state"] == "dismissed"
    with pytest.raises(urllib.error.HTTPError) as error:
        post(base + "/api/runs/triage", {"run": "runs/missing", "action": "dismiss"}, token)
    assert error.value.code == 400
    _, preview = post(
        base + "/api/schedules/preview",
        {"name": "n", "kind": "demo", "params": {}, "time": "02:00"},
        token,
    )
    assert len(preview["upcoming"]) == 5
    with pytest.raises(urllib.error.HTTPError) as error:
        post(base + "/api/runs/triage", {"run": "runs/tc-1", "action": "dismiss"})
    assert error.value.code == 403


def test_a_rejected_fix_cannot_be_published_until_reopened(tmp_path):
    from auto_fix.actions import Actions

    seed(tmp_path, "tc-1", "ready")
    actions = Actions(tmp_path)
    assert "publish" in actions.available("runs/tc-1")["actions"]
    TriageStore(tmp_path).update("runs/tc-1", "reject", "ana")
    offered = actions.available("runs/tc-1")
    assert "publish" not in offered["actions"] and offered["note"].startswith("Fix rejected")
    with pytest.raises(JobError):
        actions.perform("runs/tc-1", "publish", "ana")
    TriageStore(tmp_path).update("runs/tc-1", "reopen", "ana")
    assert "publish" in actions.available("runs/tc-1")["actions"]
