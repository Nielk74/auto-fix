from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "expanded-evidence.py"
SPEC = importlib.util.spec_from_file_location("expanded_evidence", SCRIPT)
assert SPEC and SPEC.loader
evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def run(tmp_path):
    workspace = tmp_path / "workspace"
    source = workspace / ".auto-fix" / "development-prototype"
    case = source / "sample_case"
    result = case / "state" / "runs" / "sample-run" / "result.json"
    native = result.parent / "evidence" / "verification" / "junit.xml"
    native.parent.mkdir(parents=True)
    native.write_text('<testsuites><testsuite><testcase name="a"/></testsuite></testsuites>')
    (native.parent / "test.log").write_text("1 test passed\n", encoding="utf-8")
    write_json(
        result,
        {
            "status": "published",
            "verification": {
                "report": {"passed": ["Suite.a"], "failed": []},
                "logs": [str(native)],
            },
        },
    )
    write_json(
        result.parent / "inspection-evidence-1.json",
        {"reads": [{"path": "example.cc", "content": "int f();"}]},
    )
    (result.parent / "fix.diff").write_text(
        "--- a/example.cc\n+++ b/example.cc\n@@ -1 +1 @@\n-return 0;\n+return 1;\n"
    )
    write_json(workspace / "evaluation" / "project.json", {"id": "sample"})
    write_json(
        workspace / "evaluation" / "cases.json", [{"id": "sample_case", "split": "development"}]
    )
    calls = []
    for number, kind in enumerate(("investigation", "repair"), start=1):
        call = case / "model" / f"call-{number}"
        metadata = {
            "model": "gpt-6-luna",
            "transport": "codex-cli",
            "kind": kind,
            "returncode": 0,
            "reasoning_effort": "medium",
            "usage": {"input_tokens": 50},
        }
        write_json(call / "metadata.json", metadata)
        write_json(
            call / "request.json", {"system": "test instruction", "context": {}, "kind": kind}
        )
        response = (
            {
                "summary": "Read implementation",
                "hypotheses": [],
                "queries": ["function"],
                "reads": [{"path": "example.cc", "line": 0, "symbol": ""}],
                "ready": False,
            }
            if kind == "investigation"
            else {
                "summary": "Repair boundary",
                "explanation": "Restore the observed contract",
                "edits": [{"path": "example.cc", "old": "return 0;", "new": "return 1;"}],
            }
        )
        write_json(call / "response.json", response)
        (call / "events.jsonl").write_text(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": json.dumps(response)},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        calls.append(metadata)
    entry = {
        "case": "sample_case",
        "model": "gpt-6-luna",
        "success": True,
        "baseline_failed": ["Suite.a"],
        "model_calls": calls,
        "result": str(result),
    }
    manifest = {
        "model": "gpt-6-luna",
        "backend": "codex",
        "live_inference": True,
        "case_ids": ["sample_case"],
        "source_sha256": {},
        "project_sha256": sha(workspace / "evaluation" / "project.json"),
        "cases_sha256": sha(workspace / "evaluation" / "cases.json"),
        "prompt_version": "contract-v3",
        "max_inspections": 3,
        "max_attempts": 2,
        "structured_diagnostics": True,
        "reasoning_effort": "medium",
    }
    write_json(source / "manifest.json", manifest)
    write_json(
        source / "summary.json", {"model": "gpt-6-luna", "backend": "codex", "cases": [entry]}
    )
    write_json(case / "score.json", entry)
    return workspace, source


def test_preserves_tree_exact_hashes_and_excludes_caches(run, tmp_path):
    workspace, source = run
    for relative in (
        "sample_case/source/.git/objects/object",
        "sample_case/source/.env",
        "sample_case/remote.git/config",
        "sample_case/state/worktrees/main/secret.log",
        "sample_case/model/call-1/program.exe",
    ):
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not for export")
    destination = tmp_path / "artifact"
    index = evidence.export({"dev": source}, destination, workspace=workspace)
    assert index["runs"][0]["model_calls"] == 2
    native = "results/dev/sample_case/state/runs/sample-run/evidence/verification/junit.xml"
    hashes = json.loads((destination / "SHA256SUMS.json").read_text())
    assert native in hashes
    for relative, expected in hashes.items():
        assert sha(destination / relative) == expected
    assert not any(
        ".git" in path or "/source/" in path or "worktrees" in path or path.endswith(".exe")
        for path in hashes
    )
    assert not (destination / "results/dev/sample_case/result.json").exists()


@pytest.mark.parametrize("location", ["manifest", "summary", "metadata", "summary_call"])
def test_rejects_other_models_without_publishing(run, tmp_path, location):
    workspace, source = run
    path = source / (
        "sample_case/model/call-1/metadata.json"
        if location == "metadata"
        else f"{location if location != 'summary_call' else 'summary'}.json"
    )
    document = json.loads(path.read_text())
    if location == "summary_call":
        document["cases"][0]["model_calls"][0]["model"] = "another-model"
    else:
        document["model"] = "another-model"
    write_json(path, document)
    destination = tmp_path / "artifact"
    with pytest.raises(ValueError, match="model|Luna|luna"):
        evidence.export({"dev": source}, destination, workspace=workspace)
    assert not destination.exists()
    assert not list(tmp_path.glob(".artifact-*"))


@pytest.mark.parametrize(
    "event",
    [
        {"type": "item.started", "item": {"type": kind}}
        for kind in (
            "command_execution",
            "file_change",
            "mcp_tool_call",
            "web_search",
            "collab_tool_call",
            "unknown_tool",
        )
    ]
    + [{"type": "command_execution"}, {"type": "item.completed", "item": "invalid"}],
)
def test_rejects_outside_cli_actions(run, tmp_path, event):
    workspace, source = run
    (source / "sample_case/model/call-1/events.jsonl").write_text(json.dumps(event) + "\n")
    with pytest.raises(ValueError, match="tool event"):
        evidence.export({"dev": source}, tmp_path / "artifact", workspace=workspace)


def test_rejects_malformed_cli_jsonl(run, tmp_path):
    workspace, source = run
    (source / "sample_case/model/call-1/events.jsonl").write_text('{"type":')
    with pytest.raises(ValueError):
        evidence.export({"dev": source}, tmp_path / "artifact", workspace=workspace)


@pytest.mark.parametrize("change", ["missing_kind", "not_live", "gap", "wrong_kind"])
def test_rejects_unattested_or_inconsistent_call_sequences(run, tmp_path, change):
    workspace, source = run
    call = source / "sample_case/model/call-1"
    metadata = json.loads((call / "metadata.json").read_text())
    if change == "gap":
        call.rename(call.parent / "call-3")
    elif change == "wrong_kind":
        write_json(call / "request.json", {"kind": "repair"})
    else:
        if change == "missing_kind":
            del metadata["kind"]
        else:
            metadata["live_inference"] = False
        write_json(call / "metadata.json", metadata)
    with pytest.raises(ValueError):
        evidence.export({"dev": source}, tmp_path / "artifact", workspace=workspace)


def test_archives_failed_truncated_responses_without_making_replay_claim(run, tmp_path):
    workspace, source = run
    summary = json.loads((source / "summary.json").read_text())
    summary["cases"][0]["success"] = False
    write_json(source / "summary.json", summary)
    raw = b'{"summary":"incomplete'
    (source / "sample_case/model/call-2/response.json").write_bytes(raw)
    destination = tmp_path / "artifact"
    index = evidence.export({"dev": source}, destination, workspace=workspace)
    assert "recordings" not in index
    assert (destination / "results/dev/sample_case/model/call-2/response.json").read_bytes() == raw


def test_recording_rejects_native_failures_and_bad_input_hashes(run, tmp_path):
    workspace, source = run
    config = {
        "dev": {"project_file": "evaluation/project.json", "cases_file": "evaluation/cases.json"}
    }
    (workspace / "evaluation/cases.json").write_text("{}")
    with pytest.raises(ValueError, match="SHA256"):
        evidence.export(
            {"dev": source}, tmp_path / "bad-input", workspace=workspace, recordings=config
        )
    write_json(workspace / "evaluation/cases.json", [{"id": "sample_case", "split": "development"}])
    result = source / "sample_case/state/runs/sample-run/result.json"
    write_json(
        result,
        {
            "status": "published",
            "verification": {"report": {"passed": ["Suite.a"], "failed": ["Suite.b"]}},
        },
    )
    with pytest.raises(ValueError, match="native verification"):
        evidence.export(
            {"dev": source}, tmp_path / "bad-native", workspace=workspace, recordings=config
        )


def test_investigation_then_repair_records_replay_in_sequence(run, tmp_path):
    from auto_fix.recorded_model import RecordedRepairModel

    workspace, source = run
    destination = tmp_path / "artifact"
    evidence.export(
        {"dev": source},
        destination,
        workspace=workspace,
        recordings={
            "dev": {
                "project_file": "evaluation/project.json",
                "cases_file": "evaluation/cases.json",
                "windows_case_ids": ["sample_case"],
            }
        },
    )
    index = json.loads((destination / "recordings/expanded/index.json").read_text())
    entry = index["entries"][0]
    assert entry["ci_tags"] == ["windows-representative"]
    assert [call["kind"] for call in entry["recorded_calls"]] == ["investigation", "repair"]
    model = RecordedRepairModel(destination / entry["recordings_directory"])
    assert model.inspect({}).reads[0].path == "example.cc"
    assert model.propose({}).edits[0].new == "return 1;"
    assert all(call["transport"] == "recorded-replay" for call in model.calls)


@pytest.mark.parametrize(
    "secret",
    [
        "Bearer abcdefghijklmnop123456",
        "https://admin:password@example.test",
        '{"api_key":"private-key-value"}',
    ],
)
def test_rejects_credentials_in_allowlisted_evidence(run, tmp_path, secret):
    workspace, source = run
    call = source / "sample_case/model/call-1"
    if secret.startswith("{"):
        (call / "response.json").write_text(secret)
    else:
        (call / "stderr.log").write_text(secret)
    with pytest.raises(ValueError, match="credential"):
        evidence.export({"dev": source}, tmp_path / "artifact", workspace=workspace)


def test_rejects_environment_secrets_without_printing_them(run, tmp_path, monkeypatch):
    workspace, source = run
    token = "private_environment_credential"
    monkeypatch.setenv("CUSTOM_API_TOKEN", token)
    (source / "sample_case/model/call-1/stderr.log").write_text(token)
    with pytest.raises(ValueError) as error:
        evidence.export({"dev": source}, tmp_path / "artifact", workspace=workspace)
    assert token not in str(error.value)


def test_rejects_symlinked_evidence_and_outside_result_pointer(run, tmp_path):
    workspace, source = run
    response = source / "sample_case/model/call-1/response.json"
    actual = tmp_path / "outside.json"
    response.rename(actual)
    response.symlink_to(actual)
    with pytest.raises(ValueError, match="Symlink"):
        evidence.export({"dev": source}, tmp_path / "artifact", workspace=workspace)
    response.unlink()
    actual.rename(response)
    summary = json.loads((source / "summary.json").read_text())
    summary["cases"][0]["result"] = str(tmp_path / "outside-result.json")
    write_json(source / "summary.json", summary)
    with pytest.raises(ValueError, match="escapes"):
        evidence.export({"dev": source}, tmp_path / "artifact", workspace=workspace)


def test_refuses_existing_destination_and_oversized_evidence(run, tmp_path):
    workspace, source = run
    destination = tmp_path / "artifact"
    destination.mkdir()
    with pytest.raises(ValueError, match="already exist"):
        evidence.export({"dev": source}, destination, workspace=workspace)
    assert destination.exists()
    with pytest.raises(ValueError, match="byte limit"):
        evidence.export(
            {"dev": source}, tmp_path / "limited", workspace=workspace, max_file_bytes=10
        )


def test_fixture_proofs_follow_hashes_deduplicate_and_exclude_binaries(tmp_path):
    workspace = tmp_path / "workspace"
    proof = workspace / ".auto-fix/proof/case"
    proof.mkdir(parents=True)
    for filename in ("clean.xml", "injected.xml"):
        (proof / filename).write_text("<testsuites/>")
    (proof / "test.log").write_text("actual native log\n")
    (proof / "program.exe").write_bytes(b"binary")
    (proof / "source").mkdir()
    (proof / "source/secret.log").write_text("source cache must be pruned")
    audit = workspace / "evaluation/hunk-audit.json"
    write_json(
        audit,
        {
            "evidence": {
                ".auto-fix/proof/case/injected.xml": {"sha256": sha(proof / "injected.xml")}
            }
        },
    )
    index = workspace / "evaluation/dataset-index.json"
    write_json(
        index,
        {
            "clean_junit": ".auto-fix/proof/case/clean.xml",
            "clean_junit_sha256": sha(proof / "clean.xml"),
            "audit": {"path": "evaluation/hunk-audit.json", "sha256": sha(audit)},
        },
    )
    destination = tmp_path / "artifact"
    evidence.export({}, destination, workspace=workspace, fixture_proofs=index)
    mapping = json.loads((destination / "fixture-proofs/index.json").read_text())
    files = mapping["files"]
    assert (
        files[".auto-fix/proof/case/clean.xml"]["path"]
        == files[".auto-fix/proof/case/injected.xml"]["path"]
    )
    assert ".auto-fix/proof/case/test.log" in files
    assert ".auto-fix/proof/case/injected.xml" in mapping["verified_source_hashes"]
    assert all("program.exe" not in key and "/source/" not in key for key in files)
    (proof / "injected.xml").write_text("tampered")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        evidence.export({}, tmp_path / "bad-artifact", workspace=workspace, fixture_proofs=index)


def test_fixture_proof_reference_cannot_escape_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    index = workspace / "evaluation/index.json"
    write_json(index, {"proof": ".auto-fix/../../outside.xml"})
    with pytest.raises(ValueError, match="escapes"):
        evidence.export({}, tmp_path / "artifact", workspace=workspace, fixture_proofs=index)
