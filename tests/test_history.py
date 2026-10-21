from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from types import SimpleNamespace

import pytest

from auto_fix import history, tracing
from auto_fix.config import Settings
from auto_fix.dashboard import serve
from auto_fix.models import FailedTest, Failure, Proposal, Verification
from auto_fix.models import TestReport as Report
from auto_fix.workflow import Workflow


def failure():
    return Failure(
        build_id="7",
        build_type="Cpp_Tests",
        build_url="https://teamcity.example/build/7",
        revision="a" * 40,
        tests=[FailedTest(id="1", name="math.add")],
    )


def report(*, passed=(), failed=()):
    return Verification(
        build_ok=True,
        test_ok=not failed,
        report=Report(passed=list(passed), failed=list(failed)),
        output="test evidence",
    )


class Workspace:
    branch = "auto-fix/run"

    def __init__(self, path):
        self.path = path
        self.current = "b" * 40

    def prepare(self, revision):
        pass

    def context(self, changes, max_chars, test_names=None, signals=""):
        return {"files": [{"path": "src/add.cpp", "content": "return a - b;"}]}

    def apply_edits(self, edits):
        pass

    def commit(self, summary):
        pass

    def rebase(self):
        self.current = "c" * 40
        return self.current

    def head(self):
        return self.current

    def is_clean(self):
        return True

    def has_changes_against_base(self):
        return True

    def committed_diff(self):
        return "-return a - b;\n+return a + b;\n"


class Builder:
    def __init__(self, reports, crash_on=None):
        self.reports = deque(reports)
        self.crash_on = crash_on

    def verify(self, path, label):
        if label == self.crash_on:
            raise RuntimeError("runner disappeared")
        return self.reports.popleft()


class Model:
    def __init__(self, failures=0):
        self.failures = failures
        self.calls = []

    def propose(self, context):
        self.calls.append({"usage": {"input_tokens": 1200, "output_tokens": 80}})
        if self.failures:
            self.failures -= 1
            raise ValueError("Model output was truncated or did not complete normally")
        return Proposal.model_validate(
            {
                "summary": "Fix arithmetic",
                "explanation": "Use addition.",
                "edits": [{"path": "src/add.cpp", "old": "a - b", "new": "a + b"}],
            }
        )


@pytest.fixture
def run_flow(tmp_path):
    service = {"url": "https://internal.invalid", "token_env": "UNUSED_TOKEN"}

    def run(state_dir, run_id, reports, *, model=None, crash_on=None, max_attempts=2):
        settings = Settings.model_validate(
            {
                "state_dir": state_dir,
                "teamcity": {**service, "build_types": ["Cpp_Tests"]},
                "bitbucket": {**service, "project": "CPP", "repo": "app"},
                "llm": {**service, "model": "qwen", "context_chars": 4000},
                "repository": {"path": tmp_path / "source"},
                "build": {"build": [["build"]], "test": ["tests", "{junit}"]},
                "max_attempts": max_attempts,
            }
        )
        flow = Workflow(
            settings,
            run_id,
            SimpleNamespace(build_log=lambda _id: "math.add failed"),
            SimpleNamespace(context=lambda commits: []),
            None,
            model or Model(),
            publish=False,
        )
        flow.workspace = Workspace(tmp_path)
        flow.builder = Builder(reports, crash_on)
        flow.run({"run_id": run_id, "failure": failure().model_dump()})
        return flow

    return run


def test_detail_rebuilds_executed_path_loops_and_state_changes(run_flow, tmp_path):
    state = tmp_path / "state"
    run_flow(
        state,
        "tc-7-aaaa",
        [report(failed=["math.add"]), report(failed=["math.add"]), report(passed=["math.add"])]
        + [report(passed=["math.add"])],
    )
    detail = history.run_detail(state, "runs/tc-7-aaaa")
    nodes = [step["node"] for step in detail["steps"]]
    assert nodes == [
        "collect_context",
        "prepare",
        "baseline",
        "repair",
        "verify",
        "repair",
        "verify",
        "finalize",
        "publish_pr",
    ]
    assert [step["index"] for step in detail["steps"]] == list(range(9))
    assert detail["steps"][4]["status"] == "verification_failed"
    assert "verification" in detail["steps"][4]["changes"]
    assert detail["graph"]["visits"]["repair"] == 2
    assert detail["graph"]["transitions"]["verify>repair"] == 1
    assert detail["graph"]["transitions"]["publish_pr>__end__"] == 1
    assert {edge["target"] for edge in detail["graph"]["edges"]} >= {"blocked", "investigate"}
    assert detail["summary"]["status"] == "ready"
    full = history.state_at(state, "runs/tc-7-aaaa", detail["steps"][3]["checkpoint"])
    assert full["values"]["proposal"]["summary"] == "Fix arithmetic"
    assert full["values"]["failure"]["build_id"] == "7"


