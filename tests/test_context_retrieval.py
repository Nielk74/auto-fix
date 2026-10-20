from __future__ import annotations

import json

from auto_fix.context import retrieve_sources


def retrieve(files, *, signals, changed_paths=(), max_chars=12000):
    return retrieve_sources(
        list(files),
        files.__getitem__,
        changed_paths=set(changed_paths),
        signals=signals,
        max_chars=max_chars,
    )


def excerpts(items, path):
    return "\n".join(
        excerpt["content"] for item in items if item["path"] == path for excerpt in item["excerpts"]
    )


def test_large_header_retrieves_symbol_in_middle_and_relevant_test():
    header = (
        "// Copyright and unrelated declarations\n" * 3400
        + "inline bool IsReadyForDispatch(int pending) {\n  return pending > 1;\n}\n"
        + "// Further unrelated implementation\n" * 3400
    )
    files = {
        "engine/runtime/dispatch.h": header,
        "engine/runtime/dispatch_test.cc": (
            '#include "engine/runtime/dispatch.h"\n'
            "TEST(DispatchTest, OnePendingItemIsReady) {\n"
            "  EXPECT_TRUE(IsReadyForDispatch(1));\n}\n"
        ),
        "engine/platform/a_feature.cc": "int unrelated_platform_feature = 0;\n" * 200,
    }
    result = retrieve(
        files,
        signals=["DispatchTest.OnePendingItemIsReady", "IsReadyForDispatch(1) was false"],
        changed_paths={"engine/platform/a_feature.cc"},
        max_chars=6500,
    )
    assert "return pending > 1;" in excerpts(result, "engine/runtime/dispatch.h")
    assert "EXPECT_TRUE(IsReadyForDispatch(1));" in excerpts(
        result, "engine/runtime/dispatch_test.cc"
    )
    assert len(json.dumps(result)) <= 6500


def test_related_includes_outweigh_unrelated_recent_commit_files():
    files = {
        f"src/noise/feature_{index:03d}.cc": "int unrelated_feature = 0;\n" * 100
        for index in range(120)
    }
    files.update(
        {
            "lib/cache/eviction_test.cc": (
                '#include "lib/cache/internal/policy.h"\n'
                "TEST(EvictionTest, MostRecentEntrySurvives) {\n"
                "  EXPECT_EQ(KeepRecent(entries), newest);\n}\n"
            ),
            "lib/cache/internal/policy.h": "inline int KeepRecent(int entries) { return 0; }\n",
        }
    )
    result = retrieve(
        files,
        signals=["EvictionTest.MostRecentEntrySurvives"],
        changed_paths={path for path in files if path.startswith("src/noise/")},
        max_chars=4500,
    )
    assert result[0]["path"] == "lib/cache/eviction_test.cc"
    assert "return 0;" in excerpts(result, "lib/cache/internal/policy.h")


def test_windows_stack_path_and_line_anchor_the_exact_source_window():
    lines = [f"// declaration {i}\r\n" for i in range(900)]
    lines[710] = "  return DecodeRecord(value, false);\r\n"
    content = "".join(lines)
    result = retrieve(
        {"engine/storage/reader.cc": content, "engine/aaa.cc": "int irrelevant;\n"},
        signals=[r"C:\agent\work\checkout\engine\storage\reader.cc(711): assertion failed"],
        max_chars=3500,
    )
    item = next(item for item in result if item["path"] == "engine/storage/reader.cc")
    assert any(
        excerpt["start_line"] <= 711 <= excerpt["end_line"]
        and "return DecodeRecord(value, false);\r\n" in excerpt["content"]
        for excerpt in item["excerpts"]
    )
    assert all(excerpt["content"] in content for excerpt in item["excerpts"])


def test_failing_test_calls_locate_implementation_inside_included_long_header():
    files = {
        "tests/calendar_test.cc": (
            '#include "calendar/conversion.h"\n'
            "TEST(CalendarTest, BoundaryDay) {\n"
            "  EXPECT_EQ(ConvertGregorianDate(2000, 2, 29), expected_date);\n}\n"
        ),
        "calendar/conversion.h": "// unrelated calendar documentation\n" * 4000
        + "inline int ConvertGregorianDate(int year, int month, int day) {\n"
        + "  return day - 1;\n}\n"
        + "// unrelated calendar declarations\n" * 4000,
    }
    result = retrieve(files, signals=["CalendarTest.BoundaryDay"], max_chars=4500)
    assert "return day - 1;" in excerpts(result, "calendar/conversion.h")


def test_public_header_links_failing_test_to_separate_implementation_source():
    files = {
        "tests/retry_test.cc": (
            '#include "net/retry.h"\n'
            "TEST(NetworkTest, TransientStatus) {\n"
            "  EXPECT_TRUE(ShouldRetryStatus(500));\n}\n"
        ),
        "include/net/retry.h": "bool ShouldRetryStatus(int status);\n",
        "src/net/retry.cc": "// unrelated networking implementation\n" * 4000
        + "bool ShouldRetryStatus(int status) { return status > 500; }\n",
    }
    result = retrieve(files, signals=["NetworkTest.TransientStatus"], max_chars=4500)
    assert "return status > 500;" in excerpts(result, "src/net/retry.cc")


