from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from auto_fix.experiment import (
    MODEL,
    ExperimentJob,
    _execute,
    failure_stage,
    job_command,
    load_plan,
    prune_builds,
    run_plan,
    summarize_runs,
    wilson_interval,
)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def job(id="trial-1", **overrides):
    return {
        "id": id,
        "arm": "baseline",
        "split": "development",
        "project_file": "project.json",
        "cases_file": "cases.json",
        **overrides,
    }


def plan_files(tmp_path, jobs=None, **options):
    write(tmp_path / "project.json", {"id": "fmt", "commit": "a" * 40})
    write(
        tmp_path / "cases.json",
        {
            "cases": [
                {"id": "fmt_a", "split": "development"},
                {"id": "fmt_b", "split": "development"},
                {"id": "fmt_hidden", "split": "holdout"},
            ]
        },
    )
    path = tmp_path / "plan.json"
    write(path, {"jobs": jobs or [job()], **options})
    return path


def call(kind="repair", **overrides):
    return {
        "model": MODEL,
        "transport": "codex-cli",
        "kind": kind,
        "returncode": 0,
        "usage": {"input_tokens": 100, "output_tokens": 20},
        "elapsed_seconds": 2,
        **overrides,
    }


def make_run(path, case_scores, *, ids=None, split="development", backend="codex"):
    write(
        path / "manifest.json",
        {
            "model": MODEL,
            "backend": backend,
            "live_inference": backend == "codex",
            "case_ids": ids or list(case_scores),
            "split": split,
        },
    )
    scores = []
    for case_id, spec in case_scores.items():
        score = {
            "case": case_id,
            "model": MODEL,
            "status": "published",
            "success": True,
            "attempts": 1,
            "elapsed_seconds": 10,
            "model_calls": [call()],
            **spec,
        }
        write(path / case_id / "score.json", score)
        scores.append(score)
    write(path / "summary.json", {"project": {"id": "fmt"}, "cases": scores})


def descriptor(path, id="first", **overrides):
    return {
        "id": id,
        "arm": "baseline",
        "split": "development",
        "directory": str(path),
        **overrides,
    }


@pytest.mark.parametrize("override", [{"model": "gpt-6-sol"}, {"backend": "replay"}])
def test_plan_does_not_accept_model_or_backend_overrides(tmp_path, override):
    path = plan_files(tmp_path, [job(**override)])
    with pytest.raises(ValidationError):
        load_plan(path)


@pytest.mark.parametrize("repetitions", [0, 4, True, "2"])
def test_baseline_repetition_plan_is_a_bounded_integer(tmp_path, repetitions):
    with pytest.raises(ValidationError):
        load_plan(plan_files(tmp_path, [job(baseline_repetitions=repetitions)]))


def test_repeated_baseline_policy_reaches_the_evaluator_and_report(tmp_path):
    specification = ExperimentJob.model_validate(job(baseline_repetitions=2))
    argv = job_command(specification, tmp_path / "run", tmp_path / "p", tmp_path / "c")
    assert argv[argv.index("--baseline-repetitions") + 1] == "2"
    directory = tmp_path / "run"
    make_run(directory, {"fmt_a": {"baseline_check_count": 2}})
    manifest = json.loads((directory / "manifest.json").read_text())
    manifest["baseline_repetitions"] = 2
    write(directory / "manifest.json", manifest)
    report = summarize_runs([descriptor(directory)], tmp_path / "report")
    assert report["trials"][0]["baseline_repetitions"] == 2
    assert report["trials"][0]["baseline_check_count"] == 2
    assert report["groups"][0]["observed_baseline_checks"] == 2


@pytest.mark.parametrize("parallel", [0, 4, True, "2"])
def test_parallelism_must_be_an_integer_between_one_and_three(tmp_path, parallel):
    with pytest.raises(ValidationError):
        load_plan(plan_files(tmp_path, max_parallel=parallel))


