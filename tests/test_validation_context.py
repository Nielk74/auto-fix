from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from auto_fix.build import parse_junit
from auto_fix.validation_context import failed_assertions


def report(tmp_path: Path, body: str, failures: list[str], name="verification/fresh/junit.xml"):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return {"logs": [str(path)], "report": {"failed": failures}}, path


def test_early_assertion_survives_thousands_of_later_passing_tests(tmp_path):
    body = (
        '<testsuite><testcase classname="Duration" name="Flooring">'
        '<failure message="Wrong quotient">Expected: -1\nActual: 0</failure></testcase>'
        + "".join(f'<testcase classname="Unrelated" name="Pass{i}"/>' for i in range(9000))
        + "</testsuite>"
    )
    verification, _ = report(tmp_path, body, ["Duration.Flooring"])
    verification["output"] = "[ PASSED ] Unrelated.Pass8999" * 500
    result = failed_assertions(verification, evidence_root=tmp_path)
    assert not result["errors"]
    assert result["assertions"][0]["name"] == "Duration.Flooring"
    assert result["assertions"][0]["message"] == "Wrong quotient"
    assert result["assertions"][0]["expected"] == "-1"
    assert result["assertions"][0]["actual"] == "0"
    assert result["failed_test_count"] == 1


def test_merged_canonical_report_preserves_native_guard_input_and_actual(tmp_path):
    from auto_fix.semantic_probes import CHECK_NAMES, _junit

    canonical = tmp_path / "verification/merged/junit.xml"
    checks = {name: (True, "finite") for name in CHECK_NAMES}
    checks["FloorExactMinimumUnit"] = (False, "-inf")
    _junit(canonical, checks)
    partial = canonical.with_name("junit-primary.xml")
    partial.write_text('<testsuite><testcase name="Passing"/></testsuite>')
    verification = {
        "logs": [str(partial), str(canonical), str(canonical)],
        "report": {"failed": ["SemanticGuard.DurationMinUnit.FloorExactMinimumUnit"]},
    }
    result = failed_assertions(verification, evidence_root=tmp_path)
    assertion = result["assertions"][0]
    assert "Seconds(INT64_MIN)" in assertion["text"]
    assert "rounding must preserve d" in assertion["text"]
    assert "FloorExactMinimumUnit produced -inf" in assertion["text"]
    assert assertion["classname"] == "SemanticGuard.DurationMinUnit"
    assert result["failed_test_count"] == 1 and not result["errors"]


def test_expected_actual_xml_fields_and_namespaces_match_builder_identity(tmp_path):
    verification, path = report(
        tmp_path,
        '<testsuite xmlns="urn:junit"><testcase classname="Suite" name="Boundary">'
        '<failure message="Mismatch" expected="42" actual="0">'
        "<expected>forty-two</expected><actual>zero</actual></failure>"
        '</testcase><testcase classname="Same" name="Same"><error>native crash</error>'
        "</testcase></testsuite>",
        ["Suite.Boundary", "Same"],
    )
    result = failed_assertions(verification, evidence_root=tmp_path)
    assert [item["name"] for item in result["assertions"]] == parse_junit(path).failed
    assert result["assertions"][0]["expected"] == "42\nforty-two"
    assert result["assertions"][0]["actual"] == "0\nzero"
    assert result["assertions"][1]["text"] == "native crash"


@pytest.mark.parametrize(
    "operands",
    [
        "  expected_status\n    Which is: false\n  observed_status\n    Which is: true",
        "  observed_status\n    Which is: true\n  expected_status\n    Which is: false",
        '  Decode(input)\n    Which is: "N"\n  "M"',
    ],
)
def test_google_test_operand_values_are_not_mislabeled_as_actual(tmp_path, operands):
    from xml.sax.saxutils import escape

    text = "Expected equality of these values:\n" + operands
    verification, _ = report(
        tmp_path,
        '<testsuite><testcase classname="Parser" name="Contract"><failure>'
        + escape(text)
        + "</failure></testcase></testsuite>",
        ["Parser.Contract"],
    )
    assertion = failed_assertions(verification, evidence_root=tmp_path)["assertions"][0]
    assert assertion["expected"] == assertion["actual"] == ""
    assert assertion["text"] == text


def test_round_robin_group_representatives_do_not_hide_a_later_failure_family(tmp_path):
    cases = []
    failed = []
    for group, count in (("Broad", 30), ("Parser", 2), ("Guard", 1)):
        for number in range(count):
            failed.append(f"{group}.Fail{number}")
            cases.append(
                f'<testcase classname="{group}" name="Fail{number}">'
                "<failure>cause</failure></testcase>"
            )
    verification, _ = report(tmp_path, "<testsuite>" + "".join(cases) + "</testsuite>", failed)
    result = failed_assertions(verification, evidence_root=tmp_path)
    assert [item["classname"] for item in result["assertions"][:3]] == ["Broad", "Parser", "Guard"]
    assert len(result["assertions"]) == 12
    assert result["omitted_failed_tests"] == 21 and result["truncated"]


@pytest.mark.parametrize("budget", [300, 700, 2000, 6000])
def test_total_json_budget_bounds_unicode_large_details_and_group_names(tmp_path, budget):
    failed = []
    cases = []
    for number in range(20):
        group = f"種類{number}" + "長" * 150
        failed.append(f"{group}.Boundary")
        cases.append(
            f'<testcase classname="{group}" name="Boundary"><failure message="問題">'
            + "説明" * 6000
            + "\nExpected: -1\nActual: 0</failure></testcase>"
        )
    verification, _ = report(tmp_path, "<testsuite>" + "".join(cases) + "</testsuite>", failed)
    result = failed_assertions(verification, evidence_root=tmp_path, max_chars=budget)
    assert len(json.dumps(result)) <= budget
    assert len(result["assertions"]) <= 12 and result["truncated"]
    assert all(item["name"] in failed for item in result["assertions"])


