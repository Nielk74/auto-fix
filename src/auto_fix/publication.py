"""Match Bitbucket receipts to the exact verified Git candidate."""

from __future__ import annotations

import re
from typing import Any

GIT_HEAD = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


def require_verified_pr(pr: Any, head: Any, source: str, target: str) -> None:
    if not isinstance(head, str) or not GIT_HEAD.fullmatch(head):
        raise RuntimeError("Verified candidate head is missing or is not a full Git commit ID")
    if not isinstance(pr, dict):
        raise RuntimeError("PR receipt is missing a verified commit head")
    from_ref, to_ref = pr.get("fromRef"), pr.get("toRef")
    if not isinstance(from_ref, dict) or from_ref.get("latestCommit") != head:
        raise RuntimeError("PR commit head is absent or differs from the verified candidate")
    if from_ref.get("id") != "refs/heads/" + source:
        raise RuntimeError("PR receipt source branch differs from the verified candidate")
    if not isinstance(to_ref, dict) or to_ref.get("id") != "refs/heads/" + target:
        raise RuntimeError("PR receipt target branch differs from the requested base")
