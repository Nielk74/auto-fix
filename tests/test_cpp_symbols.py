"""Syntactic retrieval fixtures, independent of benchmark mutations or model output."""

from __future__ import annotations

from auto_fix.cpp_symbols import definition_ranges


def excerpt(source: str, scope: dict) -> str:
    return "".join(source.splitlines(keepends=True)[scope["start_line"] - 1 : scope["end_line"]])


def test_definition_beats_earlier_comment_declaration_and_call_site():
    source = """// adjust is used below; the comment is not its implementation.
int adjust(int);
int caller() { return adjust(2); }

int adjust(int value) {
  return value + 1;
}
"""
    scopes = definition_ranges(source, "adjust", 1)
    assert len(scopes) == 1
    assert scopes[0]["kind"] == "function_definition"
    assert scopes[0]["start_line"] == 5 and scopes[0]["end_line"] == 7
    assert "return value + 1;" in excerpt(source, scopes[0])
    assert "caller" not in excerpt(source, scopes[0])


def test_long_function_is_returned_whole_instead_of_a_fixed_line_window():
    source = "int walk(int value) {\n" + "  value += 1;\n" * 180 + "  return value;\n}\n"
    scope = definition_ranges(source, "walk", 1)[0]
    assert scope["start_line"] == 1 and scope["end_line"] == 183
    assert excerpt(source, scope) == source


def test_template_header_inline_specifier_and_operator_body_are_retained():
    source = """template <class T>
inline T twice(T value) {
  return value + value;
}
struct Amount {};
inline Amount operator-(Amount value) {
  return value;
}
inline Amount operator-(Amount left, Amount right) {
  return left;
}
inline Amount& operator-=(Amount& left, Amount right) {
  return left;
}
"""
    template = definition_ranges(source, "twice")[0]
    assert template["start_line"] == 1 and template["focus_line"] == 2
    assert excerpt(source, template).startswith("template <class T>\ninline")
    operators = definition_ranges(source, "operator-", 10)
    assert len(operators) == 2
    assert operators[0]["focus_line"] == 9
    assert all(item["name"] == "operator-" for item in operators)
    assert all("operator-=" not in excerpt(source, item) for item in operators)


def test_qualified_methods_and_constructor_overloads_use_nearest_requested_line():
    source = """namespace demo {
struct Box {
  Box() {}
  Box(int value) : value_(value) {}
  int get() const { return value_; }
  int value_ = 0;
};
int unrelated() { return 2; }
}
"""
    constructors = definition_ranges(source, "Box::Box", 4)
    assert [item["focus_line"] for item in constructors] == [4, 3]
    assert constructors[0]["name"] == "demo::Box::Box"
    method = definition_ranges(source, "demo::Box::get")[0]
    assert method["scope"] == "demo::Box" and method["focus_line"] == 5
    assert "unrelated" not in excerpt(source, method)


def test_line_only_lookup_returns_enclosing_function_including_nested_braces_and_lambda():
    source = """int first() { return 1; }
int outer(int value) {
  auto plus = [](int x) { return x + 1; };
  if (value) { return plus(value); }
  return 0;
}
"""
    scopes = definition_ranges(source, None, 4)
    assert len(scopes) == 1 and scopes[0]["name"] == "outer"
    assert scopes[0]["start_line"] == 2 and scopes[0]["end_line"] == 6


def test_class_symbol_can_include_small_constructor_and_call_operator_contract():
    source = """template <typename Char>
struct width_handler {
  explicit width_handler(int width) : width_(width) {}
  int operator()() const { return width_; }
  int width_;
};
"""
    for symbol in ("width_handler", "struct width_handler"):
        scope = definition_ranges(source, symbol)[0]
        assert scope["kind"] == "struct_specifier" and scope["start_line"] == 1
        assert scope["end_line"] == 6
        assert "explicit width_handler" in excerpt(source, scope)
        assert "operator()" in excerpt(source, scope)
    operator = definition_ranges(source, "width_handler::operator()")[0]
    assert operator["kind"] == "function_definition" and operator["start_line"] == 4


