from __future__ import annotations

import copy
import json
from collections import deque
from types import SimpleNamespace

import pytest

from auto_fix.config import Settings
from auto_fix.models import FailedTest, Failure, Proposal, Verification
from auto_fix.models import TestReport as Report
from auto_fix.workflow import Workflow, pr_description, validates_fix


def failure():
    return Failure(
        build_id="101",
        build_type="Cpp_Tests",
        build_url="https://teamcity.example/build/101",
        revision="a" * 40,
        tests=[FailedTest(id="1", name="math.add")],
        evidence_urls=["https://teamcity.example/artifacts/before.png"],
    )


def report(*, passed=(), failed=(), skipped=(), build_ok=True, test_ok=True):
    return Verification(
        build_ok=build_ok,
        test_ok=test_ok,
        report=Report(passed=list(passed), failed=list(failed), skipped=list(skipped)),
        output="test evidence",
    )


class WorkspaceStub:
    def __init__(self, path):
        self.path = path
        self.branch = "auto-fix/test-run"
        self.current_head = "b" * 40
        self.clean = True
        self.operations = []

    def prepare(self, revision):
        self.operations.append(("prepare", revision))

    def context(self, changes, max_chars, test_names=None):
        return {"files": [{"path": "src/add.cpp", "content": "return a - b;"}]}

    def apply_edits(self, edits):
        self.operations.append(("edit", edits[0].new))
        self.clean = False

    def commit(self, summary):
        self.operations.append(("commit", summary))
        self.clean = True

    def rebase(self):
        self.operations.append(("rebase",))
        self.current_head = "c" * 40
        return self.current_head

    def head(self):
        return self.current_head

    def is_clean(self):
        return self.clean

    def has_changes_against_base(self):
        return True

    def diff(self):
        return "" if self.clean else "uncommitted diff"

    def committed_diff(self):
        return "-return a - b;\n+return a + b;\n"

    def push(self):
        self.operations.append(("push", self.current_head))


class BuilderStub:
    def __init__(self, reports):
        self.reports = deque(reports)
        self.labels = []

    def verify(self, path, label):
        self.labels.append(label)
        return self.reports.popleft()


class BitbucketStub:
    def __init__(self):
        self.existing = None
        self.created = []
        self.error = None

    def context(self, commits):
        return []

    def find_pr(self, branch, base):
        return self.existing

    def create_pr(self, branch, base, title, description):
        self.created.append((branch, base, title, description))
        if self.error:
            raise self.error
        return {"id": 42}


class ModelStub:
    def __init__(self):
        self.contexts = []

    def propose(self, context):
        self.contexts.append(context)
        return Proposal.model_validate(
            {
                "summary": "Fix arithmetic",
                "explanation": "Use addition to satisfy CPP-12.",
                "edits": [{"path": "src/add.cpp", "old": "a - b", "new": "a + b"}],
            }
        )


@pytest.fixture
def make_flow(tmp_path):
    service = {"url": "https://internal.invalid", "token_env": "UNUSED_TOKEN"}
    settings = Settings.model_validate(
        {
            "state_dir": tmp_path / "state",
            "teamcity": {**service, "build_types": ["Cpp_Tests"]},
            "bitbucket": {**service, "project": "CPP", "repo": "app"},
            "llm": {**service, "model": "qwen", "context_chars": 4000},
            "repository": {"path": tmp_path / "source"},
            "build": {"build": [["build"]], "test": ["tests", "{junit}"]},
        }
    )

    def make(reports=(), *, publish=True):
        flow = Workflow(
            settings,
            "test-run",
            SimpleNamespace(build_log=lambda _id: "math.add failed"),
            BitbucketStub(),
            None,
            ModelStub(),
            publish=publish,
        )
        flow.workspace = WorkspaceStub(tmp_path)
        flow.builder = BuilderStub(reports)
        return flow

    return make


def state_for(flow):
    return {
        "run_id": flow.run_id,
        "failure": failure().model_dump(),
        "head": flow.workspace.head(),
        "branch": flow.workspace.branch,
        "proposal": {
            "summary": "Fix arithmetic",
            "explanation": "Replace subtraction with addition.",
        },
    }


