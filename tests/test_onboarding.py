"""The demo state: real workflow runs in every status on a simulated clock, never over real data."""

from __future__ import annotations

import json
import threading
import urllib.request
from datetime import UTC, datetime

import pytest

from auto_fix import history, onboarding
from auto_fix.dashboard import serve
from auto_fix.jobs import JobStore
from auto_fix.schedules import ScheduleStore

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    root = tmp_path_factory.mktemp("demo")
    config = onboarding.build_demo(root, now=NOW)
    return root, config


def test_demo_covers_every_run_status_with_real_workflow_evidence(demo):
    root, config = demo
    state = root / "state"
    page = history.run_page(state, page_size=100)
    statuses = {run["name"]: run["status"] for run in page["runs"]}
    assert set(statuses.values()) == {
        "published",
        "ready",
        "paused",
        "cancelled",
        "blocked",
        "publication_unknown",
        "in_progress",
    }
    abandoned = next(run for run in page["runs"] if run["status"] == "in_progress")
    assert not abandoned["live"]
    # Runs start on different days, with durations a native build takes.
    days = {run["started"][:10] for run in page["runs"]}
    assert len(days) >= 5 and min(days) >= "2026-10-14"
    assert all(run["duration_seconds"] >= 20 for run in page["runs"])
    ready = history.run_detail(state, "runs/tc-48339-7a52c0de")
    assert [step["node"] for step in ready["steps"]][:4] == [
        "collect_context",
        "prepare",
        "baseline",
        "repair",
    ]
    assert ready["comparison"]["fixed"] == ["AsciiStrToLower.NonAscii"]
    assert {build["label"] for build in ready["builds"]} == {
        "baseline",
        "attempt-2",
        "final-rebased",
    }
    failed_call = next(call for call in ready["model_calls"] if call["error"])
    assert "finish_reason: length" in failed_call["error"] and failed_call["raw"]
    assert (state / "runs" / "tc-48339-7a52c0de" / "fix.diff").read_text().startswith("diff --git")
    assert ready["result"]["context"]["issues"][0]["key"] == "STR-412"
    regression = history.run_detail(state, "runs/tc-48310-5d0e8f37")
    assert regression["comparison"]["regressions"] == ["StrSplit.Basic"]
    assert config.read_text().count("demo.invalid") == 4


def test_demo_has_schedules_batches_and_review_decisions(demo):
    root, _ = demo
    state = root / "state"
    assert {spec["name"] for spec in ScheduleStore(state).all()} == {
        "Weekday evening repairs",
        "Monday fmt sweep",
    }
    batches = [job for job in JobStore(state).all() if job["kind"] == "batch"]
    summaries = [JobStore(state).batch_summary(job["id"]) for job in batches]
    assert sorted(len(summary["children"]) for summary in summaries) == [0, 2]
    page = history.run_page(state)
    assert "tc-48262-0c7d93e1" not in {run["name"] for run in page["attention"]}
    assert page["attention_total"] == 5


def test_demo_never_overwrites_a_real_state_directory(tmp_path):
    (tmp_path / "runs").mkdir()
    with pytest.raises(ValueError, match="not a demo directory"):
        onboarding.build_demo(tmp_path)
    assert (tmp_path / "runs").is_dir()
    demo_root = tmp_path / "again"
    onboarding.build_demo(demo_root, now=NOW)
    (demo_root / "state" / "triage.json").write_text("{}", encoding="utf-8")
    # A second start rebuilds the demo from scratch.
    onboarding.build_demo(demo_root, now=NOW)
    assert json.loads((demo_root / "state" / "triage.json").read_text())


def test_demo_dashboard_marks_the_page_and_keeps_run_controls(demo):
    root, config = demo
    server = serve(root / "state", "127.0.0.1", 0, config=config, demo=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/") as response:
            page = response.read().decode()
    finally:
        server.shutdown()
        server.server_close()
    assert '<meta name="auto-fix-demo" content="1">' in page
    assert 'name="auto-fix-token" content=""' not in page
