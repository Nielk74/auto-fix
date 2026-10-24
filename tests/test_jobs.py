from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest
from filelock import FileLock
from test_history import Builder, Model, failure
from test_run_control import REPORTS, RecordingWorkspace, flow

from auto_fix import control, jobs
from auto_fix.actions import Actions
from auto_fix.dashboard import serve
from auto_fix.jobs import JobError, JobStore, Runner


def state(tmp_path):
    folder = tmp_path / "state"
    folder.mkdir(exist_ok=True)
    return folder


def test_store_validates_orders_moves_and_removes_jobs(tmp_path):
    store = JobStore(state(tmp_path))
    first = store.add("batch", {"publish": True}, "me")
    assert first["params"]["date"] == time.strftime("%Y-%m-%d")
    assert first["title"].startswith("Repair batch for") and first["title"].endswith("publish")
    second = store.add("demo", {}, "me")
    urgent = store.add("evaluation", {"cases": "a, b", "max_attempts": "3"}, "me", front=True)
    assert urgent["params"]["max_attempts"] == 3
    assert [job["id"] for job in store.all()] == [urgent["id"], first["id"], second["id"]]
    store.move(second["id"], -1)
    assert [job["id"] for job in store.all()] == [urgent["id"], second["id"], first["id"]]
    store.remove(urgent["id"])
    assert [job["id"] for job in store.all()] == [second["id"], first["id"]]


def test_store_rejects_bad_parameters_field_by_field(tmp_path):
    store = JobStore(state(tmp_path))
    with pytest.raises(JobError, match="Unknown workflow"):
        store.add("rm-rf", {}, "me")
    with pytest.raises(JobError) as error:
        store.add("evaluation", {"max_attempts": 99, "prompt": "nope", "backend": "codex"}, "me")
    assert set(error.value.fields) == {"max_attempts", "prompt"}
    with pytest.raises(JobError, match="Unknown parameters"):
        store.add("demo", {"surprise": 1}, "me")
    with pytest.raises(JobError) as error:
        store.add("retry", {"run": "../../etc"}, "me")
    assert "run" in error.value.fields
    with pytest.raises(JobError):
        store.add("batch", {"date": "yesterday-ish"}, "me")


def test_equivalent_commands_match_the_cli(tmp_path):
    config = tmp_path / "config.yaml"
    batch = jobs.validate("batch", {"date": "2026-10-24", "publish": True}, tmp_path)
    assert jobs.command("batch", batch, config) == [
        "auto-fix",
        "run",
        "--config",
        str(config),
        "--date",
        "2026-10-24",
        "--publish",
    ]
    evaluation = jobs.validate(
        "evaluation", {"cases": "one,two", "structured_diagnostics": True}, tmp_path
    )
    argv = jobs.command("evaluation", evaluation, config)
    assert argv[:2] == ["auto-fix", "evaluate"]
    assert argv.count("--case") == 2 and "--structured-diagnostics" in argv
    assert "--endpoint-config" not in argv


def reporting_command(store_dir, status):
    """A stand-in job process that reports ``status`` the way ``auto-fix job`` does."""
    script = (
        "import sys; from pathlib import Path; from auto_fix.jobs import JobStore; "
        f"JobStore(Path({str(store_dir)!r})).update(sys.argv[1], status={status!r}, ended='now')"
    )
    return lambda job: [sys.executable, "-c", script, job["id"]]


def wait_for(store, job_id, statuses, runner, seconds=20):
    deadline = time.time() + seconds
    while time.time() < deadline:
        runner.tick()
        job = store.get(job_id)
        if job["status"] in statuses:
            return job
        time.sleep(0.1)
    raise AssertionError(f"job stayed {store.get(job_id)['status']}")


def test_runner_starts_jobs_one_at_a_time_and_records_outcomes(tmp_path):
    folder = state(tmp_path)
    store = JobStore(folder)
    runner = Runner(tmp_path / "config.yaml", folder, command=reporting_command(folder, "done"))
    first, second = store.add("demo", {}, "me"), store.add("demo", {}, "me")
    runner.tick()
    assert store.get(first["id"])["status"] == "running"
    assert store.get(second["id"])["status"] == "queued"
    wait_for(store, first["id"], {"done"}, runner)
    wait_for(store, second["id"], {"done"}, runner)
    assert jobs.runner_state(folder)["alive"]
    # The runner's heartbeat file sits beside the jobs but is not one.
    assert {job["id"] for job in store.all()} == {first["id"], second["id"]}
    runner.stop()


