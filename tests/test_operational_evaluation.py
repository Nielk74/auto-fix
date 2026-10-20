"""Mechanics tests only: test doubles here are not live model evaluation evidence."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from auto_fix import mock_services as mocks
from auto_fix.build import parse_junit
from auto_fix.config import BitbucketConfig
from auto_fix.evaluation import _git, _source
from auto_fix.integrations import Bitbucket, IntegrationError
from auto_fix.models import FailedTest, Failure, Proposal, Verification
from auto_fix.models import TestReport as NativeTestReport
from auto_fix.operational_evaluation import (
    MODEL,
    SCENARIOS,
    _advance_master,
    _APIFaults,
    _ModelFaults,
    _native_validated,
    _report_adapter,
    _run_scenario,
    _settings,
    judge_outcome,
    omit_report_identity,
    run_operational_evaluation,
)


def scenario(name):
    return next(item for item in SCENARIOS if item.id == name)


def test_scenarios_separate_repairs_reconciliation_and_model_free_safe_stops():
    assert len(SCENARIOS) >= 8
    assert len({item.id for item in SCENARIOS}) == len(SCENARIOS)
    assert {item.expected_outcome for item in SCENARIOS} == {"repair", "safe_stop", "reconciled"}
    assert {item.id for item in SCENARIOS if not item.needs_model} == {
        "stale_teamcity",
        "missing_original_baseline",
    }


def services_and_client(monkeypatch, name):
    monkeypatch.setenv(mocks.TOKEN_ENV, mocks.TOKEN)
    failure = Failure(
        build_id="19417",
        build_type="CppTests",
        build_url=mocks.TC_URL + "/build/19417",
        revision="a" * 40,
        tests=[FailedTest(id="1", name="AsciiStrTo.Lower")],
    )
    services = mocks.ScenarioServices(
        failure,
        now=datetime.now(ZoneInfo("Europe/Paris")),
        latest_commit=lambda _: "b" * 40,
    )
    faults = []
    transport = _APIFaults(services, scenario(name), faults)
    client = httpx.Client(transport=httpx.MockTransport(transport.handle))
    bb = Bitbucket(
        BitbucketConfig(
            url=mocks.BB_URL,
            token_env=mocks.TOKEN_ENV,
            project=mocks.PROJECT,
            repo=mocks.REPO,
        ),
        client,
    )
    return services, client, bb, faults


def test_accepted_post_timeout_keeps_receipt_and_get_reconciles_without_duplicate(monkeypatch):
    services, client, bb, faults = services_and_client(monkeypatch, "pr_creation_timeout")
    with client:
        with pytest.raises(IntegrationError, match="timeout|Timeout|failed"):
            bb.create_pr("auto-fix/example", "master", "Repair", "Native evidence")
        assert len(services.created_prs) == 1
        existing = bb.find_pr("auto-fix/example", "master")
    assert existing["id"] == services.created_prs[0]["id"]
    assert existing["fromRef"]["latestCommit"] == "b" * 40
    assert [request["method"] for request in services.requests].count("POST") == 1
    assert faults == [{"action": "accepted_pr_response_timeout", "created_pr_id": existing["id"]}]


def test_bad_pr_head_fault_preserves_real_push_head_in_fault_evidence(monkeypatch):
    services, client, bb, faults = services_and_client(monkeypatch, "incorrect_pr_head")
    with client:
        receipt = bb.create_pr("auto-fix/example", "master", "Repair", "Native evidence")
    assert receipt["fromRef"]["latestCommit"] == "0" * 40
    assert services.created_prs[0]["fromRef"]["latestCommit"] == "0" * 40
    assert faults[0]["pushed_head"] == "b" * 40
    assert len(services.created_prs) == 1


@pytest.mark.parametrize("reason", ["", "PR commit head is absent or differs from the candidate"])
def test_wrong_head_stop_is_judged_from_receipts_instead_of_error_wording(reason):
    checks = judge_outcome(
        scenario("incorrect_pr_head"),
        state={"status": "publication_unknown", "head": "b" * 40, "reason": reason},
        native_validated=True,
        protected_unchanged=True,
        remote_head="b" * 40,
        created_prs=[{"id": 19, "fromRef": {"latestCommit": "0" * 40}}],
        post_count=1,
        calls=[{"model": MODEL, "kind": "repair", "transport": "codex-cli", "returncode": 0}],
        faults=[{"action": "incorrect_pr_head"}],
    )
    assert all(checks.values())


class MechanicsModel:
    """Count explicit test-double invocations; never represents inference quality."""

    def __init__(self):
        self.calls = []

    def propose(self, context):
        self.calls.append(
            {
                "model": MODEL,
                "kind": "repair",
                "transport": "codex-cli",
                "returncode": 0,
                "test_double": True,
            }
        )
        return Proposal.model_validate(
            {
                "summary": "Mechanics fixture",
                "explanation": "No model evaluation is occurring.",
                "edits": [{"path": "src/value.cc", "old": "before", "new": "after"}],
            }
        )

    def close(self):
        pass


def test_lost_response_is_not_reused_and_next_attempt_calls_model_again():
    inner, faults = MechanicsModel(), []
    model = _ModelFaults(inner, scenario("lost_model_response"), lambda: {}, faults)
    with pytest.raises(RuntimeError, match="completed live model call"):
        model.propose({})
    proposal = model.propose({})
    assert proposal.edits[0].new == "after"
    assert len(inner.calls) == 2
    assert faults == [{"action": "discard_completed_live_response", "call_number": 1}]


def test_master_advance_happens_once_after_proposal_without_changing_it():
    inner, faults, advances = MechanicsModel(), [], []

    def advance():
        advances.append(True)
        return {"action": "master_advanced", "advanced_master": "c" * 40}

    model = _ModelFaults(inner, scenario("master_advanced"), advance, faults)
    first = model.propose({})
    second = model.propose({})
    assert first == second
    assert advances == [True]
    assert len(faults) == 1


@pytest.fixture
def git_control(tmp_path):
    """Small real Git fixture for fault mechanics; no repair-model evaluation."""
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    subprocess.run(["git", "init", "-b", "master", str(upstream)], check=True, capture_output=True)
    _git(upstream, "config", "user.name", "Mechanics Test")
    _git(upstream, "config", "user.email", "mechanics@example.invalid")
    path = upstream / "absl/strings"
    path.mkdir(parents=True)
    before = (
        "void AsciiStrToLower(std::string* s) {\n"
        "  return ascii_internal::AsciiStrCaseFold<false>(s->data(), s->data(), s->size());\n"
        "}\n"
    )
    after = before.replace("<false>", "<true>")
    (path / "ascii.cc").write_text(before)
    (path / "str_cat.cc").write_text("// unrelated source\n")
    (upstream / ".gitignore").write_text(".auto-fix-build/\n")
    _git(upstream, "add", ".")
    _git(upstream, "commit", "-m", "Clean control")
    case = {
        "mutations": [{"path": "absl/strings/ascii.cc", "before": before, "after": after}],
        "exposure": "indirect",
        "changed_files": ["absl/strings/str_cat.cc"],
        "context": {
            "commit_message": "CORE-123 Inject control",
            "pr_title": "CORE-123 Diagnostics",
        },
    }
    current = tmp_path / "scenario"
    current.mkdir()
    source, _ = _source(current, upstream, case)
    return current, source, case


@pytest.mark.parametrize("mode", ["master_advanced", "final_rebase_conflict", "stale_teamcity"])
def test_concurrent_faults_push_actual_master_commits_and_preserve_tests(git_control, mode):
    current, source, case = git_control
    old = _git(source, "rev-parse", "HEAD")
    fault = _advance_master(current, case, mode)
    remote = _git(current, "--git-dir", str(current / "remote.git"), "rev-parse", "master")
    assert fault["previous_master"] == old
    assert remote == fault["advanced_master"] != old
    names = _git(source, "diff", "--name-only", old, "HEAD").splitlines()
    assert all("_test" not in name for name in names)
    text = (source / "absl/strings/ascii.cc").read_text()
    if mode == "stale_teamcity":
        assert case["mutations"][0]["before"] in text
    elif mode == "final_rebase_conflict":
        assert "<true>" in text and "Concurrent owner annotation" in text


@pytest.mark.parametrize("mode", ["master_advanced", "final_rebase_conflict"])
def test_concurrent_commit_rebases_or_conflicts_at_the_real_git_boundary(git_control, mode):
    current, source, case = git_control
    candidate = current / "candidate"
    _git(source, "worktree", "add", "-b", "mechanics-repair", str(candidate), "HEAD")
    mutation = case["mutations"][0]
    path = candidate / mutation["path"]
    path.write_text(path.read_text().replace(mutation["after"], mutation["before"], 1))
    _git(candidate, "commit", "-am", "Mechanics candidate")
    advance = _advance_master(current, case, mode)
    _git(candidate, "fetch", "origin", "master")
    result = subprocess.run(
        ["git", "-C", str(candidate), "rebase", "origin/master"],
        capture_output=True,
        text=True,
        check=False,
    )
    if mode == "final_rebase_conflict":
        assert result.returncode != 0
        assert "CONFLICT" in result.stdout
        _git(candidate, "rebase", "--abort")
    else:
        assert result.returncode == 0
        assert _git(candidate, "rev-parse", "HEAD^") == advance["advanced_master"]


REPORT = (
    b'<testsuites><testsuite name="Suite" tests="2">'
    b'<testcase classname="Suite" name="Original"><failure>real failure</failure></testcase>'
    b'<testcase classname="Suite" name="Other"/></testsuite></testsuites>'
)


def test_report_omission_preserves_unfiltered_evidence_and_other_outcomes(tmp_path):
    junit = tmp_path / "junit.xml"
    junit.write_bytes(REPORT)
    assert omit_report_identity(junit, "Suite.Original") == 1
    assert junit.with_suffix(".unfiltered.xml").read_bytes() == REPORT
    assert b'name="Other"' in junit.read_bytes()
    assert b'name="Original"' not in junit.read_bytes()
    assert json.loads(junit.with_suffix(".fault.json").read_text())["name"] == "Suite.Original"
    with pytest.raises(ValueError, match="exactly one"):
        omit_report_identity(junit, "Suite.Missing")
    assert junit.with_suffix(".unfiltered.xml").read_bytes() == REPORT


def test_report_adapter_fault_is_limited_to_the_intended_native_stage(tmp_path):
    # This Python command represents report transport in a mechanics test only.
    producer = tmp_path / "producer.py"
    producer.write_text(
        "from pathlib import Path\nimport sys\nPath(sys.argv[1]).write_bytes("
        + repr(REPORT)
        + ")\nsys.exit(1)\n"
    )
    for stage in ("baseline", "final-rebased"):
        directory = tmp_path / (stage + "-abc123")
        directory.mkdir()
        junit = directory / "junit.xml"
        code = _report_adapter(
            [
                "--omit-stage",
                "final-rebased",
                "--identity",
                "Suite.Original",
                "--junit",
                str(junit),
                "--",
                sys.executable,
                str(producer),
                str(junit),
            ]
        )
        assert code == 1
        assert (b'name="Original"' in junit.read_bytes()) == (stage == "baseline")
        assert junit.with_suffix(".unfiltered.xml").exists() == (stage == "final-rebased")


def judge_inputs():
    head = "b" * 40
    branch = "auto-fix/mechanics"
    pr = {
        "id": 901,
        "fromRef": {"id": "refs/heads/" + branch, "latestCommit": head},
        "toRef": {"id": "refs/heads/master"},
    }
    return {
        "state": {"status": "published", "head": head, "branch": branch, "pr": pr},
        "native_validated": True,
        "protected_unchanged": True,
        "remote_head": head,
        "created_prs": [pr],
        "post_count": 1,
        "calls": [{"model": MODEL, "kind": "repair", "transport": "codex-cli", "returncode": 0}],
        "faults": [{"action": "master_advanced"}],
        "advanced_is_ancestor": True,
    }


@pytest.mark.parametrize(
    "corruption", ["wrong_head", "test_changed", "no_native", "other_model", "not_rebased"]
)
def test_published_label_cannot_mask_bad_receipts_or_native_validation(corruption):
    arguments = copy.deepcopy(judge_inputs())
    if corruption == "wrong_head":
        arguments["created_prs"][0]["fromRef"]["latestCommit"] = "c" * 40
    elif corruption == "test_changed":
        arguments["protected_unchanged"] = False
    elif corruption == "no_native":
        arguments["native_validated"] = False
    elif corruption == "other_model":
        arguments["calls"][0]["model"] = "some-other-model"
    else:
        arguments["advanced_is_ancestor"] = False
    assert not all(judge_outcome(scenario("master_advanced"), **arguments).values())
    assert all(judge_outcome(scenario("master_advanced"), **judge_inputs()).values())


def test_expected_safe_stop_passes_without_claiming_a_repair_or_calling_model(tmp_path):
    junit = tmp_path / "junit.xml"
    junit.write_bytes(REPORT.replace(b"<failure>real failure</failure>", b""))
    arguments = {
        **judge_inputs(),
        "state": {
            "status": "blocked",
            "reason": "TC failures were not reproduced",
            "failure": {"tests": [{"name": "Suite.Original"}]},
            "baseline": Verification(
                build_ok=True,
                test_ok=True,
                evidence_valid=True,
                report=parse_junit(junit),
                logs=[str(junit)],
            ).model_dump(),
        },
        "native_validated": False,
        "remote_head": None,
        "created_prs": [],
        "post_count": 0,
        "calls": [],
        "faults": [{"action": "stale_teamcity"}],
    }
    assert all(judge_outcome(scenario("stale_teamcity"), **arguments).values())
    arguments["calls"] = [{"model": MODEL, "kind": "repair"}]
    assert not judge_outcome(scenario("stale_teamcity"), **arguments)["no_model_calls"]


def omitted_baseline_arguments(tmp_path):
    junit = tmp_path / "junit.xml"
    junit.write_bytes(REPORT)
    omit_report_identity(junit, "Suite.Original")
    return {
        **judge_inputs(),
        "state": {
            "status": "blocked",
            "reason": "Baseline test evidence is invalid or incomplete",
            "failure": {"tests": [{"name": "Suite.Original"}]},
            "baseline": Verification(
                build_ok=True,
                test_ok=False,
                evidence_valid=False,
                report=parse_junit(junit),
                logs=[str(junit)],
            ).model_dump(),
        },
        "native_validated": False,
        "remote_head": None,
        "created_prs": [],
        "post_count": 0,
        "calls": [],
        "faults": [{"action": "omit_original_identity", "name": "Suite.Original"}],
    }


def test_missing_baseline_assertion_is_a_safe_stop_before_model_inference(tmp_path):
    arguments = omitted_baseline_arguments(tmp_path)
    assert all(judge_outcome(scenario("missing_original_baseline"), **arguments).values())
    assert not judge_outcome(scenario("stale_teamcity"), **arguments)["reproduction_gate_stopped"]


@pytest.mark.parametrize(
    "corruption",
    [
        "missing_xml",
        "malformed_xml",
        "no_native_original",
        "valid_flag",
        "unrelated_build_failure",
        "claimed_identity_differs",
    ],
)
def test_missing_baseline_grader_requires_actual_omitted_native_assertion(tmp_path, corruption):
    arguments = omitted_baseline_arguments(tmp_path)
    baseline = arguments["state"]["baseline"]
    junit = tmp_path / "junit.xml"
    if corruption == "missing_xml":
        junit.unlink()
    elif corruption == "malformed_xml":
        junit.write_bytes(b"<testsuite>")
    elif corruption == "no_native_original":
        junit.with_suffix(".unfiltered.xml").write_bytes(junit.read_bytes())
    elif corruption == "valid_flag":
        baseline["evidence_valid"] = True
    elif corruption == "unrelated_build_failure":
        baseline["build_ok"] = False
    else:
        baseline["report"]["passed"] = ["Suite.Invented"]
    assert not judge_outcome(scenario("missing_original_baseline"), **arguments)[
        "reproduction_gate_stopped"
    ]


@pytest.mark.parametrize("name", ["stale_teamcity", "missing_original_baseline"])
def test_baseline_stop_reason_without_native_evidence_does_not_pass_grader(name):
    arguments = {
        **judge_inputs(),
        "state": {
            "status": "blocked",
            "reason": "Baseline test evidence is invalid or incomplete; not reproduced",
        },
        "calls": [],
        "remote_head": None,
        "created_prs": [],
        "post_count": 0,
        "faults": [{"action": "stale_teamcity"}, {"action": "omit_original_identity"}],
    }
    assert not judge_outcome(scenario(name), **arguments)["reproduction_gate_stopped"]


def test_native_gate_reads_actual_report_instead_of_claimed_counts(tmp_path):
    report = tmp_path / "junit.xml"
    report.write_text('<testsuite><testcase classname="Suite" name="Other"/></testsuite>')
    state = {
        "verification": {
            "build_ok": True,
            "test_ok": True,
            "logs": [str(report)],
            "report": {"passed": ["Suite.Original"]},
        }
    }
    assert not _native_validated(state, {"Suite.Original"})
    report.write_text('<testsuite><testcase classname="Suite" name="Original"/></testsuite>')
    assert _native_validated(state, {"Suite.Original"})


@pytest.mark.parametrize("selected", [[], ["unknown-scenario"]])
def test_invalid_selection_stops_before_cloning_or_calling_a_model(tmp_path, selected):
    with pytest.raises(ValueError, match="scenario selection"):
        run_operational_evaluation(tmp_path / "output", selected=selected)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("limit", [0, 7, True, "2"])
def test_invalid_inspection_round_limit_fails_before_native_or_model_work(tmp_path, limit):
    with pytest.raises(ValueError, match="inspections_per_attempt"):
        run_operational_evaluation(tmp_path / "output", inspections_per_attempt=limit)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize(
    "configured,expected",
    [
        ({}, (6, 60000, False, 1)),
        (
            {
                "inspections_per_attempt": 2,
                "context_chars": 160000,
                "definition_reads": True,
                "baseline_repetitions": 3,
            },
            (2, 160000, True, 3),
        ),
    ],
)
def test_operational_policy_reaches_scenarios_and_evidence_manifest(
    tmp_path, monkeypatch, configured, expected
):
    from auto_fix import operational_evaluation as operations

    observed = []
    monkeypatch.setattr(operations, "_upstream", lambda *_args: tmp_path / "unused-cache")

    def run_scenario(_directory, scenario, *_args, **kwargs):
        observed.append(kwargs)
        return {
            "scenario": scenario.id,
            "operational_pass": True,
            "repair_completed": False,
            "status": "blocked",
        }

    monkeypatch.setattr(operations, "_run_scenario", run_scenario)
    directory = tmp_path / "output"
    assert (
        run_operational_evaluation(
            directory, max_inspections=4, selected=["stale_teamcity"], **configured
        )
        == 0
    )
    assert observed[0]["inspections_per_attempt"] == expected[0]
    assert observed[0]["max_inspections"] == 4
    assert observed[0]["context_chars"] == expected[1]
    assert observed[0]["definition_reads"] is expected[2]
    assert observed[0]["baseline_repetitions"] == expected[3]
    manifest = json.loads((directory / "manifest.json").read_text())
    summary = json.loads((directory / "summary.json").read_text())
    assert manifest["inspections_per_attempt"] == summary["inspections_per_attempt"] == expected[0]
    assert manifest["max_inspections"] == summary["max_inspections"] == 4
    assert manifest["context_chars"] == summary["context_chars"] == expected[1]
    assert manifest["definition_reads"] is summary["definition_reads"] is expected[2]
    assert manifest["baseline_repetitions"] == summary["baseline_repetitions"] == expected[3]
    assert manifest["max_attempts"] == 3, "Preserve the separate operational fault budget"
    assert "validation_context.py" in manifest["source_sha256"]
    assert (directory / "implementation/validation_context.py").is_file()


@pytest.mark.parametrize("evidence_valid", [True, False])
def test_scenario_passes_only_trusted_preflight_evidence_into_actual_settings(
    git_control, tmp_path, monkeypatch, evidence_valid
):
    from auto_fix import operational_evaluation as operations

    _current, source, case = git_control
    junit = tmp_path / "synthetic-preflight" / "junit.xml"
    junit.parent.mkdir()
    junit.write_text(
        '<testsuite><testcase classname="AsciiStrTo" name="Lower">'
        "<failure>Structural fixture only</failure></testcase></testsuite>"
    )
    build = {"build": [["unused-native-command"]], "test": ["unused-runner", "{junit}"]}

    class Preflight:
        def __init__(self, *_args):
            pass

        def verify(self, *_args):
            return Verification(
                build_ok=True,
                test_ok=False,
                evidence_valid=evidence_valid,
                report=NativeTestReport(failed=["AsciiStrTo.Lower"]),
                logs=[str(junit)] if evidence_valid else [],
            )

    class ObservedSettings(Exception):
        pass

    def settings(
        current,
        source,
        build,
        prompt,
        inspections,
        inspections_per_attempt,
        context_chars,
        definition_reads,
        baseline_repetitions,
    ):
        actual = _settings(
            current,
            source,
            build,
            prompt,
            inspections,
            inspections_per_attempt,
            context_chars,
            definition_reads,
            baseline_repetitions,
        )
        assert actual.max_inspections == 4 and actual.inspections_per_attempt == 2
        assert actual.llm.context_chars == 160000
        assert actual.repository.definition_reads is True
        assert actual.baseline_repetitions == 3
        default = _settings(current, source, build, prompt, inspections)
        assert default.inspections_per_attempt == 6
        assert default.llm.context_chars == 60000
        assert default.repository.definition_reads is False
        assert default.baseline_repetitions == 1
        raise ObservedSettings

    monkeypatch.setattr(operations, "_source", lambda *_args: (source, []))
    monkeypatch.setattr(operations, "_build_config", lambda *_args: build)
    monkeypatch.setattr(operations, "Builder", Preflight)
    monkeypatch.setattr(operations, "_settings", settings)
    monkeypatch.setattr(
        operations,
        "CodexRepairModel",
        lambda *_args, **_kwargs: pytest.fail("No live models in mechanics tests"),
    )
    expected = ObservedSettings if evidence_valid else RuntimeError
    message = None if evidence_valid else "preflight returned malformed native evidence"
    with pytest.raises(expected, match=message):
        _run_scenario(
            tmp_path / "scenario-policy",
            scenario("lost_model_response"),
            {},
            case,
            source,
            tmp_path / "unused-googletest",
            prompt_version="contract-v3",
            max_inspections=4,
            inspections_per_attempt=2,
            context_chars=160000,
            definition_reads=True,
            baseline_repetitions=3,
            reasoning_effort="medium",
        )


@pytest.mark.parametrize(
    "settings,field",
    [
        ({"context_chars": 3999}, "context_chars"),
        ({"context_chars": 200001}, "context_chars"),
        ({"context_chars": True}, "context_chars"),
        ({"context_chars": "160000"}, "context_chars"),
        ({"definition_reads": "true"}, "definition_reads"),
        ({"definition_reads": 1}, "definition_reads"),
    ],
)
def test_invalid_evidence_policy_fails_before_native_or_model_work(tmp_path, settings, field):
    with pytest.raises(ValueError, match=field):
        run_operational_evaluation(tmp_path / "output", **settings)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("value", [0, 4, True, "3", 1.5])
def test_invalid_baseline_repetitions_fail_before_native_or_model_work(tmp_path, value):
    with pytest.raises(ValueError, match="baseline_repetitions"):
        run_operational_evaluation(tmp_path / "output", baseline_repetitions=value)
    assert not (tmp_path / "output").exists()
