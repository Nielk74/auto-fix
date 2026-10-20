from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from auto_fix.config import RepositoryConfig
from auto_fix.investigation import gather_evidence
from auto_fix.models import Investigation, SourceRead
from auto_fix.workspace import Workspace


def git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


@pytest.fixture
def workspace(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init", "-b", "master")
    git(source, "config", "user.name", "Investigation Test")
    git(source, "config", "user.email", "test@example.invalid")
    git(source, "config", "core.autocrlf", "false")
    for name in ["src", "include", "tests", "evaluation"]:
        (source / name).mkdir()
    lines = [f"int line_{number} = {number};\n" for number in range(1, 181)]
    lines[39] = "int NormalizeToken(int value) { return value; }\n"
    lines[139] = "int NormalizeToken(long value) { return int(value); }\n"
    (source / "src/format.cc").write_text("".join(lines), encoding="utf-8")
    (source / "include/values.h").write_bytes(b"int value = 3;\r\nint other = 4;\r\n")
    (source / "tests/value_test.cc").write_text("int expected_value = 3;\n", encoding="utf-8")
    (source / "src/config.json").write_text('{"oracle":"DO_NOT_INCLUDE_ORACLE"}')
    (source / "evaluation/oracle.cc").write_text("// DO_NOT_INCLUDE_ORACLE\n")
    (source / "evaluation/cases_fmt.json").write_text('{"before":"DO_NOT_INCLUDE_ORACLE"}')
    git(source, "add", ".")
    git(source, "commit", "-m", "Tracked investigation sources")
    (source / "src/untracked.cc").write_text("// DO_NOT_INCLUDE_UNTRACKED\n")
    instance = Workspace(
        RepositoryConfig(path=source, context_paths=["src/**", "include/**", "tests/**"]),
        tmp_path / "state",
        "investigation-test",
    )
    # Evidence gathering operates on the prepared worktree; this fixture already
    # has a real Git checkout, so avoid unrelated worktree/rebase operations.
    instance.path = source
    return instance


def request(*, queries=(), reads=()):
    return Investigation(
        summary="Inspect normalization behavior",
        hypotheses=["The overload may change the value"],
        queries=list(queries),
        reads=list(reads),
        ready=False,
    )


def test_read_chooses_nearest_literal_symbol_and_preserves_exact_line_excerpt(workspace):
    source = workspace.path / "src/format.cc"
    before = source.read_bytes()
    evidence = gather_evidence(
        workspace,
        request(reads=[SourceRead(path="src/format.cc", line=100, symbol="NormalizeToken")]),
    )
    assert not evidence["errors"]
    assert len(evidence["excerpts"]) == 1
    excerpt = evidence["excerpts"][0]
    assert (excerpt["start_line"], excerpt["end_line"]) == (105, 175)
    assert excerpt["content"] == "".join(before.decode("utf-8").splitlines(keepends=True)[104:175])
    assert source.read_bytes() == before
    assert git(workspace.path, "diff", "--name-only") == ""


def test_explicit_reads_precede_broad_case_insensitive_literal_search(workspace):
    evidence = gather_evidence(
        workspace,
        request(
            queries=["normalizetoken(", "line_"],
            reads=[SourceRead(path="src/format.cc", line=140, symbol="")],
        ),
        max_chars=3500,
    )
    assert evidence["excerpts"][0]["kind"] == "read"
    assert evidence["excerpts"][0]["start_line"] == 105
    assert evidence["queries"][0]["matches_returned_or_seen"] == 2
    assert evidence["queries"][1]["matches_returned_or_seen"] <= 12
    assert len(json.dumps(evidence)) <= 3500


def test_read_preserves_crlf_and_allows_existing_test_context(workspace):
    evidence = gather_evidence(
        workspace,
        request(
            reads=[
                SourceRead(path="include/values.h", line=1, symbol=""),
                SourceRead(path="tests/value_test.cc", line=0, symbol="expected_value"),
            ]
        ),
    )
    assert evidence["excerpts"][0]["content"] == "int value = 3;\r\nint other = 4;\r\n"
    assert evidence["excerpts"][1]["path"] == "tests/value_test.cc"


@pytest.mark.parametrize(
    "path",
    [
        "../private.cc",
        "/etc/private.cc",
        "src/../evaluation/oracle.cc",
        "src\\format.cc",
        "src/untracked.cc",
        "src/config.json",
        "evaluation/cases_fmt.json",
        "evaluation/oracle.cc",
    ],
)
def test_read_rejects_traversal_untracked_unallowed_and_oracle_files(workspace, path):
    evidence = gather_evidence(workspace, request(reads=[SourceRead(path=path, line=1, symbol="")]))
    assert not evidence["excerpts"]
    assert len(evidence["errors"]) == 1
    assert "outside tracked configured source context" in evidence["errors"][0]["error"]
    assert "DO_NOT_INCLUDE" not in json.dumps(evidence)


def test_search_cannot_discover_untracked_or_oracle_content(workspace):
    evidence = gather_evidence(
        workspace, request(queries=["DO_NOT_INCLUDE_ORACLE", "DO_NOT_INCLUDE_UNTRACKED"])
    )
    assert not evidence["excerpts"]
    assert all(query["matches_returned_or_seen"] == 0 for query in evidence["queries"])


def test_tracked_symlink_never_exposes_external_source(workspace, tmp_path):
    target = tmp_path / "private.cc"
    target.write_text("int PRIVATE_UNRELATED_VALUE = 8192;\n", encoding="utf-8")
    link = workspace.path / "src/linked.cc"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("This runner does not permit creating symlinks")
    git(workspace.path, "add", "src/linked.cc")
    evidence = gather_evidence(
        workspace,
        request(
            queries=["PRIVATE_UNRELATED_VALUE"],
            reads=[SourceRead(path="src/linked.cc", line=1, symbol="")],
        ),
    )
    assert not evidence["excerpts"]
    assert "Symlink paths" in evidence["errors"][0]["error"]
    assert evidence["queries"][0]["matches_returned_or_seen"] == 0
    assert "8192" not in json.dumps(evidence)


@pytest.mark.parametrize("line,symbol", [(181, ""), (0, "AbsentSymbol")])
def test_unavailable_line_or_symbol_reports_an_error_without_inventing_source(
    workspace, line, symbol
):
    evidence = gather_evidence(
        workspace, request(reads=[SourceRead(path="src/format.cc", line=line, symbol=symbol)])
    )
    assert not evidence["excerpts"]
    assert evidence["errors"]


def test_oversized_source_is_rejected_by_scan_budget(workspace):
    path = workspace.path / "src/oversized.cc"
    path.write_bytes(b"x" * 2_000_001)
    git(workspace.path, "add", "src/oversized.cc")
    evidence = gather_evidence(
        workspace, request(reads=[SourceRead(path="src/oversized.cc", line=1, symbol="")])
    )
    assert not evidence["excerpts"]
    assert evidence["errors"][0]["error"] == "Inspection source scan budget exceeded"


@pytest.mark.parametrize("query", ["x", "a" * 161, "line_\nint"])
def test_search_requires_a_bounded_single_line_literal(workspace, query):
    evidence = gather_evidence(workspace, request(queries=[query]))
    assert not evidence["excerpts"]
    assert not evidence["queries"]
    assert evidence["errors"][0]["error"] == "Search must be a 2-160 character literal"


def test_query_metadata_alone_obeys_final_json_budget(workspace):
    evidence = gather_evidence(
        workspace, request(queries=[character * 160 for character in "abcd"]), max_chars=300
    )
    assert not evidence["excerpts"]
    assert len(json.dumps(evidence)) <= 300