def test_command_keeps_explicit_selection_and_luna_backend_without_shell(tmp_path):
    specification = ExperimentJob.model_validate(
        job(
            case="fmt_a",
            split="holdout",
            prompt="contract-v3",
            max_inspections=3,
            structured_diagnostics=True,
            reasoning_effort="high",
        )
    )
    command = job_command(specification, tmp_path / "run", tmp_path / "p", tmp_path / "c")
    assert command[:5] == ["uv", "run", "--no-sync", "auto-fix", "evaluate"]
    assert command[command.index("--model") + 1] == MODEL
    assert command[command.index("--backend") + 1] == "codex"
    assert command[command.index("--case") + 1] == "fmt_a"
    assert command[command.index("--split") + 1] == "holdout"
    assert command[command.index("--max-attempts") + 1] == "2"
    assert "--structured-diagnostics" in command
    assert "--recordings" not in command


def test_registered_adaptive_resources_reach_the_actual_evaluator_command(tmp_path):
    specification = ExperimentJob.model_validate(
        job(
            max_attempts=4,
            max_inspections=6,
            inspections_per_attempt=2,
            context_chars=160000,
            definition_reads=True,
        )
    )
    command = job_command(specification, tmp_path / "run", tmp_path / "p", tmp_path / "c")
    for flag, value in [
        ("--max-attempts", "4"),
        ("--max-inspections", "6"),
        ("--inspections-per-attempt", "2"),
        ("--context-chars", "160000"),
    ]:
        assert command[command.index(flag) + 1] == value
    assert "--definition-reads" in command


def fake_processes(monkeypatch, root, *, fail_job=None):
    invocations = []
    active = 0
    peak = 0

    async def start(*command, **kwargs):
        nonlocal active, peak
        # Every process starts only after the entire plan and inputs are frozen.
        experiment = json.loads((root / "experiment.json").read_text())
        assert len(experiment["jobs"]) >= 1
        target = Path(command[command.index("--directory") + 1])
        project = Path(command[command.index("--project-file") + 1])
        cases = Path(command[command.index("--cases-file") + 1])
        assert project.is_file() and cases.is_file()
        assert not target.exists()
        invocations.append(command)
        active += 1
        peak = max(peak, active)
        kwargs["stdout"].write(b"synthetic process stdout\n")
        kwargs["stderr"].write(b"synthetic process stderr\n")
        selected = command[command.index("--case") + 1] if "--case" in command else "fmt_a"

        class Process:
            pid = 1000 + len(invocations)

            async def wait(self):
                nonlocal active
                await asyncio.sleep(0.01)
                make_run(target, {selected: {}})
                active -= 1
                return 1 if target.parent.name == fail_job else 0

        return Process()

    monkeypatch.setattr("auto_fix.experiment.asyncio.create_subprocess_exec", start)
    return invocations, lambda: peak


@pytest.mark.parametrize("parallel", [2, 3])
def test_runner_freezes_inputs_runs_bounded_subprocesses_and_resumes_without_reinference(
    tmp_path, monkeypatch, parallel
):
    plan = plan_files(
        tmp_path, [job(f"trial-{n}", case="fmt_a") for n in range(4)], max_parallel=parallel
    )
    output = tmp_path / "experiment"
    processes, peak = fake_processes(monkeypatch, output, fail_job="trial-1")
    result = run_plan(plan, output, workdir=tmp_path)
    assert len(processes) == 4
    assert peak() == parallel
    assert result["returncode"] == 1
    manifest = json.loads((output / "experiment.json").read_text())
    assert manifest["plan_sha256"] == hashlib.sha256(plan.read_bytes()).hexdigest()
    assert (output / "plan.json").read_bytes() == plan.read_bytes()
    for item in manifest["jobs"]:
        current = Path(item["job_directory"])
        assert json.loads((current / "status.json").read_text())["status"] == "finished"
        assert (current / "stdout.log").read_text() == "synthetic process stdout\n"
        assert (current / "stderr.log").read_text() == "synthetic process stderr\n"
        assert (
            hashlib.sha256(Path(item["cases_snapshot"]).read_bytes()).hexdigest()
            == item["cases_sha256"]
        )
    assert (output / "reports/development/report.json").exists()
    run_plan(plan, output, workdir=tmp_path, resume=True)
    assert len(processes) == 4
    with pytest.raises(ValueError, match="explicit --resume"):
        run_plan(plan, output, workdir=tmp_path)


