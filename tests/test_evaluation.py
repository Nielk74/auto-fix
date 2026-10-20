from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from auto_fix import evaluation
from auto_fix.config import Settings
from auto_fix.evaluation import _build_config, _details, _git, _source, _upstream
from auto_fix.integrations import Bitbucket, Jira, TeamCity
from auto_fix.mock_services import (
    BB_URL,
    JIRA_URL,
    PROJECT,
    REPO,
    TC_URL,
    TOKEN,
    TOKEN_ENV,
    VCS_ROOT,
    ScenarioServices,
)
from auto_fix.models import FailedTest, Failure, Verification
from auto_fix.models import TestReport as NativeTestReport
from auto_fix.workflow import Workflow

ORIGINAL = "return 0xA17F;"
REGRESSION = "return 0xA16F;"


@pytest.mark.parametrize("platform_name", ["nt", "posix"])
def test_build_targets_remain_cmake_arguments_and_native_rebuild_is_scoped(
    tmp_path, monkeypatch, platform_name
):
    # Replace only this module's platform view; changing the global os.name
    # would make pathlib instantiate WindowsPath on a POSIX test runner.
    monkeypatch.setattr(evaluation, "os", SimpleNamespace(name=platform_name))
    targets = ["absl_ascii_test", "absl_escaping_test"]
    build = _build_config({"cmake_options": []}, {"build_targets": targets}, tmp_path)
    configure, command = build["configure"][0], build["build"][0]
    cmake_arguments = command[: command.index("--")] if "--" in command else command
    assert cmake_arguments[cmake_arguments.index("--target") + 1 :] == targets
    assert "--clean-first" not in command
    if platform_name == "nt":
        assert "-G" not in configure
        assert command[command.index("--") + 1 :] == ["/t:Rebuild"]
        assert "/t:Rebuild" not in cmake_arguments
    else:
        assert configure[configure.index("-G") + 1] == "Ninja"
        assert "--" not in command
        assert "/t:Rebuild" not in command


@pytest.fixture
def upstream(tmp_path):
    source = tmp_path / "cache" / "abseil"
    source.mkdir(parents=True)
    _git(source, "init", "-b", "master")
    _git(source, "config", "user.name", "Public Upstream Test")
    _git(source, "config", "user.email", "upstream@example.invalid")
    _git(source, "config", "commit.gpgsign", "false")
    _git(source, "config", "core.autocrlf", "false")
    strings = source / "absl" / "strings"
    strings.mkdir(parents=True)
    (strings / "value.cc").write_text(f"int normalize() {{ {ORIGINAL} }}\n", encoding="utf-8")
    (strings / "diagnostics.cc").write_text(
        'const char* diagnostic_label() { return "import"; }\n', encoding="utf-8"
    )
    (strings / "value_test.cc").write_text(
        "#include <cassert>\nint normalize();\nint main() { assert(normalize() == 41343); }\n",
        encoding="utf-8",
    )
    _git(source, "add", ".")
    _git(source, "commit", "-m", "Initial public upstream source")
    return source


def case(exposure="indirect"):
    return {
        "id": "tiny_import_normalization",
        "description": "The importer emits an unexpected normalization value for valid records.",
        "exposure": exposure,
        "mutations": [{"path": "absl/strings/value.cc", "before": ORIGINAL, "after": REGRESSION}],
        "changed_files": [
            "absl/strings/value.cc" if exposure == "direct" else "absl/strings/diagnostics.cc"
        ],
        "context": {
            "commit_message": "CORE-1842 Refresh importer normalization dispatch",
            "pr_title": "CORE-1842 Refresh ingestion diagnostic labels",
        },
    }


@pytest.mark.parametrize("exposure", ["direct", "indirect"])
def test_case_preparation_isolated_local_remote_protected_tests_and_history(
    upstream, tmp_path, exposure
):
    original_head = _git(upstream, "rev-parse", "HEAD")
    test_before = (upstream / "absl/strings/value_test.cc").read_bytes()
    work = tmp_path / exposure
    work.mkdir()
    source, changes = _source(work, upstream, case(exposure))
    assert _git(upstream, "rev-parse", "HEAD") == original_head
    assert _git(upstream, "status", "--porcelain") == ""
    assert ORIGINAL in (upstream / "absl/strings/value.cc").read_text(encoding="utf-8")
    assert REGRESSION in (source / "absl/strings/value.cc").read_text(encoding="utf-8")
    assert (source / "absl/strings/value_test.cc").read_bytes() == test_before
    assert _git(source, "status", "--porcelain") == ""
    assert Path(_git(source, "remote", "get-url", "origin")) == work / "remote.git"
    assert _git(work / "remote.git", "rev-parse", "refs/heads/master") == _git(
        source, "rev-parse", "HEAD"
    )
    assert len(changes) == (2 if exposure == "direct" else 1)
    visible = "\n".join(_git(source, "show", change["version"]) for change in changes)
    if exposure == "direct":
        assert ORIGINAL in visible and REGRESSION in visible
    else:
        assert ORIGINAL not in visible and REGRESSION not in visible
        assert "diagnostics.cc" in visible
    (source / ".auto-fix-build").mkdir()
    (source / ".auto-fix-build" / "artifact.log").write_text("native build output")
    assert _git(source, "status", "--porcelain") == ""


