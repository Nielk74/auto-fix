"""Persistent workflow schedules, dispatched by the existing single job runner."""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from filelock import FileLock

from auto_fix.jobs import JobError, JobStore, validate


def _local(naive: datetime, zone: ZoneInfo) -> datetime | None:
    candidate = naive.replace(tzinfo=zone, fold=0)
    # A spring-forward gap has no corresponding instant. Fall-back runs once, at fold 0.
    if candidate.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != naive:
        return None
    return candidate.astimezone(UTC)


def next_occurrence(spec: dict[str, Any], after: datetime) -> str | None:
    zone = ZoneInfo(spec["timezone"])
    if spec["frequency"] == "once":
        value = datetime.fromisoformat(spec["at"])
        candidate = value.astimezone(UTC) if value.tzinfo else _local(value, zone)
        return candidate.isoformat() if candidate and candidate > after else None
    clock = time.fromisoformat(spec["time"])
    today = after.astimezone(zone).date()
    for offset in range(370):
        day = today + timedelta(days=offset)
        if spec["frequency"] == "weekly" and day.weekday() not in spec["weekdays"]:
            continue
        candidate = _local(datetime.combine(day, clock), zone)
        if candidate and candidate > after:
            return candidate.isoformat()
    return None


class ScheduleStore:
    def __init__(self, state_dir: Path, timezone: str = "Europe/Paris"):
        self.state_dir, self.timezone = state_dir, timezone
        self.path = state_dir / "schedules.json"
        self.lock = FileLock(str(state_dir / "schedules.lock"), timeout=10)

    def _read(self) -> list[dict[str, Any]]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, ValueError) as exc:
            raise JobError("Schedule storage could not be read") from exc

    def _write(self, schedules: list[dict[str, Any]]) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(schedules, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def all(self) -> list[dict[str, Any]]:
        result = self._read()
        for spec in result:
            upcoming, occurrence = [], spec.get("next_run") if spec["enabled"] else None
            while occurrence and len(upcoming) < 5:
                upcoming.append(occurrence)
                occurrence = next_occurrence(spec, datetime.fromisoformat(occurrence))
            spec["upcoming"] = upcoming
            if spec.get("last_job"):
                path = self.state_dir / "jobs" / f"{spec['last_job']}.json"
                try:
                    spec["last_outcome"] = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    spec["last_outcome"] = None
        return result

    def _validated(self, data: dict[str, Any], at: datetime) -> dict[str, Any]:
        """A checked schedule with its next run, or a JobError naming each wrong field."""
        errors: dict[str, str] = {}
        kind = data.get("kind", "")
        if kind not in {"batch", "evaluation", "operations", "demo"}:
            raise JobError("Choose a launchable workflow", {"kind": "Unsupported workflow"})
        params = data.get("params", {})
        clean = validate(kind, params, self.state_dir)
        if kind == "batch" and params.get("date", "today") in {"", "today", None}:
            clean["date"] = "today"
        spec = {
            "name": str(data.get("name", "")).strip()[:160],
            "kind": kind,
            "params": clean,
            "timezone": data.get("timezone", self.timezone),
            "frequency": data.get("frequency", "daily"),
            "time": data.get("time", "17:30"),
            "weekdays": data.get("weekdays", [0, 1, 2, 3, 4]),
            "at": data.get("at", ""),
            "missed": data.get("missed", "once"),
            "overlap": data.get("overlap", "skip"),
            "enabled": data.get("enabled", True),
        }
        if not spec["name"]:
            errors["name"] = "Enter a schedule name"
        if not isinstance(spec["enabled"], bool):
            errors["enabled"] = "Expected true or false"
        try:
            ZoneInfo(spec["timezone"])
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            errors["timezone"] = "Enter an IANA timezone, for example Europe/Paris"
        if spec["frequency"] not in {"once", "daily", "weekly"}:
            errors["frequency"] = "Choose once, daily or weekly"
        try:
            parsed = time.fromisoformat(spec["time"])
            if parsed.tzinfo or parsed.second or parsed.microsecond:
                raise ValueError
            spec["time"] = parsed.strftime("%H:%M")
        except (ValueError, TypeError):
            errors["time"] = "Enter a time as HH:MM"
        if spec["frequency"] == "weekly" and (
            not isinstance(spec["weekdays"], list)
            or not spec["weekdays"]
            or any(type(day) is not int or not 0 <= day <= 6 for day in spec["weekdays"])
        ):
            errors["weekdays"] = "Choose at least one weekday"
        if spec["missed"] not in {"once", "skip"}:
            errors["missed"] = "Choose catch up once or skip"
        if spec["overlap"] not in {"skip", "queue"}:
            errors["overlap"] = "Choose skip or queue"
        if not errors:
            try:
                spec["next_run"] = next_occurrence(spec, at)
            except (ValueError, TypeError):
                errors["at"] = "Enter a valid date and time"
            else:
                if spec["frequency"] == "once" and spec["next_run"] is None:
                    errors["at"] = "Choose a future time that exists in this timezone"
        if errors:
            raise JobError("Check the schedule fields", errors)
        return spec

    def preview(self, data: dict[str, Any], *, at: datetime | None = None) -> list[str]:
        """The next five occurrences of an unsaved schedule."""
        spec = self._validated(data, at or datetime.now(UTC))
        upcoming, occurrence = [], spec.get("next_run")
        while occurrence and len(upcoming) < 5:
            upcoming.append(occurrence)
            occurrence = next_occurrence(spec, datetime.fromisoformat(occurrence))
        return upcoming

    def save(
        self,
        data: dict[str, Any],
        by: str,
        schedule_id: str = "",
        *,
        at: datetime | None = None,
    ) -> dict[str, Any]:
        at = at or datetime.now(UTC)
        spec = self._validated(data, at)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with self.lock:
            records = self._read()
            previous = next((s for s in records if s["id"] == schedule_id), None)
            if schedule_id and previous is None:
                raise JobError("Unknown schedule")
            spec = {
                **(previous or {}),
                **spec,
                "id": schedule_id or secrets.token_hex(8),
                "updated_by": by,
                "updated": at.isoformat(),
            }
            self._write([s for s in records if s["id"] != spec["id"]] + [spec])
        return spec

    def toggle(self, schedule_id: str, enabled: bool, *, at: datetime | None = None) -> None:
        if not isinstance(enabled, bool):
            raise JobError("Enabled must be true or false")
        with self.lock:
            records = self._read()
            spec = next((s for s in records if s["id"] == schedule_id), None)
            if spec is None:
                raise JobError("Unknown schedule")
            spec["enabled"] = enabled
            if enabled:
                spec["next_run"] = next_occurrence(spec, at or datetime.now(UTC))
                if not spec["next_run"]:
                    raise JobError("This one-time schedule has ended; edit its date first")
            self._write(records)

    def remove(self, schedule_id: str) -> None:
        with self.lock:
            records = self._read()
            if not any(s["id"] == schedule_id for s in records):
                raise JobError("Unknown schedule")
            self._write([s for s in records if s["id"] != schedule_id])

    def tick(self, store: JobStore, *, at: datetime | None = None) -> None:
        at = at or datetime.now(UTC)
        with self.lock:
            records = self._read()
            changed = False
            for spec in records:
                if not spec["enabled"] or not spec.get("next_run"):
                    continue
                due = datetime.fromisoformat(spec["next_run"])
                if due > at:
                    continue
                occurrence_id = "schedule-" + spec["id"] + "-" + due.strftime("%Y%m%d%H%M%S")
                existing = store.get(occurrence_id)
                active = any(
                    job.get("schedule_id") == spec["id"] and job["status"] in {"queued", "running"}
                    for job in store.all()
                )
                if existing:
                    spec.update(last_job=existing["id"], last_status="queued")
                elif spec["overlap"] == "skip" and active:
                    spec["last_status"] = "skipped_overlap"
                elif spec["missed"] == "skip" and (at - due).total_seconds() > 60:
                    spec["last_status"] = "skipped_missed"
                else:
                    params = dict(spec["params"])
                    job = store.add(
                        spec["kind"],
                        params,
                        "Schedule: " + spec["name"],
                        job_id=occurrence_id,
                        schedule_id=spec["id"],
                        scheduled_for=due.isoformat(),
                        date_timezone=spec["timezone"] if params.get("date") == "today" else None,
                    )
                    spec.update(last_job=job["id"], last_status="queued")
                spec.update(last_triggered=at.isoformat(), next_run=next_occurrence(spec, at))
                if spec["frequency"] == "once":
                    spec["enabled"] = False
                changed = True
            if changed:
                self._write(records)