@pytest.mark.parametrize(
    "verification",
    [
        report(passed=["unrelated"]),
        report(passed=["unrelated"], skipped=["math.add"]),
        report(passed=["math.add"], test_ok=False),
        report(passed=["math.add"], build_ok=False),
    ],
)
def test_passing_exit_or_other_tests_cannot_hide_missing_original_test(verification):
    assert not validates_fix(verification, {"math.add"})


def test_baseline_rejects_an_unrelated_failure(make_flow):
    flow = make_flow([report(failed=["another.test"], test_ok=False)])
    result = flow.baseline(state_for(flow))
    assert result["status"] == "blocked"
    assert "not reproduced" in result["reason"]
    assert not flow.model.contexts


def test_graph_checks_original_test_after_final_rebase_before_publication(make_flow):
    flow = make_flow(
        [
            report(failed=["math.add"], test_ok=False),
            report(passed=["math.add", "other"]),
            report(passed=["other"], skipped=["math.add"]),
        ]
    )
    result = flow.run({"run_id": flow.run_id, "failure": failure().model_dump()})
    assert result["status"] == "blocked"
    assert result["reason"] == "Validation after final rebase failed"
    assert flow.builder.labels == ["baseline", "attempt-1", "final-rebased"]
    assert not flow.bitbucket.created
    assert not any(op[0] == "push" for op in flow.workspace.operations)


def test_graph_publishes_the_final_rebased_verified_head_once(make_flow):
    flow = make_flow(
        [
            report(failed=["math.add"], test_ok=False),
            report(passed=["math.add"]),
            report(passed=["math.add"]),
        ]
    )
    result = flow.run({"run_id": flow.run_id, "failure": failure().model_dump()})
    assert result["status"] == "published"
    assert result["head"] == "c" * 40
    assert flow.builder.labels == ["baseline", "attempt-1", "final-rebased"]
    assert flow.workspace.operations == [
        ("prepare", "a" * 40),
        ("edit", "a + b"),
        ("commit", "Fix arithmetic"),
        ("rebase",),
        ("push", "c" * 40),
    ]
    assert len(flow.bitbucket.created) == 1
    assert "`" + "c" * 40 + "`" in flow.bitbucket.created[0][3]
    assert "teamcity.example/build/101" in flow.bitbucket.created[0][3]
    assert "artifacts/before.png" in flow.bitbucket.created[0][3]
    assert (flow.directory / "fix.diff").read_text() == flow.workspace.committed_diff()
    assert json.loads((flow.directory / "publication.json").read_text())["status"] == "published"


def test_failed_repair_budget_cannot_publish_when_original_test_disappears(make_flow):
    flow = make_flow(
        [
            report(failed=["math.add"], test_ok=False),
            report(passed=["other"]),
            report(passed=["other"]),
        ]
    )
    result = flow.run({"run_id": flow.run_id, "failure": failure().model_dump()})
    assert result["status"] == "blocked"
    assert result["attempt"] == 2
    assert flow.builder.labels == ["baseline", "attempt-1", "attempt-2"]
    assert not flow.bitbucket.created
    assert not any(op[0] in {"commit", "push", "rebase"} for op in flow.workspace.operations)


def test_local_candidate_does_not_push_or_create_pr(make_flow):
    flow = make_flow(publish=False)
    flow.bitbucket.find_pr = lambda *_: pytest.fail("Local preparation must not query publication")
    assert flow.publish_pr(state_for(flow)) == {"status": "ready"}
    assert not flow.bitbucket.created
    assert not flow.workspace.operations


def test_existing_pr_reconciles_without_pushing_or_resubmitting(make_flow):
    flow = make_flow()
    flow.bitbucket.existing = {"id": 12}
    assert flow.publish_pr(state_for(flow)) == {"status": "published", "pr": {"id": 12}}
    assert not flow.workspace.operations
    assert not flow.bitbucket.created