def test_runner_marks_a_job_that_died_without_reporting_as_failed(tmp_path):
    folder = state(tmp_path)
    store = JobStore(folder)
    runner = Runner(
        tmp_path / "config.yaml",
        folder,
        command=lambda job: [sys.executable, "-c", "raise SystemExit(9)"],
    )
    job = store.add("demo", {}, "me")
    failed = wait_for(store, job["id"], {"failed"}, runner)
    assert "without reporting" in failed["error"]
    runner.stop()


def test_repairs_wait_while_another_process_holds_the_worker_lock(tmp_path):
    folder = state(tmp_path)
    store = JobStore(folder)
    flow(tmp_path, "tc-7-lock", Builder(REPORTS)).run(
        {"run_id": "tc-7-lock", "failure": failure().model_dump()}
    )
    runner = Runner(tmp_path / "config.yaml", folder, command=reporting_command(folder, "done"))
    job = store.add("resume", {"run": "tc-7-lock"}, "me")
    with FileLock(str(folder / "worker.lock")):
        runner.tick()
        assert store.get(job["id"])["status"] == "queued"
        assert "worker lock" in json.loads((folder / "jobs/runner.json").read_text())["waiting"]
    wait_for(store, job["id"], {"done"}, runner)
    runner.stop()


def test_only_one_runner_schedules(tmp_path):
    folder = state(tmp_path)
    one = Runner(tmp_path / "c.yaml", folder, command=reporting_command(folder, "done"))
    two = Runner(tmp_path / "c.yaml", folder, command=reporting_command(folder, "done"))
    one.tick()
    two.tick()
    assert one.active and not two.active
    one.stop()


def paused_run(tmp_path, run_id="tc-7-p"):
    from test_run_control import AskingBuilder

    run = tmp_path / "state/runs" / run_id
    flow(tmp_path, run_id, AskingBuilder(REPORTS, run, "baseline", "pause")).run(
        {"run_id": run_id, "failure": failure().model_dump()}
    )
    return run


def test_actions_follow_the_run_state(tmp_path):
    run = paused_run(tmp_path)
    actions = Actions(tmp_path / "state")
    assert actions.available("runs/tc-7-p")["actions"] == ["resume", "cancel", "replay"]
    queued = actions.perform("runs/tc-7-p", "resume", "me")["job"]
    assert queued["kind"] == "resume" and queued["created_by"] == "me"
    # A queued job blocks further actions on the run until it has run.
    assert actions.available("runs/tc-7-p")["note"].startswith("Queued: Resume")
    with pytest.raises(JobError, match="not available"):
        actions.perform("runs/tc-7-p", "cancel", "me")
    actions.store.remove(queued["id"])
    actions.perform("runs/tc-7-p", "cancel", "me")
    assert json.loads((run / "result.json").read_text())["status"] == "cancelled"
    assert actions.available("runs/tc-7-p")["actions"] == ["retry", "replay"]
    with pytest.raises(JobError, match="re-run can start"):
        actions.perform("runs/tc-7-p", "replay", "me", step=0)
    replay = actions.perform("runs/tc-7-p", "replay", "me", step=2)["job"]
    assert replay["params"] == {"run": "tc-7-p", "step": 2}
    with pytest.raises(JobError, match="cannot be controlled"):
        actions.available("evaluations/x/runs/y") and actions.perform("runs/../x", "retry", "me")


def test_live_runs_take_requests_and_stop_is_refused_while_publishing(tmp_path):
    run = paused_run(tmp_path, "tc-7-live")
    result = json.loads((run / "result.json").read_text())
    (run / "result.json").write_text(json.dumps({**result, "status": "working"}))
    control.mark_process(run)  # this test process plays the running workflow
    actions = Actions(tmp_path / "state")
    assert actions.available("runs/tc-7-live")["actions"] == ["pause", "cancel", "stop"]
    actions.perform("runs/tc-7-live", "pause", "me")
    assert control.pending(run)["request"] == "pause"
    assert actions.available("runs/tc-7-live")["actions"] == ["stop"]
    with (run / "events.jsonl").open("a") as handle:
        handle.write(json.dumps({"time": "t", "node": "publish_pr"}) + "\n")
    assert actions.available("runs/tc-7-live")["actions"] == []


