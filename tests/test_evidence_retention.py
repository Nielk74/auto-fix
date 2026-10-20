"""Toy-source retention checks; no benchmark mutations or model outputs are used."""

from __future__ import annotations

import copy
import json

import pytest

from auto_fix.investigation import invalidate_evidence, merge_evidence


def lines(count=240, width=50, ending="\n"):
    return [
        f"int toy_value_{number} = {number}; // " + "x" * width + ending
        for number in range(1, count + 1)
    ]


def excerpt(path, source, start, end, *, focus=None, kind="read"):
    return {
        "path": path,
        "start_line": start,
        "end_line": end,
        "content": "".join(source[start - 1 : end]),
        "kind": kind,
        "focus_line": focus or (start + end) // 2,
    }


def batch(*items, queries=(), errors=()):
    return {"queries": list(queries), "excerpts": list(items), "errors": list(errors)}


def content(result):
    return "\n".join(item["content"] for item in result["excerpts"])


def assert_exact(result, sources):
    seen = set()
    for item in result["excerpts"]:
        start, end, path = item["start_line"], item["end_line"], item["path"]
        assert item["content"] == "".join(sources[path][start - 1 : end])
        for line in range(start, end + 1):
            assert (path, line) not in seen, "Overlaps must not spend the context budget twice"
            seen.add((path, line))


def test_retains_distinct_earlier_and_newer_functions_instead_of_evicting_a_batch():
    source = lines(width=80)
    source[49] = "int AlphaBoundary(int value) { return value + 1; }\n"
    source[179] = "int BetaBoundary(int value) { return value - 1; }\n"
    previous = batch(excerpt("src/units.cc", source, 15, 85, focus=50))
    current = batch(excerpt("src/units.cc", source, 145, 215, focus=180))
    assert len(json.dumps([previous, current])) > 12000
    result = merge_evidence([previous], current)
    assert "int AlphaBoundary(" in content(result)
    assert "int BetaBoundary(" in content(result)
    assert len(json.dumps(result)) <= 18000
    assert_exact(result, {"src/units.cc": source})


def test_overlapping_and_adjacent_windows_coalesce_without_repeating_source():
    source = lines(width=5)
    previous = batch(excerpt("src/units.cc", source, 1, 70, focus=35))
    current = batch(
        excerpt("src/units.cc", source, 50, 110, focus=80),
        excerpt("src/units.cc", source, 111, 120, focus=115, kind="search"),
    )
    result = merge_evidence([previous, previous], current)
    assert len(result["excerpts"]) == 1
    assert result["excerpts"][0]["start_line"] == 1
    assert result["excerpts"][0]["end_line"] == 120
    assert result["excerpts"][0]["kind"] == "read"
    assert_exact(result, {"src/units.cc": source})


def test_compaction_preserves_distinct_requested_anchors_with_exact_disjoint_ranges():
    source = lines(width=70)
    source[59] = "int AlphaBoundary() { return 1; }\n"
    source[114] = "int BetaBoundary() { return 2; }\n"
    previous = batch(excerpt("src/units.cc", source, 25, 95, focus=60))
    current = batch(excerpt("src/units.cc", source, 80, 150, focus=115))
    result = merge_evidence(previous, current, max_chars=2500)
    assert "int AlphaBoundary(" in content(result)
    assert "int BetaBoundary(" in content(result)
    assert len(json.dumps(result)) <= 2500
    assert_exact(result, {"src/units.cc": source})


def test_explicit_reads_and_distinct_paths_survive_many_large_search_hits():
    source = lines(width=60)
    source[49] = "int ReadContractAlpha() { return 1; }\n"
    second = lines(width=60)
    second[49] = "int ReadContractBeta() { return 2; }\n"
    previous = batch(excerpt("src/alpha.cc", source, 15, 85, focus=50))
    current = batch(
        excerpt("include/beta.h", second, 15, 85, focus=50),
        *[
            excerpt(f"src/noise_{number}.cc", lines(width=80), 10, 30, focus=20, kind="search")
            for number in range(20)
        ],
    )
    result = merge_evidence(previous, current, max_chars=5000)
    assert "ReadContractAlpha" in content(result)
    assert "ReadContractBeta" in content(result)
    assert len(json.dumps(result)) <= 5000


