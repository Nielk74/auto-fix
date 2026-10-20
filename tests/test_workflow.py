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

    def context(self, changes, max_chars, test_names=None, signals=""):
        self.context_signals = signals
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
        return {
            "id": 42,
            "fromRef": {"id": "refs/heads/" + branch, "latestCommit": "c" * 40},
            "toRef": {"id": "refs/heads/" + base},
        }


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


@pytest.mark.parametrize(
    "second",
    [
        report(failed=["math.add"], passed=["new.pass"], test_ok=False),
        report(failed=["math.add", "new.failure"], test_ok=False),
        report(failed=["math.add"], skipped=["changed.skip"], test_ok=False),
    ],
)
def test_repeated_baseline_requires_all_outcome_identities_to_stay_the_same(make_flow, second):
    flow = make_flow([report(failed=["math.add"], test_ok=False), second])
    flow.settings.baseline_repetitions = 2
    result = flow.baseline(state_for(flow))
    assert result["status"] == "blocked" and "unstable" in result["reason"]
    assert len(result["baseline_checks"]) == 2
    saved = json.loads((flow.directory / "baseline-checks.json").read_text())
    assert saved["requested"] == saved["observed"] == 2
    assert not flow.model.contexts


def test_baseline_invalid_evidence_cannot_be_inferred_from_test_ok_alone(make_flow):
    baseline = report(failed=["math.add"], test_ok=False)
    baseline.evidence_valid = False
    flow = make_flow([baseline])
    result = flow.baseline(state_for(flow))
    assert result["status"] == "blocked" and "evidence" in result["reason"]
    assert result["baseline_checks"][0]["evidence_valid"] is False
    assert not flow.model.contexts


def test_invalid_evidence_never_satisfies_candidate_validation():
    result = report(passed=["math.add"])
    result.evidence_valid = False
    assert not validates_fix(result, {"math.add"})


def test_first_repair_uses_assertions_from_the_latest_baseline_repetition(make_flow):
    flow = make_flow()
    flow.settings.structured_diagnostics = True
    checks = []
    for number in (1, 2):
        directory = flow.directory / "evidence" / f"baseline-{number}"
        directory.mkdir(parents=True)
        junit = directory / "junit.xml"
        junit.write_text(
            '<testsuite><testcase classname="math" name="add">'
            f"<failure>current baseline observation {number}</failure>"
            "</testcase></testsuite>"
        )
        check = report(failed=["math.add"], test_ok=False).model_dump()
        check["logs"] = [str(junit)]
        checks.append(check)
    state = {**state_for(flow), "baseline": checks[0], "baseline_checks": checks}
    context = flow._model_context(state, 1)
    assertions = json.dumps(context["latest_validation"]["assertions"])
    assert "current baseline observation 2" in assertions
    assert "current baseline observation 1" not in assertions


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


@pytest.mark.parametrize("missing_at", ["attempt", "final"])
def test_previously_passing_test_cannot_disappear_after_repair(make_flow, missing_at):
    complete = report(passed=["math.add", "math.multiply"])
    incomplete = report(passed=["math.add"])
    flow = make_flow(
        [
            report(passed=["math.multiply"], failed=["math.add"], test_ok=False),
            incomplete if missing_at == "attempt" else complete,
            incomplete,
        ]
    )
    result = flow.run({"run_id": flow.run_id, "failure": failure().model_dump()})
    assert result["status"] == "blocked"
    assert not flow.bitbucket.created
    assert not any(operation[0] == "push" for operation in flow.workspace.operations)


def test_existing_pr_reconciles_without_pushing_or_resubmitting(make_flow):
    flow = make_flow()
    flow.bitbucket.existing = {
        "id": 12,
        "fromRef": {"id": "refs/heads/" + flow.workspace.branch, "latestCommit": "b" * 40},
        "toRef": {"id": "refs/heads/master"},
    }
    assert flow.publish_pr(state_for(flow)) == {
        "status": "published",
        "pr": flow.bitbucket.existing,
    }
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


@pytest.mark.parametrize("observed", [0, 1])
def test_resuming_old_candidate_cannot_bypass_an_increased_baseline_policy(make_flow, observed):
    flow = make_flow()
    flow.settings.baseline_repetitions = 2
    initial = {
        **state_for(flow),
        "resume_ready": True,
        "baseline_checks": [report(failed=["math.add"], test_ok=False).model_dump()] * observed,
    }
    result = flow.finalize(initial)
    assert result["status"] == "blocked" and "fewer baseline checks" in result["reason"]
    assert not flow.workspace.operations and not flow.builder.labels
    assert not flow.bitbucket.created


