"""Reproducible large-repository evaluations with real native tests and isolated services."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from defusedxml import ElementTree

from auto_fix import mock_services as mocks
from auto_fix.build import Builder
from auto_fix.codex_model import CodexRepairModel
from auto_fix.config import Settings
from auto_fix.integrations import Bitbucket, Jira, TeamCity
from auto_fix.llm import RepairModel
from auto_fix.mock_services import ScenarioServices
from auto_fix.models import FailedTest, Failure
from auto_fix.prompts import repair_prompt
from auto_fix.recorded_model import RecordedRepairModel
from auto_fix.workflow import Workflow, failure_key, write_json


def _git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        env=dict(os.environ, GIT_TERMINAL_PROMPT="0"),
    )
    return result.stdout.strip()


def evaluation_root() -> Path:
    root = Path(__file__).resolve().parents[2] / "evaluation"
    if not root.is_dir():
        raise ValueError("Run the benchmark from a source checkout containing evaluation/")
    return root


def _upstream(cache: Path, spec: dict[str, Any], name: str) -> Path:
    path = cache / name
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "git",
                "-c",
                "core.autocrlf=false",
                "clone",
                "--depth",
                "1",
                "--branch",
                spec["tag"],
                spec["repository"],
                str(path),
            ],
            check=True,
            timeout=240,
        )
    if _git(path, "rev-parse", "HEAD") != spec["commit"] or _git(path, "status", "--porcelain"):
        raise ValueError(f"Cached {name} checkout must be clean at pinned commit {spec['commit']}")
    return path


def _details(junit: Path) -> dict[str, str]:
    result = {}
    for case in ElementTree.parse(junit).getroot().iter("testcase"):
        name = case.get("name", "")
        cls = case.get("classname", "")
        identity = f"{cls}.{name}" if cls and cls != name else name
        failures = list(case.iter("failure")) + list(case.iter("error"))
        if failures:
            result[identity] = "\n".join(
                (item.text or item.get("message", "")) for item in failures
            )
    return result


def _build_config(project: dict, case: dict, googletest: Path | None) -> dict:
    generator = [] if os.name == "nt" else ["-G", "Ninja"]
    google_option = project.get("google_test_option", "ABSL_LOCAL_GOOGLETEST_DIR")
    # VS maps CMake's global clean target to the whole solution. Rebuild only
    # the selected project and dependencies, while forcing edited sources to
    # compile even when Windows timestamps coincide within the same second.
    native_rebuild = ["--", "/t:Rebuild"] if os.name == "nt" else []
    config = {
        "configure": [
            [
                "cmake",
                "-S",
                ".",
                "-B",
                ".auto-fix-build",
                *generator,
                *project["cmake_options"],
                *([f"-D{google_option}={googletest}"] if googletest else []),
            ]
        ],
        "build": [
            [
                "cmake",
                "--build",
                ".auto-fix-build",
                "--config",
                "Release",
                "--parallel",
                "4",
                "--target",
                *case["build_targets"],
                *native_rebuild,
            ]
        ],
        "test": [
            sys.executable,
            str(Path(__file__).with_name("native_tests.py")),
            "--build-dir",
            ".auto-fix-build",
            "--targets",
            *case["build_targets"],
            "--junit",
            "{junit}",
        ],
        "timeout_seconds": 600,
    }
    for suite in project.get("additional_test_suites", []):
        probe = suite.get("probe")
        if probe not in (
            "duration-min-unit",
            "duration-rounding-boundaries",
            "fmt-contract-boundaries",
        ):
            raise ValueError("Unknown trusted additional test suite")
        if set(suite.get("targets_any", [])) & set(case["build_targets"]):
            if probe == "fmt-contract-boundaries":
                from auto_fix.fmt_semantic_probes import fmt_contract_command

                command = fmt_contract_command(probe=probe)
            else:
                from auto_fix.semantic_probes import duration_min_unit_command

                command = duration_min_unit_command(probe=probe)
            config.setdefault("additional_tests", []).append(command)
    return config


def _source(directory: Path, upstream: Path, case: dict) -> tuple[Path, list[dict]]:
    source = directory / "source"
    subprocess.run(
        ["git", "-c", "core.autocrlf=false", "clone", "--no-hardlinks", str(upstream), str(source)],
        check=True,
        capture_output=True,
        timeout=180,
    )
    _git(source, "checkout", "-B", "master")
    _git(source, "config", "core.autocrlf", "false")
    _git(source, "config", "user.name", "Synthetic Meridian CI")
    _git(source, "config", "user.email", "ci@meridian.invalid")
    with (source / ".gitignore").open("a", encoding="utf-8") as handle:
        handle.write("\n.auto-fix-build/\n")
    _git(source, "add", ".gitignore")
    _git(source, "commit", "-m", "Configure isolated native build output")
    for mutation in case["mutations"]:
        path = source / mutation["path"]
        original = path.read_bytes().decode("utf-8")
        if original.count(mutation["before"]) != 1:
            raise ValueError(f"Pinned mutation anchor changed: {mutation['path']}")
        path.write_bytes(original.replace(mutation["before"], mutation["after"], 1).encode("utf-8"))
    _git(source, "commit", "-am", case["context"]["commit_message"])
    mutation_sha = _git(source, "rev-parse", "HEAD")
    changes = []
    if case["exposure"] == "direct":
        changes.append({"version": mutation_sha, "comment": case["context"]["commit_message"]})
    # Indirect cases model an older regression discovered by a newer CI run. Its current
    # changes deliberately contain no inverse patch; the model must locate the implementation.
    path = source / case["changed_files"][0]
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n// Keep runtime diagnostic labels consistent across ingestion workers.\n")
    _git(source, "commit", "-am", case["context"]["pr_title"])
    changes.append(
        {"version": _git(source, "rev-parse", "HEAD"), "comment": case["context"]["pr_title"]}
    )
    remote = directory / "remote.git"
    subprocess.run(
        ["git", "clone", "--bare", str(source), str(remote)],
        check=True,
        capture_output=True,
        timeout=180,
    )
    _git(source, "remote", "set-url", "origin", str(remote))
    return source, changes


def run_evaluation(
    directory: Path,
    *,
    profile: str = "legacy",
    backend: str = "codex",
    model_name: str = "gpt-6-luna",
    selected: list[str] | None = None,
    upstream_cache: Path | None = None,
    endpoint_config: Path | None = None,
    recordings: Path | None = None,
    project_file: Path | None = None,
    cases_file: Path | None = None,
    split: str | None = None,
    prompt_version: str = "repair-v1",
    max_inspections: int = 0,
    inspections_per_attempt: int = 6,
    max_attempts: int = 2,
    baseline_repetitions: int = 1,
    reasoning_effort: str = "medium",
    structured_diagnostics: bool = False,
    context_chars: int = 60000,
    definition_reads: bool = False,
) -> int:
    if type(baseline_repetitions) is not int or not 1 <= baseline_repetitions <= 3:
        raise ValueError("baseline_repetitions must be between one and three")
    if backend not in {"codex", "endpoint", "replay"}:
        raise ValueError("Unknown evaluation backend")
    if profile not in {"legacy", "focused"}:
        raise ValueError("Unknown context profile")
    root = evaluation_root()
    project_file = project_file or root / "project.json"
    cases_file = cases_file or root / "cases.json"
    project = json.loads(project_file.read_text(encoding="utf-8"))
    endpoint_settings = None
    if backend == "endpoint":
        from dotenv import load_dotenv

        from auto_fix.config import load_settings

        if not endpoint_config:
            raise ValueError("Endpoint evaluation requires --config with your model settings")
        load_dotenv(endpoint_config.resolve().parent / ".env", override=False)
        endpoint_settings = load_settings(endpoint_config)
        model_name = endpoint_settings.llm.model
    cases = json.loads(cases_file.read_text(encoding="utf-8"))["cases"]
    if split:
        if split not in {"development", "holdout"}:
            raise ValueError("Unknown evaluation split")
        cases = [case for case in cases if case.get("split", "development") == split]
    if selected:
        cases = [case for case in cases if case["id"] in selected]
        if {case["id"] for case in cases} != set(selected):
            raise ValueError("Unknown evaluation case ID")
    if not cases:
        raise ValueError("Evaluation selection contains no cases")
    repair_prompt(prompt_version)
    directory = directory.resolve()
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("Evaluation directory must be empty; prior evidence is preserved")
    directory.mkdir(parents=True, exist_ok=True)
    source_files = sorted(path.name for path in Path(__file__).parent.glob("*.py"))
    packages = {}
    for package in ("langgraph", "pydantic", "tree-sitter", "tree-sitter-cpp"):
        try:
            packages[package] = version(package)
        except PackageNotFoundError:
            packages[package] = None
    snapshot = directory / "implementation"
    snapshot.mkdir()
    for name in source_files:
        (snapshot / name).write_bytes(Path(__file__).with_name(name).read_bytes())
    write_json(
        directory / "manifest.json",
        {
            "model": model_name,
            "backend": backend,
            "profile": profile,
            "prompt_version": prompt_version,
            "prompt_sha256": hashlib.sha256(repair_prompt(prompt_version).encode()).hexdigest(),
            "max_attempts": max_attempts,
            "baseline_repetitions": baseline_repetitions,
            "max_inspections": max_inspections,
            "inspections_per_attempt": inspections_per_attempt,
            "reasoning_effort": reasoning_effort,
            "structured_diagnostics": structured_diagnostics,
            "context_chars": context_chars,
            "definition_reads": definition_reads,
            "runtime": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "packages": packages,
            },
            "split": split,
            "case_ids": [case["id"] for case in cases],
            "source_sha256": {
                name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                for name in source_files
            },
            "cases_sha256": hashlib.sha256(cases_file.read_bytes()).hexdigest(),
            "project_sha256": hashlib.sha256(project_file.read_bytes()).hexdigest(),
            "project_commit": project["commit"],
            "live_inference": backend != "replay",
            "oracle_manifest_sent_to_model": False,
        },
    )
    cache = (upstream_cache or Path(".auto-fix/upstream")).resolve()
    upstream = _upstream(cache, project, project.get("id", "abseil"))
    googletest = (
        _upstream(cache, project["google_test"], "googletest")
        if project.get("google_test")
        else None
    )
    allowed_paths = project.get("allowed_paths", ["absl/**"])
    context_paths = project.get("context_paths", ["absl/**"])
    old_token = os.environ.get(mocks.TOKEN_ENV)
    os.environ[mocks.TOKEN_ENV] = mocks.TOKEN
    results = []
    try:
        for index, case in enumerate(cases):
            started = time.monotonic()
            current = directory / case["id"]
            current.mkdir()
            source, changes = _source(current, upstream, case)
            config = _build_config(project, case, googletest)
            # Obtain failure names/details from actual upstream tests, never hand-written logs.
            from auto_fix.config import BuildConfig

            preflight = Builder(BuildConfig.model_validate(config), current / "preflight").verify(
                source, "injected"
            )
            if not preflight.evidence_valid:
                raise RuntimeError(
                    f"Case {case['id']} preflight returned malformed native evidence"
                )
            if not preflight.build_ok or not preflight.report.failed:
                raise RuntimeError(f"Case {case['id']} failed to reproduce its injected regression")
            junit = next(Path(path) for path in preflight.logs if path.endswith("junit.xml"))
            details = _details(junit)
            failure = Failure(
                build_id=str(284761 + index),
                build_type="Platform_CppRuntime_Win64_UnitTests",
                build_url=f"{mocks.TC_URL}/viewLog.html?buildId={284761 + index}",
                revision=_git(source, "rev-parse", "HEAD"),
                branch="refs/heads/master",
                tests=[
                    FailedTest(
                        id=hashlib.sha256(name.encode()).hexdigest()[:16],
                        name=name,
                        details=details.get(name, ""),
                    )
                    for name in preflight.report.failed
                ],
                changes=changes,
            )
            now = datetime.now(ZoneInfo("Europe/Paris"))
            services = ScenarioServices(
                failure,
                now=now,
                issue_key=case["context"]["jira_key"],
                issue_summary=case["context"]["jira_summary"],
                issue_description=case["description"],
                latest_commit=lambda branch, current=current: _git(
                    current,
                    "--git-dir",
                    str(current / "remote.git"),
                    "rev-parse",
                    branch,
                ),
            )
            service = {"token_env": mocks.TOKEN_ENV}
            payload = {
                "state_dir": current / "state",
                "timezone": "Europe/Paris",
                "max_attempts": max_attempts,
                "baseline_repetitions": baseline_repetitions,
                "max_inspections": max_inspections,
                "inspections_per_attempt": inspections_per_attempt,
                "structured_diagnostics": structured_diagnostics,
                "teamcity": {
                    **service,
                    "url": mocks.TC_URL,
                    "build_types": [failure.build_type],
                    "vcs_root_id": mocks.VCS_ROOT,
                    "evidence_artifact_paths": [mocks.EVIDENCE_PATH],
                },
                "bitbucket": {
                    **service,
                    "url": mocks.BB_URL,
                    "project": mocks.PROJECT,
                    "repo": mocks.REPO,
                },
                "jira": {**service, "url": mocks.JIRA_URL},
                "llm": {
                    **service,
                    "url": "https://model.meridian.invalid/v1",
                    "model": model_name,
                    "prompt_version": prompt_version,
                    "context_chars": context_chars,
                },
                "repository": {
                    "path": source,
                    "allowed_paths": allowed_paths,
                    "context_paths": context_paths,
                    "definition_reads": definition_reads,
                },
                "build": config,
            }
            # Legacy is the pre-improvement workflow; focused is enabled after baseline capture.
            payload["repository"]["context_strategy"] = profile
            settings = Settings.model_validate(payload)
            run_id = failure_key(failure)
            if backend == "codex":
                model = CodexRepairModel(
                    current / "model",
                    model_name,
                    prompt_version=prompt_version,
                    reasoning_effort=reasoning_effort,
                )
            elif backend == "replay":
                recorded_root = recordings or root / "recordings" / "accepted"
                model = RecordedRepairModel(recorded_root / case["id"], model_name)
            else:
                model = RepairModel(endpoint_settings.llm)
            with services.client() as client:
                tc, bb, jira = (
                    TeamCity(settings.teamcity, client),
                    Bitbucket(settings.bitbucket, client),
                    Jira(settings.jira, client),
                )
                discovered = tc.failures(now.date(), settings.timezone)
                if len(discovered) != 1:
                    raise RuntimeError("Synthetic discovery must find one applicable failed build")
                flow = Workflow(settings, run_id, tc, bb, jira, model, publish=True)
                state = flow.run({"run_id": run_id, "failure": discovered[0].model_dump()})
                final_tests = state.get("verification", {}).get("report", {})
                entry = {
                    "case": case["id"],
                    "profile": profile,
                    "prompt_version": prompt_version,
                    "split": case.get("split"),
                    "category": case.get("category"),
                    "complexity": case.get("complexity"),
                    "model": model_name,
                    "status": state["status"],
                    "success": state["status"] == "published",
                    "reason": state.get("reason", ""),
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "attempts": state.get("attempt", 0),
                    "inspections": state.get("inspections", 0),
                    "baseline_repetitions": baseline_repetitions,
                    "baseline_check_count": len(state.get("baseline_checks", [])),
                    "baseline_failed": preflight.report.failed,
                    "baseline_test_names": sorted(
                        {*preflight.report.passed, *preflight.report.failed}
                    ),
                    "passed_test_count": len(final_tests.get("passed", [])),
                    "remaining_failures": final_tests.get("failed", []),
                    "model_calls": getattr(model, "calls", []),
                    "pull_requests_created": len(services.created_prs),
                    "result": str(flow.directory / "result.json"),
                }
                # Independent checks: source tests stay byte-for-byte unchanged and PR branch is
                # exactly the final tested SHA. This is separate from workflow routing decisions.
                if entry["success"]:
                    original_tests = {*preflight.report.passed, *preflight.report.failed}
                    if not original_tests.issubset(set(final_tests.get("passed", []))):
                        raise RuntimeError(
                            "Evaluation invalid: an originally executed test "
                            "is absent or not passing"
                        )
                    changed = _git(
                        flow.workspace.path, "diff", "--name-only", failure.revision, "HEAD"
                    ).splitlines()
                    if any(
                        "_test" in path
                        or not any(fnmatch.fnmatchcase(path, pattern) for pattern in allowed_paths)
                        for path in changed
                    ):
                        raise RuntimeError(
                            "Evaluation invalid: repaired candidate changed protected "
                            "tests/configuration"
                        )
                    remote_sha = _git(
                        current,
                        "--git-dir",
                        str(current / "remote.git"),
                        "rev-parse",
                        "refs/heads/" + state["branch"],
                    )
                    if remote_sha != state["head"] or len(services.created_prs) != 1:
                        raise RuntimeError(
                            "Evaluation publication evidence disagrees with verified candidate"
                        )
                    entry["verified_head"] = remote_sha
                write_json(current / "requests.json", services.requests)
                write_json(current / "pull-requests.json", services.created_prs)
                write_json(current / "score.json", entry)
                results.append(entry)
                model.close()
                print(
                    f"EVALUATION {case['id']}: {state['status']} "
                    f"({entry['attempts']} model attempts)",
                    flush=True,
                )
            write_json(
                directory / "summary.json",
                {
                    "project": project,
                    "profile": profile,
                    "prompt_version": prompt_version,
                    "max_inspections": max_inspections,
                    "inspections_per_attempt": inspections_per_attempt,
                    "baseline_repetitions": baseline_repetitions,
                    "reasoning_effort": reasoning_effort,
                    "structured_diagnostics": structured_diagnostics,
                    "context_chars": context_chars,
                    "definition_reads": definition_reads,
                    "split": split,
                    "model": model_name,
                    "backend": backend,
                    "platform": platform.platform(),
                    "cases": results,
                    "successes": sum(item["success"] for item in results),
                    "total": len(results),
                },
            )
        return int(any(not item["success"] for item in results))
    finally:
        if old_token is None:
            os.environ.pop(mocks.TOKEN_ENV, None)
        else:
            os.environ[mocks.TOKEN_ENV] = old_token