@pytest.mark.parametrize("change", ["plan", "snapshot", "command"])
def test_resume_rejects_changed_plan_inputs_or_fixed_model_command(tmp_path, monkeypatch, change):
    plan = plan_files(tmp_path)
    output = tmp_path / "experiment"
    processes, _peak = fake_processes(monkeypatch, output)
    run_plan(plan, output, workdir=tmp_path)
    if change == "plan":
        data = json.loads(plan.read_text())
        data["jobs"][0]["prompt"] = "evidence-v2"
        write(plan, data)
    elif change == "snapshot":
        write(output / "jobs/trial-1/cases.json", {"changed": True})
    else:
        manifest = json.loads((output / "experiment.json").read_text())
        command = manifest["jobs"][0]["command"]
        command[command.index("--model") + 1] = "another-model"
        write(output / "experiment.json", manifest)
    with pytest.raises(ValueError, match="changed"):
        run_plan(plan, output, workdir=tmp_path, resume=True)
    assert len(processes) == 1


def test_zero_case_selection_fails_before_a_subprocess_or_output_directory(tmp_path, monkeypatch):
    plan = plan_files(tmp_path, [job(case="not_present")])
    output = tmp_path / "experiment"
    processes, _peak = fake_processes(monkeypatch, output)
    with pytest.raises(ValueError, match="selects no cases"):
        run_plan(plan, output, workdir=tmp_path)
    assert not output.exists()
    assert not processes


def test_interruption_stops_the_real_child_and_keeps_an_explicit_nonresumable_status(tmp_path):
    current = tmp_path / "job"
    write(current / "status.json", {"status": "queued"})
    specification = {
        "id": "interrupted",
        "job_directory": str(current),
        "directory": str(current / "run"),
        "command": [sys.executable, "-c", "import time; time.sleep(60)"],
    }

    async def interrupt():
        task = asyncio.create_task(_execute(specification, tmp_path, asyncio.Semaphore(1)))
        for _ in range(500):
            await asyncio.sleep(0.01)
            status = json.loads((current / "status.json").read_text())
            if status["status"] == "running":
                break
        else:
            task.cancel()
            pytest.fail("Harmless Python subprocess did not start")
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(interrupt())
    status = json.loads((current / "status.json").read_text())
    assert status["status"] == "interrupted"
    assert status["returncode"] == 130
    assert status["process_returncode"] is not None
    assert status["finished_at"] and status["elapsed_seconds"] >= 0
    assert (current / "stdout.log").is_file() and (current / "stderr.log").is_file()


def test_interruption_also_stops_descendant_processes(tmp_path):
    current = tmp_path / "job"
    write(current / "status.json", {"status": "queued"})
    ready = tmp_path / "descendant-ready"
    escaped = tmp_path / "descendant-survived"
    descendant = (
        "from pathlib import Path; import time; "
        f"Path({str(ready)!r}).write_text('ready'); "
        f"time.sleep(0.6); Path({str(escaped)!r}).write_text('survived')"
    )
    parent = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable,'-c',{descendant!r}]); time.sleep(60)"
    )
    specification = {
        "id": "interrupted-tree",
        "job_directory": str(current),
        "directory": str(current / "run"),
        "command": [sys.executable, "-c", parent],
    }

    async def interrupt():
        task = asyncio.create_task(_execute(specification, tmp_path, asyncio.Semaphore(1)))
        for _ in range(500):
            await asyncio.sleep(0.01)
            if ready.exists():
                break
        else:
            task.cancel()
            pytest.fail("Harmless descendant subprocess did not start")
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0.8)

    asyncio.run(interrupt())
    assert ready.is_file()
    assert not escaped.exists(), "The runner left a descendant alive after interruption"


