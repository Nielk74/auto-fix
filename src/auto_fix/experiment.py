"""Frozen Luna experiment plans, isolated CLI processes, and native-outcome reports."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MODEL = "gpt-6-luna"
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,100}\Z")


class ExperimentJob(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    arm: str = Field(min_length=1, max_length=100)
    split: Literal["development", "holdout"]
    project_file: Path
    cases_file: Path
    prompt: Literal["repair-v1", "evidence-v2", "contract-v3"] = "repair-v1"
    max_inspections: int = Field(default=0, ge=0, le=6)
    inspections_per_attempt: int = Field(default=6, ge=1, le=6)
    structured_diagnostics: bool = False
    reasoning_effort: Literal["medium", "high"] = "medium"
    context_chars: int = Field(default=60000, ge=4000, le=200000)
    definition_reads: bool = False
    max_attempts: int = Field(default=2, ge=1, le=5, strict=True)
    case: str | None = None

    @field_validator("id", "case")
    @classmethod
    def safe_identifier(cls, value: str | None) -> str | None:
        if value is not None and not SAFE_ID.fullmatch(value):
            raise ValueError("Experiment identifiers must be plain letters, digits, _ or -")
        return value


class ExperimentPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    jobs: list[ExperimentJob] = Field(min_length=1)
    max_parallel: int = Field(default=2, ge=1, le=3, strict=True)
    prune_native_builds: bool = False


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_plan(path: Path) -> ExperimentPlan:
    data = json.loads(path.read_text(encoding="utf-8"))
    plan = ExperimentPlan.model_validate({"jobs": data} if isinstance(data, list) else data)
    if len({job.id for job in plan.jobs}) != len(plan.jobs):
        raise ValueError("Experiment job IDs must be unique")
    return plan


def job_command(job: ExperimentJob, directory: Path, project: Path, cases: Path) -> list[str]:
    """No shell, provider switch, model override, or implicit holdout selection."""
    command = [
        "uv",
        "run",
        "--no-sync",
        "auto-fix",
        "evaluate",
        "--model",
        MODEL,
        "--backend",
        "codex",
        "--directory",
        str(directory),
        "--project-file",
        str(project),
        "--cases-file",
        str(cases),
        "--split",
        job.split,
        "--prompt",
        job.prompt,
        "--max-inspections",
        str(job.max_inspections),
        "--inspections-per-attempt",
        str(job.inspections_per_attempt),
        "--max-attempts",
        str(job.max_attempts),
        "--reasoning-effort",
        job.reasoning_effort,
        "--context-chars",
        str(job.context_chars),
        "--upstream-cache",
        str(directory.parent / "upstream-cache"),
    ]
    if job.structured_diagnostics:
        command.append("--structured-diagnostics")
    if job.definition_reads:
        command.append("--definition-reads")
    if job.case:
        command.extend(["--case", job.case])
    return command


def wilson_interval(successes: int, total: int) -> list[float] | None:
    """Two-sided Wilson 95% interval for distinct Bernoulli case outcomes."""
    if not 0 <= successes <= total:
        raise ValueError("Wilson counts require 0 <= successes <= total")
    if not total:
        return None
    z = 1.959963984540054
    rate = successes / total
    denominator = 1 + z * z / total
    center = (rate + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(rate * (1 - rate) / total + z * z / (4 * total * total)) / denominator
    return [max(0.0, center - radius), min(1.0, center + radius)]


def failure_stage(score: dict, state: dict, calls: list[dict]) -> str:
    if score.get("success") and score.get("status") == "published":
        return "success"
    reason = str(score.get("reason") or state.get("reason", "")).casefold()
    verification = state.get("verification", {})
    if "context exceeds" in reason:
        return "context_budget_before_model" if not calls else "context_budget_after_model"
    if "investigation failed" in reason:
        return "investigation" if calls else "investigation_before_model"
    if "baseline build" in reason:
        return "baseline_build"
    if "not reproduced" in reason:
        return "baseline_reproduction"
    if "final rebase" in reason or "rebase failed" in reason:
        return "final_rebase"
    if score.get("status") == "publication_unknown" or "publication" in reason:
        return "publication"
    if any(call.get("returncode", 0) for call in calls):
        return "model_provider"
    if verification.get("build_ok") is False:
        return "native_build"
    if verification.get("test_ok") is False or score.get("remaining_failures"):
        return "native_tests"
    if not calls:
        return "workflow_before_model"
    if reason or state.get("status") == "invalid_proposal":
        return "model_proposal"
    return "incomplete"


def _state(directory: Path, case: str, score: dict) -> dict:
    paths = sorted((directory / case / "state/runs").glob("*/result.json"))
    candidate = score.get("result")
    if candidate:
        path = Path(candidate)
        path = path if path.is_absolute() else directory / path
        if path.resolve().is_relative_to(directory.resolve()) and path.is_file():
            paths = [path]
    return _json(paths[-1]) if paths else {}


def _calls(directory: Path, case: str, score: dict) -> list[dict]:
    paths = sorted(
        (directory / case / "model").glob("call-*/metadata.json"),
        key=lambda path: int(path.parent.name.removeprefix("call-")),
    )
    calls = [_json(path) for path in paths] if paths else score.get("model_calls", [])
    for call in calls:
        if call.get("model") != MODEL or call.get("transport") != "codex-cli":
            raise ValueError("Reports accept live GPT-6 Luna CLI calls only; replay is excluded")
    return calls


def _run_trials(run: dict) -> tuple[list[dict], dict]:
    directory = Path(run["directory"]).resolve()
    manifest = _json(directory / "manifest.json") if (directory / "manifest.json").is_file() else {}
    summary = _json(directory / "summary.json") if (directory / "summary.json").is_file() else {}
    if manifest and (
        manifest.get("model") != MODEL
        or manifest.get("backend") != "codex"
        or manifest.get("live_inference") is not True
    ):
        raise ValueError("Reports require an attested live GPT-6 Luna codex run, never replay")
    if manifest.get("split") not in (None, run["split"]):
        raise ValueError("Run descriptor split disagrees with its evaluation manifest")
    project_data = summary.get("project", {})
    project = (
        project_data.get("id")
        or project_data.get("name")
        or run.get("project")
        or manifest.get("project_commit", "unknown")
    )
    scores = {item["case"]: item for item in summary.get("cases", [])}
    for path in sorted(directory.glob("*/score.json")):
        score = _json(path)
        scores[score["case"]] = score
    if scores and not manifest:
        raise ValueError("Completed scores without a live model manifest cannot count as evidence")
    case_ids = list(dict.fromkeys([*manifest.get("case_ids", run.get("case_ids", [])), *scores]))
    trials = []
    for case in case_ids:
        if not SAFE_ID.fullmatch(case):
            raise ValueError("Unsafe case identifier in evaluation evidence")
        score = scores.get(case, {})
        if score.get("model", MODEL) != MODEL:
            raise ValueError("A score from another model cannot count as Luna evidence")
        calls = _calls(directory, case, score)
        state = _state(directory, case, score)
        success = bool(score.get("success")) and score.get("status") == "published"
        trials.append(
            {
                "run_id": run["id"],
                "arm": run["arm"],
                "split": run["split"],
                "project": project,
                "case": case,
                "completed": bool(score),
                "success": success,
                "status": score.get("status", "incomplete"),
                "first_attempt_success": success and score.get("attempts") == 1,
                "attempts": score.get("attempts", state.get("attempt", 0)),
                "inspections": score.get("inspections", state.get("inspections", 0)),
                "failure_stage": failure_stage(score, state, calls),
                "reason": score.get("reason", state.get("reason", "")),
                "elapsed_seconds": score.get("elapsed_seconds", 0),
                "calls": calls,
                "directory": str(directory / case),
            }
        )
    process_path = directory.parent / "status.json"
    process = _json(process_path) if process_path.is_file() else {}
    return trials, {
        **run,
        "directory": str(directory),
        "project": project,
        "planned_cases": len(case_ids),
        "completed_cases": len(scores),
        "process": process,
    }


def _group(trials: list[dict], arm: str, split: str, project: str) -> dict:
    completed = [trial for trial in trials if trial["completed"]]
    by_case: dict[str, list[dict]] = defaultdict(list)
    for trial in completed:
        by_case[trial["case"]].append(trial)
    first_successes = sum(repeats[0]["success"] for repeats in by_case.values())
    calls = [call for trial in trials for call in trial["calls"]]
    tokens: Counter = Counter()
    for call in calls:
        tokens.update(
            {key: value for key, value in call.get("usage", {}).items() if isinstance(value, int)}
        )
    return {
        "arm": arm,
        "split": split,
        "project": project,
        "planned_trials": len(trials),
        "completed_trials": len(completed),
        "incomplete_trials": len(trials) - len(completed),
        "successful_trials": sum(trial["success"] for trial in completed),
        "first_attempt_successes": sum(trial["first_attempt_success"] for trial in completed),
        "unique_cases": len(by_case),
        "unique_case_first_trial_successes": first_successes,
        "wilson95_unique_first_trial": wilson_interval(first_successes, len(by_case)),
        "repeated_trials": len(completed) - len(by_case),
        "case_repeat_outcomes": {
            case: [trial["success"] for trial in repeats] for case, repeats in by_case.items()
        },
        "calls_by_kind": dict(Counter(call.get("kind", "repair") for call in calls)),
        "tokens": dict(tokens),
        "model_elapsed_seconds": round(sum(call.get("elapsed_seconds", 0) for call in calls), 3),
        "trial_elapsed_seconds": round(sum(trial["elapsed_seconds"] for trial in completed), 3),
        "failure_stages": dict(
            Counter(trial["failure_stage"] for trial in trials if not trial["success"])
        ),
    }


def summarize_runs(runs: list[dict], output: Path, *, report_split: str | None = None) -> dict:
    """Report direct evaluator directories or experiment-runner jobs without model calls.

    Run-list order defines the first completed trial for each unique case. The
    Wilson denominator counts each case once; every repeated trial remains in
    the table and repeat-outcome lists. Arms and splits are never auto-selected.
    """
    if report_split not in {None, "development", "holdout"}:
        raise ValueError("Report split must be development or holdout")
    selected = [run for run in runs if report_split is None or run["split"] == report_split]
    if len({run["id"] for run in selected}) != len(selected):
        raise ValueError("Report run IDs must be unique")
    if len({Path(run["directory"]).resolve() for run in selected}) != len(selected):
        raise ValueError("Report evidence directories must be unique after resolving paths")
    trials, run_reports = [], []
    for run in selected:
        rows, run_report = _run_trials(run)
        trials.extend(rows)
        run_reports.append(run_report)
    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for trial in trials:
        grouped[(trial["arm"], trial["split"], trial["project"])].append(trial)
    report = {
        "model": MODEL,
        "live_inference_only": True,
        "report_split": report_split,
        "generated_at": datetime.now(UTC).isoformat(),
        "interval_method": (
            "Wilson 95% on the first completed listed trial per unique (project, case); "
            "repeats are separate, not independent cases."
        ),
        "selection": (
            "No arm selection or model grader; outcomes come from native validation scores."
        ),
        "runs": run_reports,
        "groups": [_group(items, *key) for key, items in grouped.items()],
        "trials": trials,
    }
    output.mkdir(parents=True, exist_ok=True)
    _write(output / "report.json", report)
    lines = [
        "# GPT-6 Luna native evaluation report",
        "",
        report["interval_method"],
        "",
        "No model grader or automatic arm selection. Incomplete trials are reported separately.",
        "",
        "| Arm | Split | Project | Completed/planned | Fixes | First attempt | Unique | Repeats |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for group in report["groups"]:
        cells = [
            group["arm"],
            group["split"],
            group["project"],
            f"{group['completed_trials']}/{group['planned_trials']}",
            group["successful_trials"],
            group["first_attempt_successes"],
            group["unique_cases"],
            group["repeated_trials"],
        ]
        lines.append("| " + " | ".join(str(cell) for cell in cells) + " |")
    for group in report["groups"]:
        lines.extend(
            [
                "",
                f"**{group['arm']} / {group['split']} / {group['project']}**",
                "",
                f"Calls: `{json.dumps(group['calls_by_kind'])}`. "
                f"Tokens: `{json.dumps(group['tokens'])}`. "
                f"Wilson 95%: `{group['wilson95_unique_first_trial']}`. "
                f"Failure stages: `{json.dumps(group['failure_stages'])}`.",
            ]
        )
    lines.extend(
        [
            "",
            "| Run | Arm | Split | Case | Outcome | Attempts | Failed stage |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for trial in trials:
        cells = [
            trial[key]
            for key in ("run_id", "arm", "split", "case", "status", "attempts", "failure_stage")
        ]
        lines.append("| " + " | ".join(str(cell) for cell in cells) + " |")
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def prune_builds(directory: Path) -> list[str]:
    """Prune rebuildable outputs only after the caller's evaluation process exits."""
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Pruning requires a real evaluation directory")
    root = directory.resolve()
    if not (root / "manifest.json").is_file():
        raise ValueError("Pruning requires an evaluation manifest")
    candidates = []
    for current, names, _files in os.walk(root, followlinks=False):
        for name in list(names):
            if name != ".auto-fix-build":
                continue
            path = Path(current) / name
            parts = path.relative_to(root).parts
            allowed = (
                len(parts) == 3
                and parts[1] == "source"
                or len(parts) == 5
                and parts[1:3] == ("state", "worktrees")
            )
            if not allowed:
                continue
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError("Refusing symlink or external native build directory")
            for base, directories, files in os.walk(path, followlinks=False):
                if any((Path(base) / item).is_symlink() for item in [*directories, *files]):
                    raise ValueError("Refusing native build output containing symlinks")
            candidates.append(path)
            names.remove(name)
    for path in candidates:
        shutil.rmtree(path)
    return [str(path.relative_to(root)) for path in candidates]


