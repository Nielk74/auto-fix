from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from auto_fix.build import Builder, parse_junit, run_command
from auto_fix.config import BuildConfig
from auto_fix.semantic_probes import (
    CHECK_NAMES,
    _native_checks,
    duration_min_unit_command,
    run_probe,
)


def command(xml: str, exit_code: int = 0, marker: Path | None = None) -> list[str]:
    return [
        sys.executable,
        "-c",
        "import pathlib,sys;pathlib.Path(sys.argv[1]).write_text(sys.argv[2]);"
        "pathlib.Path(sys.argv[4]).touch() if sys.argv[4] != '-' else None;"
        "raise SystemExit(int(sys.argv[3]))",
        "{junit}",
        xml,
        str(exit_code),
        str(marker) if marker else "-",
    ]


def suite(name: str, outcome: str = "") -> str:
    return f'<testsuite><testcase classname="Native" name="{name}">{outcome}</testcase></testsuite>'


def verify(tmp_path: Path, primary: list[str], additional: list[list[str]]):
    return Builder(
        BuildConfig(
            build=[[sys.executable, "-c", "pass"]],
            test=primary,
            additional_tests=additional,
        ),
        tmp_path / "evidence",
    ).verify(tmp_path, "additional-validation")


def test_additional_commands_require_their_own_fresh_junit_placeholder():
    with pytest.raises(ValidationError, match="Each test command"):
        BuildConfig(build=[["compile"]], test=["test", "{junit}"], additional_tests=[["guard"]])


def test_optional_additional_validation_preserves_default():
    assert BuildConfig(build=[["compile"]], test=["test", "{junit}"]).additional_tests == []
    assert "{junit}" in duration_min_unit_command()


def test_success_merges_unique_cases_and_keeps_all_native_xml(tmp_path):
    result = verify(
        tmp_path,
        command(suite("Original")),
        [command(suite("Guard", "<system-out>native detail</system-out>"))],
    )
    assert result.build_ok and result.test_ok
    assert result.report.passed == ["Native.Original", "Native.Guard"]
    canonical = [Path(path) for path in result.logs if path.endswith("junit.xml")]
    assert len(canonical) == 1
    assert parse_junit(canonical[0]) == result.report
    assert "native detail" in canonical[0].read_text()
    reports = [Path(path) for path in result.logs if path.endswith(".xml")]
    assert len(reports) == 3 and len(set(reports)) == 3


def test_all_additional_commands_run_after_primary_failure(tmp_path):
    markers = [tmp_path / "first-ran", tmp_path / "second-ran"]
    result = verify(
        tmp_path,
        command(suite("Original", "<failure>native failure text</failure>"), exit_code=1),
        [command(suite("One"), marker=markers[0]), command(suite("Two"), marker=markers[1])],
    )
    assert result.build_ok and not result.test_ok
    assert all(path.exists() for path in markers)
    assert result.report.failed == ["Native.Original"]
    assert result.report.passed == ["Native.One", "Native.Two"]
    canonical = next(Path(path) for path in result.logs if path.endswith("junit.xml"))
    assert "native failure text" in canonical.read_text()


def test_additional_command_runs_even_when_primary_xml_is_invalid(tmp_path):
    marker = tmp_path / "guard-ran"
    result = verify(tmp_path, command("invalid XML"), [command(suite("Guard"), marker=marker)])
    assert marker.exists() and not result.test_ok
    assert result.report.passed == ["Native.Guard"]
    assert "Invalid test evidence (primary)" in result.output
    assert not any(path.endswith("junit.xml") for path in result.logs)


@pytest.mark.parametrize(
    ("xml", "exit_code"),
    [
        (suite("Guard", "<failure>semantic mismatch</failure>"), 0),
        (suite("Guard"), 5),
        ("malformed XML", 0),
        (suite("Guard", "<skipped/>"), 0),
    ],
)
def test_any_additional_failure_blocks_a_passing_primary_suite(tmp_path, xml, exit_code):
    result = verify(tmp_path, command(suite("Original")), [command(xml, exit_code)])
    assert result.build_ok and not result.test_ok
    assert "Native.Original" in result.report.passed


def test_missing_additional_report_cannot_reuse_primary_evidence(tmp_path):
    result = verify(
        tmp_path,
        command(suite("Original")),
        [[sys.executable, "-c", "pass", "{junit}"]],
    )
    assert not result.test_ok
    assert "fresh JUnit report" in result.output


def test_duplicate_canonical_identity_across_suites_is_rejected(tmp_path):
    result = verify(tmp_path, command(suite("Same")), [command(suite("Same"))])
    assert not result.test_ok
    assert "unique across validation suites" in result.output
    assert not any(path.endswith("junit.xml") for path in result.logs)


def test_each_run_gets_distinct_report_destinations_for_all_suites(tmp_path):
    config = BuildConfig(
        build=[[sys.executable, "-c", "pass"]],
        test=command(suite("Original")),
        additional_tests=[command(suite("Guard"))],
    )
    builder = Builder(config, tmp_path / "evidence")
    first, second = builder.verify(tmp_path, "same"), builder.verify(tmp_path, "same")
    assert first.test_ok and second.test_ok
    assert set(first.logs).isdisjoint(second.logs)


def test_native_probe_requires_every_distinct_trusted_assertion():
    output = "".join(f"AUTO_FIX_PROBE\t{name}\tPASS\tfinite\n" for name in CHECK_NAMES)
    assert all(passed for passed, _ in _native_checks(output).values())
    with pytest.raises(ValueError, match="every trusted assertion"):
        _native_checks(output.splitlines()[0])
    with pytest.raises(ValueError, match="repeated assertion"):
        _native_checks(output + output.splitlines()[0])


def test_native_probe_preserves_explicit_failed_assertions():
    output = "".join(
        f"AUTO_FIX_PROBE\t{name}\t{'FAIL' if 'Floor' in name else 'PASS'}\t-inf\n"
        for name in CHECK_NAMES
    )
    assert _native_checks(output)["FloorExactMinimumUnit"] == (False, "-inf")


def test_probe_refuses_stale_report_without_overwriting_it(tmp_path):
    junit = tmp_path / "stale.xml"
    junit.write_text("old evidence")
    assert run_probe(tmp_path, junit) != 0
    assert junit.read_text() == "old evidence"


def test_probe_invalid_workspace_emits_explicit_execution_error(tmp_path):
    junit = tmp_path / "new.xml"
    assert run_probe(tmp_path, junit) != 0
    assert parse_junit(junit).failed == ["SemanticGuard.DurationMinUnit.Execution"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX process group assertion")
def test_builder_timeout_also_terminates_probe_compiler_descendants(tmp_path):
    marker = tmp_path / "surviving-compiler"
    delayed = f"import pathlib,time;time.sleep(2);pathlib.Path({str(marker)!r}).touch()"
    compiler = (
        "import subprocess,sys,time;"
        f"subprocess.Popen([sys.executable,'-c',{delayed!r}]);time.sleep(30)"
    )
    launcher = (
        "import sys;from pathlib import Path;from auto_fix.semantic_probes import _command;"
        "_command([sys.executable,'-c',sys.argv[1]],Path.cwd(),Path(sys.argv[2]))"
    )
    result = run_command(
        [sys.executable, "-c", launcher, compiler, str(tmp_path / "compiler.log")],
        tmp_path,
        1,
        tmp_path / "outer.log",
    )
    assert result.returncode == 124
    run_command([sys.executable, "-c", "import time;time.sleep(2)"], tmp_path, 5, tmp_path / "wait")
    assert not marker.exists()