def test_existing_pr_with_different_head_cannot_claim_verified_publication(make_flow):
    flow = make_flow()
    flow.bitbucket.existing = {"id": 12, "fromRef": {"latestCommit": "d" * 40}}
    with pytest.raises(RuntimeError, match="[Cc]ommit|[Hh]ead|[Ss][Hh][Aa]|[Vv]erif"):
        flow.publish_pr(state_for(flow))
    assert not flow.workspace.operations
    assert not flow.bitbucket.created


def test_publisher_rejects_unresolved_intent_when_remote_lookup_finds_nothing(make_flow):
    flow = make_flow()
    (flow.directory / "publication.json").write_text(
        json.dumps({"status": "intent", "branch": flow.workspace.branch, "head": "b" * 40})
    )
    with pytest.raises(RuntimeError, match="[Uu]nknown|[Uu]ncertain|[Ii]ntent|[Pp]ublication"):
        flow.publish_pr(state_for(flow))
    assert not flow.workspace.operations
    assert not flow.bitbucket.created


def test_uncertain_post_records_intent_and_run_returns_unknown(make_flow):
    flow = make_flow(
        [
            report(failed=["math.add"], test_ok=False),
            report(passed=["math.add"]),
            report(passed=["math.add"]),
        ]
    )
    flow.bitbucket.error = RuntimeError("connection lost after request")
    result = flow.run({"run_id": flow.run_id, "failure": failure().model_dump()})
    assert result["status"] == "publication_unknown"
    assert len(flow.bitbucket.created) == 1
    journal = json.loads((flow.directory / "publication.json").read_text())
    assert journal["status"] == "intent"
    assert journal["head"] == result["head"]


def test_created_pr_with_different_head_records_unknown_publication(make_flow):
    flow = make_flow(
        [
            report(failed=["math.add"], test_ok=False),
            report(passed=["math.add"]),
            report(passed=["math.add"]),
        ]
    )
    created = []

    def create_pr(*args):
        created.append(args)
        return {"id": 42, "fromRef": {"latestCommit": "d" * 40}}

    flow.bitbucket.create_pr = create_pr
    result = flow.run({"run_id": flow.run_id, "failure": failure().model_dump()})
    assert result["status"] == "publication_unknown"
    assert len(created) == 1
    journal = json.loads((flow.directory / "publication.json").read_text())
    assert journal["status"] == "intent"
    assert journal["head"] == "c" * 40


@pytest.mark.parametrize("dirty,head", [(True, "b" * 40), (False, "d" * 40)])
def test_resuming_changed_candidate_stops_before_rebase_or_push(make_flow, dirty, head):
    flow = make_flow()
    initial = {**state_for(flow), "resume_ready": True}
    flow.workspace.clean = not dirty
    flow.workspace.current_head = head
    with pytest.raises(RuntimeError, match="changed since verification"):
        flow.finalize(initial)
    assert not flow.workspace.operations
    assert not flow.builder.labels


def test_context_budget_pruning_preserves_durable_pr_and_jira_evidence(make_flow):
    flow = make_flow()
    context = {
        "pull_requests": [{"description": "x" * 6000}],
        "issues": [{"key": "CPP-12", "url": "https://jira.example/browse/CPP-12"}],
        "ci_log": "test failure details",
    }
    initial = {**state_for(flow), "context": context}
    original = copy.deepcopy(context)
    assert flow.repair(initial)["status"] == "working"
    assert initial["context"] == original
    assert "pull_requests" not in flow.model.contexts[0]["context"]


def test_description_retains_jira_and_related_pr_links(make_flow):
    flow = make_flow()
    state = state_for(flow)
    state["context"] = {
        "issues": [{"key": "CPP-12", "url": "https://jira.example/browse/CPP-12"}],
        "pull_requests": [{"id": 9, "links": {"self": [{"href": "https://git.example/pr/9"}]}}],
    }
    body = pr_description(state)
    assert "https://jira.example/browse/CPP-12" in body
    assert "https://git.example/pr/9" in body
    assert "https://teamcity.example/build/101" in body
