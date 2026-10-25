"""Reviewer decisions about runs: dismissed, rejected, handled elsewhere or snoozed, with notes.

Decisions live in one ``triage.json`` beside the runs, so run directories stay exactly as the
workflow wrote them. A decided run leaves Needs attention; its evidence and history stay.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

from filelock import FileLock

from auto_fix.jobs import JobError

# Decisions that close a run for review; a snooze closes it until its time passes.
CLOSED = {"dismissed", "rejected", "handled"}
ACTIONS = {"dismiss", "reject", "handled", "snooze", "reopen", "note", "rate"}
STATE_OF = {"dismiss": "dismissed", "reject": "rejected", "handled": "handled", "snooze": "snoozed"}
NOTE_LIMIT = 4000


def load(root: Path) -> dict[str, dict[str, Any]]:
    """Every run's decision record, keyed by run id; unreadable storage reads as empty."""
    try:
        data = json.loads((root / "triage.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def active(record: dict[str, Any] | None, at: datetime | None = None) -> bool:
    """Whether a decision currently takes the run out of Needs attention."""
    if not record or not record.get("state"):
        return False
    if record["state"] in CLOSED:
        return True
    if record["state"] == "snoozed" and record.get("until"):
        try:
            return datetime.fromisoformat(record["until"]) > (at or datetime.now(UTC))
        except ValueError:
            return False
    return False


def _until(value: Any, at: datetime) -> str:
    """A snooze end as an aware ISO time; a bare date means the start of that day in UTC."""
    if not isinstance(value, str) or not value:
        raise JobError("Choose when the snooze ends", {"until": "Choose a date"})
    try:
        parsed = (
            datetime.combine(date.fromisoformat(value), time(), UTC)
            if len(value) == 10
            else datetime.fromisoformat(value)
        )
    except ValueError as exc:
        raise JobError("Choose when the snooze ends", {"until": "Enter a valid date"}) from exc
    parsed = parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    if parsed <= at:
        raise JobError("Choose when the snooze ends", {"until": "Choose a future date"})
    return parsed.isoformat()


class TriageStore:
    def __init__(self, root: Path):
        self.root = root
        self.path = root / "triage.json"
        self.lock = FileLock(str(root / "triage.lock"), timeout=10)

    def get(self, run_id: str) -> dict[str, Any]:
        return load(self.root).get(run_id, {})

    def update(
        self,
        run_id: str,
        action: str,
        by: str,
        *,
        note: str = "",
        until: str = "",
        rating: str = "",
        at: datetime | None = None,
    ) -> dict[str, Any]:
        at = at or datetime.now(UTC)
        if action not in ACTIONS:
            raise JobError(f"Unknown triage action: {action}")
        note = str(note or "").strip()[:NOTE_LIMIT]
        if action == "note" and not note:
            raise JobError("Write a note first", {"note": "Write a note"})
        if action == "rate" and rating not in {"good", "bad"}:
            raise JobError("Rate the fix good or bad", {"rating": "Choose good or bad"})
        snooze_end = _until(until, at) if action == "snooze" else None
        stamp = {"by": by, "at": at.isoformat()}
        with self.lock:
            records = load(self.root)
            record = dict(records.get(run_id, {}))
            notes = list(record.get("notes", []))
            if action in STATE_OF:
                record.update(state=STATE_OF[action], until=snooze_end, **stamp)
            elif action == "reopen":
                record.update(state=None, until=None, **stamp)
            elif action == "rate":
                record["rating"] = {"value": rating, "comment": note, **stamp}
            # A decision may carry a reason; it is kept with the other notes.
            if note and action != "rate":
                notes.append({"text": note, "action": action, **stamp})
            record["notes"] = notes
            records[run_id] = record
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(records, indent=2), encoding="utf-8")
            temporary.replace(self.path)
        return record