def test_every_model_call_is_recorded_with_context_usage_and_errors(run_flow, tmp_path):
    state = tmp_path / "state"
    run_flow(
        state,
        "tc-7-bbbb",
        [report(failed=["math.add"]), report(passed=["math.add"]), report(passed=["math.add"])],
        model=Model(failures=1),
    )
    calls = history.run_detail(state, "runs/tc-7-bbbb")["model_calls"]
    assert [(c["index"], c["kind"], c["attempt"]) for c in calls] == [
        (1, "repair", 1),
        (2, "repair", 2),
    ]
    assert "truncated" in calls[0]["error"] and calls[0]["response"] is None
    assert calls[1]["error"] is None and calls[1]["response"]["summary"] == "Fix arithmetic"
    assert calls[1]["usage"] == {"input_tokens": 1200, "output_tokens": 80}
    record = json.loads((state / "runs/tc-7-bbbb/model-calls/02-repair.json").read_text())
    assert record["context"]["failure"]["build_id"] == "7"
    events = (state / "runs/tc-7-bbbb/events.jsonl").read_text().splitlines()
    assert sum(json.loads(line)["node"] == "model_call" for line in events) == 2


def test_node_stopped_by_exception_is_interrupted_and_never_reaches_end(run_flow, tmp_path):
    state = tmp_path / "state"
    run_flow(state, "tc-7-cccc", [report(failed=["math.add"])], crash_on="attempt-1")
    detail = history.run_detail(state, "runs/tc-7-cccc")
    assert detail["steps"][-1]["node"] == "verify"
    assert detail["steps"][-1]["status"] == "interrupted"
    assert "__end__" not in detail["graph"]["visits"]
    assert detail["summary"]["status"] == "blocked"
    assert "runner disappeared" in detail["summary"]["reason"]