@pytest.mark.parametrize(
    "body,failed,code",
    [
        (
            '<testsuite><testcase name="x"><failure/></testcase><testcase name="x"/></testsuite>',
            ["x"],
            "duplicate_test_name",
        ),
        ("<testsuite><testcase><failure/></testcase></testsuite>", ["x"], "missing_test_name"),
        (
            '<testsuite><testcase name="actual"><failure/></testcase></testsuite>',
            ["invented"],
            "failure_identity_mismatch",
        ),
        ('<testsuite><testcase name="x"/></testsuite>', ["x"], "failure_identity_mismatch"),
        ("<testsuite>", ["x"], "malformed_xml"),
        (
            '<!DOCTYPE testsuite><testsuite><testcase name="x"><failure/></testcase></testsuite>',
            ["x"],
            "unsafe_xml",
        ),
        (
            '<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///etc/passwd">]><testsuite>&secret;</testsuite>',
            ["x"],
            "unsafe_xml",
        ),
    ],
)
def test_invalid_or_inconsistent_reports_return_errors_without_assertions(
    tmp_path, body, failed, code
):
    verification, _ = report(tmp_path, body, failed)
    result = failed_assertions(verification, evidence_root=tmp_path)
    assert not result["assertions"]
    assert result["errors"][0]["code"] == code


def test_only_logged_canonical_report_is_read_not_older_reports_or_model_paths(tmp_path):
    older = tmp_path / "verification/old/junit.xml"
    older.parent.mkdir(parents=True)
    older.write_text(
        '<testsuite><testcase name="old"><failure>stale</failure></testcase></testsuite>'
    )
    verification, current = report(
        tmp_path,
        '<testsuite><testcase name="fresh"><failure>new</failure></testcase></testsuite>',
        ["fresh"],
    )
    verification["model_path"] = str(older)
    result = failed_assertions(verification, evidence_root=tmp_path)
    assert result["assertions"][0]["text"] == "new"
    verification["logs"] = [str(older), str(current)]
    assert (
        failed_assertions(verification, evidence_root=tmp_path)["errors"][0]["code"]
        == "ambiguous_report"
    )
    verification["logs"] = [str(current.with_name("junit-additional-1.xml"))]
    assert (
        failed_assertions(verification, evidence_root=tmp_path)["errors"][0]["code"]
        == "missing_report"
    )


def test_outside_and_symlinked_report_paths_are_rejected(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    verification, outside = report(
        tmp_path,
        '<testsuite><testcase name="x"><failure/></testcase></testsuite>',
        ["x"],
        "outside/junit.xml",
    )
    assert (
        failed_assertions(verification, evidence_root=run)["errors"][0]["code"] == "untrusted_path"
    )
    linked = run / "junit.xml"
    try:
        linked.symlink_to(outside)
    except OSError:
        pytest.skip("Symlink creation unavailable")
    verification["logs"] = [str(linked)]
    assert failed_assertions(verification, evidence_root=run)["errors"][0]["code"] == "symlink"
    linked.unlink()
    (run / "linked").symlink_to(outside.parent, target_is_directory=True)
    verification["logs"] = [str(run / "linked/junit.xml")]
    assert failed_assertions(verification, evidence_root=run)["errors"][0]["code"] == "symlink"


def test_missing_oversized_and_relative_reports_fail_closed_with_bounded_errors(tmp_path):
    verification, path = report(
        tmp_path, '<testsuite><testcase name="x"><failure/></testcase></testsuite>', ["x"]
    )
    result = failed_assertions(
        verification, evidence_root=tmp_path, max_report_bytes=10, max_chars=300
    )
    assert result["errors"][0]["code"] == "oversized_report" and not result["assertions"]
    assert len(json.dumps(result)) <= 300
    path.unlink()
    assert (
        failed_assertions(verification, evidence_root=tmp_path)["errors"][0]["code"]
        == "unreadable_report"
    )
    verification["logs"] = ["verification/fresh/junit.xml"]
    assert (
        failed_assertions(verification, evidence_root=tmp_path)["errors"][0]["code"]
        == "untrusted_path"
    )


def test_passing_and_skipped_tests_do_not_become_assertions(tmp_path):
    verification, _ = report(
        tmp_path,
        '<testsuite><testcase name="pass"/><testcase name="skip"><skipped/></testcase></testsuite>',
        [],
    )
    result = failed_assertions(verification, evidence_root=tmp_path)
    assert result["failed_test_count"] == 0 and result["assertions"] == []
    assert not result["errors"]


def test_failure_value_clipping_is_disclosed_even_when_the_packet_fits(tmp_path):
    verification, _ = report(
        tmp_path,
        '<testsuite><testcase name="failure"><failure expected="'
        + "long_expected_" * 100
        + '" actual="0"/></testcase></testsuite>',
        ["failure"],
    )
    result = failed_assertions(verification, evidence_root=tmp_path)
    assert result["truncated"] and result["assertions"][0]["truncated"]
    assert len(result["assertions"][0]["expected"]) == 800


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFO required")
def test_special_report_file_is_rejected_without_blocking(tmp_path):
    path = tmp_path / "junit.xml"
    os.mkfifo(path)
    result = failed_assertions(
        {"logs": [str(path)], "report": {"failed": []}}, evidence_root=tmp_path
    )
    assert result["errors"][0]["code"] == "invalid_file" and not result["assertions"]
