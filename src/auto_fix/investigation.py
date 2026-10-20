"""Bounded, read-only evidence gathering for model-directed investigation."""

from __future__ import annotations

import fnmatch
import json
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

    def append(path: str, lines: list[str], center: int, radius: int, kind: str) -> bool:
        start, end = max(0, center - radius), min(len(lines), center + radius + 1)
        content = "".join(lines[start:end])
        item = {
            "path": path,
            "start_line": start + 1,
            "end_line": end,
            "content": content,
            "kind": kind,
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