def test_include_graph_is_bounded_and_does_not_read_untracked_paths():
    files = {
        "tests/parser_test.cc": '#include "parser/a.h"\nTEST(ParserTest, EmptyInput) {}\n',
        "parser/a.h": '#include "b.h"\n#include "../../secret.h"\nint Parse();\n',
        "parser/b.h": '#include "a.h"\nint ParseHelper();\n',
    }
    result = retrieve(files, signals=["ParserTest.EmptyInput"], max_chars=5000)
    assert {item["path"] for item in result} == set(files)
    assert len(result) == len({item["path"] for item in result})


def test_source_budget_accounts_for_json_escaping_and_unicode():
    files = {
        "src/codec.cc": (
            '// Unicode: é and quotation marks: "\\\\"\n' * 300
            + "int DecodeCodePoint(int input) { return input - 1; }\n"
        )
    }
    result = retrieve(files, signals=["DecodeCodePoint"], max_chars=1700)
    assert "DecodeCodePoint" in excerpts(result, "src/codec.cc")
    assert len(json.dumps(result)) <= 1700
    for item in result:
        for excerpt in item["excerpts"]:
            assert excerpt["content"] in files[item["path"]]


def test_feedback_symbol_refreshes_context_after_an_unsuccessful_attempt():
    files = {
        "lib/data/types.h": "using ItemId = int;\n" * 800
        + "inline bool IsReservedItem(ItemId id) { return id == 0; }\n",
        "lib/data/types_test.cc": "TEST(ItemTest, ReservedValues) {}\n",
    }
    result = retrieve(
        files,
        signals=["ItemTest.ReservedValues", "types_test.cc:99: IsReservedItem(-1) was false"],
        max_chars=3500,
    )
    assert "id == 0" in excerpts(result, "lib/data/types.h")


def test_failure_location_and_implementation_unit_outrank_many_shared_container_headers():
    files = {
        f"containers/shared_{index}.h": (
            "// tokenize windows whitespace status metadata code records types\n" * 350
        )
        for index in range(18)
    }
    files.update(
        {
            "lib/ingest/tokenize_test.cc": (
                "".join(f'#include "containers/shared_{index}.h"\n' for index in range(18))
                + '#include "lib/ingest/tokenize.h"\n'
                + "TEST(TokenizeTest, WindowsWhitespace) {\n"
                + '  EXPECT_EQ(Tokenize("a\\rb"), expected_records);\n}\n'
            ),
            "lib/ingest/tokenize.h": "int Tokenize(const char* input);\n",
            "lib/ingest/tokenize.cc": (
                '#include "lib/ingest/tokenize.h"\n'
                'int Tokenize(const char* input) { return SplitAt(input, " \\n"); }\n'
            ),
        }
    )
    result = retrieve(
        files,
        signals=[
            "TokenizeTest.WindowsWhitespace",
            "D:/BuildAgent/work/project/lib/ingest/tokenize_test.cc:21: assertion failed\n"
            "Tokenize returned records with an unexpected carriage return\n"
            "Agent: Windows; branch: master; status: failure; metadata: test records",
        ],
        max_chars=5500,
    )
    assert result[0]["path"] == "lib/ingest/tokenize_test.cc"
    paths = [item["path"] for item in result]
    assert paths.index("lib/ingest/tokenize.cc") < min(
        (index for index, path in enumerate(paths) if path.startswith("containers/")),
        default=len(paths),
    )
    assert "SplitAt" in excerpts(result, "lib/ingest/tokenize.cc")


def test_testcase_concepts_locate_middle_of_parser_despite_generic_entry_point_and_keywords():
    implementation = (
        "// decoder status metadata code: declarations not related to the failure\n" * 2200
        + "// <qualified-record-type> ::= <record-type> [<reference-qualifier>]\n"
        + "bool ParseRecordType(State* state) {\n"
        + "  return ParseReferenceQualifier(state, false);\n}\n"
        + "// decoder status metadata code: other declarations\n" * 2200
        + "bool DecodeRecord(const char* input) { return ParseRecord(input); }\n"
    )
    files = {
        "lib/decoder_test.cc": (
            '#include "lib/decoder.h"\n'
            "TEST(Decoder, QualifiedRecordTypes) {\n"
            "  EXPECT_TRUE(DecodeRecord(reference_qualified_record));\n"
            "  static_assert(sizeof(Record) > 1);\n}\n"
        ),
        "lib/decoder.h": "bool DecodeRecord(const char* input);\n",
        "lib/decoder.cc": implementation,
    }
    result = retrieve(
        files,
        signals=[
            "Decoder.QualifiedRecordTypes",
            "C:/agent/checkout/lib/decoder_test.cc:3: assertion failed\n"
            "Decoder returned false. Agent: Windows; status: failure; metadata: native code",
        ],
        max_chars=7000,
    )
    assert "ParseReferenceQualifier(state, false)" in excerpts(result, "lib/decoder.cc")
    assert all(
        excerpt["content"] in implementation
        for item in result
        if item["path"] == "lib/decoder.cc"
        for excerpt in item["excerpts"]
    )
