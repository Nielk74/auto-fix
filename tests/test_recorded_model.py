from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from auto_fix.models import Proposal
from auto_fix.recorded_model import RecordedRepairModel


def record(directory, number=1, *, metadata=None, response=None):
    path = directory / f"call-{number}"
    path.mkdir(parents=True)
    metadata = metadata or {
        "model": "gpt-6-luna",
        "transport": "codex-cli",
        "returncode": 0,
        "elapsed_seconds": 9.83,
        "usage": {"input_tokens": 1300, "output_tokens": 180},
    }
    response = response or {
        "summary": "Restore byte conversion",
        "explanation": "The current arithmetic yields an incorrect value for hexadecimal letters.",
        "edits": [{"path": "absl/strings/escaping.cc", "old": "x += 8;", "new": "x += 9;"}],
    }
    (path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (path / "response.json").write_text(json.dumps(response), encoding="utf-8")
    return path


def test_replay_returns_recorded_proposal_with_provenance_and_no_live_token_usage(tmp_path):
    path = record(tmp_path)
    before = {item.name: item.read_bytes() for item in path.iterdir()}
    context = {"failure": {"name": "Unescape.BasicFunction"}, "private": "unused-context-value"}
    model = RecordedRepairModel(tmp_path)
    proposal = model.propose(context)
    assert isinstance(proposal, Proposal)
    assert proposal.edits[0].new == "x += 9;"
    assert model.calls[0]["transport"] == "recorded-replay"
    assert model.calls[0]["live_inference"] is False
    assert model.calls[0]["usage"] == {}
    assert model.calls[0]["recorded_usage"] == {"input_tokens": 1300, "output_tokens": 180}
    provenance = model.calls[0]["provenance"]
    assert provenance["metadata"]["transport"] == "codex-cli"
    assert provenance["response_sha256"] == hashlib.sha256(before["response.json"]).hexdigest()
    assert "unused-context-value" not in json.dumps(model.calls)
    assert context["private"] == "unused-context-value"
    assert before == {item.name: item.read_bytes() for item in path.iterdir()}
    assert len(list(tmp_path.iterdir())) == 1
    model.close()


def test_replay_consumes_one_record_per_attempt_and_never_reuses_final_response(tmp_path):
    record(tmp_path)
    record(
        tmp_path,
        2,
        response={
            "summary": "Restore casing",
            "explanation": "Preserve the documented casing direction.",
            "edits": [{"path": "absl/strings/ascii.cc", "old": "<true>", "new": "<false>"}],
        },
    )
    model = RecordedRepairModel(tmp_path)
    assert model.propose({}).summary == "Restore byte conversion"
    assert model.propose({}).summary == "Restore casing"
    with pytest.raises(RuntimeError, match="call-3 is missing"):
        model.propose({})
    assert len(model.calls) == 3
    assert model.calls[2]["returncode"] == 1
    assert all(call["usage"] == {} for call in model.calls)


@pytest.mark.parametrize("model_name", ["gpt-6-sol", "qwen3.8-27b", None])
def test_recorded_model_identity_must_match_exactly(tmp_path, model_name):
    record(tmp_path, metadata={"model": model_name, "returncode": 0})
    model = RecordedRepairModel(tmp_path)
    with pytest.raises(RuntimeError, match="model differs from expected gpt-6-luna"):
        model.propose({})
    assert model.calls[0]["returncode"] == 1


@pytest.mark.parametrize("returncode", [1, -9, None, False, "0"])
def test_recorded_incomplete_or_failed_live_calls_are_rejected(tmp_path, returncode):
    record(tmp_path, metadata={"model": "gpt-6-luna", "returncode": returncode})
    with pytest.raises(RuntimeError, match="did not complete successfully"):
        RecordedRepairModel(tmp_path).propose({})


@pytest.mark.parametrize("missing", ["metadata.json", "response.json"])
def test_missing_recording_parts_stop_explicitly(tmp_path, missing):
    path = record(tmp_path)
    (path / missing).unlink()
    with pytest.raises(RuntimeError, match="missing response or metadata"):
        RecordedRepairModel(tmp_path).propose({})


@pytest.mark.parametrize("invalid", ["[]", "{broken", '"metadata"'])
def test_corrupt_metadata_cannot_be_replayed(tmp_path, invalid):
    path = record(tmp_path)
    (path / "metadata.json").write_text(invalid, encoding="utf-8")
    with pytest.raises(RuntimeError, match="metadata"):
        RecordedRepairModel(tmp_path).propose({})


@pytest.mark.parametrize("response", ["{broken", "{}", '{"summary":"Missing edits"}'])
def test_corrupt_or_schema_invalid_responses_are_rejected(tmp_path, response):
    path = record(tmp_path)
    (path / "response.json").write_text(response, encoding="utf-8")
    with pytest.raises(RuntimeError, match="invalid proposal"):
        RecordedRepairModel(tmp_path).propose({})


def test_recording_directory_and_expected_identity_are_required(tmp_path):
    with pytest.raises(ValueError, match="existing recording directory"):
        RecordedRepairModel(tmp_path / "missing")
    with pytest.raises(ValueError, match="expected model identity"):
        RecordedRepairModel(tmp_path, expected_model="")


def test_replay_has_no_dependency_on_cli_or_network(tmp_path, monkeypatch):
    record(tmp_path)
    monkeypatch.setenv("PATH", "")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AUTO_FIX_EVALUATION_TOKEN", raising=False)
    model = RecordedRepairModel(Path(tmp_path))
    assert model.propose({}).edits[0].old == "x += 8;"