def write_config(tmp_path):
    config = tmp_path / "config.yaml"
    service = "url: https://internal.invalid, token_env: UNUSED_TOKEN"
    lines = [
        "state_dir: state",
        f"teamcity: {{{service}, build_types: [Cpp_Tests]}}",
        f"bitbucket: {{{service}, project: CPP, repo: app}}",
        f"llm: {{{service}, model: qwen, context_chars: 4000}}",
        "repository: {path: source}",
        "build: {build: [[build]], test: [tests, '{junit}']}",
        "max_attempts: 2",
    ]
    config.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return config


@pytest.fixture
def fake_services(monkeypatch, tmp_path):
    """Job processes build real services and worktrees; these tests swap in the fakes."""
    builds = []
    services = (
        SimpleNamespace(build_log=lambda _id: "math.add failed", close=lambda: None),
        SimpleNamespace(context=lambda commits: [], find_pr=lambda *a: None, close=lambda: None),
        None,
        Model(),
    )
    monkeypatch.setattr(jobs, "_services", lambda settings: (services, []))
    monkeypatch.setattr("auto_fix.workflow.Workspace", lambda *args: RecordingWorkspace(tmp_path))
    monkeypatch.setattr(
        "auto_fix.workflow.Builder", lambda *args: builds.pop(0) if builds else Builder([])
    )
    return builds


def test_resume_job_finishes_a_paused_run_and_updates_its_receipt(tmp_path, fake_services):
    paused_run(tmp_path)
    config = write_config(tmp_path)
    receipt = tmp_path / "state/receipts/tc-7-p.json"
    receipt.parent.mkdir()
    receipt.write_text(json.dumps({"run_id": "tc-7-p", "status": "paused"}))
    fake_services.append(Builder(REPORTS[1:]))
    job = JobStore(tmp_path / "state").add("resume", {"run": "tc-7-p"}, "me")
    assert jobs.execute(config, job["id"]) == 0
    done = JobStore(tmp_path / "state").get(job["id"])
    assert done["status"] == "done" and done["result"] == "ready" and done["run_id"] == "tc-7-p"
    assert json.loads(receipt.read_text())["status"] == "ready"


def test_replay_job_forks_into_a_new_run(tmp_path, fake_services):
    flow(tmp_path, "tc-7-s", Builder(REPORTS)).run(
        {"run_id": "tc-7-s", "failure": failure().model_dump()}
    )
    config = write_config(tmp_path)
    fake_services.append(Builder(REPORTS[1:]))
    job = JobStore(tmp_path / "state").add("replay", {"run": "tc-7-s", "step": 4}, "me")
    assert jobs.execute(config, job["id"]) == 0
    done = JobStore(tmp_path / "state").get(job["id"])
    assert done["run_id"] == "tc-7-s-r1" and done["result"] == "ready"
    events = (tmp_path / "state/runs/tc-7-s-r1/events.jsonl").read_text()
    assert '"node": "forked"' in events


def test_retry_job_repairs_a_cancelled_run_in_a_fresh_run(tmp_path, fake_services):
    run = paused_run(tmp_path, "tc-7-ffff")
    control.mark_stopped(run, "cancelled", "Cancelled by me", "me")
    config = write_config(tmp_path)
    fake_services.append(Builder(REPORTS))
    job = JobStore(tmp_path / "state").add("retry", {"run": "tc-7-ffff"}, "me")
    assert jobs.execute(config, job["id"]) == 0
    done = JobStore(tmp_path / "state").get(job["id"])
    assert done["status"] == "done" and done["run_id"].startswith("tc-7-")
    assert done["run_id"] != "tc-7-ffff"


def test_a_busy_worker_lock_puts_the_job_back_at_the_front(tmp_path, fake_services):
    paused_run(tmp_path)
    config = write_config(tmp_path)
    store = JobStore(tmp_path / "state")
    store.add("demo", {}, "me")
    job = store.add("resume", {"run": "tc-7-p"}, "me")
    with FileLock(str(tmp_path / "state/worker.lock")):
        assert jobs.execute(config, job["id"]) == jobs.LOCK_BUSY
    again = store.get(job["id"])
    assert again["status"] == "queued" and store.all()[0]["id"] == job["id"]


