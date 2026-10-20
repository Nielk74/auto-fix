from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pytest

from auto_fix.native_tests import run_native


def executable(build: Path, name: str) -> Path:
    path = build / "bin" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("executable-placeholder")
    return path


def install_runner(monkeypatch, *, returncode=0, write_report=True, root="testsuites"):
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        output = Path(
            next(
                part.removeprefix("--gtest_output=xml:")
                for part in argv
                if part.startswith("--gtest_output=xml:")
            )
        )
        if write_report:
            suite = (
                '<testsuite name="DispatchTest" tests="1"><testcase name="Boundary"/></testsuite>'
            )
            output.write_text(
                f"<testsuites>{suite}</testsuites>" if root == "testsuites" else suite
            )
        return SimpleNamespace(returncode=returncode)

    monkeypatch.setattr("auto_fix.native_tests.subprocess.run", run)
    return calls


@pytest.mark.parametrize("root", ["testsuites", "testsuite"])
def test_complete_native_suites_are_run_and_merged_without_a_filter(monkeypatch, tmp_path, root):
    build = tmp_path / "build"
    executable(build, "alpha_test")
    executable(build, "beta_test.exe")
    calls = install_runner(monkeypatch, root=root)
    junit = tmp_path / "evidence" / "junit.xml"
    assert run_native(build, ["alpha_test", "beta_test"], junit) == 0
    assert len(ET.parse(junit).getroot().findall("testsuite")) == 2
    assert len(calls) == 2
    for argv, kwargs in calls:
        assert not any("filter" in part for part in argv)
        assert "--gtest_color=no" in argv
        assert kwargs["timeout"] == 180
        assert Path(argv[0]).is_absolute()


def test_nonzero_native_exit_remains_a_failed_run_with_evidence(monkeypatch, tmp_path):
    build = tmp_path / "build"
    executable(build, "alpha_test")
    install_runner(monkeypatch, returncode=1)
    junit = tmp_path / "junit.xml"
    assert run_native(build, ["alpha_test"], junit) == 1
    assert junit.is_file()


def test_successful_process_without_junit_cannot_pass(monkeypatch, tmp_path):
    build = tmp_path / "build"
    executable(build, "alpha_test")
    install_runner(monkeypatch, write_report=False)
    with pytest.raises(ValueError, match="did not produce test evidence"):
        run_native(build, ["alpha_test"], tmp_path / "junit.xml")
    assert not (tmp_path / "junit.xml").exists()


def test_stale_native_report_is_rejected_before_executing(monkeypatch, tmp_path):
    build = tmp_path / "build"
    executable(build, "alpha_test")
    calls = install_runner(monkeypatch)
    old = tmp_path / "junit-alpha_test.xml"
    old.write_text("stale")
    with pytest.raises(ValueError, match="must be fresh"):
        run_native(build, ["alpha_test"], tmp_path / "junit.xml")
    assert not calls
    assert old.read_text() == "stale"


@pytest.mark.parametrize("count", [0, 2])
def test_missing_or_ambiguous_binary_is_rejected(monkeypatch, tmp_path, count):
    build = tmp_path / "build"
    for index in range(count):
        executable(build / str(index), "alpha_test")
    calls = install_runner(monkeypatch)
    with pytest.raises(ValueError, match="exactly one built executable"):
        run_native(build, ["alpha_test"], tmp_path / "junit.xml")
    assert not calls
