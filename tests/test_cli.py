import json

import pytest
import yaml

from auto_fix.cli import main
from auto_fix.config import load_settings
from auto_fix.models import FailedTest, Failure
from auto_fix.workflow import failure_key


@pytest.fixture
def config_file(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_TOKEN", "test-token-local")
    service = {"url": "https://internal.invalid", "token_env": "TEST_TOKEN"}
    data = {
        "teamcity": {**service, "build_types": ["Cpp_Tests"]},
        "bitbucket": {**service, "project": "CPP", "repo": "repo"},
        "llm": {**service, "model": "qwen"},
        "repository": {"path": "clone"},
        "build": {"build": [["cmake", "--build", "build"]], "test": ["runner", "{junit}"]},
    }
    path = tmp_path / "config.local.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def failure():
    return Failure(
        build_id="10",
        build_type="Cpp_Tests",
        build_url="https://tc/build/10",
        revision="a" * 40,
        tests=[FailedTest(id="1", name="math.add")],
    )


def test_config_paths_resolve_against_config_file(config_file, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path.parent)
    settings = load_settings(config_file)
    assert settings.repository.path == tmp_path / "clone"
    assert settings.state_dir == tmp_path / ".auto-fix"


def test_unknown_publication_reconciles_without_creating_new_pr(config_file, monkeypatch):
    from auto_fix import cli

    f = failure()
    state_dir = config_file.parent / ".auto-fix"
    receipt = state_dir / "receipts" / f"{failure_key(f)}.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(
        json.dumps(
            {"status": "publication_unknown", "branch": "auto-fix/previous", "head": "b" * 40}
        )
    )

    class TC:
        def __init__(self, *_):
            pass

        def failures(self, *_):
            return [f]

        def close(self):
            pass

    class BB:
        def __init__(self, *_):
            pass

        def find_pr(self, branch, base):
            assert branch == "auto-fix/previous"
            return {
                "id": 123,
                "fromRef": {"id": "refs/heads/" + branch, "latestCommit": "b" * 40},
                "toRef": {"id": "refs/heads/" + base},
            }

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
        cli, "Workflow", lambda *_a, **_kw: pytest.fail("Must not repair or repost")
    )
    assert main(["run", "--config", str(config_file), "--publish", "--retry-blocked"]) == 0
    assert json.loads(receipt.read_text())["pr"]["id"] == 123


def test_graph_needs_no_credentials(capsys):
    assert main(["graph"]) == 0
    assert "Qwen" in capsys.readouterr().out
