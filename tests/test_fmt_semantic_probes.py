"""Mechanical adapter checks; genuine native receipts are stored separately."""

import json
import os
import sys
from pathlib import Path

import pytest

from auto_fix import fmt_semantic_probes as probes
from auto_fix.build import Builder, parse_junit
from auto_fix.config import BuildConfig
from auto_fix.evaluation import _build_config


def trace(*, actual=None, windows=False):
    actual = actual or {}
    lines = []
    for name in probes.CHECKS:
        expected = probes._expected(name, windows=windows)
        result = actual.get(name, expected)
        status = "PASS" if result == expected else "FAIL"
        lines.append(
            f"AUTO_FIX_FMT\t{name}\t{status}\t{result.encode().hex()}\t{expected.encode().hex()}\n"
        )
    return "".join(lines)


def workspace(tmp_path):
    directory = tmp_path / "source"
    headers = directory / "include/fmt"
    headers.mkdir(parents=True)
    for name in ("printf.h", "chrono.h", "format.h", "format-inl.h"):
        (headers / name).write_text("// Fake header used only by mocked build adapter tests.\n")
    return directory


def fake_commands(monkeypatch, *, output=None, native_code=0, configure_code=0):
    def command(argv, directory, log):
        stage = log.stem
        result = ""
        code = 0
        if stage == "configure":
            code = configure_code
            build = Path(argv[argv.index("-B") + 1])
            build.mkdir(parents=True, exist_ok=True)
            (build / "sanitizer.txt").write_text("undefined-nonrecovering")
        if stage == "native":
            result, code = (
                output if output is not None else trace(windows=os.name == "nt"),
                native_code,
            )
        log.write_text(result)
        return {"argv": argv, "returncode": code, "output": result, "log": str(log)}

    monkeypatch.setattr(probes, "_command", command)


def test_exact_records_preserve_empty_strings_and_validate_trusted_expectations():
    checks = probes._native_checks(trace(actual={"DynamicStringZero": "a"}))
    assert len(checks) == 12
    assert checks["DynamicStringZero"] == (False, "a")
    assert checks["DynamicStringNegative"] == (True, "")
    assert checks["DynamicFloatNegative"] == (True, "1")
    assert checks["ChronoNanosecondsMaximum"][1] == "2262-04-11 23:47:16.854775807"
    with pytest.raises(ValueError, match="trusted expected"):
        probes._native_checks(trace().replace("\t616263\t616263", "\t616263\t61", 1))
    with pytest.raises(ValueError, match="trusted expected"):
        probes._native_checks(trace().replace("\tPASS\t", "\tFAIL\t", 1))


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda output: output.splitlines(keepends=True)[0] + output,
        lambda output: "".join(output.splitlines(keepends=True)[:-1]),
        lambda output: output.replace("616263", "zz", 1),
        lambda output: output.replace("DynamicStringPositive", "Unknown", 1),
    ],
)
def test_partial_duplicate_unknown_or_malformed_native_records_are_invalid(corrupt):
    with pytest.raises(ValueError):
        probes._native_checks(corrupt(trace()))


def test_windows_negative_epoch_contract_is_explicit_not_posix_rendering_claim():
    checks = probes._native_checks(trace(windows=True), windows=True)
    assert checks["ChronoNanosecondsMinimum"] == (True, probes.WINDOWS_MINIMUM)
    with pytest.raises(ValueError, match="trusted expected"):
        probes._native_checks(trace(windows=True))


def test_native_failures_emit_inputs_expected_and_actual_in_junit(tmp_path):
    checks = probes._native_checks(trace(actual={"DynamicStringZero": "a"}))
    path = tmp_path / "junit.xml"
    probes._junit(path, checks)
    report = parse_junit(path)
    assert len(report.passed) == 11
    assert report.failed == [f"{probes.PROBE_CLASS}.DynamicStringZero"]
    text = path.read_text()
    assert 'sprintf("%.*s", 0, "abcdef")' in text
    assert 'must produce ""; actual = "a"' in text


@pytest.mark.parametrize("changed,expected_code", [(False, 0), (True, 1)])
def test_completed_native_result_has_distinct_success_or_contract_failure(
    tmp_path, monkeypatch, changed, expected_code
):
    source = workspace(tmp_path)
    changes = {"StaticIntegerPrecisionThree": "12"} if changed else None
    fake_commands(
        monkeypatch, output=trace(actual=changes, windows=os.name == "nt"), native_code=int(changed)
    )
    junit = tmp_path / "junit.xml"
    assert probes.run_probe(source, junit) == expected_code
    evidence = json.loads(junit.with_suffix(".evidence.json").read_text())
    assert not evidence["error"] and len(evidence["checks"]) == 12
    generated = source / ".auto-fix-build/sg/fmt/p/probe.cc"
    assert generated.read_bytes() == probes.CPP_PROBE.encode()


@pytest.mark.parametrize("failure", ["configure", "partial", "crash-after-records", "report"])
def test_infrastructure_parse_process_or_report_errors_return_incomplete_127(
    tmp_path, monkeypatch, failure
):
    source = workspace(tmp_path)
    output = trace(windows=os.name == "nt")
    if failure == "partial":
        output = "".join(output.splitlines(keepends=True)[:-1])
    fake_commands(
        monkeypatch,
        output=output,
        configure_code=int(failure == "configure"),
        native_code=2 if failure == "crash-after-records" else 0,
    )
    if failure == "report":

        def denied(*args, **kwargs):
            raise PermissionError("report cannot be persisted")

        monkeypatch.setattr(probes, "_junit", denied)
    assert probes.run_probe(source, tmp_path / "junit.xml") == 127


def test_stale_report_and_unknown_probe_never_overwrite_outputs(tmp_path):
    path = tmp_path / "junit.xml"
    path.write_text("original evidence")
    assert probes.run_probe(tmp_path / "absent", path) == 127
    assert path.read_text() == "original evidence"
    with pytest.raises(ValueError, match="Unknown fmt"):
        probes.run_probe(tmp_path, path, "invented")


def test_actual_builder_rejects_valid_error_xml_from_incomplete_fmt_execution(tmp_path):
    # No fmt headers: the real adapter emits an Execution error and exits127.
    # Builder must classify infrastructure evidence as invalid, not a repairable test failure.
    primary = (
        "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text("
        '\'<testsuite><testcase classname="Original" name="Pass"/></testsuite>\')'
    )
    config = BuildConfig(
        build=[[sys.executable, "-c", "pass"]],
        test=[sys.executable, "-c", primary, "{junit}"],
        additional_tests=[probes.fmt_contract_command()],
    )
    result = Builder(config, tmp_path / "artifacts").verify(tmp_path, "bad-fmt-environment")
    assert result.build_ok and not result.test_ok and not result.evidence_valid
    assert "command did not complete" in result.output
    assert f"{probes.PROBE_CLASS}.Execution" in result.report.failed


def test_versioned_project_routes_only_relevant_suites_without_changing_original():
    root = Path(__file__).resolve().parents[1]
    original = json.loads((root / "evaluation/expanded/fmt.json").read_text())
    project = json.loads((root / "evaluation/expanded/fmt-validation-v6.json").read_text())
    assert all(project[key] == value for key, value in original.items())
    for target in ("printf-test", "format-test", "chrono-test"):
        config = _build_config(project, {"build_targets": [target]}, None)
        assert config["additional_tests"][0][-1] == probes.PROBE_ID
    assert "additional_tests" not in _build_config(
        project, {"build_targets": ["ranges-test"]}, None
    )
    assert "additional_tests" not in _build_config(
        original, {"build_targets": ["printf-test"]}, None
    )