class CapturePacket:
    def __init__(self):
        self.context = None

    def propose(self, context):
        self.context = copy.deepcopy(context)
        raise RuntimeError("Packet captured; this test performs no model inference")


@pytest.mark.parametrize("exposure", ["direct", "indirect"])
def test_model_packet_contains_observable_evidence_without_oracle_case_data(
    upstream, tmp_path, monkeypatch, exposure
):
    monkeypatch.setenv(TOKEN_ENV, TOKEN)
    current = tmp_path / exposure
    current.mkdir()
    specification = case(exposure)
    source, changes = _source(current, upstream, specification)
    failure = Failure(
        build_id="284761",
        build_type="Platform_CppRuntime_Win64_UnitTests",
        build_url=TC_URL + "/viewLog.html?buildId=284761",
        revision=_git(source, "rev-parse", "HEAD"),
        tests=[
            FailedTest(id="8101", name="ValueTest.Normalize", details="expected 41343, got 41327")
        ],
        changes=changes,
    )
    services = ScenarioServices(
        failure,
        now=datetime(2026, 10, 20, 10, 14, tzinfo=ZoneInfo("Europe/Paris")),
        issue_key="CORE-1842",
        issue_description=specification["description"],
    )
    shared = {"token_env": TOKEN_ENV}
    settings = Settings.model_validate(
        {
            "state_dir": current / "state",
            "teamcity": {
                **shared,
                "url": TC_URL,
                "build_types": [failure.build_type],
                "vcs_root_id": VCS_ROOT,
            },
            "bitbucket": {**shared, "url": BB_URL, "project": PROJECT, "repo": REPO},
            "jira": {**shared, "url": JIRA_URL},
            "llm": {**shared, "url": "https://model.meridian.invalid/v1", "model": "gpt-6-luna"},
            "repository": {
                "path": source,
                "allowed_paths": ["absl/**"],
                "context_paths": ["absl/**"],
            },
            "build": {"build": [["unused-build"]], "test": ["unused-test", "{junit}"]},
        }
    )
    model = CapturePacket()
    with services.client() as client:
        tc = TeamCity(settings.teamcity, client)
        failures = tc.failures(services.now.date(), settings.timezone)
        flow = Workflow(
            settings,
            "packet-audit",
            tc,
            Bitbucket(settings.bitbucket, client),
            Jira(settings.jira, client),
            model,
        )
        state = {"run_id": "packet-audit", "failure": failures[0].model_dump()}
        state.update(flow.collect_context(state))
        state.update(flow.prepare(state))
        state["feedback"] = "ValueTest.Normalize: expected 41343, got 41327"
        assert flow.repair(state)["status"] == "invalid_proposal"
    packet = json.dumps(model.context)
    assert "ValueTest.Normalize" in packet
    assert REGRESSION in packet
    assert (ORIGINAL in packet) is (exposure == "direct")
    for oracle_key in ["mutations", "source_metrics", "expected_failed_tests", "before", "after"]:
        assert f'"{oracle_key}":' not in packet
    assert TOKEN not in packet
    assert "Authorization" not in packet
    assert ORIGINAL in (upstream / "absl/strings/value.cc").read_text(encoding="utf-8")
    assert REGRESSION in (source / "absl/strings/value.cc").read_text(encoding="utf-8")
    assert _git(source, "status", "--porcelain") == ""
    assert {request["host"] for request in services.requests} == {
        "ci.meridian.invalid",
        "code.meridian.invalid",
        "issues.meridian.invalid",
    }


def test_cached_public_checkout_must_match_exact_pin_and_be_clean(upstream):
    spec = {
        "repository": "https://example.invalid/must-not-contact",
        "tag": "v1",
        "commit": "f" * 40,
    }
    with pytest.raises(ValueError, match="pinned commit"):
        _upstream(upstream.parent, spec, "abseil")
    spec["commit"] = _git(upstream, "rev-parse", "HEAD")
    assert _upstream(upstream.parent, spec, "abseil") == upstream
    (upstream / "unexpected.txt").write_text("uncommitted file", encoding="utf-8")
    with pytest.raises(ValueError, match="must be clean"):
        _upstream(upstream.parent, spec, "abseil")


def test_changed_mutation_anchor_stops_without_touching_upstream(upstream, tmp_path):
    specification = case()
    specification["mutations"][0]["before"] = "anchor absent from pinned upstream"
    current = tmp_path / "bad-anchor"
    current.mkdir()
    original_head = _git(upstream, "rev-parse", "HEAD")
    with pytest.raises(ValueError, match="mutation anchor changed"):
        _source(current, upstream, specification)
    assert _git(upstream, "rev-parse", "HEAD") == original_head
    assert _git(upstream, "status", "--porcelain") == ""
    assert not (current / "remote.git").exists()


