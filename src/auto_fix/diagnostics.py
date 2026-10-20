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
    lines = text.splitlines()
    important = [index for index, line in enumerate(lines) if IMPORTANT.search(line)]
    selected = set()
    for index in important:
        selected.update(range(max(0, index - 3), min(len(lines), index + 8)))
    if not selected:
        return (
            text
            if len(text) <= max_chars
            else text[: max_chars // 2] + "\n...\n" + text[-max_chars // 2 :]
        )
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