def test_resume_rejects_interrupted_evidence_before_starting_queued_siblings(tmp_path, monkeypatch):
    plan = plan_files(tmp_path, [job("first"), job("second")])
    output = tmp_path / "experiment"
    processes, _peak = fake_processes(monkeypatch, output)
    run_plan(plan, output, workdir=tmp_path)
    write(output / "jobs/first/status.json", {"status": "interrupted", "returncode": 130})
    write(output / "jobs/second/status.json", {"status": "queued"})
    with pytest.raises(ValueError, match="prior execution evidence"):
        run_plan(plan, output, workdir=tmp_path, resume=True)
    assert len(processes) == 2


def test_process_launch_error_keeps_logs_status_and_planned_partial_report(tmp_path, monkeypatch):
    plan = plan_files(tmp_path)
    output = tmp_path / "experiment"

    async def unavailable(*_args, **_kwargs):
        raise FileNotFoundError("uv executable unavailable")

    monkeypatch.setattr("auto_fix.experiment.asyncio.create_subprocess_exec", unavailable)
    result = run_plan(plan, output, workdir=tmp_path)
    assert result["returncode"] == 1
    current = output / "jobs/trial-1"
    status = json.loads((current / "status.json").read_text())
    assert status["returncode"] == 127
    assert (current / "stdout.log").exists() and (current / "stderr.log").exists()
    report = json.loads((output / "reports/development/report.json").read_text())
    assert report["groups"][0]["planned_trials"] == 2
    assert report["groups"][0]["completed_trials"] == 0
    assert not report["groups"][0]["calls_by_kind"]


def test_pruning_requires_explicit_plan_option(tmp_path):
    assert load_plan(plan_files(tmp_path)).prune_native_builds is False
    assert load_plan(plan_files(tmp_path, prune_native_builds=True)).prune_native_builds is True


def test_report_partial_scores_counts_live_call_kinds_and_incomplete_work_separately(tmp_path):
    run = tmp_path / "run"
    make_run(
        run, {"fmt_a": {"model_calls": [call("investigation"), call()]}}, ids=["fmt_a", "fmt_b"]
    )
    write(run / "fmt_b/model/call-1/metadata.json", call("investigation"))
    write(run.parent / "status.json", {"status": "finished", "returncode": 1})
    report = summarize_runs([descriptor(run)], tmp_path / "report")
    group = report["groups"][0]
    assert (group["completed_trials"], group["planned_trials"], group["incomplete_trials"]) == (
        1,
        2,
        1,
    )
    assert group["calls_by_kind"] == {"investigation": 2, "repair": 1}
    assert group["tokens"] == {"input_tokens": 300, "output_tokens": 60}
    assert group["unique_cases"] == 1
    assert report["runs"][0]["process"]["returncode"] == 1
    assert len(report["trials"]) == 2
    assert (tmp_path / "report/report.md").is_file()


