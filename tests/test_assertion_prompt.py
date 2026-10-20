"""Prompt routing checks use synthetic transports, never live model inference."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from auto_fix.cli import main
from auto_fix.codex_model import CodexRepairModel
from auto_fix.config import LLMConfig
from auto_fix.experiment import ExperimentJob, job_command
from auto_fix.llm import RepairModel
from auto_fix.prompts import CONTRACT, INVESTIGATE, repair_prompt

PROPOSAL = {
    "summary": "Restore generic boundary",
    "explanation": "The expected boundary includes the pending value.",
    "edits": [{"path": "src/example.cc", "old": "count > 1", "new": "count > 0"}],
}


def test_additive_prompt_preserves_historical_prompt_bytes():
    hashes = {
        "repair-v1": "68ade6197d32466da3541f6ec5f083b40af1975884051b51b9b788e7c02e61a0",
        "evidence-v2": "63fe81e213b235afc30c02fca60cb7a7c8acf0ea1036255b99d09434f8522e9f",
        "contract-v3": "34b980f105a63191f6e388221c600aba9e53dda9f257dbeaf7d6ad741cd927dd",
    }
    for name, expected in hashes.items():
        assert hashlib.sha256(repair_prompt(name).encode()).hexdigest() == expected
    assert (
        hashlib.sha256(INVESTIGATE.encode()).hexdigest()
        == "8f57886e90aa8413091205cb751ab4b4dd327bf470376b7f3fcb9747d37dfe01"
    )
    assert repair_prompt("assertion-v4").startswith(CONTRACT)


def test_custom_endpoint_sends_selected_assertion_prompt(monkeypatch):
    monkeypatch.setenv("MODEL_TOKEN", "synthetic-test-token")
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(PROPOSAL)}}]}
        )

    config = LLMConfig(
        url="https://model.invalid/v1",
        token_env="MODEL_TOKEN",
        model="qwen3.8-27b",
        prompt_version="assertion-v4",
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert (
            RepairModel(config, client).propose({"failure": "Suite.Case"}).model_dump() == PROPOSAL
        )
    assert seen[0]["messages"][0]["content"] == repair_prompt("assertion-v4")
    assert seen[0]["model"] == "qwen3.8-27b" and "tools" not in seen[0]


def test_codex_adapter_records_new_prompt_hash_without_changing_model(monkeypatch, tmp_path):
    invocations = []
    monkeypatch.setattr("auto_fix.codex_model.shutil.which", lambda _: "/synthetic/codex")

    def run(argv, **kwargs):
        invocations.append((argv, kwargs))
        Path(argv[argv.index("--output-last-message") + 1]).write_text(json.dumps(PROPOSAL))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("auto_fix.codex_model.subprocess.run", run)
    model = CodexRepairModel(tmp_path, prompt_version="assertion-v4", reasoning_effort="high")
    assert model.propose({"failure": "Suite.Case"}).model_dump() == PROPOSAL
    request = json.loads((tmp_path / "call-1/request.json").read_text())
    metadata = json.loads((tmp_path / "call-1/metadata.json").read_text())
    assert request["system"] == repair_prompt("assertion-v4")
    assert metadata["prompt_version"] == "assertion-v4"
    assert metadata["prompt_sha256"] == hashlib.sha256(request["system"].encode()).hexdigest()
    argv = invocations[0][0]
    assert argv[argv.index("--model") + 1] == "gpt-6-luna"


@pytest.mark.parametrize("command", ["evaluate", "evaluate-operations"])
def test_cli_routes_explicit_prompt_to_evaluator(monkeypatch, tmp_path, command):
    target = (
        "auto_fix.evaluation.run_evaluation"
        if command == "evaluate"
        else "auto_fix.operational_evaluation.run_operational_evaluation"
    )
    seen = []

    def evaluate(*args, **kwargs):
        seen.append(kwargs)
        return 0

    monkeypatch.setattr(target, evaluate)
    assert main([command, "--directory", str(tmp_path), "--prompt", "assertion-v4"]) == 0
    assert seen[0]["prompt_version"] == "assertion-v4"


def test_experiment_and_recorded_replay_accept_the_same_additive_prompt(tmp_path):
    job = ExperimentJob(
        id="assertion-example",
        arm="assertion-expanded",
        split="development",
        project_file=Path("project.json"),
        cases_file=Path("cases.json"),
        prompt="assertion-v4",
        max_attempts=4,
        max_inspections=6,
        inspections_per_attempt=2,
    )
    argv = job_command(job, tmp_path / "run", tmp_path / "project", tmp_path / "cases")
    assert argv[argv.index("--prompt") + 1] == "assertion-v4"
    assert argv[argv.index("--max-attempts") + 1] == "4"
    assert argv[argv.index("--max-inspections") + 1] == "6"
    script = Path(__file__).resolve().parents[1] / "scripts/replay-expanded.py"
    spec = importlib.util.spec_from_file_location("assertion_prompt_replay", script)
    assert spec and spec.loader
    replay = importlib.util.module_from_spec(spec)
    monkey_module = sys.modules.setdefault(spec.name, replay)
    try:
        spec.loader.exec_module(replay)
        case = replay.ReplayCase(
            id="synthetic_case",
            project_file="project.json",
            project_sha256="a" * 64,
            cases_file="cases.json",
            cases_sha256="b" * 64,
            recordings_directory="recordings/synthetic_case",
            prompt="assertion-v4",
            max_inspections=6,
            inspections_per_attempt=2,
            structured_diagnostics=True,
            reasoning_effort="high",
            max_attempts=4,
            expected_completion=True,
            expected_test_names=["Suite.Case"],
            recorded_calls=[
                {
                    "directory": "call-1",
                    "kind": "repair",
                    "metadata_sha256": "c" * 64,
                    "response_sha256": "d" * 64,
                }
            ],
        )
        assert case.prompt == "assertion-v4"
    finally:
        if monkey_module is replay:
            sys.modules.pop(spec.name, None)
