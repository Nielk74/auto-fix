"""Structural replay checks use synthetic metadata and tiny local Git repositories.

These fixtures are not live model evidence and never enter the exported index.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/replay-expanded.py"
SPEC = importlib.util.spec_from_file_location("expanded_replay", SCRIPT)
assert SPEC and SPEC.loader
replay = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = replay
SPEC.loader.exec_module(replay)


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def recording(tmp_path):
    root = tmp_path.resolve()
    project, cases = root / "project.json", root / "cases.json"
    write(project, {"id": "structural", "allowed_paths": ["src/**"]})
    write(cases, {"cases": [{"id": "cpp_case"}, {"id": "cpp_other"}]})
    entries = []
    for number, name in enumerate(["cpp_case", "cpp_other"]):
        recorded = root / "recordings" / name / "call-1"
        write(
            recorded / "metadata.json",
            {
                "model": "gpt-6-luna",
                "transport": "codex-cli",
                "kind": "repair",
                "returncode": 0,
                "reasoning_effort": "medium",
                "fixture_notice": "Synthetic structural fixture; not live model evidence",
            },
        )
        write(
            recorded / "response.json",
            {
                "summary": "Structural fixture",
                "explanation": "Not an evaluation result",
                "edits": [{"path": "src/lib.cc", "old": "broken", "new": "fixed"}],
            },
        )
        entries.append(
            {
                "id": name,
                "project_file": "project.json",
                "project_sha256": digest(project),
                "cases_file": "cases.json",
                "cases_sha256": digest(cases),
                "recordings_directory": f"recordings/{name}",
                "prompt": "contract-v3",
                "max_inspections": 0,
                "structured_diagnostics": True,
                "reasoning_effort": "medium",
                "max_attempts": 2,
                "expected_completion": True,
                "expected_test_names": ["Suite.Case"],
                "ci_tags": ["windows-representative"] if number == 0 else [],
                "recorded_calls": [
                    {
                        "directory": "call-1",
                        "kind": "repair",
                        "metadata_sha256": digest(recorded / "metadata.json"),
                        "response_sha256": digest(recorded / "response.json"),
                    }
                ],
            }
        )
    index = root / "index.json"
    payload = {
        "schema_version": 1,
        "model": "gpt-6-luna",
        "live_inference_transport": "codex-cli",
        "entries": entries,
    }
    write(index, payload)
    return root, index, payload


def test_matrix_includes_all_linux_cases_and_only_explicit_windows_tags(recording):
    root, index, _payload = recording
    parsed = replay.load_index(index, root)
    assert replay.matrix(parsed, "linux") == {
        "include": [{"case": "cpp_case"}, {"case": "cpp_other"}]
    }
    assert replay.matrix(parsed, "windows") == {"include": [{"case": "cpp_case"}]}
    with pytest.raises(ValueError, match="linux or windows"):
        replay.matrix(parsed, "macos")


def test_investigation_then_repair_preserves_the_saved_action_sequence(recording):
    root, index, payload = recording
    directory = root / "recordings/cpp_case"
    (directory / "call-1").rename(directory / "call-2")
    entry = payload["entries"][0]
    entry["recorded_calls"][0]["directory"] = "call-2"
    write(
        directory / "call-1/metadata.json",
        {
            "model": "gpt-6-luna",
            "transport": "codex-cli",
            "kind": "investigation",
            "returncode": 0,
            "reasoning_effort": "medium",
            "fixture_notice": "Synthetic structural fixture; not live model evidence",
        },
    )
    write(
        directory / "call-1/response.json",
        {
            "summary": "Inspect current implementation",
            "hypotheses": ["Boundary handling"],
            "queries": ["function_name"],
            "reads": [],
            "ready": False,
        },
    )
    entry["max_inspections"] = 3
    entry["recorded_calls"].insert(
        0,
        {
            "directory": "call-1",
            "kind": "investigation",
            "metadata_sha256": digest(directory / "call-1/metadata.json"),
            "response_sha256": digest(directory / "call-1/response.json"),
        },
    )
    write(index, payload)
    parsed = replay.load_index(index, root).entries[0]
    assert [call.kind for call in parsed.recorded_calls] == ["investigation", "repair"]


def test_matrix_cli_emits_valid_github_json_without_starting_a_process(
    recording, monkeypatch, capsys
):
    root, index, _payload = recording

    def forbidden(*_args, **_kwargs):
        pytest.fail("Matrix generation must not launch native builds or model calls")

    monkeypatch.setattr(replay.subprocess, "run", forbidden)
    assert (
        replay.main(["--root", str(root), "--index", str(index), "matrix", "--platform", "windows"])
        == 0
    )
    assert json.loads(capsys.readouterr().out) == {"include": [{"case": "cpp_case"}]}


@pytest.mark.parametrize(
    "field,value",
    [
        ("model", "gpt-6-sol"),
        ("transport", "recorded-replay"),
        ("kind", "investigation"),
        ("kind", None),
        ("returncode", 124),
        ("returncode", False),
        ("reasoning_effort", "high"),
        ("live_inference", False),
    ],
)
def test_rejects_non_luna_replay_failed_or_mismatched_action_metadata(recording, field, value):
    root, index, payload = recording
    metadata = root / "recordings/cpp_case/call-1/metadata.json"
    data = json.loads(metadata.read_text())
    data[field] = value
    write(metadata, data)
    payload["entries"][0]["recorded_calls"][0]["metadata_sha256"] = digest(metadata)
    write(index, payload)
    with pytest.raises(ValueError, match="original Luna CLI action metadata"):
        replay.load_index(index, root)


def test_rejects_changed_recording_or_manifest_hashes(recording):
    root, index, _payload = recording
    path = root / "recordings/cpp_case/call-1/response.json"
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="call hash differs"):
        replay.load_index(index, root)


@pytest.mark.parametrize(
    "field,value",
    [
        ("recordings_directory", "../outside"),
        ("project_file", "/outside/project.json"),
        ("cases_file", "C:\\outside\\cases.json"),
    ],
)
def test_rejects_traversal_and_nonportable_paths(recording, field, value):
    root, index, payload = recording
    payload["entries"][0][field] = value
    write(index, payload)
    with pytest.raises(ValueError, match="repository-relative"):
        replay.load_index(index, root)


def test_rejects_symlink_input_even_with_matching_content(recording):
    root, index, payload = recording
    link = root / "linked-project.json"
    try:
        link.symlink_to(root / "project.json")
    except OSError:
        pytest.skip("Symlink creation unavailable")
    payload["entries"][0]["project_file"] = link.name
    write(index, payload)
    with pytest.raises(ValueError, match="symlinks"):
        replay.load_index(index, root)


@pytest.mark.parametrize("change", ["gap", "extra", "duplicate", "budget", "response"])
def test_rejects_incomplete_sequence_duplicate_cases_and_invalid_responses(recording, change):
    root, index, payload = recording
    entry = payload["entries"][0]
    if change == "gap":
        entry["recorded_calls"][0]["directory"] = "call-2"
    elif change == "extra":
        (root / "recordings/cpp_case/call-2").mkdir()
    elif change == "duplicate":
        payload["entries"].append(entry)
    elif change == "budget":
        entry["recorded_calls"][0]["kind"] = "investigation"
    else:
        response = root / "recordings/cpp_case/call-1/response.json"
        write(response, {"summary": "No edits"})
        entry["recorded_calls"][0]["response_sha256"] = digest(response)
    write(index, payload)
    with pytest.raises(ValueError):
        replay.load_index(index, root)


@pytest.mark.parametrize("completion", [False, 1, "true"])
def test_only_explicit_accepted_completions_are_eligible(recording, completion):
    root, index, payload = recording
    payload["entries"][0]["expected_completion"] = completion
    write(index, payload)
    with pytest.raises(ValidationError, match="natively accepted completions"):
        replay.load_index(index, root)


def test_replay_command_pins_backend_and_all_workflow_settings(recording, tmp_path):
    root, index, _payload = recording
    case = replay.load_index(index, root).entries[0]
    command = replay.replay_command(case, root, tmp_path / "output")
    assert command[:5] == ["uv", "run", "--no-sync", "auto-fix", "evaluate"]
    assert command[command.index("--backend") + 1] == "replay"
    assert command[command.index("--model") + 1] == "gpt-6-luna"
    assert command[command.index("--recordings") + 1] == str(root / "recordings")
    assert command[command.index("--case") + 1] == "cpp_case"
    assert command[command.index("--prompt") + 1] == "contract-v3"
    assert command[command.index("--max-attempts") + 1] == "2"
    assert "--structured-diagnostics" in command
    assert "--config" not in command and "--backend codex" not in " ".join(command)


def git(path, *args):
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def evidence(root, case, directory):
    """Create structural evidence with real local Git; no compiler or model is invoked."""
    run = directory / "run"
    current = run / case.id
    candidate = current / "state/worktrees/tc-fixture"
    candidate.mkdir(parents=True)
    git(candidate, "init", "-q")
    git(candidate, "config", "user.name", "Structural Test")
    git(candidate, "config", "user.email", "test@example.invalid")
    source = candidate / "src/lib.cc"
    source.parent.mkdir()
    source.write_text("broken\n")
    git(candidate, "add", ".")
    git(candidate, "commit", "-qm", "structural fixture base")
    revision = git(candidate, "rev-parse", "HEAD")
    source.write_text("fixed\n")
    git(candidate, "commit", "-qam", "structural fixture fix")
    head = git(candidate, "rev-parse", "HEAD")
    remote = current / "remote.git"
    git(candidate, "init", "--bare", "-q", str(remote))
    git(candidate, "push", "-q", str(remote), "HEAD:refs/heads/auto-fix/tc-fixture")
    xml = current / "state/runs/tc-fixture/evidence/final/junit.xml"
    xml.parent.mkdir(parents=True)
    xml.write_text(
        '<testsuite><testcase classname="Suite" name="Case"/>'
        '<testcase classname="Suite" name="Other"/></testsuite>'
    )
    write(
        run / "manifest.json",
        {
            "backend": "replay",
            "model": "gpt-6-luna",
            "live_inference": False,
            "case_ids": [case.id],
            "prompt_version": case.prompt,
            "max_inspections": case.max_inspections,
            "max_attempts": case.max_attempts,
            "structured_diagnostics": case.structured_diagnostics,
            "reasoning_effort": case.reasoning_effort,
            "project_sha256": case.project_sha256,
            "cases_sha256": case.cases_sha256,
        },
    )
    score = {
        "case": case.id,
        "success": True,
        "status": "published",
        "baseline_failed": ["Suite.Case"],
        "remaining_failures": [],
        "passed_test_count": 2,
        "pull_requests_created": 1,
        "verified_head": head,
        "model_calls": [
            {
                "model": "gpt-6-luna",
                "kind": "repair",
                "transport": "recorded-replay",
                "live_inference": False,
                "usage": {},
                "returncode": 0,
                "provenance": {"response_sha256": case.recorded_calls[0].response_sha256},
            }
        ],
    }
    write(current / "score.json", score)
    write(
        run / "summary.json",
        {
            "total": 1,
            "successes": 1,
            "cases": [score],
            "backend": "replay",
            "model": "gpt-6-luna",
        },
    )
    state = {
        "status": "published",
        "head": head,
        "branch": "auto-fix/tc-fixture",
        "failure": {"revision": revision, "tests": [{"name": "Suite.Case"}]},
        "baseline": {"report": {"passed": ["Suite.Other"], "failed": ["Suite.Case"]}},
        "verification": {
            "build_ok": True,
            "test_ok": True,
            "logs": [str(xml)],
            "report": {"passed": ["Suite.Case", "Suite.Other"], "failed": []},
        },
    }
    write(current / "state/runs/tc-fixture/result.json", state)
    write(current / "pull-requests.json", [{"fromRef": {"latestCommit": head}}])
    return current


def test_verifies_native_identity_protected_files_and_exact_git_publication_evidence(recording):
    root, index, _payload = recording
    case = replay.load_index(index, root).entries[0]
    output = root / "output"
    evidence(root, case, output)
    result = replay.verify_result(case, root, output)
    assert result["mechanical_replay_passed"] is True
    assert result["live_inference"] is False and result["live_tokens"] == 0
    assert result["protected_tests_unchanged"] is True
    assert result["passed_test_count"] == 2


@pytest.mark.parametrize("corruption", ["test_identity", "pr_head", "call_kind", "live_usage"])
def test_post_run_verifier_rejects_corrupted_native_or_publication_evidence(recording, corruption):
    root, index, _payload = recording
    case = replay.load_index(index, root).entries[0]
    output = root / "output"
    current = evidence(root, case, output)
    if corruption == "pr_head":
        write(current / "pull-requests.json", [{"fromRef": {"latestCommit": "a" * 40}}])
    elif corruption == "test_identity":
        result = current / "state/runs/tc-fixture/result.json"
        state = json.loads(result.read_text())
        state["verification"]["report"]["passed"] = ["Suite.Other"]
        write(result, state)
    else:
        score_path = current / "score.json"
        score = json.loads(score_path.read_text())
        if corruption == "call_kind":
            score["model_calls"][0]["kind"] = "investigation"
        else:
            score["model_calls"][0]["usage"] = {"input_tokens": 200}
        write(score_path, score)
    with pytest.raises(ValueError):
        replay.verify_result(case, root, output)


@pytest.mark.parametrize("missing_test", ["omitted", "skipped"])
def test_rejects_lost_passing_test_even_when_final_state_score_and_junit_agree(
    recording, missing_test
):
    root, index, _payload = recording
    case = replay.load_index(index, root).entries[0]
    output = root / "output"
    current = evidence(root, case, output)
    result_path = current / "state/runs/tc-fixture/result.json"
    state = json.loads(result_path.read_text())
    state["verification"]["report"]["passed"] = ["Suite.Case"]
    write(result_path, state)
    score_path = current / "score.json"
    score = json.loads(score_path.read_text())
    score["passed_test_count"] = 1
    write(score_path, score)
    junit = Path(state["verification"]["logs"][0])
    skipped = '<testcase classname="Suite" name="Other"><skipped/></testcase>'
    junit.write_text(
        '<testsuite><testcase classname="Suite" name="Case"/>'
        + (skipped if missing_test == "skipped" else "")
        + "</testsuite>"
    )
    with pytest.raises(ValueError, match="every originally passing and failing test identity"):
        replay.verify_result(case, root, output)


def test_protected_test_edit_is_rejected_even_if_all_head_fields_agree(recording):
    root, index, _payload = recording
    case = replay.load_index(index, root).entries[0]
    output = root / "output"
    current = evidence(root, case, output)
    candidate = current / "state/worktrees/tc-fixture"
    (candidate / "src/lib_test.cc").write_text("// weakened structural test fixture\n")
    git(candidate, "add", ".")
    git(candidate, "commit", "-qm", "unacceptable protected test mutation")
    head = git(candidate, "rev-parse", "HEAD")
    git(candidate, "push", "-q", str(current / "remote.git"), "HEAD:refs/heads/auto-fix/tc-fixture")
    result_path, score_path = current / "state/runs/tc-fixture/result.json", current / "score.json"
    state, score = json.loads(result_path.read_text()), json.loads(score_path.read_text())
    state["head"], score["verified_head"] = head, head
    write(result_path, state)
    write(score_path, score)
    write(current / "pull-requests.json", [{"fromRef": {"latestCommit": head}}])
    with pytest.raises(ValueError, match="protected tests/configuration"):
        replay.verify_result(case, root, output)


def test_run_is_replay_only_keeps_logs_and_refuses_reusing_prior_evidence(recording, monkeypatch):
    root, index, _payload = recording
    case = replay.load_index(index, root).entries[0]
    output = root / "output"
    original = replay.subprocess.run
    invocations = []

    def evaluate(command, **kwargs):
        if command[0] != "uv":
            return original(command, **kwargs)
        invocations.append(command)
        assert command[command.index("--backend") + 1] == "replay"
        evidence(root, case, output)
        kwargs["stdout"].write(b"synthetic evaluator output\n")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(replay.subprocess, "run", evaluate)
    assert replay.run_case(index, root, case.id, output) == 0
    saved = json.loads((output / "replay-result.json").read_text())
    assert saved["live_inference"] is False and saved["mechanical_replay_passed"] is True
    assert (output / "stdout.log").read_text() == "synthetic evaluator output\n"
    assert len(invocations) == 1
    with pytest.raises(ValueError, match="prior evidence is preserved"):
        replay.run_case(index, root, case.id, output)


def test_failed_native_process_keeps_nonzero_status_and_logs(recording, monkeypatch):
    root, index, _payload = recording
    output = root / "output"

    def failed(command, **kwargs):
        kwargs["stderr"].write(b"synthetic native compilation failure\n")
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(replay.subprocess, "run", failed)
    assert replay.run_case(index, root, "cpp_case", output) == 1
    saved = json.loads((output / "replay-result.json").read_text())
    assert saved["process_returncode"] == 1
    assert saved["live_inference"] is False and "error" in saved
    assert "compilation failure" in (output / "stderr.log").read_text()
