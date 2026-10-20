"""Crash recovery must inspect side-effect journals before trusting old receipts."""

import json

import pytest
import yaml

from auto_fix import cli
from auto_fix.models import FailedTest, Failure
from auto_fix.workflow import failure_key


@pytest.mark.parametrize("prior_status,attempt_suffix", [("ready", ""), ("blocked", "-r1")])
def test_unresolved_publication_journal_overrides_stale_receipt(
    tmp_path, monkeypatch, prior_status, attempt_suffix
):
    service = {"url": "https://internal.invalid", "token_env": "TEST_RECOVERY_TOKEN"}
    config_file = tmp_path / "config.local.yaml"
    config_file.write_text(
        yaml.safe_dump(
            {
                "teamcity": {**service, "build_types": ["Cpp_Tests"]},
                "bitbucket": {**service, "project": "CPP", "repo": "repo"},
                "llm": {**service, "model": "qwen"},
                "repository": {"path": "clone"},
                "build": {
                    "build": [["cmake", "--build", "build"]],
                    "test": ["runner", "{junit}"],
                },
            }
        )
    )
    failure = Failure(
        build_id="10",
        build_type="Cpp_Tests",
        build_url="https://tc/build/10",
        revision="a" * 40,
        tests=[FailedTest(id="1", name="math.add")],
    )
    key = failure_key(failure)
    state_dir = tmp_path / ".auto-fix"
    receipt = state_dir / "receipts" / f"{key}.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(
        json.dumps({"status": prior_status, "run_id": key, "branch": f"auto-fix/{key}"})
    )
    interrupted = state_dir / "runs" / (key + attempt_suffix)
    interrupted.mkdir(parents=True)
    journal = {
        "status": "intent",
        "branch": f"auto-fix/{key}{attempt_suffix}",
        "head": "b" * 40,
    }
    (interrupted / "publication.json").write_text(json.dumps(journal))
    looked_up = []

    class TC:
        def __init__(self, *_):
            pass

        def failures(self, *_):
            return [failure]

        def close(self):
            pass

    class BB:
        def __init__(self, *_):
            pass

        def find_pr(self, branch, base):
            looked_up.append((branch, base))
            return None

        def create_pr(self, *_):
            pytest.fail("An unresolved POST must never be resubmitted automatically")

        def close(self):
            pass

    class Model:
        def __init__(self, *_):
            pass

        def close(self):
            pass

    monkeypatch.setattr(cli, "TeamCity", TC)
    monkeypatch.setattr(cli, "Bitbucket", BB)
    monkeypatch.setattr(cli, "RepairModel", Model)
    monkeypatch.setattr(
        cli, "Workflow", lambda *_a, **_kw: pytest.fail("Journal must stop graph replay")
    )
    assert cli.main(["run", "--config", str(config_file), "--publish", "--retry-blocked"]) == 1
    saved = json.loads(receipt.read_text())
    assert saved["status"] == "publication_unknown"
    assert saved["branch"] == journal["branch"]
    assert looked_up == [(journal["branch"], "master")]
