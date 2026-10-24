from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from test_history import Builder, Model, Workspace, failure, report

from auto_fix import control, history
from auto_fix.config import Settings
from auto_fix.workflow import Workflow, fork

SERVICE = {"url": "https://internal.invalid", "token_env": "UNUSED_TOKEN"}


def settings(tmp_path):
    return Settings.model_validate(
        {
            "state_dir": tmp_path / "state",
            "teamcity": {**SERVICE, "build_types": ["Cpp_Tests"]},
            "bitbucket": {**SERVICE, "project": "CPP", "repo": "app"},
            "llm": {**SERVICE, "model": "qwen", "context_chars": 4000},
            "repository": {"path": tmp_path / "source"},
            "build": {"build": [["build"]], "test": ["tests", "{junit}"]},
            "max_attempts": 2,
        }
    )


class AskingBuilder(Builder):
    """Fake builder that files a control request while one labelled check runs."""

    def __init__(self, reports, run, ask_on, action):
        super().__init__(reports)
        self.run, self.ask_on, self.action = run, ask_on, action

    def verify(self, path, label):
        if label == self.ask_on:
            control.request(self.run, self.action, "tester")
        return super().verify(path, label)


def flow(tmp_path, run_id, builder=None, model=None):
    made = Workflow(
        settings(tmp_path),
        run_id,
        SimpleNamespace(build_log=lambda _id: "math.add failed"),
        SimpleNamespace(context=lambda commits: []),
        None,
        model or Model(),
        publish=False,
    )
    made.workspace = Workspace(tmp_path)
    made.builder = builder
    return made


REPORTS = [report(failed=["math.add"]), report(passed=["math.add"]), report(passed=["math.add"])]


def nodes(tmp_path, run_id):
    detail = history.run_detail(tmp_path / "state", "runs/" + run_id)
    return detail, [step["node"] for step in detail["steps"]]


def test_pause_stops_after_the_step_and_resume_continues_from_its_checkpoint(tmp_path):
    run = tmp_path / "state/runs/tc-7-pause"
    first = flow(tmp_path, "tc-7-pause", AskingBuilder(REPORTS, run, "baseline", "pause"))
    paused = first.run({"run_id": "tc-7-pause", "failure": failure().model_dump()})
    assert paused["status"] == "paused" and paused["reason"] == "Paused by tester"
    assert not (run / control.CONTROL).exists() and not (run / control.PROCESS).exists()
    detail, executed = nodes(tmp_path, "tc-7-pause")
    assert executed[-1] == "baseline" and detail["summary"]["status"] == "paused"
    assert detail["result"]["prepared_head"] == "b" * 40

    # The next process resumes the same thread; baseline is not run a second time.
    second = flow(tmp_path, "tc-7-pause", Builder(REPORTS[1:]))
    done = second.run(None)
    assert done["status"] == "ready"
    detail, executed = nodes(tmp_path, "tc-7-pause")
    assert executed == [
        "collect_context",
        "prepare",
        "baseline",
        "repair",
        "verify",
        "finalize",
        "publish_pr",
    ]
    assert detail["summary"]["status"] == "ready"
    assert [e["node"] for e in detail["events"]].count("resumed") == 1


def test_cancel_stops_after_the_step_as_a_terminal_status(tmp_path):
    run = tmp_path / "state/runs/tc-7-cancel"
    made = flow(tmp_path, "tc-7-cancel", AskingBuilder(REPORTS, run, "attempt-1", "cancel"))
    result = made.run({"run_id": "tc-7-cancel", "failure": failure().model_dump()})
    assert result["status"] == "cancelled" and result["reason"] == "Cancelled by tester"
    detail, executed = nodes(tmp_path, "tc-7-cancel")
    assert executed[-1] == "verify" and detail["summary"]["status"] == "cancelled"


def test_a_stale_request_does_not_stop_a_new_process(tmp_path):
    run = tmp_path / "state/runs/tc-7-stale"
    control.request(run, "pause", "earlier")
    result = flow(tmp_path, "tc-7-stale", Builder(REPORTS)).run(
        {"run_id": "tc-7-stale", "failure": failure().model_dump()}
    )
    assert result["status"] == "ready"