def test_huge_class_does_not_expand_into_thousands_of_unrelated_lines():
    source = "struct Huge {\n  Huge() {}\n  int operator()() { return 1; }\n"
    source += "\n".join(f"  int member{number};" for number in range(200)) + "\n};\n"
    scopes = definition_ranges(source, "Huge")
    assert len(scopes) == 2
    assert {scope["name"] for scope in scopes} == {"Huge::Huge", "Huge::operator()"}
    assert all(scope["end_line"] - scope["start_line"] < 5 for scope in scopes)


def test_preprocessor_branches_are_source_not_semantically_resolved():
    source = """#if defined(USE_FIRST)
int convert(int value) { return value; }
#else
int convert(int value) { return -value; }
#endif
"""
    scopes = definition_ranges(source, "convert", 4)
    assert [scope["focus_line"] for scope in scopes] == [4, 2]
    assert all(scope["start_line"] == scope["end_line"] for scope in scopes)


def test_leading_attribute_macro_does_not_hide_valid_operator_body():
    source = """ATTRIBUTE_PURE constexpr Amount operator-(Amount value) {
  return negate(value);
}
"""
    scope = definition_ranges(source, "operator-")[0]
    assert scope["name"] == "operator-" and scope["end_line"] == 3
    assert not scope["body_has_error"]
    assert "return negate(value);" in excerpt(source, scope)


def test_comments_quoted_braces_and_raw_strings_do_not_end_the_scope():
    source = """const char* render() {
  // Ignore this closing brace: }
  const char* text = R"mark({ nested } \" quoted \" })mark";
  return text; /* } */
}
int after() { return 0; }
"""
    scope = definition_ranges(source, "render")[0]
    assert scope["end_line"] == 5
    assert "return text;" in excerpt(source, scope)
    assert "after" not in excerpt(source, scope)


def test_utf8_and_crlf_lines_are_measured_from_original_byte_offsets():
    source = (
        "// Résumé: 日本語\r\nint first() { return 0; }\r\nint café() {\r\n  return 1;\r\n}\r\n"
    )
    scope = definition_ranges(source, "café")[0]
    assert scope["start_line"] == 3 and scope["end_line"] == 5
    assert excerpt(source, scope).endswith("}\r\n")


def test_current_source_changes_invalidate_index_and_returned_records_cannot_poison_cache():
    first = "int repair() { return 0; }\n"
    record = definition_ranges(first, "repair")[0]
    record["end_line"] = 9000
    assert definition_ranges(first, "repair")[0]["end_line"] == 1
    changed = "int repair() {\n  return 1;\n}\n"
    assert definition_ranges(changed, "repair")[0]["end_line"] == 3
    assert "return 1;" in excerpt(changed, definition_ranges(changed, "repair")[0])


def test_declarations_constants_missing_symbols_and_empty_source_use_safe_fallback():
    source = "int announced(int);\nconstexpr int buffer_size = 512;\n"
    assert definition_ranges(source, "announced") == []
    assert definition_ranges(source, "buffer_size") == []
    assert definition_ranges(source, "missing") == []
    assert definition_ranges(source, None, 999) == []
    assert definition_ranges(source, "") == []
    assert definition_ranges("", "anything") == []


def test_conversion_operator_destructor_and_reference_declarator():
    source = """struct Item {
  ~Item() {}
  operator bool() const { return true; }
  Item& operator+=(const Item& other) { return *this; }
};
"""
    assert definition_ranges(source, "Item::~Item")[0]["focus_line"] == 2
    assert definition_ranges(source, "operator bool")[0]["focus_line"] == 3
    assert definition_ranges(source, "operator+=")[0]["focus_line"] == 4


def test_literal_return_type_and_signature_can_match_definition_header():
    source = "int parse(int value) { return value; }\n"
    assert definition_ranges(source, "int parse")[0]["focus_line"] == 1
    assert definition_ranges(source, "parse(int value)")[0]["focus_line"] == 1


def test_oversized_source_uses_fallback_without_an_unbounded_index():
    source = " " * 2_000_001
    assert definition_ranges(source, "function") == []