async def _stop_process(process: asyncio.subprocess.Process) -> None:
    """Stop the isolated CLI and its native/model children before recording interruption."""
    if process.returncode is not None:
        return
    if os.name == "nt":
        # terminate() alone leaves descendants of uv/the CLI running on Windows.
        try:
            killer = await asyncio.create_subprocess_exec(
                "taskkill",
                "/PID",
                str(process.pid),
                "/T",
                "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                await asyncio.wait_for(killer.wait(), timeout=5)
            except TimeoutError:
                killer.kill()
                await killer.wait()
        except OSError:
            process.terminate()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except TimeoutError:
        if os.name == "nt":
            process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        await process.wait()


async def _execute(job: dict, workdir: Path, semaphore: asyncio.Semaphore) -> None:
    async with semaphore:
        directory = Path(job["job_directory"])
        status_path = directory / "status.json"
        status = _json(status_path)
        if status["status"] == "finished":
            return
        if status["status"] != "queued":
            raise ValueError(f"Job {job['id']} has prior execution evidence; use a new job/run")
        target = Path(job["directory"])
        if target.exists() and any(target.iterdir()):
            raise ValueError(f"Job {job['id']} evaluation directory must be empty")
        started = time.monotonic()
        status.update(status="starting", started_at=datetime.now(UTC).isoformat())
        _write(status_path, status)
        process = None
        try:
            with (
                (directory / "stdout.log").open("wb") as out,
                (directory / "stderr.log").open("wb") as err,
            ):
                process = await asyncio.create_subprocess_exec(
                    *job["command"],
                    cwd=workdir,
                    stdout=out,
                    stderr=err,
                    env=dict(os.environ),
                    **(
                        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
                        if os.name == "nt"
                        else {"start_new_session": True}
                    ),
                )
                status.update(status="running", pid=process.pid)
                _write(status_path, status)
                returncode = await process.wait()
            status.update(status="finished", returncode=returncode)
        except OSError as exc:
            status.update(status="finished", returncode=127, error=str(exc))
        except (asyncio.CancelledError, KeyboardInterrupt):
            try:
                if process is not None:
                    await _stop_process(process)
            finally:
                status.update(
                    status="interrupted",
                    returncode=130,
                    process_returncode=process.returncode if process is not None else None,
                    error="Runner interrupted; use a new job/run rather than reinference on resume",
                )
            raise
        finally:
            if (
                status["status"] == "finished"
                and job.get("prune_native_builds")
                and target.is_dir()
            ):
                try:
                    status["pruned_paths"] = prune_builds(target)
                except ValueError as exc:
                    status["prune_error"] = str(exc)
            status.update(
                elapsed_seconds=round(time.monotonic() - started, 3),
                finished_at=datetime.now(UTC).isoformat(),
            )
            _write(status_path, status)


def run_plan(
    plan_path: Path, directory: Path, *, workdir: Path | None = None, resume: bool = False
) -> dict:
    """Run a frozen plan with 1-3 independent subprocesses; finished jobs never rerun."""
    plan_path, directory = plan_path.resolve(), directory.resolve()
    workdir = (workdir or Path.cwd()).resolve()
    plan = load_plan(plan_path)
    manifest_path = directory / "experiment.json"
    if directory.exists() and any(directory.iterdir()):
        if not resume:
            raise ValueError("Experiment directory must be new/empty; use explicit --resume")
        manifest = _json(manifest_path)
        if manifest["plan_sha256"] != _hash(plan_path):
            raise ValueError("Cannot resume a changed experiment plan")
        if _hash(directory / "plan.json") != manifest["plan_sha256"]:
            raise ValueError("Frozen experiment plan changed")
        if manifest.get("model") != MODEL or manifest.get("backend") != "codex":
            raise ValueError("Experiment manifest must retain the fixed Luna backend")
        if [job["id"] for job in manifest["jobs"]] != [job.id for job in plan.jobs]:
            raise ValueError("Experiment jobs changed")
        if manifest["max_parallel"] != plan.max_parallel:
            raise ValueError("Experiment concurrency changed")
        if manifest.get("prune_native_builds", False) != plan.prune_native_builds:
            raise ValueError("Experiment pruning policy changed")
        for job in manifest["jobs"]:
            expected_directory = directory / "jobs" / job["id"]
            if (
                Path(job["job_directory"]) != expected_directory
                or Path(job["directory"]) != expected_directory / "run"
                or job.get("prune_native_builds", False) != plan.prune_native_builds
            ):
                raise ValueError("Frozen experiment job location or policy changed")
            for key in ("project", "cases"):
                if _hash(Path(job[key + "_snapshot"])) != job[key + "_sha256"]:
                    raise ValueError("Frozen experiment input changed")
            specification = next(item for item in plan.jobs if item.id == job["id"])
            if job["specification"] != specification.model_dump(mode="json"):
                raise ValueError("Frozen experiment job specification changed")
            expected = job_command(
                specification,
                Path(job["directory"]),
                Path(job["project_snapshot"]),
                Path(job["cases_snapshot"]),
            )
            if job["command"] != expected:
                raise ValueError("Frozen experiment command changed")
    else:
        if resume:
            raise ValueError("Cannot resume an experiment without prior results")
        # Validate all inputs before creating any model-call intent or process.
        inputs = []
        for job in plan.jobs:
            project = (workdir / job.project_file).resolve()
            cases = (workdir / job.cases_file).resolve()
            project_bytes, cases_bytes = project.read_bytes(), cases.read_bytes()
            cases_data = json.loads(cases_bytes)["cases"]
            selected = [
                case
                for case in cases_data
                if case.get("split", "development") == job.split
                and (not job.case or case["id"] == job.case)
            ]
            if not selected:
                raise ValueError(f"Job {job.id} selects no cases")
            inputs.append((job, project_bytes, cases_bytes, [item["id"] for item in selected]))
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "plan.json").write_bytes(plan_path.read_bytes())
        jobs = []
        for job, project_bytes, cases_bytes, selected_ids in inputs:
            current = directory / "jobs" / job.id
            current.mkdir(parents=True)
            project, cases = current / "project.json", current / "cases.json"
            project.write_bytes(project_bytes)
            cases.write_bytes(cases_bytes)
            record = {
                "id": job.id,
                "arm": job.arm,
                "split": job.split,
                "directory": str(current / "run"),
                "job_directory": str(current),
                "project_snapshot": str(project),
                "project_sha256": _hash(project),
                "cases_snapshot": str(cases),
                "cases_sha256": _hash(cases),
                "specification": job.model_dump(mode="json"),
                "case_ids": selected_ids,
                "project": json.loads(project_bytes).get("id", "unknown"),
                "prune_native_builds": plan.prune_native_builds,
                "command": job_command(job, current / "run", project, cases),
            }
            _write(current / "job.json", record)
            _write(current / "status.json", {"status": "queued"})
            jobs.append(record)
        manifest = {
            "model": MODEL,
            "backend": "codex",
            "plan_sha256": _hash(plan_path),
            "max_parallel": plan.max_parallel,
            "prune_native_builds": plan.prune_native_builds,
            "created_at": datetime.now(UTC).isoformat(),
            "jobs": jobs,
        }
        _write(manifest_path, manifest)

    descriptors = [
        {key: job[key] for key in ("id", "arm", "split", "directory", "project", "case_ids")}
        for job in manifest["jobs"]
    ]
    # Check all statuses before scheduling anything: one interrupted job must not
    # allow untouched queued siblings to start during a conservative resume.
    for job in manifest["jobs"]:
        status = _json(Path(job["job_directory"]) / "status.json")
        if status["status"] not in {"queued", "finished"}:
            raise ValueError(f"Job {job['id']} has prior execution evidence; use a new job/run")

    async def execute_all():
        semaphore = asyncio.Semaphore(manifest["max_parallel"])

        async def execute_and_report(job):
            try:
                await _execute(job, workdir, semaphore)
            finally:
                for split in {item["split"] for item in descriptors}:
                    summarize_runs(descriptors, directory / "reports" / split, report_split=split)

        results = await asyncio.gather(
            *(execute_and_report(job) for job in manifest["jobs"]), return_exceptions=True
        )
        errors = [str(result) for result in results if isinstance(result, BaseException)]
        _write(directory / "runner-result.json", {"errors": errors, "runs": descriptors})
        if errors:
            raise RuntimeError("Experiment runner stopped: " + "; ".join(errors))

    asyncio.run(execute_all())
    failed = any(
        _json(Path(job["job_directory"]) / "status.json").get("returncode") != 0
        for job in manifest["jobs"]
    )
    return {"experiment": str(manifest_path), "runs": descriptors, "returncode": int(failed)}
