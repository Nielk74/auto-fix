"""Verify saved Luna provenance, then run native workflow replays without live inference.

Index schema v1 is documented in docs/expanded-evaluation.md. Paths are relative
to the repository root; recordings_directory names the case directory containing
contiguous call-N/{metadata,response}.json files. Hashes attest exported file
integrity, not cryptographic authentication of the model provider.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from auto_fix.build import parse_junit
from auto_fix.models import Investigation, Proposal

MODEL = "gpt-6-luna"
SHA = r"^[0-9a-f]{64}$"
DEFAULT_INDEX = Path("evaluation/recordings/expanded/index.json")


class RecordedCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    directory: str = Field(pattern=r"^call-[1-9][0-9]*$")
    kind: Literal["repair", "investigation"]
    metadata_sha256: str = Field(pattern=SHA)
    response_sha256: str = Field(pattern=SHA)


class ReplayCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,100}$")
    project_file: str
    project_sha256: str = Field(pattern=SHA)
    cases_file: str
    cases_sha256: str = Field(pattern=SHA)
    recordings_directory: str
    prompt: Literal["repair-v1", "evidence-v2", "contract-v3"]
    max_inspections: int = Field(ge=0, le=6, strict=True)
    inspections_per_attempt: int = Field(default=6, ge=1, le=6, strict=True)
    context_chars: int = Field(default=60000, ge=4000, le=200000, strict=True)
    definition_reads: bool = Field(default=False, strict=True)
    structured_diagnostics: bool = Field(strict=True)
    reasoning_effort: Literal["medium", "high"]
    max_attempts: int = Field(ge=1, le=5, strict=True)
    expected_completion: Literal[True]
    expected_test_names: list[str] = Field(min_length=1)
    ci_tags: list[Literal["windows-representative"]] = Field(default_factory=list)
    recorded_calls: list[RecordedCall] = Field(min_length=1)
    source_run: dict[str, Any] | str | None = None

    @field_validator("expected_completion", mode="before")
    @classmethod
    def completed_only(cls, value):
        if value is not True:
            raise ValueError("Only natively accepted completions are eligible for replay")
        return value

    @field_validator("expected_test_names")
    @classmethod
    def distinct_tests(cls, names):
        if any(not name.strip() for name in names) or len(set(names)) != len(names):
            raise ValueError("Expected test identities must be nonempty and distinct")
        return names


class ReplayIndex(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    model: Literal["gpt-6-luna"]
    live_inference_transport: Literal["codex-cli"]
    entries: list[ReplayCase] = Field(min_length=1)
    provenance: dict[str, Any] | str | None = None


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _path(root: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in relative or ":" in relative:
        raise ValueError("Index paths must be portable repository-relative paths")
    candidate = root.joinpath(*path.parts)
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError("Index path escapes the repository")
    if any(item.is_symlink() for item in [candidate, *candidate.parents] if item != root.parent):
        raise ValueError("Replay inputs must not contain symlinks")
    return candidate


def load_index(index_path: Path, root: Path) -> ReplayIndex:
    """Validate every exported case before generating a matrix or invoking native builds."""
    index = ReplayIndex.model_validate(_json(index_path))
    if len({case.id for case in index.entries}) != len(index.entries):
        raise ValueError("Replay case IDs must be unique")
    for case in index.entries:
        project = _path(root, case.project_file)
        cases = _path(root, case.cases_file)
        recordings = _path(root, case.recordings_directory)
        if _hash(project) != case.project_sha256 or _hash(cases) != case.cases_sha256:
            raise ValueError(f"Frozen project/case input hash differs for {case.id}")
        if recordings.name != case.id or not recordings.is_dir():
            raise ValueError("Recording case directory must match its case ID")
        matches = [item for item in _json(cases)["cases"] if item["id"] == case.id]
        if len(matches) != 1:
            raise ValueError(f"Replay case {case.id} is absent or duplicated in its manifest")
        expected_directories = [
            f"call-{number}" for number in range(1, len(case.recorded_calls) + 1)
        ]
        if [call.directory for call in case.recorded_calls] != expected_directories:
            raise ValueError("Recorded calls must form a contiguous ordered sequence")
        if {path.name for path in recordings.glob("call-*")} != set(expected_directories):
            raise ValueError("Index must account for every recorded call directory")
        kinds = [call.kind for call in case.recorded_calls]
        if kinds.count("repair") > case.max_attempts or kinds.count("repair") == 0:
            raise ValueError("Recorded repairs disagree with the repair budget")
        if kinds.count("investigation") > case.max_inspections:
            raise ValueError("Recorded investigations exceed the inspection budget")
        for call in case.recorded_calls:
            current = _path(root, f"{case.recordings_directory}/{call.directory}")
            metadata_path = _path(root, f"{current.relative_to(root).as_posix()}/metadata.json")
            response_path = _path(root, f"{current.relative_to(root).as_posix()}/response.json")
            if (
                _hash(metadata_path) != call.metadata_sha256
                or _hash(response_path) != call.response_sha256
            ):
                raise ValueError("Recorded call hash differs from the trusted exported index")
            metadata = _json(metadata_path)
            if (
                not isinstance(metadata, dict)
                or metadata.get("model") != MODEL
                or metadata.get("transport") != "codex-cli"
                or metadata.get("kind") != call.kind
                or type(metadata.get("returncode")) is not int
                or metadata["returncode"] != 0
                or metadata.get("reasoning_effort") != case.reasoning_effort
                or metadata.get("live_inference") is False
            ):
                raise ValueError("Replay requires successful original Luna CLI action metadata")
            response = Proposal if call.kind == "repair" else Investigation
            response.model_validate_json(response_path.read_bytes())
    return index


def matrix(index: ReplayIndex, platform: str) -> dict:
    if platform not in {"linux", "windows"}:
        raise ValueError("Replay matrix platform must be linux or windows")
    return {
        "include": [
            {"case": case.id}
            for case in index.entries
            if platform == "linux" or "windows-representative" in case.ci_tags
        ]
    }


def replay_command(case: ReplayCase, root: Path, directory: Path) -> list[str]:
    command = [
        "uv",
        "run",
        "--no-sync",
        "auto-fix",
        "evaluate",
        "--backend",
        "replay",
        "--model",
        MODEL,
        "--directory",
        str(directory / "run"),
        "--project-file",
        str(_path(root, case.project_file)),
        "--cases-file",
        str(_path(root, case.cases_file)),
        "--recordings",
        str(_path(root, case.recordings_directory).parent),
        "--case",
        case.id,
        "--prompt",
        case.prompt,
        "--max-inspections",
        str(case.max_inspections),
        "--inspections-per-attempt",
        str(case.inspections_per_attempt),
        "--max-attempts",
        str(case.max_attempts),
        "--reasoning-effort",
        case.reasoning_effort,
        "--upstream-cache",
        str(directory / "upstream-cache"),
    ]
    if case.structured_diagnostics:
        command.append("--structured-diagnostics")
    command.extend(["--context-chars", str(case.context_chars)])
    if case.definition_reads:
        command.append("--definition-reads")
    return command


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _git(directory: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(directory), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def verify_result(case: ReplayCase, root: Path, directory: Path) -> dict:
    """Independently inspect replay evidence after the normal evaluator's native gates."""
    run = directory / "run"
    manifest, summary = _json(run / "manifest.json"), _json(run / "summary.json")
    _require(
        manifest.get("backend") == "replay"
        and manifest.get("live_inference") is False
        and manifest.get("model") == MODEL
        and manifest.get("case_ids") == [case.id]
        and manifest.get("prompt_version") == case.prompt
        and manifest.get("max_inspections") == case.max_inspections
        and manifest.get("inspections_per_attempt", 6) == case.inspections_per_attempt
        and manifest.get("context_chars", 60000) == case.context_chars
        and manifest.get("definition_reads", False) is case.definition_reads
        and manifest.get("max_attempts") == case.max_attempts
        and manifest.get("structured_diagnostics") is case.structured_diagnostics
        and manifest.get("reasoning_effort") == case.reasoning_effort
        and manifest.get("project_sha256") == case.project_sha256
        and manifest.get("cases_sha256") == case.cases_sha256,
        "Replay manifest has a different backend, model, or case selection",
    )
    _require(
        summary.get("total") == 1
        and summary.get("successes") == 1
        and summary.get("backend") == "replay"
        and summary.get("model") == MODEL
        and [item.get("case") for item in summary.get("cases", [])] == [case.id],
        "Replay must complete exactly one accepted case",
    )
    score = _json(run / case.id / "score.json")
    results = list((run / case.id / "state/runs").glob("*/result.json"))
    _require(len(results) == 1, "Replay must retain exactly one workflow result")
    state = _json(results[0])
    _require(
        state.get("status") == "published"
        and score.get("case") == case.id
        and score.get("success") is True
        and score.get("status") == "published"
        and score.get("pull_requests_created") == 1,
        "Replay did not reach one verified publication",
    )
    report = state.get("verification", {}).get("report", {})
    baseline = state.get("baseline", {}).get("report", {})
    original = {item["name"] for item in state.get("failure", {}).get("tests", [])}
    expected = set(case.expected_test_names)
    _require(
        expected
        == set(score.get("baseline_failed", []))
        == set(baseline.get("failed", []))
        == original
        and expected <= set(report.get("passed", []))
        and not report.get("failed")
        and score.get("remaining_failures") == [],
        "Original test identities must reproduce and all pass the final native suites",
    )
    verification = state.get("verification", {})
    _require(
        verification.get("build_ok") is True and verification.get("test_ok") is True,
        "Replay native verification did not pass",
    )
    xml = [
        Path(path)
        for path in verification.get("logs", [])
        if path.endswith("/junit.xml") or path.endswith("\\junit.xml")
    ]
    _require(
        len(xml) == 1 and xml[0].resolve().is_relative_to(run.resolve()),
        "Replay requires its actual final native JUnit evidence",
    )
    native = parse_junit(xml[0])
    _require(
        set(native.passed) == set(report["passed"])
        and not native.failed
        and score.get("passed_test_count") == len(native.passed),
        "Native JUnit evidence differs from the final reported test identities",
    )
    required_baseline = set(baseline.get("passed", [])) | set(baseline.get("failed", []))
    _require(
        required_baseline <= set(native.passed),
        "Final native JUnit must retain every originally passing and failing test identity",
    )
    worktrees = [path for path in (run / case.id / "state/worktrees").iterdir() if path.is_dir()]
    _require(len(worktrees) == 1, "Replay requires one preserved candidate worktree")
    candidate = worktrees[0]
    head, branch = state.get("head", ""), state.get("branch", "")
    _require(bool(re.fullmatch(r"[0-9a-f]{40,64}", head)), "Missing verified Git head")
    remote = run / case.id / "remote.git"
    pushed = _git(run, "--git-dir", str(remote), "rev-parse", "refs/heads/" + branch)
    prs = _json(run / case.id / "pull-requests.json")
    _require(
        len(prs) == 1
        and head
        == score.get("verified_head")
        == pushed
        == _git(candidate, "rev-parse", "HEAD")
        == prs[0].get("fromRef", {}).get("latestCommit"),
        "Tested, pushed, and pull-request heads must agree exactly",
    )
    _require(
        not _git(candidate, "status", "--porcelain", "--untracked-files=no"),
        "Candidate has uncommitted tracked changes after verification",
    )
    revision = state["failure"]["revision"]
    _require(bool(re.fullmatch(r"[0-9a-f]{40,64}", revision)), "Invalid original Git revision")
    changed = _git(candidate, "diff", "--name-only", revision, "HEAD").splitlines()
    allowed = _json(_path(root, case.project_file))["allowed_paths"]
    _require(
        bool(changed)
        and all(
            "_test" not in path and any(fnmatch.fnmatchcase(path, pattern) for pattern in allowed)
            for path in changed
        ),
        "Replay changed protected tests/configuration or produced no source fix",
    )
    calls = score.get("model_calls", [])
    _require(len(calls) == len(case.recorded_calls), "Replay consumed a different call count")
    for actual, recorded in zip(calls, case.recorded_calls, strict=True):
        _require(
            actual.get("model") == MODEL
            and actual.get("kind") == recorded.kind
            and actual.get("transport") == "recorded-replay"
            and actual.get("live_inference") is False
            and actual.get("usage") == {}
            and actual.get("returncode") == 0
            and actual.get("provenance", {}).get("response_sha256") == recorded.response_sha256,
            "Replay call provenance or sequence differs; this must never count as live inference",
        )
    return {
        "case": case.id,
        "status": "published",
        "mechanical_replay_passed": True,
        "live_inference": False,
        "model_calls": len(calls),
        "live_tokens": 0,
        "passed_test_count": len(native.passed),
        "verified_head": head,
        "protected_tests_unchanged": True,
    }