def test_resuming_candidate_with_sufficient_baseline_evidence_still_reverifies(make_flow):
    flow = make_flow([report(passed=["math.add"])])
    flow.settings.baseline_repetitions = 2
    baseline = report(failed=["math.add"], test_ok=False).model_dump()
    initial = {
        **state_for(flow),
        "resume_ready": True,
        "baseline": baseline,
        "baseline_checks": [baseline, baseline],
    }
    result = flow.finalize(initial)
    assert result["status"] == "ready"
    assert flow.builder.labels == ["final-rebased"]
    assert flow.workspace.operations == [("rebase",)]


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


def test_retrieval_signals_exclude_successful_ninja_and_native_test_progress(make_flow):
    flow = make_flow()
    state = {
        **state_for(flow),
        "feedback": (
            "[1/147] Building CXX object unrelated/noisy_backend.cc.o\n"
            "[2/147] Linking CXX executable another_passing_test\n"
            "[ RUN      ] UnrelatedTest.Works\n"
            "[       OK ] UnrelatedTest.Works (0 ms)\n"
            "[100%] Built target unrelated_generated_code\n"
            "[  FAILED  ] math.add\n"
            "src/math.cpp:71: error: no matching AddNumbers overload\n"
        ),
    }
    assert flow.repair(state)["status"] == "working"
    assert "noisy_backend" not in flow.workspace.context_signals
    assert "another_passing" not in flow.workspace.context_signals
    assert "UnrelatedTest" not in flow.workspace.context_signals
    assert "unrelated_generated" not in flow.workspace.context_signals
    assert "math.add" in flow.workspace.context_signals
    assert "AddNumbers" in flow.workspace.context_signals


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


def inspection(*, ready=True, queries=()):
    from auto_fix.models import Investigation

    return Investigation(
        summary="Inspect arithmetic dispatch",
        hypotheses=["The selected operation may not match the caller contract"],
        queries=list(queries),
        reads=[],
        ready=ready,
    )


class InvestigatingModel(ModelStub):
    def __init__(self, requests):
        super().__init__()
        self.requests = deque(requests)
        self.inspection_contexts = []
        self.order = []

    def inspect(self, context):
        self.order.append("inspect")
        self.inspection_contexts.append(copy.deepcopy(context))
        return self.requests.popleft()

    def propose(self, context):
        self.order.append("repair")
        return super().propose(context)


def test_investigation_runs_before_repairs_and_carries_observed_evidence(make_flow, monkeypatch):
    flow = make_flow(
        [
            report(failed=["math.add"], test_ok=False),
            report(failed=["math.add"], test_ok=False),
            report(passed=["math.add"]),
            report(passed=["math.add"]),
        ]
    )
    flow.settings.llm.context_chars = 60000
    flow.settings.max_inspections = 2
    flow.model = InvestigatingModel([inspection(queries=["add"]), inspection()])
    observed = []

    def gather(workspace, request, max_chars):
        observed.append((workspace, request.queries, max_chars))
        return {
            "queries": [],
            "excerpts": [
                {
                    "path": "include/add.h",
                    "start_line": 1,
                    "end_line": 1,
                    "content": "int add(int a, int b);",
                }
            ],
            "errors": [],
        }

    monkeypatch.setattr("auto_fix.workflow.gather_evidence", gather)
    result = flow.run({"run_id": flow.run_id, "failure": failure().model_dump()})
    assert result["status"] == "published"
    assert flow.model.order == ["inspect", "repair", "inspect", "repair"]
    assert result["inspections"] == 2
    assert result["attempt"] == 2
    assert observed == [(flow.workspace, ["add"], 10000)]
    evidence = flow.model.contexts[0]["investigation"]["evidence"]
    assert evidence[0]["excerpts"][0]["content"] == "int add(int a, int b);"
    assert (flow.directory / "inspection-evidence-1.json").exists()
    assert flow.builder.labels == ["baseline", "attempt-1", "attempt-2", "final-rebased"]


def test_investigation_budget_is_global_across_repair_attempts(make_flow, monkeypatch):
    flow = make_flow(
        [
            report(failed=["math.add"], test_ok=False),
            report(failed=["math.add"], test_ok=False),
            report(passed=["math.add"]),
            report(passed=["math.add"]),
        ]
    )
    flow.settings.max_inspections = 3
    flow.model = InvestigatingModel([inspection(ready=False, queries=["add"])] * 3)
    monkeypatch.setattr(
        "auto_fix.workflow.gather_evidence",
        lambda *_args, **_kwargs: {"queries": [], "excerpts": [], "errors": []},
    )
    result = flow.run({"run_id": flow.run_id, "failure": failure().model_dump()})
    assert result["status"] == "published"
    assert flow.model.order == ["inspect", "inspect", "inspect", "repair", "repair"]
    assert result["inspections"] == 3
    assert not flow.model.requests
    assert not (flow.directory / "investigation-4.json").exists()


