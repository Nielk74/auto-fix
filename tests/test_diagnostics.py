from auto_fix.diagnostics import failure_diagnostics


def test_passing_only_output_does_not_displace_fresh_structured_assertions():
    assert failure_diagnostics("[       OK ] OtherTest.Works (0 ms)\n" * 9000) == ""


def test_unrecognized_output_keeps_head_and_tail_within_exact_budget():
    evidence = failure_diagnostics("BEGIN " + "x" * 20000 + " END", max_chars=1024)
    assert len(evidence) == 1024
    assert evidence.startswith("BEGIN ")
    assert evidence.endswith(" END")


def test_failed_assertion_survives_thousands_of_later_passing_tests():
    text = (
        "codec_test.cc:87: Failure\nExpected equality of these values:\n"
        '  Decode("TQ==")\n    Which is: "N"\n  "M"\n'
        "[  FAILED  ] CodecTest.Padding\n"
        + "[       OK ] OtherTest.Works (0 ms)\n" * 4000
        + "[  PASSED  ] 4000 tests.\n[  FAILED  ] 1 test, listed below:\n"
    )
    evidence = failure_diagnostics(text)
    assert len(evidence) <= 6000
    assert "codec_test.cc:87" in evidence
    assert 'Decode("TQ==")' in evidence
    assert 'Which is: "N"' in evidence
    assert "CodecTest.Padding" in evidence


def test_windows_compiler_error_keeps_source_location_and_candidate_context():
    text = (
        "[2/48] Building CXX object unrelated.obj\n"
        "C:\\worker\\src\\format.cc(195): error C2664: cannot convert argument 1\n"
        "note: candidate function expects basic_string_view<char>\n"
        "while trying to match the argument list '(const wchar_t *)'\n"
        + "[3/48] Building CXX object another.obj\n" * 900
        + "ninja: build stopped: subcommand failed.\n"
    )
    evidence = failure_diagnostics(text)
    assert "format.cc(195): error C2664" in evidence
    assert "basic_string_view<char>" in evidence
    assert "const wchar_t *" in evidence
    assert "ninja: build stopped" in evidence