def run_case(index_path: Path, root: Path, case_id: str, directory: Path) -> int:
    root, directory = root.resolve(), directory.resolve()
    index = load_index(index_path, root)
    index_sha256 = _hash(index_path)
    selected = [case for case in index.entries if case.id == case_id]
    if len(selected) != 1:
        raise ValueError("Unknown accepted replay case ID")
    case = selected[0]
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("Replay directory must be new/empty; prior evidence is preserved")
    directory.mkdir(parents=True, exist_ok=True)
    command = replay_command(case, root, directory)
    status = {
        "case": case.id,
        "live_inference": False,
        "index_sha256": index_sha256,
        "command": command,
        "returncode": 1,
    }
    try:
        with (
            (directory / "stdout.log").open("wb") as out,
            (directory / "stderr.log").open("wb") as err,
        ):
            result = subprocess.run(command, cwd=root, stdout=out, stderr=err, check=False)
        status["process_returncode"] = result.returncode
        if result.returncode:
            raise ValueError("Native replay evaluator exited unsuccessfully; see retained logs")
        _require(_hash(index_path) == index_sha256, "Replay index changed during execution")
        load_index(index_path, root)  # Frozen inputs and recordings must remain intact.
        status.update(verify_result(case, root, directory), returncode=0)
    except Exception as exc:
        # Preserve structured failure for malformed or incomplete native artifacts.
        status["error"] = str(exc)
    finally:
        (directory / "replay-result.json").write_text(
            json.dumps(status, indent=2) + "\n", encoding="utf-8"
        )
    return status["returncode"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser(
        "matrix", help="Emit a GitHub include matrix; no native/model calls"
    )
    generate.add_argument("--platform", choices=["linux", "windows"], required=True)
    run = commands.add_parser("run", help="Run one accepted response sequence through native gates")
    run.add_argument("--case", required=True)
    run.add_argument("--directory", type=Path, required=True)
    commands.add_parser("validate", help="Verify index schema, hashes, and original call metadata")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    index_path = args.index if args.index.is_absolute() else root / args.index
    if args.command == "run":
        return run_case(index_path, root, args.case, args.directory)
    index = load_index(index_path, root)
    print(
        json.dumps(
            matrix(index, args.platform)
            if args.command == "matrix"
            else {
                "accepted_cases": len(index.entries),
                "live_inference": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
