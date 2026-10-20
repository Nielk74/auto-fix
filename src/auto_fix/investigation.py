"""Bounded, read-only evidence gathering for model-directed investigation."""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from auto_fix.models import Investigation

if TYPE_CHECKING:
    from auto_fix.workspace import Workspace

SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".h",
    ".hh",
    ".hpp",
    ".hxx",
    ".inc",
    ".inl",
    ".ipp",
    ".tpp",
}


@dataclass
class _Window:
    path: str
    lines: dict[int, str]
    focus: set[int]
    reads: set[int]
    order: int


def _batches(evidence: dict | list[dict] | None) -> list[dict]:
    values = [evidence] if isinstance(evidence, dict) else list(evidence or [])
    if any(not isinstance(value, dict) for value in values):
        raise ValueError("Evidence batches must be objects")
    return values


def _window(excerpt: dict, order: int) -> _Window:
    start, end = excerpt["start_line"], excerpt["end_line"]
    lines = excerpt["content"].splitlines(keepends=True)
    if type(start) is not int or type(end) is not int or start < 1 or end < start:
        raise ValueError("Evidence must have valid source line bounds")
    if len(lines) != end - start + 1:
        raise ValueError("Evidence content must match its exact source line bounds")
    focus = set(excerpt.get("focus_lines", [excerpt.get("focus_line", (start + end) // 2)]))
    reads = set(excerpt.get("read_lines", focus if excerpt.get("kind") == "read" else []))
    if any(type(line) is not int or not start <= line <= end for line in focus | reads):
        raise ValueError("Evidence focus must fall inside its source window")
    return _Window(excerpt["path"], dict(enumerate(lines, start)), focus, reads, order)


def _coalesce(windows: list[_Window]) -> list[_Window]:
    result: list[_Window] = []
    for window in sorted(windows, key=lambda value: (value.path, min(value.lines))):
        if (
            result
            and result[-1].path == window.path
            and min(window.lines) <= max(result[-1].lines) + 1
        ):
            current = result[-1]
            current.lines.update(window.lines)
            current.focus.update(window.focus)
            current.reads.update(window.reads)
            current.order = max(current.order, window.order)
        else:
            result.append(window)
    return result


def _segments(window: _Window, selected: set[int]) -> list[dict]:
    ranges: list[list[int]] = []
    for line in sorted(selected):
        if ranges and ranges[-1][-1] + 1 == line:
            ranges[-1].append(line)
        else:
            ranges.append([line])
    return [
        {
            "path": window.path,
            "start_line": lines[0],
            "end_line": lines[-1],
            "content": "".join(window.lines[line] for line in lines),
            "kind": "read" if window.reads.intersection(lines) else "search",
            "focus_lines": sorted(window.focus.intersection(lines)),
            "read_lines": sorted(window.reads.intersection(lines)),
        }
        for lines in ranges
    ]


def _compact(window: _Window, limit: int) -> list[dict]:
    full = _segments(window, set(window.lines))
    if len(json.dumps(full)) <= limit:
        return full
    # Keep exact neighborhoods around distinct requested locations. A single
    # long merged region must not displace every other previously read function.
    anchors = sorted(window.focus | window.reads, key=lambda line: (line not in window.reads, line))
    while anchors:
        for radius in (32, 24, 16, 12, 8, 4, 0):
            selected = {
                line
                for anchor in anchors
                for line in range(anchor - radius, anchor + radius + 1)
                if line in window.lines
            }
            compact = _segments(window, selected)
            if len(json.dumps(compact)) <= limit:
                return compact
        anchors.pop()
    return []


def merge_evidence(
    previous: dict | list[dict] | None,
    new: dict | None,
    max_chars: int = 18000,
    *,
    changed_paths: set[str] | tuple[str, ...] = (),
) -> dict:
    """Merge already gathered evidence into one bounded batch without new reads.

    Overlaps are coalesced exactly, explicit reads take precedence over search
    hits, and separate source regions share the budget. New conflicting content
    invalidates all older excerpts for its file. The caller must also supply
    every edited path, even when new excerpts do not overlap the old locations.
    This pure utility does not grant access to paths or read source files.
    """
    if type(max_chars) is not int or max_chars < 100:
        raise ValueError("Merged evidence JSON budget must be at least 100 characters")
    changed = set(changed_paths)
    old = _batches(previous)
    batches = [*old, *_batches(new)]
    windows: list[_Window] = []
    for batch_index, batch in enumerate(batches):
        for excerpt in batch.get("excerpts", []):
            if batch_index < len(old) and excerpt["path"] in changed:
                continue
            window = _window(excerpt, batch_index)
            if any(
                older.path == window.path
                and any(
                    older.lines[line] != window.lines[line]
                    for line in older.lines.keys() & window.lines.keys()
                )
                for older in windows
            ):
                windows = [older for older in windows if older.path != window.path]
            windows.append(window)
    candidates = _coalesce(windows)
    ordered: list[_Window] = []
    seen: dict[str, int] = {}
    while candidates:
        chosen = min(
            candidates,
            key=lambda value: (
                not bool(value.reads),
                seen.get(value.path, 0),
                -value.order,
                min(value.lines),
            ),
        )
        candidates.remove(chosen)
        ordered.append(chosen)
        seen[chosen.path] = seen.get(chosen.path, 0) + 1
    result: dict[str, Any] = {"queries": [], "excerpts": [], "errors": []}
    excerpt_budget = max_chars - min(1200, max_chars // 8)
    full = [excerpt for window in ordered for excerpt in _segments(window, set(window.lines))]
    if len(json.dumps({**result, "excerpts": full})) <= excerpt_budget:
        result["excerpts"] = full
    else:
        weight = sum(3 if window.reads else 1 for window in ordered)
        for window in ordered:
            priority = 3 if window.reads else 1
            available = excerpt_budget - len(json.dumps(result))
            allocation = max(0, available * priority // weight)
            weight -= priority
            compact = _compact(window, allocation)
            candidate = {**result, "excerpts": [*result["excerpts"], *compact]}
            if len(json.dumps(candidate)) <= excerpt_budget:
                result = candidate
    # Metadata follows the excerpts and counts toward the same escaped-JSON cap.
    seen_metadata: set[tuple[str, str]] = set()
    for batch_index, batch in reversed(list(enumerate(batches))):
        for name in ("queries", "errors"):
            for item in batch.get(name, []):
                if name == "errors" and batch_index < len(old) and item.get("path") in changed:
                    continue
                key = (name, str(item.get("query")) if name == "queries" else json.dumps(item))
                if key in seen_metadata:
                    continue
                seen_metadata.add(key)
                candidate = {**result, name: [*result[name], dict(item)]}
                if len(json.dumps(candidate)) <= max_chars:
                    result = candidate
    return result


def invalidate_evidence(
    previous: dict | list[dict] | None,
    changed_paths: set[str] | tuple[str, ...],
    max_chars: int = 18000,
) -> dict:
    """Remove every prior excerpt for edited files before the next model packet."""
    return merge_evidence(previous, None, max_chars, changed_paths=changed_paths)


def gather_evidence(workspace: Workspace, request: Investigation, max_chars: int = 12000) -> dict:
    if max_chars < 100:
        raise ValueError("Inspection JSON budget must be at least 100 characters")
    paths = {
        path
        for path in workspace._tracked_paths()
        if PurePosixPath(path).suffix.casefold() in SUFFIXES
        and any(fnmatch.fnmatchcase(path, pattern) for pattern in workspace.config.context_paths)
    }
    result: dict[str, Any] = {"queries": [], "excerpts": [], "errors": []}
    documents: dict[str, list[str]] = {}
    scanned = 0

    def read(path: str) -> list[str]:
        nonlocal scanned
        if path not in paths:
            raise ValueError("Path is outside tracked configured source context")
        if path not in documents:
            source = workspace._safe_existing_path(path)
            size = source.stat().st_size
            if size > 2_000_000 or scanned + size > 32_000_000:
                raise ValueError("Inspection source scan budget exceeded")
            documents[path] = source.read_bytes().decode("utf-8").splitlines(keepends=True)
            scanned += size
        return documents[path]

    def append(
        path: str,
        lines: list[str],
        center: int,
        radius: int,
        kind: str,
        bounds: tuple[int, int] | None = None,
    ) -> bool:
        start, end = bounds or (max(0, center - radius), min(len(lines), center + radius + 1))
        content = "".join(lines[start:end])
        item = {
            "path": path,
            "start_line": start + 1,
            "end_line": end,
            "content": content,
            "kind": kind,
            "focus_line": center + 1,
        }
        if any(e["path"] == path and e["start_line"] == start + 1 for e in result["excerpts"]):
            return True
        if len(json.dumps({**result, "excerpts": [*result["excerpts"], item]})) > max_chars:
            return False
        result["excerpts"].append(item)
        return True

    # Explicit reads precede searches so broad symbols cannot crowd them out.
    for wanted in request.reads:
        try:
            lines = read(wanted.path)
            if workspace.config.definition_reads:
                from auto_fix.cpp_symbols import definition_ranges

                definitions = definition_ranges(
                    "".join(lines), symbol=wanted.symbol or None, line=wanted.line or None
                )
                returned = False
                for definition in definitions[:2]:
                    if definition["has_error"] or definition["body_has_error"]:
                        result["errors"].append(
                            {
                                "path": wanted.path,
                                "error": "C++ syntax parser reported errors in this definition; "
                                "its scope boundary may be approximate. Source lines are exact.",
                                "definition_start_line": definition["start_line"],
                                "definition_end_line": definition["end_line"],
                                "has_error": definition["has_error"],
                                "body_has_error": definition["body_has_error"],
                            }
                        )
                    bounds = (definition["start_line"] - 1, definition["end_line"])
                    returned |= append(
                        wanted.path,
                        lines,
                        definition["focus_line"] - 1,
                        35,
                        "read",
                        bounds=bounds,
                    )
                if returned:
                    continue
                if definitions:
                    result["errors"].append(
                        {
                            "path": wanted.path,
                            "error": "Complete definition exceeds the remaining evidence budget; "
                            "returning a partial neighborhood. Request a specific interior line "
                            "to inspect a different part.",
                            "definition_start_line": definitions[0]["start_line"],
                            "definition_end_line": definitions[0]["end_line"],
                        }
                    )
            line = wanted.line - 1 if wanted.line else 0
            if wanted.symbol:
                hits = [i for i, text in enumerate(lines) if wanted.symbol in text]
                if not hits:
                    raise ValueError("Requested literal symbol was not found")
                line = min(hits, key=lambda i: abs(i - line)) if wanted.line else hits[0]
            if not 0 <= line < len(lines):
                raise ValueError("Requested line is outside source file")
            append(wanted.path, lines, line, 35, "read")
        except (OSError, UnicodeError, RuntimeError, ValueError) as exc:
            result["errors"].append({"path": wanted.path, "error": str(exc)[:300]})
    for query in request.queries:
        if not 2 <= len(query) <= 160 or any(ord(char) < 32 for char in query):
            result["errors"].append({"error": "Search must be a 2-160 character literal"})
            continue
        matches = 0
        for path in sorted(paths):
            try:
                lines = read(path)
            except (OSError, UnicodeError, RuntimeError, ValueError):
                continue
            for index, line in enumerate(lines):
                if query.casefold() in line.casefold():
                    matches += 1
                    if not append(path, lines, index, 10, "search") or matches >= 12:
                        break
            if matches >= 12 or len(json.dumps(result)) >= max_chars - 800:
                break
        result["queries"].append({"query": query, "matches_returned_or_seen": matches})
    # Error text and query metadata also obey the final JSON budget.
    while len(json.dumps(result)) > max_chars and result["excerpts"]:
        result["excerpts"].pop()
    while len(json.dumps(result)) > max_chars and result["errors"]:
        result["errors"].pop()
    while len(json.dumps(result)) > max_chars and result["queries"]:
        result["queries"].pop()
    return result
