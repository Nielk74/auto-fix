"""Failure-boundary regressions: no model calls and no frozen-fixture changes."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import yaml

from auto_fix import cli
from auto_fix.config import RepositoryConfig, Settings
from auto_fix.evaluation import _git, _source
from auto_fix.llm import RepairModel
from auto_fix.models import Edit, FailedTest, Failure, Proposal
from auto_fix.operational_evaluation import (
    CLI_RECOVERY_SCENARIOS,
    MODEL,
    ORIGINAL_SCENARIOS,
    SCENARIOS,
    judge_outcome,
)
from auto_fix.workflow import Workflow, failure_key
from auto_fix.workspace import Workspace, WorkspaceError

HEAD = "b" * 40
OTHER_HEAD = "c" * 40
BRANCH = "auto-fix/publication-boundary"


def failure():
    return Failure(
        build_id="212",
        build_type="CppTests",
        build_url="https://tc.example/build/212",
        revision="a" * 40,
        tests=[FailedTest(id="1", name="Arithmetic.Add")],
    )


def receipt(head=HEAD, *, source=BRANCH, target="master"):
    result = {
        "id": 911,
        "state": "OPEN",
        "fromRef": {"id": "refs/heads/" + source},
        "toRef": {"id": "refs/heads/" + target},
    }
    if head is not None:
        result["fromRef"]["latestCommit"] = head
    return result


def make_flow(tmp_path, *, existing=None, created=None):
    service = {"url": "https://service.example", "token_env": "UNUSED_BOUNDARY_TOKEN"}
    settings = Settings.model_validate(
        {
            "state_dir": tmp_path / "state",
            "teamcity": {**service, "build_types": ["CppTests"]},
            "bitbucket": {**service, "project": "CPP", "repo": "runtime"},
            "llm": {**service, "model": "not-invoked"},
            "repository": {"path": tmp_path / "source"},
            "build": {"build": [["not-invoked"]], "test": ["not-invoked", "{junit}"]},
        }
    )
    writes = []
    bb = SimpleNamespace(
        find_pr=lambda *_: existing,
        create_pr=lambda *_: writes.append("POST") or created,
    )
    flow = Workflow(settings, "publication-boundary", None, bb, None, None, publish=True)
    flow.workspace = SimpleNamespace(
        branch=BRANCH,
        head=lambda: HEAD,
        is_clean=lambda: True,
        push=lambda: writes.append("push"),
    )
    state = {
        "run_id": flow.run_id,
        "failure": failure().model_dump(),
        "head": HEAD,
        "branch": BRANCH,
        "proposal": {"summary": "Repair candidate", "explanation": "Native tests passed."},
    }
    return flow, state, writes


@pytest.mark.parametrize("phase", ["existing", "created"])
def test_pr_without_commit_identity_cannot_claim_verified_publication(tmp_path, phase):
    malformed = receipt(head=None)
    flow, state, writes = make_flow(
        tmp_path,
        existing=malformed if phase == "existing" else None,
        created=malformed if phase == "created" else None,
    )
    with pytest.raises(RuntimeError, match="head|commit|receipt|verified"):
        flow.publish_pr(state)
    assert writes == ([] if phase == "existing" else ["push", "POST"])
    journal = flow.directory / "publication.json"
    if journal.exists():
        assert json.loads(journal.read_text())["status"] != "published"


@pytest.mark.parametrize(
    "malformed",
    [receipt(source="someone-elses-branch"), receipt(target="release/old")],
)
def test_created_pr_must_reference_the_requested_source_and_target_branches(tmp_path, malformed):
    flow, state, writes = make_flow(tmp_path, created=malformed)
    with pytest.raises(RuntimeError):
        flow.publish_pr(state)
    assert writes == ["push", "POST"]
    assert json.loads((flow.directory / "publication.json").read_text())["status"] == "intent"


def interrupted_run(tmp_path, *, journal_head=HEAD, saved_head=HEAD):
    key = failure_key(failure())
    directory = tmp_path / "runs" / key
    directory.mkdir(parents=True)
    journal = {"status": "intent", "branch": BRANCH}
    if journal_head is not None:
        journal["head"] = journal_head
    saved = {"status": "publication_unknown", "branch": BRANCH, "run_id": key}
    if saved_head is not None:
        saved["head"] = saved_head
    (directory / "publication.json").write_text(json.dumps(journal))
    (directory / "result.json").write_text(json.dumps(saved))
    return key, directory


@pytest.mark.parametrize("returned_head", [OTHER_HEAD, None])
def test_cli_journal_recovery_rejects_wrong_or_absent_pr_commit(tmp_path, returned_head):
    key, directory = interrupted_run(tmp_path)
    bb = SimpleNamespace(find_pr=lambda *_: receipt(returned_head))
    recovered = cli.recover_publication(tmp_path, key, bb, "master")
    assert recovered["status"] == "publication_unknown"
    assert "head" in recovered["reason"].lower() or "commit" in recovered["reason"].lower()
    assert json.loads((directory / "publication.json").read_text())["status"] == "intent"


def test_cli_recovery_uses_verified_journal_head_instead_of_stale_result_head(tmp_path):
    key, _ = interrupted_run(tmp_path, journal_head=HEAD, saved_head=OTHER_HEAD)
    bb = SimpleNamespace(find_pr=lambda *_: receipt(HEAD))
    recovered = cli.recover_publication(tmp_path, key, bb, "master")
    assert recovered["status"] == "published"
    assert recovered["head"] == HEAD
    assert recovered["pr"]["fromRef"]["latestCommit"] == recovered["head"]


def test_cli_recovery_cannot_invent_verification_when_both_head_records_are_absent(tmp_path):
    key, directory = interrupted_run(tmp_path, journal_head=None, saved_head=None)
    recovered = cli.recover_publication(
        tmp_path, key, SimpleNamespace(find_pr=lambda *_: receipt(HEAD)), "master"
    )
    assert recovered["status"] == "publication_unknown"
    assert json.loads((directory / "publication.json").read_text())["status"] == "intent"


@pytest.mark.parametrize("returned_head", [OTHER_HEAD, None])
def test_legacy_uncertain_receipt_does_not_bypass_head_validation(
    tmp_path, monkeypatch, returned_head
):
    monkeypatch.setenv("BOUNDARY_TOKEN", "mechanics-boundary-token")
    service = {"url": "https://internal.example", "token_env": "BOUNDARY_TOKEN"}
    config = {
        "teamcity": {**service, "build_types": ["CppTests"]},
        "bitbucket": {**service, "project": "CPP", "repo": "runtime"},
        "llm": {**service, "model": "not-invoked"},
        "repository": {"path": "source"},
        "build": {"build": [["not-invoked"]], "test": ["not-invoked", "{junit}"]},
    }
    config_file = tmp_path / "config.local.yaml"
    config_file.write_text(yaml.safe_dump(config))
    previous = tmp_path / ".auto-fix/receipts" / f"{failure_key(failure())}.json"
    previous.parent.mkdir(parents=True)
    previous.write_text(
        json.dumps({"status": "publication_unknown", "branch": BRANCH, "head": HEAD})
    )

    class Service:
        def __init__(self, *_):
            pass

        def close(self):
            pass

    class TC(Service):
        def failures(self, *_):
            return [failure()]

    class BB(Service):
        def find_pr(self, *_):
            return receipt(returned_head)

    monkeypatch.setattr(cli, "TeamCity", TC)
    monkeypatch.setattr(cli, "Bitbucket", BB)
    monkeypatch.setattr(cli, "RepairModel", Service)
    monkeypatch.setattr(
        cli, "Workflow", lambda *_a, **_k: pytest.fail("No repair or repost allowed")
    )
    assert cli.main(["run", "--config", str(config_file), "--publish"]) != 0
    assert json.loads(previous.read_text())["status"] == "publication_unknown"


@pytest.mark.parametrize(
    "calls",
    [
        [],
        [{"model": MODEL, "kind": "investigation", "transport": "codex-cli", "returncode": 0}],
        [{"model": MODEL, "kind": "repair", "transport": "recorded-replay", "returncode": 0}],
        [{"model": MODEL, "kind": "repair", "transport": "codex-cli", "returncode": 124}],
    ],
)
def test_operational_repair_score_requires_a_completed_live_luna_repair_call(calls):
    chosen = next(item for item in SCENARIOS if item.id == "jira_prompt_injection")
    checks = judge_outcome(
        chosen,
        state={"status": "published", "head": HEAD, "branch": BRANCH, "pr": receipt(HEAD)},
        native_validated=True,
        protected_unchanged=True,
        remote_head=HEAD,
        created_prs=[receipt(HEAD)],
        post_count=1,
        calls=calls,
        faults=[],
        injection_exposed=True,
    )
    assert not all(checks.values())


def test_real_endpoint_timeout_enters_bounded_repair_retry_instead_of_escaping(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("UNUSED_BOUNDARY_TOKEN", "mechanics-boundary-token")
    flow, state, _ = make_flow(tmp_path)
    flow.settings.llm.model = MODEL
    requests = []

    def lost_response(request):
        requests.append(request)
        raise httpx.ReadTimeout("Transport lost the model response", request=request)

    with httpx.Client(transport=httpx.MockTransport(lost_response)) as client:
        flow.model = RepairModel(flow.settings.llm, client)
        flow._model_context = lambda *_: {"failure": "mechanics transport fixture"}
        result = flow.repair(state)
    assert result["status"] == "invalid_proposal"
    assert result["attempt"] == 1
    assert "timeout" in result["feedback"].lower() or "response" in result["feedback"].lower()
    assert len(requests) == 1


def test_fixture_preparation_and_multiline_replay_ignore_global_autocrlf_true(
    tmp_path, monkeypatch
):
    config = tmp_path / "git-global-config"
    config.write_text("[core]\n\tautocrlf = true\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    subprocess.run(["git", "init", "-b", "master", str(upstream)], check=True, capture_output=True)
    _git(upstream, "config", "user.name", "Boundary Mechanics")
    _git(upstream, "config", "user.email", "mechanics@example.invalid")
    _git(upstream, "config", "commit.gpgsign", "false")
    (upstream / "src").mkdir()
    before = "int add(int a, int b) {\n  return a + b;\n}\n"
    after = before.replace("a + b", "a - b")
    (upstream / "src/value.cc").write_bytes(before.encode())
    (upstream / "src/diagnostics.cc").write_bytes(b"// unrelated runtime diagnostics\n")
    _git(upstream, "add", ".")
    _git(upstream, "commit", "-m", "Boundary control")
    current = tmp_path / "scenario"
    current.mkdir()
    case = {
        "mutations": [{"path": "src/value.cc", "before": before, "after": after}],
        "exposure": "indirect",
        "changed_files": ["src/diagnostics.cc"],
        "context": {"commit_message": "CPP-12 Source change", "pr_title": "CPP-12 Diagnostics"},
    }
    source, _ = _source(current, upstream, case)
    workspace = Workspace(RepositoryConfig(path=source), current / "state", "crlf-boundary")
    workspace.prepare(_git(source, "rev-parse", "HEAD"))
    workspace.apply_edits([Edit(path="src/value.cc", old=after, new=before)])
    assert (workspace.path / "src/value.cc").read_bytes() == before.encode()
    assert _git(source, "config", "--get", "core.autocrlf") == "false"


def rejected_proposal_flow(tmp_path):
    flow, state, _ = make_flow(tmp_path)
    flow.settings.structured_diagnostics = True
    proposal = Proposal.model_validate(
        {
            "summary": "Mechanics proposal with an invalid anchor",
            "explanation": "Test fixture only; no model inference.",
            "edits": [{"path": "src/value.cc", "old": "NOT_PRESENT", "new": "PROPOSED_VALUE"}],
        }
    )
    flow.model = SimpleNamespace(propose=lambda *_: proposal)
    flow.workspace.context = lambda *_a, **_k: {
        "head": HEAD,
        "commits": [],
        "files": [{"path": "src/value.cc", "content": "return actual_value;\n"}],
    }

    def reject(_):
        raise WorkspaceError("Expected old text exactly once in src/value.cc; found 0")

    flow.workspace.apply_edits = reject
    outcome = flow.repair(state)
    assert outcome["status"] == "invalid_proposal"
    return flow, {**state, **outcome}, proposal


def test_rejected_model_proposal_is_durable_before_edit_validation(tmp_path):
    flow, _, proposal = rejected_proposal_flow(tmp_path)
    evidence = flow.directory / "proposal-1.json"
    assert evidence.is_file()
    serialized = evidence.read_text()
    assert proposal.edits[0].old in serialized and proposal.edits[0].new in serialized


def test_retry_packet_contains_rejected_edit_and_unapplied_status(tmp_path):
    flow, state, proposal = rejected_proposal_flow(tmp_path)
    packet = flow._model_context(state, 2)
    serialized = json.dumps(packet)
    assert proposal.edits[0].old in serialized and proposal.edits[0].new in serialized

    def has_unapplied(value):
        if isinstance(value, dict):
            return value.get("applied") is False or any(has_unapplied(v) for v in value.values())
        if isinstance(value, list):
            return any(has_unapplied(v) for v in value)
        return False

    assert has_unapplied(packet)


def test_rejected_edit_evidence_survives_actual_graph_state_and_reaches_next_request(tmp_path):
    """Exercise LangGraph propagation with mechanics doubles, without inference."""
    flow, state, _ = make_flow(tmp_path)
    flow.settings.structured_diagnostics = True
    flow.collect_context = lambda _: {"context": {}, "attempt": 0, "status": "working"}
    flow.prepare = lambda _: {"branch": BRANCH}
    flow.baseline = lambda _: {"status": "working", "feedback": "Original assertion failed"}
    flow.verify = lambda _: {"status": "validated"}
    flow.finalize = lambda _: {"status": "ready", "head": HEAD}
    flow.publish_pr = lambda _: {"status": "published"}
    flow.workspace.context = lambda *_a, **_k: {
        "head": HEAD,
        "commits": [],
        "files": [{"path": "src/value.cc", "content": "return actual_value;\n"}],
    }
    contexts = []

    def propose(context):
        contexts.append(context)
        old = "NOT_PRESENT" if len(contexts) == 1 else "actual_value"
        return Proposal.model_validate(
            {
                "summary": "Mechanics retry",
                "explanation": "No live model evaluation.",
                "edits": [{"path": "src/value.cc", "old": old, "new": "PROPOSED_VALUE"}],
            }
        )

    def apply(edits):
        if edits[0].old == "NOT_PRESENT":
            raise WorkspaceError("Expected old text exactly once in src/value.cc; found 0")

    flow.model = SimpleNamespace(propose=propose)
    flow.workspace.apply_edits = apply
    result = flow.run(state)
    assert result["status"] == "published"
    assert len(contexts) == 2
    previous_edit = json.dumps(contexts[1])
    assert "NOT_PRESENT" in previous_edit and "PROPOSED_VALUE" in previous_edit


def test_operations_addendum_preserves_frozen_parent_and_declares_all_new_cases():
    root = Path(__file__).resolve().parents[1]
    path = root / "evaluation/expanded/protocol-operations-v2.json"
    addendum = json.loads(path.read_text())
    assert (
        hashlib.sha256((root / addendum["parent_protocol"]).read_bytes()).hexdigest()
        == (addendum["parent_protocol_sha256"])
    )
    assert [item.id for item in ORIGINAL_SCENARIOS] == [
        item["id"] for item in addendum["original_scenarios_preserved"]
    ]
    assert [item.id for item in CLI_RECOVERY_SCENARIOS] == [
        item["id"] for item in addendum["added_scenarios_declared_before_live_execution"]
    ]
    assert addendum["original_count"] == 9
    assert addendum["added_count"] == 4
    assert addendum["total_count"] == len(SCENARIOS) == 13
    assert addendum["model_policy"]["replay_allowed"] is False


@pytest.mark.parametrize("id", ["cli_recovery_wrong_head", "cli_recovery_missing_head"])
def test_cli_operational_safe_stop_does_not_count_wrong_receipt_as_a_repair(id):
    chosen = next(item for item in SCENARIOS if item.id == id)
    checks = judge_outcome(
        chosen,
        state={"status": "publication_unknown", "head": HEAD, "branch": BRANCH},
        native_validated=True,
        protected_unchanged=True,
        remote_head=HEAD,
        created_prs=[receipt(None if id.endswith("missing_head") else OTHER_HEAD)],
        post_count=1,
        calls=[{"model": MODEL, "kind": "repair", "transport": "codex-cli", "returncode": 0}],
        faults=[
            {"action": "accepted_pr_response_timeout"},
            {"action": "production_cli_recovery"},
            {"action": id},
        ],
        first_status="publication_unknown",
    )
    assert all(checks.values())
