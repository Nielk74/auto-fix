"""Keep failure evidence visible when native output contains many passing tests."""

from __future__ import annotations

import re

IMPORTANT = re.compile(
    r"error[: ]|error C\d+|fatal error|Expected|Which is|Value of:|Actual:|"
    r"\[\s*FAILED\s*\]|assertion|runtime error|undefined reference|exception|"
    r"AddressSanitizer|UndefinedBehaviorSanitizer",
    re.IGNORECASE,
)
PROGRESS = re.compile(r"^\s*\[(?:\s*(?:RUN|OK|PASSED|={2,}|-{2,})\s*|\d+%|\d+/\d+)\]")


def failure_diagnostics(text: str, max_chars: int = 6000) -> str:
    lines = [line for line in text.splitlines() if not PROGRESS.match(line)]
    text = "\n".join(lines)
    important = [index for index, line in enumerate(lines) if IMPORTANT.search(line)]
    selected = set()
    for index in important:
        selected.update(range(max(0, index - 3), min(len(lines), index + 8)))
    if not selected:
        if len(text) <= max_chars:
            return text
        marker = "\n...\n"
        if max_chars <= len(marker):
            return text[: max(0, max_chars)]
        available = max_chars - len(marker)
        first = available // 2
        return text[:first] + marker + text[-(available - first) :]
    output = []
    remaining = max_chars - 800
    for index in sorted(selected):
        line = lines[index]
        if PROGRESS.match(line):
            continue
        if len(line) + 1 > remaining:
            continue
        output.append(line)
        remaining -= len(line) + 1
    return ("\n".join(output) + "\n--- latest output tail ---\n" + text[-700:])[:max_chars]