def test_wilson_counts_unique_cases_and_keeps_repeated_trials_explicit(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    failure = {"success": False, "status": "blocked", "reason": "invalid proposal"}
    make_run(first, {"fmt_a": {}, "fmt_b": failure})
    make_run(second, {"fmt_a": failure})
    report = summarize_runs(
        [descriptor(first), descriptor(second, id="repeat")], tmp_path / "report"
    )
    group = report["groups"][0]
    assert group["completed_trials"] == 3
    assert group["unique_cases"] == 2
    assert group["repeated_trials"] == 1
    assert group["unique_case_first_trial_successes"] == 1
    assert group["case_repeat_outcomes"]["fmt_a"] == [True, False]
    assert group["wilson95_unique_first_trial"] == pytest.approx(wilson_interval(1, 2))
    assert group["wilson95_unique_first_trial"] != pytest.approx(wilson_interval(1, 3))


def test_report_rejects_the_same_evidence_under_distinct_ids_and_path_aliases(tmp_path):
    run = tmp_path / "run"
    make_run(run, {"fmt_a": {}})
    with pytest.raises(ValueError, match="evidence directories must be unique"):
        summarize_runs(
            [descriptor(run), descriptor(run / ".." / "run", id="apparent-repeat")],
            tmp_path / "report",
        )
    assert not (tmp_path / "report").exists()


@pytest.mark.parametrize("backend", ["replay", "endpoint"])
def test_report_rejects_replay_or_other_provider_manifest(tmp_path, backend):
    run = tmp_path / "run"
    make_run(run, {"fmt_a": {}}, backend=backend)
    with pytest.raises(ValueError, match="attested live"):
        summarize_runs([descriptor(run)], tmp_path / "report")


def test_report_rejects_recorded_call_disguised_under_a_live_manifest(tmp_path):
    run = tmp_path / "run"
    make_run(run, {"fmt_a": {"model_calls": [call(transport="recorded-replay")]}})
    with pytest.raises(ValueError, match="replay is excluded"):
        summarize_runs([descriptor(run)], tmp_path / "report")


def test_report_split_never_selects_or_combines_holdout_for_development(tmp_path):
    development, holdout = tmp_path / "development", tmp_path / "holdout"
    make_run(development, {"fmt_a": {}})
    make_run(holdout, {"fmt_hidden": {}}, split="holdout")
    report = summarize_runs(
        [descriptor(development), descriptor(holdout, id="hidden", split="holdout")],
        tmp_path / "report",
        report_split="development",
    )
    assert [trial["case"] for trial in report["trials"]] == ["fmt_a"]
    assert len(report["groups"]) == 1
    assert "No arm selection" in report["selection"]


@pytest.mark.parametrize(
    "reason,state,calls,expected",
    [
        ("Context exceeds configured model budget", {}, [], "context_budget_before_model"),
        ("Context exceeds configured model budget", {}, [call()], "context_budget_after_model"),
        ("Baseline build failed", {}, [], "baseline_build"),
        ("Baseline test evidence is invalid or incomplete", {}, [], "baseline_evidence"),
        (
            "Baseline outcomes varied across repetitions; test suite is unstable",
            {},
            [],
            "baseline_stability",
        ),
        ("Corresponding TC tests not reproduced", {}, [], "baseline_reproduction"),
        (
            "Repair budget exhausted",
            {"verification": {"build_ok": False}},
            [call()],
            "native_build",
        ),
        ("Repair budget exhausted", {"verification": {"test_ok": False}}, [call()], "native_tests"),
        ("Invalid proposed edit", {}, [call()], "model_proposal"),
        ("Model timed out", {}, [call(returncode=124)], "model_provider"),
    ],
)
def test_failure_classification_distinguishes_workflow_blocks_from_model_failures(
    reason, state, calls, expected
):
    assert failure_stage({"reason": reason}, state, calls) == expected


def test_wilson_empty_and_known_interval():
    assert wilson_interval(0, 0) is None
    assert wilson_interval(1, 2) == pytest.approx([0.0945312057, 0.9054687943])
    with pytest.raises(ValueError):
        wilson_interval(3, 2)


def test_pruning_removes_only_new_case_build_outputs_and_preserves_all_evidence(tmp_path):
    run = tmp_path / "run"
    write(run / "manifest.json", {"model": MODEL, "backend": "codex"})
    builds = [
        run / "case/source/.auto-fix-build",
        run / "case/state/worktrees/tc-1/.auto-fix-build",
    ]
    protected = [
        run / "case/source/.git/index",
        run / "case/remote.git/HEAD",
        run / "case/model/call-1/response.json",
        run / "case/preflight/junit.xml",
        run / "case/state/runs/tc-1/fix.diff",
        run / "upstream-cache/fmt/.auto-fix-build/object",
    ]
    for build in builds:
        write(build / "object.obj", "compiled output")
    for path in protected:
        write(path, "preserved")
    pruned = prune_builds(run)
    assert len(pruned) == 2
    assert all(not build.exists() for build in builds)
    assert all(path.is_file() for path in protected)


def test_pruning_refuses_symlink_build_directory_without_removing_other_files(tmp_path):
    run = tmp_path / "run"
    write(run / "manifest.json", {})
    external = tmp_path / "external"
    write(external / "keep.obj", "unrelated")
    link = run / "case/source/.auto-fix-build"
    link.parent.mkdir(parents=True)
    try:
        link.symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("This runner does not allow creating symlinks")
    with pytest.raises(ValueError, match="symlink"):
        prune_builds(run)
    assert (external / "keep.obj").is_file()