def test_inspection_round_limit_reserves_evidence_calls_for_failed_repair(make_flow, monkeypatch):
    flow = make_flow(
        [
            report(failed=["math.add"], test_ok=False),
            report(failed=["math.add"], test_ok=False),
            report(passed=["math.add"]),
            report(passed=["math.add"]),
        ]
    )
    flow.settings.max_inspections = 4
    flow.settings.inspections_per_attempt = 2
    flow.model = InvestigatingModel([inspection(ready=False, queries=["add"])] * 4)
    monkeypatch.setattr(
        "auto_fix.workflow.gather_evidence",
        lambda *_args, **_kwargs: {"queries": [], "excerpts": [], "errors": []},
    )
    result = flow.run({"run_id": flow.run_id, "failure": failure().model_dump()})
    assert result["status"] == "published"
    assert flow.model.order == ["inspect", "inspect", "repair", "inspect", "inspect", "repair"]
    assert result["inspections"] == 4
    assert result["inspection_round"] == 2
    assert result["round_inspections"] == 2
    assert flow.model.inspection_contexts[2]["latest_validation"]["failed"] == ["math.add"]


def test_applied_edits_invalidate_stale_source_evidence_for_retry(make_flow, monkeypatch):
    flow = make_flow()
    flow.settings.llm.context_chars = 60000
    flow.settings.structured_diagnostics = True
    observed = []

    def invalidate(batches, changed_paths, max_chars):
        observed.append((batches, changed_paths, max_chars))
        return {"queries": [], "excerpts": [], "errors": []}

    monkeypatch.setattr("auto_fix.workflow.invalidate_evidence", invalidate)
    stale = [{"excerpts": [{"path": "src/add.cpp", "content": "return a - b;"}]}]
    state = {**state_for(flow), "investigation": {"evidence": stale}}
    result = flow.repair(state)
    assert result["status"] == "working"
    assert observed == [(stale, {"src/add.cpp"}, 18000)]
    assert not result["investigation"]["evidence"][0]["excerpts"]


def test_retry_packet_includes_new_native_assertion_instead_of_only_original_failure(make_flow):
    flow = make_flow()
    flow.settings.structured_diagnostics = True
    evidence = flow.directory / "evidence/latest"
    evidence.mkdir(parents=True)
    junit = evidence / "junit.xml"
    junit.write_text(
        '<testsuite><testcase classname="Boundary" name="FiniteMinimum">'
        '<failure message="preserve finite exact multiple">'
        "input d=unit=Seconds(INT64_MIN); expected finite d; actual -inf"
        "</failure></testcase></testsuite>"
    )
    latest = report(failed=["Boundary.FiniteMinimum"], test_ok=False).model_dump()
    latest["logs"] = [str(junit)]
    state = {**state_for(flow), "verification": latest, "feedback": "[       OK ] Other\n" * 9000}
    packet = flow._model_context(state, 2)
    assertions = packet["latest_validation"]["assertions"]
    serialized = json.dumps(assertions)
    assert "Seconds(INT64_MIN)" in serialized
    assert "expected finite d" in serialized
    assert "actual -inf" in serialized
    assert "Boundary.FiniteMinimum" in serialized


def test_no_investigation_or_repair_when_baseline_cannot_reproduce_original_failure(make_flow):
    flow = make_flow([report(failed=["unrelated"], test_ok=False)])
    flow.settings.max_inspections = 3
    flow.model = InvestigatingModel([inspection()])
    result = flow.run({"run_id": flow.run_id, "failure": failure().model_dump()})
    assert result["status"] == "blocked"
    assert not flow.model.order
    assert not flow.bitbucket.created


def test_sampling_model_evidence_never_weakens_complete_original_failure_validator(make_flow):
    original = failure()
    original.tests = [
        FailedTest(
            id=str(number), name=f"Suite{number % 4}.Test{number}", details="native assertion"
        )
        for number in range(40)
    ]
    all_names = [test.name for test in original.tests]
    flow = make_flow(
        [
            report(failed=all_names, test_ok=False),
            report(passed=all_names[:12]),
            report(passed=all_names[:12]),
        ]
    )
    flow.settings.max_inspections = 1
    flow.model = InvestigatingModel([inspection()])
    result = flow.run({"run_id": flow.run_id, "failure": original.model_dump()})
    assert result["status"] == "blocked"
    assert len(result["failure"]["tests"]) == 40
    assert {test["name"] for test in result["failure"]["tests"]} == set(all_names)
    for context in [*flow.model.inspection_contexts, *flow.model.contexts]:
        assert len(context["failure"]["tests"]) == 12
        assert context["failure_groups"]["total_failed_tests"] == 40
    assert flow.model.order == ["inspect", "repair", "repair"]
    assert not flow.bitbucket.created
    assert not any(operation[0] == "push" for operation in flow.workspace.operations)
