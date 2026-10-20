"""Mechanical evidence checks; live/native model trials are kept separately."""

import hashlib
import sys
from xml.etree import ElementTree as XML

import pytest

from auto_fix import semantic_probes as probes
from auto_fix.build import Builder, parse_junit
from auto_fix.config import BuildConfig


def trace(names, *, failed=()):
    return "".join(
        f"AUTO_FIX_PROBE\t{name}\t{'FAIL' if name in failed else 'PASS'}\tactual\n"
        for name in names
    )


def test_new_boundary_report_requires_all_ten_actual_assertions():
    assert len(probes.BOUNDARY_CHECK_NAMES) == 10
    checks = probes._native_checks(trace(probes.BOUNDARY_CHECK_NAMES), probes.BOUNDARY_CHECK_NAMES)
    assert len(checks) == 10 and all(passed for passed, _ in checks.values())
    with pytest.raises(ValueError, match="every trusted assertion"):
        probes._native_checks(trace(probes.CHECK_NAMES), probes.BOUNDARY_CHECK_NAMES)
    with pytest.raises(ValueError, match="invalid assertion"):
        probes._native_checks(trace(probes.BOUNDARY_CHECK_NAMES))


def test_boundary_xml_explains_non_multiple_and_infinite_input_contracts(tmp_path):
    failed = ("CeilMinimumPositiveThree", "FloorMinimumNegativeThree", "CeilMinimumInfiniteUnit")
    checks = probes._native_checks(
        trace(probes.BOUNDARY_CHECK_NAMES, failed=failed), probes.BOUNDARY_CHECK_NAMES
    )
    path = tmp_path / "junit.xml"
    probes._junit(
        path, checks, check_names=probes.BOUNDARY_CHECK_NAMES, classname=probes.BOUNDARY_CLASS
    )
    report = parse_junit(path)
    assert len(report.passed) == 7 and len(report.failed) == 3
    failures = [node for node in XML.parse(path).getroot().iter("failure")]
    assert all(node.get("message") == "Duration rounding boundary changed" for node in failures)
    text = " ".join(node.text or "" for node in failures)
    assert "unit = Seconds(3)" in text and "Ceil must be d + Seconds(2)" in text
    assert "unit = Seconds(-3)" in text and "Floor must be -infinity" in text
    assert "unit = InfiniteDuration()" in text and "Ceil must be ZeroDuration()" in text


def test_historical_four_check_probe_source_remains_byte_identical():
    # Captured from the original v3 native integration receipt, not regenerated.
    assert (
        hashlib.sha256(probes.DURATION_PROBE.encode()).hexdigest()
        == "a0a69311683491302142b0a3c87ca8738da2ead3caf8011b9b161a6574a44c20"
    )
    assert len(probes.CHECK_NAMES) == 4
    assert "FloorMinimumPositiveThree" not in probes.DURATION_PROBE
    assert "FloorMinimumPositiveThree" in probes.BOUNDARY_PROBE
    assert probes.duration_min_unit_command()[-1] == "duration-min-unit"
    assert (
        probes.duration_min_unit_command("duration-rounding-boundaries")[-1]
        == "duration-rounding-boundaries"
    )


def test_unknown_probe_is_rejected_before_any_evidence_creation(tmp_path):
    with pytest.raises(ValueError, match="Unknown duration"):
        probes.run_probe(tmp_path / "absent-source", tmp_path / "out.xml", "unknown")
    assert list(tmp_path.iterdir()) == []


def test_trusted_probe_execution_error_is_not_valid_baseline_evidence(tmp_path):
    primary = [
        sys.executable,
        "-c",
        "from pathlib import Path; import sys; "
        "Path(sys.argv[1]).write_text("
        "'<testsuite><testcase name=\"original\"><failure/></testcase></testsuite>'); "
        "sys.exit(1)",
        "{junit}",
    ]
    config = BuildConfig(
        configure=[],
        build=[[sys.executable, "-c", "pass"]],
        test=primary,
        additional_tests=[probes.duration_min_unit_command("duration-rounding-boundaries")],
        timeout_seconds=30,
    )
    # The primary failure is genuine XML; the trusted probe cannot execute in
    # this workspace. Its diagnostic <error> must not qualify as an assertion.
    result = Builder(config, tmp_path / "evidence").verify(tmp_path, "baseline")
    assert result.build_ok and not result.evidence_valid and not result.test_ok
    assert "original" in result.report.failed
    assert "command did not complete" in result.output
    assert "Workspace is not an Abseil" in result.output