def test_discovery_groups_evaluation_cases_and_skips_checkouts_and_model_calls(tmp_path):
    for relative in [
        "case_a/state/runs/tc-1-aaaa",
        "case_b/state/runs/tc-2-bbbb",
        "case_a/source/state/runs/tc-9-hidden",
        "case_a/model/call-1",
    ]:
        (tmp_path / relative).mkdir(parents=True)
        (tmp_path / relative / "events.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "case_a/source/.git").mkdir()
    runs = {run["id"]: run for run in history.list_runs(tmp_path)}
    assert set(runs) == {"case_a/state/runs/tc-1-aaaa", "case_b/state/runs/tc-2-bbbb"}
    assert runs["case_a/state/runs/tc-1-aaaa"]["group"] == "case_a"
    assert runs["case_a/state/runs/tc-1-aaaa"]["status"] == "in_progress"


def test_reconciled_receipt_status_wins_over_the_graph_result(run_flow, tmp_path):
    state = tmp_path / "state"
    run_flow(
        state,
        "tc-7-dddd",
        [report(failed=["math.add"]), report(passed=["math.add"]), report(passed=["math.add"])],
    )
    pr = {"id": 5, "links": {"self": [{"href": "https://bitbucket.example/pr/5"}]}}
    receipt = {"run_id": "tc-7-dddd", "status": "published", "pr": pr}
    (state / "receipts").mkdir()
    (state / "receipts/tc-7-dddd.json").write_text(json.dumps(receipt), encoding="utf-8")
    summary = history.list_runs(state)[0]
    assert summary["status"] == "published"
    assert summary["graph_status"] == "ready"
    assert summary["pr_url"] == "https://bitbucket.example/pr/5"


def test_runs_without_checkpoints_fall_back_to_logged_node_events(tmp_path):
    run = tmp_path / "runs" / "tc-1-old"
    run.mkdir(parents=True)
    events = [
        {"time": "2026-01-02T10:00:00+00:00", "node": "collect_context"},
        {"time": "2026-01-02T10:00:05+00:00", "node": "repair", "attempt": 1},
        {"time": "2026-01-02T10:00:06+00:00", "node": "model_call", "kind": "repair"},
    ]
    (run / "events.jsonl").write_text("\n".join(map(json.dumps, events)), encoding="utf-8")
    detail = history.run_detail(tmp_path, "runs/tc-1-old")
    assert [step["node"] for step in detail["steps"]] == ["collect_context", "repair"]
    assert detail["steps"][1]["details"] == {"attempt": 1}
    assert detail["summary"]["duration_seconds"] == 6


def test_artifact_reads_stay_inside_the_run_and_exclude_checkpoints(run_flow, tmp_path):
    state = tmp_path / "state"
    run_flow(state, "tc-7-eeee", [report(failed=["other"])])
    (state / "secret.txt").write_text("outside", encoding="utf-8")
    assert history.read_file(state, "runs/tc-7-eeee", "result.json")[1] == "application/json"
    assert history.read_file(state, "runs/tc-7-eeee", "events.jsonl")[1] == "text/plain"
    assert history.read_file(state, "runs/tc-7-eeee", "../../secret.txt") is None
    assert history.read_file(state, "runs/tc-7-eeee", "checkpoints.sqlite") is None
    assert history.read_file(state, "runs/missing", "result.json") is None
    assert all("checkpoints" not in f["path"] for f in history.files(state / "runs/tc-7-eeee"))


@pytest.fixture
def dashboard(run_flow, tmp_path):
    state = tmp_path / "state"
    run_flow(state, "tc-7-ffff", [report(failed=["other"])])
    server = serve(state, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


def fetch(url, host=None):
    request = urllib.request.Request(url, headers={"Host": host} if host else {})
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, response.headers, response.read().decode("utf-8")


def test_dashboard_serves_page_and_run_api_with_restrictive_headers(dashboard):
    status, headers, page = fetch(dashboard + "/")
    assert status == 200 and "<title>Auto Fix Runs</title>" in page
    assert "default-src 'none'" in headers["Content-Security-Policy"]
    _, _, body = fetch(dashboard + "/api/runs")
    runs = json.loads(body)["runs"]
    assert [run["id"] for run in runs] == ["runs/tc-7-ffff"]
    _, _, body = fetch(dashboard + "/api/run?id=runs%2Ftc-7-ffff")
    assert json.loads(body)["summary"]["status"] == "blocked"
    _, headers, _ = fetch(dashboard + "/api/file?id=runs%2Ftc-7-ffff&path=events.jsonl")
    assert headers["Content-Type"].startswith("text/plain")


def test_dashboard_rejects_traversal_unknown_runs_and_foreign_hosts(dashboard):
    for path in [
        "/api/file?id=runs%2Ftc-7-ffff&path=..%2F..%2Fsecret.txt",
        "/api/run?id=runs%2Fnope",
        "/api/state?id=runs%2Ftc-7-ffff&step=x",
    ]:
        with pytest.raises(urllib.error.HTTPError) as error:
            fetch(dashboard + path)
        assert error.value.code == 404
    with pytest.raises(urllib.error.HTTPError) as error:
        fetch(dashboard + "/api/runs", host="attacker.example:8765")
    assert error.value.code == 403


def test_dashboard_redacts_secrets_present_in_stored_evidence(dashboard, monkeypatch, tmp_path):
    monkeypatch.setenv("AUTO_FIX_TEST_TOKEN", "token-value-1234")
    events = tmp_path / "state/runs/tc-7-ffff/events.jsonl"
    events.write_text(events.read_text() + '{"node": "x", "leak": "token-value-1234"}\n')
    _, _, body = fetch(dashboard + "/api/file?id=runs%2Ftc-7-ffff&path=events.jsonl")
    assert "token-value-1234" not in body and "[REDACTED]" in body


def test_tracing_is_a_noop_without_configuration(monkeypatch):
    monkeypatch.delenv(tracing.ENDPOINT_ENV, raising=False)
    assert tracing.configure() is False
    with tracing.session("run"), tracing.model_span("repair", "qwen", {}) as finish:
        finish({"summary": "x"}, {}, None)
    tracing.shutdown()


def test_graph_nodes_and_model_calls_export_as_one_phoenix_session(run_flow, tmp_path, monkeypatch):
    pytest.importorskip("phoenix.otel")
    pytest.importorskip("openinference.instrumentation.langchain")
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    monkeypatch.setenv("AUTO_FIX_TEST_TOKEN", "token-value-5678")
    exporter = InMemorySpanExporter()
    # Nothing listens on the discard port, so only the in-memory copy is inspected.
    assert tracing.configure("http://127.0.0.1:9/v1/traces", "auto-fix-test")
    tracing._provider.add_span_processor(SimpleSpanProcessor(exporter))
    try:
        run_flow(
            tmp_path / "state",
            "tc-7-trace",
            [report(failed=["math.add"]), report(passed=["math.add"]), report(passed=["math.add"])],
        )
    finally:
        started = time.monotonic()
        tracing.shutdown()
        assert time.monotonic() - started < 15
    spans = exporter.get_finished_spans()
    by_name = {span.name: span for span in spans}
    assert {"collect_context", "baseline", "repair", "verify", "finalize"} <= set(by_name)
    model = by_name["model.repair"]
    assert model.attributes["openinference.span.kind"] == "LLM"
    assert model.attributes["llm.model_name"] == "qwen"
    assert model.attributes["llm.token_count.prompt"] == 1200
    assert json.loads(model.attributes["output.value"])["summary"] == "Fix arithmetic"
    assert model.parent.span_id == by_name["repair"].context.span_id
    assert {span.attributes.get("session.id") for span in spans} == {"tc-7-trace"}
    assert not any("token-value-5678" in str(span.attributes) for span in spans)
