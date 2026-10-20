"""Bounded failure details from the current trusted native verification report.

This helper reads only the canonical report named in Verification.logs. The
caller supplies its trusted run directory; model-supplied paths are never used.
It does not scan old artifact directories or infer failures from output tails.
"""

from __future__ import annotations

import io
import json
import os
import re
import stat
from collections import defaultdict
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException


class EvidenceError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _tag(element: Any) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _size(value: dict) -> int:
    # Match the caller's ordinary JSON serialization, including Unicode escapes.
    return len(json.dumps(value))


def _is_link(path: Path) -> bool:
    # Windows directory junctions are reparse points, too; Python 3.11's
    # Path.is_symlink does not identify every junction configuration.
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except FileNotFoundError:
        return False
    return path.is_symlink() or bool(
        attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit < 12:
        return text[:limit]
    # Assertion values sometimes appear at the end of a long diagnostic.
    head = (limit - 5) * 2 // 3
    return text[:head] + " ... " + text[-(limit - head - 5) :]


def _report_bytes(verification: dict, root: Path, limit: int) -> tuple[Path, bytes]:
    logs = verification.get("logs", [])
    if not isinstance(logs, list) or any(not isinstance(path, str) for path in logs):
        raise EvidenceError("invalid_logs", "Verification logs must be a list of trusted paths")
    paths = list(dict.fromkeys(path for path in logs if Path(path).name == "junit.xml"))
    if not paths:
        raise EvidenceError("missing_report", "Current verification has no canonical junit.xml")
    if len(paths) != 1:
        raise EvidenceError(
            "ambiguous_report", "Current verification names multiple canonical reports"
        )
    root = Path(os.path.abspath(root))
    path = Path(paths[0])
    if not path.is_absolute():
        raise EvidenceError(
            "untrusted_path", "JUnit report must be an absolute trusted evidence path"
        )
    path = Path(os.path.abspath(path))
    if not path.is_relative_to(root):
        raise EvidenceError("untrusted_path", "JUnit report is outside the trusted run directory")
    if _is_link(root):
        raise EvidenceError("symlink", "Trusted evidence directory must not be a symlink")
    for item in (path, *path.parents):
        if item == root:
            break
        if _is_link(item):
            raise EvidenceError(
                "symlink", "JUnit report and its evidence parents must not be symlinks"
            )
    if not path.resolve().is_relative_to(root.resolve()):
        raise EvidenceError(
            "untrusted_path", "JUnit report resolves outside the trusted run directory"
        )
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as report:
        info = os.fstat(report.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise EvidenceError("invalid_file", "JUnit report must be a regular file")
        if info.st_size > limit:
            raise EvidenceError(
                "oversized_report", "JUnit report exceeds the configured byte limit"
            )
        data = report.read(limit + 1)
    if len(data) > limit:
        raise EvidenceError("oversized_report", "JUnit report exceeds the configured byte limit")
    return path.relative_to(root), data


def _explicit_values(failures: list[Any], text: str, kind: str) -> str:
    values = []
    for failure in failures:
        if failure.get(kind):
            values.append(failure.get(kind))
        values.extend("".join(child.itertext()).strip() for child in failure if _tag(child) == kind)
    if not any(values):
        # Keep explicit expected/actual labels only; prose and symbolic operands
        # remain verbatim in text instead of being turned into guessed values.
        labels = re.findall(rf"(?im)^\s*{kind}\s*:\s*([^\n]+)", text)
        if kind == "actual":
            labels.extend(re.findall(r"(?i)\bactual\s*:\s*([^\n]+)", text))
        # GoogleTest's "Which is" describes the immediately preceding operand,
        # which may be the expected operand. Keep those values with their named
        # expressions in the original text; assigning them all to actual reverses
        # contracts such as EXPECT_EQ(expected_status, observed_status).
        values.extend(labels)
    return "\n".join(dict.fromkeys(value for value in values if value))


def _assertion(case: Any, identity: str, classname: str) -> dict:
    failures = [child for child in case if _tag(child) in {"failure", "error"}]
    messages = list(dict.fromkeys(child.get("message", "") for child in failures))
    bodies = list(dict.fromkeys("".join(child.itertext()).strip() for child in failures))
    message = "\n".join(value for value in messages if value)
    text = "\n".join(value for value in bodies if value)
    combined = message + "\n" + text
    expected = _explicit_values(failures, combined, "expected")
    actual = _explicit_values(failures, combined, "actual")
    return {
        "name": identity,
        "classname": classname,
        "message": _clip(message, 1600),
        "text": _clip(text, 2400),
        "expected": _clip(expected, 800),
        "actual": _clip(actual, 800),
        "failure_elements": len(failures),
        "truncated": any(
            len(value) > limit
            for value, limit in ((message, 1600), (text, 2400), (expected, 800), (actual, 800))
        ),
    }


def failed_assertions(
    verification: dict,
    *,
    evidence_root: Path,
    max_chars: int = 6000,
    max_report_bytes: int = 20_000_000,
    max_representatives: int = 12,
) -> dict:
    """Return real failed assertions or bounded errors; never claim validation success.

    Identity and duplicate rules match build.parse_junit. A mismatch with the
    current Verification.report.failed invalidates all extracted assertions.
    At most twelve test representatives are selected round-robin by classname.
    Expected/actual fields contain only explicit XML attributes/elements/labels;
    the original assertion text retains other input and contract descriptions.
    """
    if max_chars < 300 or max_report_bytes < 1 or not 1 <= max_representatives <= 12:
        raise ValueError(
            "Diagnostic limits require >=300 chars, positive bytes and 1-12 representatives"
        )
    result: dict = {
        "source": "current_native_junit",
        "failed_test_count": 0,
        "group_count": 0,
        "groups": [],
        "assertions": [],
        "omitted_failed_tests": 0,
        "truncated": False,
        "errors": [],
    }
    try:
        if not isinstance(verification, dict):
            raise EvidenceError(
                "invalid_verification", "Verification must be a trusted result object"
            )
        expected = verification.get("report", {}).get("failed", [])
        if (
            not isinstance(expected, list)
            or any(not isinstance(name, str) or not name for name in expected)
            or len(expected) != len(set(expected))
        ):
            raise EvidenceError(
                "invalid_failure_names", "Verification failed identities must be unique names"
            )
        relative, data = _report_bytes(verification, evidence_root, max_report_bytes)
        tree = ElementTree.parse(io.BytesIO(data), forbid_dtd=True).getroot()
        grouped: dict[str, list[dict]] = defaultdict(list)
        seen: set[str] = set()
        failed: set[str] = set()
        for case in tree.iter():
            if _tag(case) != "testcase":
                continue
            name, classname = case.get("name", ""), case.get("classname", "")
            if not name:
                raise EvidenceError("missing_test_name", "JUnit testcase is missing its name")
            identity = f"{classname}.{name}" if classname and classname != name else name
            if identity in seen:
                raise EvidenceError("duplicate_test_name", "JUnit testcase names must be unique")
            seen.add(identity)
            if any(_tag(child) in {"failure", "error"} for child in case):
                failed.add(identity)
                grouped[classname].append(_assertion(case, identity, classname))
        if failed != set(expected):
            raise EvidenceError(
                "failure_identity_mismatch",
                "Canonical JUnit differs from current failed test identities",
            )
        result.update(
            report=relative.as_posix(), failed_test_count=len(failed), group_count=len(grouped)
        )
        for offset in range(max_representatives):
            for assertions in grouped.values():
                if offset < len(assertions) and len(result["assertions"]) < max_representatives:
                    result["assertions"].append(assertions[offset])
        result["groups"] = [
            {"classname": _clip(name, 160), "failed_test_count": len(assertions)}
            for name, assertions in list(grouped.items())[:max_representatives]
        ]
        result["omitted_failed_tests"] = len(failed) - len(result["assertions"])
        result["truncated"] = bool(result["omitted_failed_tests"]) or any(
            item["truncated"] for item in result["assertions"]
        )
        while _size(result) > max_chars:
            fields = [
                (len(json.dumps(item[key])), item, key)
                for item in result["assertions"]
                for key in ("text", "message", "expected", "actual")
                if len(item[key]) > 32
            ]
            if fields:
                _, item, key = max(fields, key=lambda field: field[0])
                item[key] = _clip(item[key], max(32, len(item[key]) // 2))
                item["truncated"] = True
            elif result["assertions"]:
                result["assertions"].pop()
            elif result["groups"]:
                result["groups"].pop()
            elif "report" in result:
                del result["report"]
            else:
                break
            result["omitted_failed_tests"] = len(failed) - len(result["assertions"])
            result["truncated"] = True
    except EvidenceError as exc:
        result["errors"] = [{"code": exc.code, "message": str(exc)}]
    except DefusedXmlException:
        result["errors"] = [
            {"code": "unsafe_xml", "message": "JUnit DTD/entity content is forbidden"}
        ]
    except (ParseError, UnicodeError):
        result["errors"] = [
            {"code": "malformed_xml", "message": "Canonical JUnit is not valid XML"}
        ]
    except (OSError, TypeError, AttributeError, ValueError):
        result["errors"] = [
            {
                "code": "unreadable_report",
                "message": "Canonical native report could not be read safely",
            }
        ]
    # Error packets are also bounded for small operator-selected budgets.
    while _size(result) > max_chars and result["errors"]:
        result["errors"][0].pop("message", None)
        if _size(result) > max_chars:
            result["errors"] = [{"code": "invalid_evidence"}]
    return result
