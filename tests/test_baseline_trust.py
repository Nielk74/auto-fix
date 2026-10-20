"""Zero-live-inference native controls for baseline trust and repair publication."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from auto_fix.build import Builder
from auto_fix.config import Settings
from auto_fix.models import FailedTest, Failure, Proposal
from auto_fix.workflow import Workflow

CMAKE = shutil.which("cmake")
pytestmark = pytest.mark.skipif(CMAKE is None, reason="CMake is required for native controls")
EXECUTABLE = Path(".native-build/bin") / ("native-suite.exe" if os.name == "nt" else "native-suite")

NATIVE_CMAKE = """cmake_minimum_required(VERSION 3.20)
project(NativeBaselineControl LANGUAGES CXX)
add_executable(native_suite src/answer.cpp tests/native_suite.cpp)
set_target_properties(native_suite PROPERTIES
  CXX_STANDARD 17
  CXX_STANDARD_REQUIRED YES
  CXX_EXTENSIONS NO
  OUTPUT_NAME native-suite
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
foreach(configuration RELEASE DEBUG RELWITHDEBINFO MINSIZEREL)
  set_target_properties(native_suite PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY_${configuration} "${CMAKE_BINARY_DIR}/bin")
endforeach()
"""

NATIVE_SUITE = r"""#include <fstream>
#include <iostream>
#include <string>

int answer();

int main(int argc, char** argv) {
  if (argc != 4) return 2;
  const std::string mode = argv[3];
  int previous = 0;
  { std::ifstream counter(argv[2]); counter >> previous; }
  const int invocation = previous + 1;
  { std::ofstream counter(argv[2]); counter << invocation; }
  std::ofstream xml(argv[1]);
  std::cout << "mode=" << mode << " invocation=" << invocation
            << " answer=" << answer() << '\n';
  if (mode == "malformed-additional") {
    xml << "<testsuite><testcase";
    return 0;
  }
  const bool failed = mode == "fail-then-pass" ? invocation == 1 : answer() != 7;
  xml << "<testsuite><testcase classname=\"Native\" name=\"Answer\">";
  if (failed) xml << "<failure>Expected answer 7; invocation=" << invocation << "</failure>";
  xml << "</testcase><testcase classname=\"Native\" name=\"StableControl\"/></testsuite>";
  return failed ? 1 : 0;
}
"""


def git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=path, capture_output=True, text=True, check=True
    ).stdout.strip()


class ScriptedProposal:
    """Mechanical candidate fixture; never connects to an inference service."""

    def __init__(self, old: str, new: str, *, forbidden: bool):
        self.old, self.new, self.forbidden = old, new, forbidden
        self.calls = 0

    def propose(self, _context):
        self.calls += 1
        if self.forbidden:
            raise AssertionError("An untrusted baseline must stop before proposing")
        return Proposal(
            summary="Synthetic native control repair",
            explanation="Zero-live-inference mechanical regression control.",
            edits=[{"path": "src/answer.cpp", "old": self.old, "new": self.new}],
        )


class LocalPRReceipt:
    """Return the actual locally pushed Git head, without an HTTP service."""

    def __init__(self, remote: Path):
        self.remote = remote
        self.created = []

    def context(self, _commits):
        return []

    def find_pr(self, *_args):
        return None

    def create_pr(self, branch, base, _title, _description):
        receipt = {
            "id": 1,
            "state": "OPEN",
            "fromRef": {
                "id": "refs/heads/" + branch,
                "latestCommit": git(self.remote, "rev-parse", "refs/heads/" + branch),
            },
            "toRef": {"id": "refs/heads/" + base},
        }
        self.created.append(receipt)
        return receipt


@pytest.fixture
def native_flow(tmp_path):
    def make(*, mode="stable", repetitions=None, malformed=False, forbidden=True):
        source = tmp_path / "source"
        (source / "src").mkdir(parents=True)
        (source / "tests").mkdir()
        initial = 7 if mode == "fail-then-pass" else 6
        implementation = f"int answer() {{ return {initial}; }}\n"
        (source / "src/answer.cpp").write_text(implementation, encoding="utf-8")
        (source / "tests/native_suite.cpp").write_text(NATIVE_SUITE, encoding="utf-8")
        (source / "CMakeLists.txt").write_text(NATIVE_CMAKE, encoding="utf-8")
        (source / ".gitignore").write_text(".native-build/\n", encoding="utf-8")
        git(source, "init", "--initial-branch=master")
        git(source, "config", "user.name", "Native Regression Control")
        git(source, "config", "user.email", "native-control@example.invalid")
        git(source, "add", ".")
        git(source, "commit", "-m", "Synthetic native baseline control")
        revision = git(source, "rev-parse", "HEAD")
        remote = tmp_path / "remote.git"
        git(tmp_path, "clone", "--bare", str(source), str(remote))
        git(source, "remote", "add", "origin", str(remote))
        test_command = [
            str(source / EXECUTABLE),
            "{junit}",
            str(tmp_path / "primary-counter"),
            mode,
        ]
        service = {"url": "https://native-control.invalid", "token_env": "NEVER_USED"}
        payload = {
            "state_dir": tmp_path / "state",
            "teamcity": {**service, "build_types": ["NativeControl"]},
            "bitbucket": {**service, "project": "CONTROL", "repo": "local"},
            "llm": {**service, "model": "ZERO_LIVE_INFERENCE"},
            "repository": {"path": source},
            "build": {
                "configure": [[CMAKE, "-S", ".", "-B", ".native-build"]],
                "build": [
                    [
                        CMAKE,
                        "--build",
                        ".native-build",
                        "--config",
                        "Release",
                        "--target",
                        "native_suite",
                        "--clean-first",
                    ]
                ],
                "test": test_command,
                "timeout_seconds": 120,
            },
        }
        if repetitions is not None:
            payload["baseline_repetitions"] = repetitions
        if malformed:
            payload["build"]["additional_tests"] = [
                [
                    str(source / EXECUTABLE),
                    "{junit}",
                    str(tmp_path / "additional-counter"),
                    "malformed-additional",
                ]
            ]
        settings = Settings.model_validate(payload)
        model = ScriptedProposal(
            f"return {initial};",
            "return 7 + 0;" if mode == "fail-then-pass" else "return 7;",
            forbidden=forbidden,
        )
        bitbucket = LocalPRReceipt(remote)
        flow = Workflow(
            settings,
            "native-control",
            SimpleNamespace(build_log=lambda _build: "Synthetic native assertion failure"),
            bitbucket,
            None,
            model,
            publish=True,
        )
        # Windows Popen does not resolve relative executables against cwd reliably.
        native_executable = str(flow.workspace.path / EXECUTABLE)
        settings.build.test[0] = native_executable
        for command in settings.build.additional_tests:
            command[0] = native_executable
        failure = Failure(
            build_id="999",
            build_type="NativeControl",
            build_url="https://native-control.invalid/build/999",
            revision=revision,
            tests=[FailedTest(id="1", name="Native.Answer")],
        )
        return SimpleNamespace(
            flow=flow,
            source=source,
            remote=remote,
            revision=revision,
            initial={"run_id": flow.run_id, "failure": failure.model_dump()},
            test_sha=hashlib.sha256((source / "tests/native_suite.cpp").read_bytes()).hexdigest(),
        )

    return make


def assert_protected_test_unchanged(control):
    assert (
        hashlib.sha256(
            (control.flow.workspace.path / "tests/native_suite.cpp").read_bytes()
        ).hexdigest()
        == control.test_sha
    )


def assert_stopped_before_proposal(control, result):
    assert result["status"] == "blocked", result.get("reason")
    assert control.flow.model.calls == 0
    assert not control.flow.bitbucket.created
    assert control.flow.workspace.head() == control.revision
    assert control.flow.workspace.is_clean()
    assert git(control.remote, "for-each-ref", "refs/heads/auto-fix/") == ""
    assert_protected_test_unchanged(control)


def test_repeated_baseline_blocks_unchanged_native_fail_pass_sequence(native_flow, tmp_path):
    control = native_flow(mode="fail-then-pass", repetitions=2)
    config = control.flow.settings.build.model_copy(deep=True)
    config.test[0] = str(control.source / EXECUTABLE)
    config.test[2] = str(tmp_path / "unchanged-counter")
    builder = Builder(config, tmp_path / "unchanged-native-evidence")
    unchanged = [builder.verify(control.source, f"control-{index}") for index in range(3)]
    assert [check.test_ok for check in unchanged] == [False, True, True]
    assert all(check.build_ok and check.evidence_valid for check in unchanged)
    assert git(control.source, "rev-parse", "HEAD") == control.revision
    assert git(control.source, "status", "--porcelain") == ""

    result = control.flow.run(control.initial)

    assert_stopped_before_proposal(control, result)
    assert len(result["baseline_checks"]) == 2
    assert result["baseline"] == result["baseline_checks"][0]
    assert result["baseline_checks"][0]["report"]["failed"] == ["Native.Answer"]
    assert result["baseline_checks"][1]["report"]["failed"] == []
    assert (tmp_path / "primary-counter").read_text() == "2"


def test_single_baseline_compatibility_can_publish_a_semantically_unchanged_candidate(native_flow):
    control = native_flow(mode="fail-then-pass", forbidden=False)
    assert control.flow.settings.baseline_repetitions == 1

    result = control.flow.run(control.initial)

    assert result["status"] == "published", result.get("reason")
    assert len(result["baseline_checks"]) == 1
    assert result["baseline"]["report"]["failed"] == ["Native.Answer"]
    assert result["verification"]["report"]["failed"] == []
    assert "return 7 + 0;" in (control.flow.workspace.path / "src/answer.cpp").read_text()
    assert control.flow.model.calls == 1
    assert len(control.flow.bitbucket.created) == 1
    assert result["head"] == control.flow.bitbucket.created[0]["fromRef"]["latestCommit"]
    assert_protected_test_unchanged(control)


def test_malformed_additional_native_evidence_blocks_a_matching_baseline_failure(native_flow):
    control = native_flow(malformed=True)

    result = control.flow.run(control.initial)

    assert_stopped_before_proposal(control, result)
    assert len(result["baseline_checks"]) == 1
    assert result["baseline"]["build_ok"]
    assert result["baseline"]["report"]["failed"] == ["Native.Answer"]
    assert not result["baseline"]["evidence_valid"]
    assert "Invalid test evidence (additional-1)" in result["baseline"]["output"]


def test_stable_repeated_native_failure_accepts_a_real_repair_and_publishes(native_flow, tmp_path):
    control = native_flow(repetitions=2, forbidden=False)

    result = control.flow.run(control.initial)

    assert result["status"] == "published", result.get("reason")
    assert len(result["baseline_checks"]) == 2
    assert all(
        check["report"]["failed"] == ["Native.Answer"] for check in result["baseline_checks"]
    )
    assert all(check["evidence_valid"] for check in result["baseline_checks"])
    assert result["verification"]["report"]["passed"] == ["Native.Answer", "Native.StableControl"]
    assert result["verification"]["evidence_valid"]
    assert result["head"] == control.flow.bitbucket.created[0]["fromRef"]["latestCommit"]
    assert (
        git(control.remote, "rev-parse", "refs/heads/" + control.flow.workspace.branch)
        == result["head"]
    )
    assert (tmp_path / "primary-counter").read_text() == "4"
    assert control.flow.model.calls == len(control.flow.bitbucket.created) == 1
    assert git(control.flow.workspace.path, "diff", "--name-only", "origin/master", "HEAD") == (
        "src/answer.cpp"
    )
    assert_protected_test_unchanged(control)