def test_edited_files_lose_all_prior_anchors_but_fresh_evidence_is_allowed():
    previous = batch(
        excerpt("src/edited.cc", ["old source\n"] * 5, 1, 5),
        excerpt("src/untouched.cc", ["stable source\n"] * 5, 1, 5),
        errors=[{"path": "src/edited.cc", "error": "Previously absent symbol"}],
    )
    invalidated = invalidate_evidence([previous], {"src/edited.cc"})
    assert [item["path"] for item in invalidated["excerpts"]] == ["src/untouched.cc"]
    assert not invalidated["errors"]
    current = batch(
        excerpt("src/edited.cc", ["new source\n"] * 5, 1, 5),
        errors=[{"path": "src/edited.cc", "error": "New read error"}],
    )
    result = merge_evidence(previous, current, changed_paths={"src/edited.cc"})
    assert "old source" not in content(result)
    assert "new source" in content(result) and "stable source" in content(result)
    assert result["errors"] == [{"path": "src/edited.cc", "error": "New read error"}]


def test_conflicting_new_overlap_discards_all_older_regions_for_that_file():
    previous = batch(
        excerpt("src/changed.cc", ["old\n"] * 20, 1, 5),
        excerpt("src/changed.cc", ["old\n"] * 20, 15, 20),
        excerpt("src/stable.cc", ["stable\n"] * 5, 1, 5),
    )
    current = batch(excerpt("src/changed.cc", ["new\n"] * 20, 18, 20))
    result = merge_evidence(previous, current)
    assert "old" not in content(result)
    assert "new" in content(result) and "stable" in content(result)


def test_crlf_unicode_and_inputs_are_preserved_without_mutation():
    source = lines(count=80, width=1, ending="\r\n")
    source[39] = 'const char* marker = "λ😀";\r\n'
    previous = batch(excerpt("src/utf8.cc", source, 5, 55, focus=40))
    current = batch(excerpt("src/utf8.cc", source, 35, 70, focus=40))
    before = copy.deepcopy([previous, current])
    result = merge_evidence(previous, current, max_chars=3000)
    assert "λ😀" in content(result)
    assert "\r\n" in content(result)
    assert [previous, current] == before
    assert len(json.dumps(result)) <= 3000
    assert_exact(result, {"src/utf8.cc": source})


def test_metadata_is_deduplicated_newest_wins_and_counts_toward_json_budget():
    previous = batch(
        queries=[{"query": "ReadContract", "matches_returned_or_seen": 1}],
        errors=[{"error": "old " + "λ" * 3000}],
    )
    current = batch(
        queries=[{"query": "ReadContract", "matches_returned_or_seen": 2}],
        errors=[{"error": "new " + "λ" * 3000}],
    )
    result = merge_evidence(previous, current, max_chars=300)
    assert result["queries"] == [{"query": "ReadContract", "matches_returned_or_seen": 2}]
    assert len(json.dumps(result)) <= 300


def test_full_excerpts_are_not_compacted_when_the_complete_set_fits():
    source = lines(count=100, width=50)
    result = merge_evidence(
        batch(excerpt("src/long.cc", source, 1, 100)),
        batch(excerpt("src/short.cc", source, 1, 3)),
        max_chars=12000,
    )
    longest = next(item for item in result["excerpts"] if item["path"] == "src/long.cc")
    assert (longest["start_line"], longest["end_line"]) == (1, 100)


def test_repeated_merges_keep_exact_ranges_and_deduplicate_prior_compacted_evidence():
    source = lines(width=30)
    result = batch()
    for start in (1, 20, 40, 90, 130, 170):
        result = merge_evidence(
            [result], batch(excerpt("src/units.cc", source, start, start + 60)), max_chars=3500
        )
        assert len(json.dumps(result)) <= 3500
        assert_exact(result, {"src/units.cc": source})


@pytest.mark.parametrize("budget", [0, 99, True, "18000"])
def test_invalid_json_budget_is_rejected(budget):
    with pytest.raises(ValueError, match="at least 100"):
        merge_evidence([], batch(), max_chars=budget)


def test_malformed_line_coordinates_are_not_relabelled_as_exact_source():
    malformed = {
        "path": "src/units.cc",
        "start_line": 1,
        "end_line": 8,
        "content": "one line\n",
        "kind": "read",
    }
    with pytest.raises(ValueError, match="exact source line bounds"):
        merge_evidence([], batch(malformed))
