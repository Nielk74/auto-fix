"""Deterministic C++ definition ranges for bounded, read-only source inspection.

Only the exact supplied source is parsed. This is syntactic navigation rather
than overload resolution or preprocessing. Native nodes never escape the index;
records contain original-source, 1-based line ranges and uncertainty metadata.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import tree_sitter_cpp
from tree_sitter import Language, Parser, Query, QueryCursor

_LANGUAGE = Language(tree_sitter_cpp.language())
_QUERY = Query(
    _LANGUAGE,
    "(function_definition) @function\n(class_specifier) @class\n(struct_specifier) @class",
)
_MAX_SOURCE_BYTES = 2_000_000
_MAX_CLASS_LINES = 120
_MAX_CLASS_BYTES = 8000
_MAX_MATCHES = 8


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _text(source: bytes, node) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8") if node else ""


def _name(source: bytes, declarator) -> str:
    """Follow the declarator spine, excluding parameter identifiers and call sites."""
    current = declarator
    for _ in range(20):
        if current is None:
            return ""
        if current.type == "operator_cast":
            return "operator " + _text(source, current.child_by_field_name("type"))
        if current.type in {
            "identifier",
            "field_identifier",
            "type_identifier",
            "qualified_identifier",
            "operator_name",
            "destructor_name",
            "template_function",
        }:
            return _text(source, current)
        child = current.child_by_field_name("declarator")
        if child is None and current.type.endswith("_declarator"):
            child = next(
                (
                    candidate
                    for candidate in current.named_children
                    if candidate.type.endswith("_declarator")
                    or candidate.type
                    in {"identifier", "field_identifier", "qualified_identifier", "operator_name"}
                ),
                None,
            )
        current = child
    return ""


def _qualified(source: bytes, node, local: str) -> tuple[str, str]:
    names = []
    parent = node.parent
    for _ in range(100):
        if parent is None:
            break
        if parent.type in {"namespace_definition", "class_specifier", "struct_specifier"}:
            name = _text(source, parent.child_by_field_name("name"))
            if name:
                names.append(name)
        parent = parent.parent
    scope = "::".join(reversed(names))
    return (f"{scope}::{local}" if scope else local), scope


def _extent(node):
    while node.parent is not None and node.parent.type == "template_declaration":
        node = node.parent
    return node


@dataclass(frozen=True)
class _Scope:
    kind: str
    name: str
    local_name: str
    owner: str
    declarator: str
    header: str
    start: int
    end: int
    focus: int
    start_byte: int
    end_byte: int
    has_error: bool
    body_has_error: bool

    def record(self) -> dict:
        return {
            "kind": self.kind,
            "name": self.name,
            "scope": self.owner,
            "declarator": self.declarator,
            "start_line": self.start,
            "end_line": self.end,
            "focus_line": self.focus,
            "has_error": self.has_error,
            "body_has_error": self.body_has_error,
        }


@lru_cache(maxsize=8)
def _index(source: str) -> tuple[_Scope, ...]:
    if len(source) > _MAX_SOURCE_BYTES:
        return ()
    raw = source.encode("utf-8")
    if len(raw) > _MAX_SOURCE_BYTES:
        return ()
    parser = Parser(_LANGUAGE)
    tree = parser.parse(raw)
    cursor = QueryCursor(_QUERY)
    captured = cursor.captures(tree.root_node)
    scopes = []
    nodes = [*captured.get("function", []), *captured.get("class", [])]
    for node in sorted(nodes, key=lambda item: item.start_byte):
        if len(scopes) >= 10_000:
            break
        body = node.child_by_field_name("body")
        if body is None:
            continue
        if node.type == "function_definition":
            declarator = node.child_by_field_name("declarator")
            local = _name(raw, declarator)
            # Deleted/defaulted declarations have no executable brace-delimited body.
            if body.type not in {"compound_statement", "try_statement"}:
                continue
        else:
            declarator = node.child_by_field_name("name")
            local = _text(raw, declarator)
        if not local or declarator is None:
            continue
        if raw[body.end_byte - 1 : body.end_byte] != b"}":
            continue
        extent = _extent(node)
        name, owner = _qualified(raw, node, local)
        # Use byte offsets, avoiding the 0.26 Point API regression observed in research.
        scopes.append(
            _Scope(
                kind=node.type,
                name=name,
                local_name=local,
                owner=owner,
                declarator=_text(raw, declarator),
                header=raw[node.start_byte : body.start_byte].decode("utf-8"),
                start=raw.count(b"\n", 0, extent.start_byte) + 1,
                end=raw.count(b"\n", 0, extent.end_byte) + 1,
                focus=raw.count(b"\n", 0, declarator.start_byte) + 1,
                start_byte=extent.start_byte,
                end_byte=extent.end_byte,
                has_error=node.has_error,
                body_has_error=body.has_error,
            )
        )
    return tuple(scopes)


def _small_class(scope: _Scope) -> bool:
    return (
        scope.kind != "function_definition"
        and scope.end - scope.start + 1 <= _MAX_CLASS_LINES
        and scope.end_byte - scope.start_byte <= _MAX_CLASS_BYTES
    )


def _distance(scope: _Scope, line: int | None) -> int:
    if line is None:
        return 0
    return (
        0
        if scope.start <= line <= scope.end
        else min(abs(line - scope.start), abs(line - scope.end))
    )


def _match(scope: _Scope, symbol: str) -> int | None:
    query = _compact(symbol)
    qualified = _compact(scope.name)
    local = _compact(scope.local_name)
    short = local.rsplit("::", 1)[-1]
    if query == qualified or qualified.endswith("::" + query):
        return 0
    if query == local or query == short:
        return 1
    # Simple symbol requests must not match prefixes (operator- versus operator-=,
    # or parse_header versus unrelated_parse_header).
    if re.fullmatch(r"[A-Za-z_]\w*", symbol.strip()) or re.fullmatch(
        r"operator[^A-Za-z0-9_:]+", query
    ):
        return None
    if "::" in query and query.rsplit("::", 1)[-1] == short:
        return 3  # A scope/alias mismatch remains explicitly a candidate, not resolution.
    if query in _compact(scope.declarator) or query in _compact(scope.header):
        return 2
    return None


def definition_ranges(
    source: str, symbol: str | None = None, line: int | None = None
) -> list[dict]:
    """Locate definitions before references; return [] for unsupported/unknown symbols.

    Function/template/operator extents are complete syntax-node ranges, with
    parser error flags preserved. The caller retains path safety and JSON-budget
    enforcement and must mark any clipped range partial. A matching small class
    can include its constructor/operator contract; large classes return bounded
    constructor/operator members rather than the entire class.
    """
    if not isinstance(source, str):
        raise TypeError("C++ source must be decoded text")
    if symbol is not None and not isinstance(symbol, str):
        raise TypeError("C++ symbol must be a string or None")
    if line is not None and (type(line) is not int or line < 0):
        raise ValueError("Source line must be nonnegative or None")
    line = line or None
    scopes = _index(source)
    if symbol and symbol.strip():
        symbol = re.sub(r"^\s*(?:class|struct)\s+", "", symbol).strip()
        classes = [
            scope
            for scope in scopes
            if scope.kind != "function_definition" and _match(scope, symbol) in (0, 1)
        ]
        small_classes = [scope for scope in classes if _small_class(scope)]
        if small_classes:
            chosen = sorted(small_classes, key=lambda scope: (_distance(scope, line), scope.start))
            return [scope.record() for scope in chosen[:_MAX_MATCHES]]
        matches = [
            (score, scope)
            for scope in scopes
            if scope.kind == "function_definition" and (score := _match(scope, symbol)) is not None
        ]
        if classes:
            # A huge named class still has useful bounded constructor/operator scopes.
            names = {_compact(scope.name) for scope in classes}
            existing = {scope for _, scope in matches}
            matches.extend(
                [
                    (2, scope)
                    for scope in scopes
                    if scope.kind == "function_definition"
                    and scope not in existing
                    and _compact(scope.owner) in names
                    and (
                        scope.local_name.rsplit("::", 1)[-1].startswith("operator")
                        or scope.local_name == scope.owner.rsplit("::", 1)[-1]
                    )
                ]
            )
        chosen = sorted(
            matches, key=lambda pair: (pair[0], _distance(pair[1], line), pair[1].start)
        )
        return [scope.record() for _, scope in chosen[:_MAX_MATCHES]]
    if line is None:
        return []
    enclosing = [
        scope
        for scope in scopes
        if scope.start <= line <= scope.end
        and (scope.kind == "function_definition" or _small_class(scope))
    ]
    chosen = sorted(
        enclosing, key=lambda scope: (scope.kind != "function_definition", scope.end - scope.start)
    )
    return [scope.record() for scope in chosen[:1]]