def test_genuine_junit_assertion_details_are_not_replaced_with_fixture_text(tmp_path):
    junit = tmp_path / "junit.xml"
    junit.write_text(
        '<testsuites><testsuite name="Normalize"><testcase name="Valid" classname="ValueTest">'
        '<failure message="assertion failed">actual value 41327\nexpected 41343</failure>'
        '</testcase><testcase name="Unchanged" classname="ValueTest"/>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    assert _details(junit) == {"ValueTest.Valid": "actual value 41327\nexpected 41343"}


@pytest.mark.parametrize("invalid", ["unknown-case", "occupied-directory"])
def test_invalid_evaluation_request_stops_before_upstream_or_model_access(
    tmp_path, monkeypatch, invalid
):
    manifest = tmp_path / "manifest"
    manifest.mkdir()
    (manifest / "project.json").write_text("{}", encoding="utf-8")
    (manifest / "cases.json").write_text(json.dumps({"cases": [case()]}), encoding="utf-8")
    monkeypatch.setattr(evaluation, "evaluation_root", lambda: manifest)

    def forbid_upstream(*args, **kwargs):
        raise AssertionError("invalid requests must fail before cloning or model access")

    monkeypatch.setattr(evaluation, "_upstream", forbid_upstream)
    destination = tmp_path / "evaluation"
    if invalid == "occupied-directory":
        destination.mkdir()
        (destination / "prior-result.json").write_text("preserved", encoding="utf-8")
    with pytest.raises(ValueError, match="Unknown evaluation case ID|must be empty"):
        evaluation.run_evaluation(
            destination, selected=["unknown"] if invalid == "unknown-case" else None
        )
    if invalid == "occupied-directory":
        assert (destination / "prior-result.json").read_text(encoding="utf-8") == "preserved"


@pytest.mark.parametrize("value", [0, 4, True, "3", 1.5])
def test_invalid_baseline_repetitions_stop_before_loading_inputs_or_running_work(
    tmp_path, monkeypatch, value
):
    monkeypatch.setattr(
        evaluation,
        "evaluation_root",
        lambda: pytest.fail("Invalid counts must fail before loading evaluation inputs"),
    )
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="baseline_repetitions"):
        evaluation.run_evaluation(output, baseline_repetitions=value)
    assert not output.exists()


@pytest.mark.parametrize(
    "configured,requested,observed,evidence_valid",
    [({}, 1, 1, True), ({"baseline_repetitions": 3}, 3, 2, True), ({}, 1, 0, False)],
)
def test_baseline_policy_reaches_settings_and_records_requested_and_observed_counts(
    upstream, tmp_path, monkeypatch, configured, requested, observed, evidence_valid
):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    specification = case()
    specification.update(build_targets=["tiny_target"])
    specification["context"].update(jira_key="CORE-1842", jira_summary="Import normalization")
    (inputs / "cases.json").write_text(json.dumps({"cases": [specification]}))
    (inputs / "project.json").write_text(
        json.dumps({"commit": _git(upstream, "rev-parse", "HEAD"), "cmake_options": []})
    )
    junit = tmp_path / "preflight-junit.xml"
    junit.write_text(
        '<testsuite><testcase classname="ValueTest" name="Normalize">'
        "<failure>Structural preflight fixture</failure></testcase></testsuite>"
    )
    preflight = Verification(
        build_ok=True,
        test_ok=False,
        evidence_valid=evidence_valid,
        report=NativeTestReport(failed=["ValueTest.Normalize"]),
        logs=[str(junit)] if evidence_valid else [],
    )

    class Preflight:
        def __init__(self, *_args):
            pass

        def verify(self, *_args):
            return preflight

    class NoModel:
        calls = []

        def __init__(self, *_args, **_kwargs):
            pass

        def close(self):
            pass

    class CapturedWorkflow:
        def __init__(self, settings, run_id, *_args, **_kwargs):
            assert settings.baseline_repetitions == requested
            self.directory = settings.state_dir / "runs" / run_id

        def run(self, state):
            return {
                **state,
                "status": "baseline_unstable",
                "baseline_checks": [preflight.model_dump() for _ in range(observed)],
            }

    monkeypatch.setattr(evaluation, "evaluation_root", lambda: inputs)
    monkeypatch.setattr(evaluation, "_upstream", lambda *_args: upstream)
    monkeypatch.setattr(evaluation, "Builder", Preflight)
    monkeypatch.setattr(evaluation, "CodexRepairModel", NoModel)
    monkeypatch.setattr(evaluation, "Workflow", CapturedWorkflow)
    output = tmp_path / "output"
    if not evidence_valid:
        with pytest.raises(RuntimeError, match="preflight returned malformed native evidence"):
            evaluation.run_evaluation(output, **configured)
        return
    assert evaluation.run_evaluation(output, **configured) == 1
    manifest = json.loads((output / "manifest.json").read_text())
    summary = json.loads((output / "summary.json").read_text())
    score = json.loads((output / specification["id"] / "score.json").read_text())
    assert manifest["baseline_repetitions"] == summary["baseline_repetitions"] == requested
    assert score["baseline_repetitions"] == requested
    assert score["baseline_check_count"] == observed
    assert summary["cases"][0] == score
