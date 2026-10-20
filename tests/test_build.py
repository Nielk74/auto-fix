from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from auto_fix.build import Builder, parse_junit, run_command
from auto_fix.config import BuildConfig


def python(script: str, *args: str) -> list[str]:
    return [sys.executable, "-c", script, *args]


def builder(tmp_path: Path, xml: str, exit_code: int = 0) -> Builder:
    return Builder(
        BuildConfig(
            build=[python("pass")],
            test=python(
                "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text(sys.argv[2]); "
                "sys.exit(int(sys.argv[3]))",
                "{junit}",
                xml,
                str(exit_code),
            ),
        ),
        tmp_path / "artifacts",
    )


def test_success_requires_executed_cases_and_uses_exact_names(tmp_path):
    result = builder(
        tmp_path, '<testsuite><testcase classname="C" name="Exact.Name"/></testsuite>'
    ).verify(tmp_path, "success")
    assert result.build_ok and result.test_ok
    assert result.report.passed == ["C.Exact.Name"]
    assert all(Path(log).is_file() for log in result.logs)


@pytest.mark.parametrize(
    "xml",
    [
        '<testsuite tests="30" failures="0"/>',
        '<testsuite><testcase name="disabled"><skipped/></testcase></testsuite>',
        '<testsuite><testcase name="disabled" status="notrun"/></testsuite>',
        '<testsuite><testcase name="broken"><failure/></testcase></testsuite>',
        '<testsuite><testcase name="broken"><error/></testcase></testsuite>',
        "not XML",
        '<!DOCTYPE x [<!ENTITY bad "danger">]><testsuite>&bad;</testsuite>',
    ],
)
def test_invalid_or_unsuccessful_evidence_fails_even_with_zero_exit(tmp_path, xml):
    result = builder(tmp_path, xml).verify(tmp_path, "evidence")
    assert result.build_ok and not result.test_ok


def test_nonzero_test_exit_fails_even_with_passing_report(tmp_path):
    result = builder(tmp_path, '<testsuite><testcase name="pass"/></testsuite>', 2).verify(
        tmp_path, "nonzero"
    )
    assert not result.test_ok and result.report.passed == ["pass"]
    assert not result.evidence_valid


def test_stale_report_cannot_satisfy_next_run(tmp_path):
    stale = tmp_path / "junit.xml"
    stale.write_text('<testsuite><testcase name="old"/></testsuite>')
    config = BuildConfig(build=[python("pass")], test=python("pass", "{junit}"))
    result = Builder(config, tmp_path / "artifacts").verify(tmp_path, "stale")
    assert not result.test_ok
    assert not result.evidence_valid
    assert "fresh JUnit" in result.output


def test_build_failure_prevents_tests(tmp_path):
    marker = tmp_path / "test-ran"
    config = BuildConfig(
        build=[python("raise SystemExit(7)")],
        test=python("import pathlib,sys;pathlib.Path(sys.argv[1]).touch()", str(marker), "{junit}"),
    )
    result = Builder(config, tmp_path / "artifacts").verify(tmp_path, "build-failed")
    assert not result.build_ok and not result.test_ok and not marker.exists()
    assert not result.evidence_valid


@pytest.mark.parametrize(
    "xml,exit_code,valid",
    [
        (
            '<testsuite><testcase name="case"><failure>assertion</failure></testcase></testsuite>',
            1,
            True,
        ),
        (
            '<testsuite><testcase name="case"><failure>assertion</failure></testcase></testsuite>',
            124,
            False,
        ),
        (
            '<testsuite><testcase name="case"><failure>assertion</failure></testcase></testsuite>',
            127,
            False,
        ),
        ('<testsuite><testcase name="case"/></testsuite>', 3, False),
        ("<testsuite><testcase", 0, False),
    ],
)
def test_structured_evidence_flag_distinguishes_assertions_from_invalid_execution(
    tmp_path, xml, exit_code, valid
):
    result = builder(tmp_path, xml, exit_code).verify(tmp_path, "evidence-trust")
    assert result.evidence_valid is valid
    assert not result.test_ok