@pytest.fixture
def controlled(tmp_path):
    paused_run(tmp_path)
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


def post(url, data, token=None, origin=None, kind="application/json"):
    headers = {"Content-Type": kind}
    if token:
        headers["X-Auto-Fix-Token"] = token
    if origin:
        headers["Origin"] = origin
    request = urllib.request.Request(url, json.dumps(data).encode(), headers, method="POST")
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read())


def test_write_endpoints_need_the_page_token_and_same_origin(controlled):
    base, token = controlled
    assert len(token) > 30
    for kwargs in (
        {},
        {"token": "guess"},
        {"token": token, "origin": "https://evil.example"},
        {"token": token, "kind": "text/plain"},
    ):
        with pytest.raises(urllib.error.HTTPError) as error:
            post(base + "/api/jobs", {"kind": "demo"}, **kwargs)
        assert error.value.code in {403, 415}
    status, body = post(base + "/api/jobs", {"kind": "demo"}, token, origin=base)
    assert status == 200 and body["job"]["kind"] == "demo"
    _, listed = post(base + "/api/jobs/preview", {"kind": "batch", "params": {}}, token)
    assert listed["command"][:2] == ["auto-fix", "run"]
    with pytest.raises(urllib.error.HTTPError) as error:
        post(base + "/api/jobs", {"kind": "evaluation", "params": {"max_attempts": 0}}, token)
    assert error.value.code == 400
    assert "max_attempts" in json.loads(error.value.read())["fields"]
    # Internal kinds are only reachable through run actions.
    with pytest.raises(urllib.error.HTTPError):
        post(base + "/api/jobs", {"kind": "replay", "params": {"run": "tc-7-p", "step": 2}}, token)
    _, done = post(base + "/api/runs/action", {"run": "runs/tc-7-p", "action": "resume"}, token)
    assert done["job"]["kind"] == "resume"
    with urllib.request.urlopen(base + "/api/run?id=runs%2Ftc-7-p") as response:
        assert json.loads(response.read())["controls"]["note"].startswith("Queued")
    with urllib.request.urlopen(base + "/api/jobs") as response:
        assert len(json.loads(response.read())["jobs"]) == 2


def test_read_only_dashboard_refuses_every_write(tmp_path):
    paused_run(tmp_path)
    server = serve(tmp_path / "state", "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    with urllib.request.urlopen(base + "/api/workflows") as response:
        assert json.loads(response.read()) == {"actions": False, "user": "", "workflows": {}}
    with pytest.raises(urllib.error.HTTPError) as error:
        post(base + "/api/jobs", {"kind": "demo"}, "anything")
    assert error.value.code == 403
    with urllib.request.urlopen(base + "/") as response:
        assert b'name="auto-fix-token" content=""' in response.read()
    server.shutdown()
    server.server_close()


def test_process_markers_name_the_live_process(tmp_path):
    control.mark_process(tmp_path)
    assert control.process(tmp_path)["pid"] == os.getpid()
    (tmp_path / control.PROCESS).write_text(json.dumps({"pid": 2**30}))
    assert control.process(tmp_path) is None


def test_a_running_job_can_be_stopped(tmp_path):
    folder = state(tmp_path)
    store = JobStore(folder)
    runner = Runner(
        tmp_path / "config.yaml",
        folder,
        command=lambda job: [sys.executable, "-c", "import time; time.sleep(120)"],
    )
    job = store.add("demo", {}, "me")
    runner.tick()
    pid = store.get(job["id"])["pid"]
    assert control.alive(pid)
    stopped = Actions(folder).stop_job(job["id"], "me")["job"]
    assert stopped["status"] == "cancelled" and stopped["error"] == "Stopped by me"
    deadline = time.time() + 10
    while control.alive(pid) and time.time() < deadline:
        time.sleep(0.1)
    assert not control.alive(pid)
    runner.tick()  # the runner must not overwrite the recorded outcome
    assert store.get(job["id"])["status"] == "cancelled"
    with pytest.raises(JobError, match="Only a running job"):
        Actions(folder).stop_job(job["id"], "me")
    runner.stop()