def test_mark_stopped_writes_result_event_and_receipt(tmp_path):
    run = tmp_path / "state/runs/tc-7-x-r2"
    run.mkdir(parents=True)
    (run / "result.json").write_text(json.dumps({"status": "paused", "attempt": 1}))
    control.request(run, "pause", "someone")
    control.mark_stopped(run, "cancelled", "Cancelled by tester", "tester")
    result = json.loads((run / "result.json").read_text())
    assert result == {"status": "cancelled", "attempt": 1, "reason": "Cancelled by tester"}
    receipt = json.loads((tmp_path / "state/receipts/tc-7-x.json").read_text())
    assert receipt["run_id"] == "tc-7-x-r2" and receipt["status"] == "cancelled"
    assert not (run / control.CONTROL).exists()
    assert json.loads((run / "events.jsonl").read_text().splitlines()[-1])["by"] == "tester"


def test_requests_and_liveness_are_validated(tmp_path):
    with pytest.raises(ValueError):
        control.request(tmp_path, "explode", "x")
    (tmp_path / control.CONTROL).write_text('{"request": "explode"}')
    assert control.pending(tmp_path) is None
    import os

    assert control.alive(os.getpid()) and not control.alive(0)
    control.mark_process(tmp_path)
    assert control.process(tmp_path)["pid"] == os.getpid()


class RecordingWorkspace(Workspace):
    def __init__(self, path):
        super().__init__(path)
        self.started_from = None
        self.applied = []

    def prepare(self, revision, start=None):
        self.started_from = start

    def apply_edits(self, edits):
        self.applied.append([edit.path for edit in edits])


def test_rerun_from_a_step_replays_earlier_edits_and_continues_from_its_checkpoint(tmp_path):
    reports = [
        report(failed=["math.add"]),
        report(failed=["math.add"]),
        report(passed=["math.add"]),
        report(passed=["math.add"]),
    ]
    flow(tmp_path, "tc-7-src", Builder(reports)).run(
        {"run_id": "tc-7-src", "failure": failure().model_dump()}
    )
    _, executed = nodes(tmp_path, "tc-7-src")
    assert executed[4] == "verify" and executed[5] == "repair"

    # Re-run from the second repair: the first attempt's edit must be in the new worktree.
    copy = flow(tmp_path, "tc-7-src-r1", Builder(reports[2:]))
    copy.workspace = RecordingWorkspace(tmp_path)
    fork(copy, tmp_path / "state/runs/tc-7-src", 5)
    assert copy.workspace.started_from == "b" * 40
    assert copy.workspace.applied == [["src/add.cpp"]]
    result = copy.run(None)
    assert result["status"] == "ready" and result["run_id"] == "tc-7-src-r1"
    detail, executed = nodes(tmp_path, "tc-7-src-r1")
    assert executed == ["repair", "verify", "finalize", "publish_pr"]
    assert detail["summary"]["forked_from"] == {"source": "tc-7-src", "step": 5, "node": "repair"}
    assert detail["result"]["attempt"] == 2
    # The source run is untouched.
    _, source = nodes(tmp_path, "tc-7-src")
    assert len(source) == 9


def test_rerun_refuses_steps_that_cannot_be_repeated(tmp_path):
    flow(tmp_path, "tc-7-pub", Builder(REPORTS)).run(
        {"run_id": "tc-7-pub", "failure": failure().model_dump()}
    )
    copy = flow(tmp_path, "tc-7-pub-r1", Builder([]))
    copy.workspace = RecordingWorkspace(tmp_path)
    for index in (0, 5, 6, 99):  # collect_context, finalize, publish_pr, out of range
        with pytest.raises(ValueError):
            fork(copy, tmp_path / "state/runs/tc-7-pub", index)


def test_resuming_without_a_checkpoint_keeps_the_saved_result(tmp_path):
    run = tmp_path / "state/runs/tc-7-none"
    run.mkdir(parents=True)
    (run / "result.json").write_text(json.dumps({"status": "paused", "failure": {"build_id": "7"}}))
    result = flow(tmp_path, "tc-7-none", Builder([])).run(None)
    assert result["status"] == "blocked" and "no checkpoint" in result["reason"]
    assert result["failure"] == {"build_id": "7"}


def test_rerun_needs_checkpoints(tmp_path):
    source = tmp_path / "state/runs/tc-7-old"
    source.mkdir(parents=True)
    (source / "events.jsonl").write_text(json.dumps({"time": "t", "node": "baseline"}) + "\n")
    copy = flow(tmp_path, "tc-7-old-r1", Builder([]))
    copy.workspace = RecordingWorkspace(tmp_path)
    with pytest.raises(ValueError, match="no checkpoints"):
        fork(copy, source, 1)