def test_timeout_cannot_turn_partial_failure_xml_into_valid_baseline_evidence(tmp_path):
    xml = (
        '<testsuite><testcase name="case"><failure>early assertion</failure></testcase></testsuite>'
    )
    worker = builder(tmp_path, xml)
    worker.config.timeout_seconds = 1
    worker.config.test = python(
        "import pathlib,sys,time;pathlib.Path(sys.argv[1]).write_text(sys.argv[2]);time.sleep(30)",
        "{junit}",
        xml,
    )
    result = worker.verify(tmp_path, "partial-native-evidence")
    assert result.report.failed == ["case"]
    assert "timed out" in result.output
    assert not result.evidence_valid and not result.test_ok


def test_unique_reports_and_namespaced_junit(tmp_path):
    worker = builder(tmp_path, '<testsuite xmlns="urn:x"><testcase name="case"/></testsuite>')
    first = worker.verify(tmp_path, "repeat")
    second = worker.verify(tmp_path, "repeat")
    assert first.test_ok and second.test_ok and first.logs != second.logs


def test_command_timeout_and_secret_redaction(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTO_FIX_TEST_API_TOKEN", "a-very-specific-secret")
    result = run_command(
        python(
            "import os,time;print(os.environ['AUTO_FIX_TEST_API_TOKEN'],flush=True);time.sleep(30)"
        ),
        tmp_path,
        1,
        tmp_path / "timeout.log",
    )
    assert result.returncode == 124
    assert "timed out" in result.output
    assert "a-very-specific-secret" not in result.output
    assert "[REDACTED]" in (tmp_path / "timeout.log").read_text()


def test_parser_prefers_failure_over_skipped(tmp_path):
    report = tmp_path / "report.xml"
    report.write_text(
        '<testsuite><testcase name="case"><skipped/><failure/></testcase></testsuite>'
    )
    assert parse_junit(report).failed == ["case"]


def test_missing_executable_is_a_failed_command(tmp_path):
    result = run_command([str(tmp_path / "not-an-executable")], tmp_path, 1, tmp_path / "bad.log")
    assert result.returncode == 127


@pytest.mark.skipif(os.name == "nt", reason="POSIX process group assertion")
def test_timeout_terminates_child_process_group(tmp_path):
    marker = tmp_path / "orphan-output"
    child = "import pathlib,time; time.sleep(2); pathlib.Path(" + repr(str(marker)) + ").touch()"
    parent = (
        "import subprocess,sys,time;"
        "subprocess.Popen([sys.executable,'-c',sys.argv[1]]);time.sleep(30)"
    )
    result = run_command(python(parent, child), tmp_path, 1, tmp_path / "tree.log")
    assert result.returncode == 124
    # A second subprocess gives a surviving child enough time to create its marker.
    run_command(python("import time;time.sleep(2)"), tmp_path, 5, tmp_path / "wait.log")
    assert not marker.exists()


def test_gtest_cases_are_disambiguated_by_classname(tmp_path):
    result = builder(
        tmp_path,
        '<testsuite><testcase classname="A" name="same"/>'
        '<testcase classname="B" name="same"/></testsuite>',
    ).verify(tmp_path, "duplicate")
    assert result.test_ok
    assert result.report.passed == ["A.same", "B.same"]


def test_duplicate_canonical_case_names_are_rejected(tmp_path):
    result = builder(
        tmp_path,
        '<testsuite><testcase classname="A" name="same"/>'
        '<testcase classname="A" name="same"/></testsuite>',
    ).verify(tmp_path, "duplicate")
    assert not result.test_ok
    assert "duplicate name" in result.output


def test_ctest_identical_classname_does_not_repeat_name(tmp_path):
    result = builder(
        tmp_path, '<testsuite><testcase classname="Exact.Name" name="Exact.Name"/></testsuite>'
    ).verify(tmp_path, "ctest")
    assert result.report.passed == ["Exact.Name"]
