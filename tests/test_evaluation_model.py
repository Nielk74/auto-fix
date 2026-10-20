from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from auto_fix.codex_model import CodexRepairModel

PROPOSAL = {
    "summary": "Correct dispatch boundary",
    "explanation": "A single pending item is ready for dispatch.",
    "edits": [{"path": "src/dispatch.cc", "old": "pending > 1", "new": "pending > 0"}],
}


def install_runner(monkeypatch, *, response=PROPOSAL, events=(), returncode=0):
    invocations = []
    monkeypatch.setattr("auto_fix.codex_model.shutil.which", lambda name: "/fake/codex")

    def run(argv, **kwargs):
        invocations.append((argv, kwargs))
        for event in events:
            kwargs["stdout"].write(json.dumps(event) + "\n")
        if response is not None:
            output = Path(argv[argv.index("--output-last-message") + 1])
            output.write_text(response if isinstance(response, str) else json.dumps(response))
        return SimpleNamespace(returncode=returncode)

    monkeypatch.setattr("auto_fix.codex_model.subprocess.run", run)
    return invocations


def test_evaluation_uses_explicit_luna_model_and_exact_packet_with_auditable_usage(
    monkeypatch, tmp_path
):
    usage = {"input_tokens": 1250, "cached_input_tokens": 0, "output_tokens": 121}
    calls = install_runner(monkeypatch, events=[{"type": "turn.completed", "usage": usage}])
    context = {"failure": "DispatchTest.OnePendingItem", "repository": {"files": []}}
    model = CodexRepairModel(tmp_path)
    proposal = model.propose(context)
    assert proposal.model_dump() == PROPOSAL
    argv, kwargs = calls[0]
    assert argv[argv.index("--model") + 1] == "gpt-6-luna"
    assert argv[argv.index("--sandbox") + 1] == "read-only"
    assert "--ignore-user-config" in argv
    assert "--ephemeral" in argv
    assert "Do not call tools" in kwargs["input"]
    assert json.dumps(context, ensure_ascii=False) in kwargs["input"]
    directory = tmp_path / "call-1"
    assert kwargs["cwd"] == directory
    assert json.loads((directory / "request.json").read_text())["context"] == context
    assert json.loads((directory / "schema.json").read_text())["title"] == "Proposal"
    metadata = json.loads((directory / "metadata.json").read_text())
    assert metadata["model"] == "gpt-6-luna"
    assert metadata["usage"] == usage
    assert model.calls[0] == metadata


@pytest.mark.parametrize(
    "tool_type", ["command_execution", "file_change", "mcp_tool_call", "web_search"]
)
def test_outside_tool_access_invalidates_even_a_well_formed_fix(monkeypatch, tmp_path, tool_type):
    install_runner(
        monkeypatch,
        events=[{"type": "item.completed", "item": {"type": tool_type}}],
    )
    model = CodexRepairModel(tmp_path)
    with pytest.raises(RuntimeError, match="outside tool access"):
        model.propose({})
    assert (tmp_path / "call-1" / "events.jsonl").exists()
    assert (tmp_path / "call-1" / "metadata.json").exists()


@pytest.mark.parametrize("response", ['{"summary": "truncated",', {"summary": "missing edits"}])
def test_invalid_or_truncated_json_cannot_become_a_repair(monkeypatch, tmp_path, response):
    install_runner(monkeypatch, response=response)
    with pytest.raises(ValidationError):
        CodexRepairModel(tmp_path).propose({})


def test_provider_failure_cannot_accept_a_leftover_response(monkeypatch, tmp_path):
    install_runner(
        monkeypatch,
        returncode=1,
        events=[{"type": "turn.failed", "error": {"message": "model unavailable"}}],
    )
    with pytest.raises(RuntimeError, match="model unavailable"):
        CodexRepairModel(tmp_path).propose({})


def test_missing_response_is_an_explicit_provider_failure(monkeypatch, tmp_path):
    install_runner(monkeypatch, response=None)
    with pytest.raises(RuntimeError, match="Codex model call failed"):
        CodexRepairModel(tmp_path).propose({})


def test_timeout_keeps_request_and_event_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr("auto_fix.codex_model.shutil.which", lambda name: "/fake/codex")

    def timeout(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr("auto_fix.codex_model.subprocess.run", timeout)
    with pytest.raises(RuntimeError, match="timed out"):
        CodexRepairModel(tmp_path, timeout=1).propose({"failure": "boundary"})
    assert (tmp_path / "call-1" / "request.json").exists()
    assert (tmp_path / "call-1" / "stderr.log").exists()


def test_missing_codex_executable_does_not_silently_change_model(monkeypatch, tmp_path):
    monkeypatch.setattr("auto_fix.codex_model.shutil.which", lambda name: None)
    with pytest.raises(RuntimeError, match="Install and authenticate"):
        CodexRepairModel(tmp_path).propose({})
