from __future__ import annotations

from datetime import datetime

import pytest

from auto_fix.jobs import JobError, JobStore


def stamp(value):
    return datetime.fromisoformat(value)


def create(tmp_path, **patch):
    from auto_fix.schedules import ScheduleStore

    store = ScheduleStore(tmp_path)
    data = {
        "name": "Daily repairs",
        "kind": "batch",
        "params": {"date": "today"},
        "timezone": "Europe/Paris",
        "frequency": "daily",
        "time": "17:30",
        "missed": "once",
        "overlap": "skip",
        **patch,
    }
    return store, store.save(data, "me", at=stamp("2026-10-24T12:00:00+00:00"))


def test_schedules_resolve_dates_at_execution_and_do_not_duplicate_after_restart(tmp_path):
    from auto_fix.schedules import ScheduleStore

    store, scheduled = create(tmp_path)
    assert scheduled["next_run"] == "2026-10-24T15:30:00+00:00"
    jobs = JobStore(tmp_path)
    store.tick(jobs, at=stamp("2026-10-24T15:30:01+00:00"))
    ScheduleStore(tmp_path).tick(jobs, at=stamp("2026-10-24T15:30:02+00:00"))
    assert len(jobs.all()) == 1
    assert jobs.all()[0]["params"]["date"] == "today"
    assert jobs.all()[0]["date_timezone"] == "Europe/Paris"
    assert jobs.all()[0]["schedule_id"] == scheduled["id"]
    assert store.all()[0]["next_run"] == "2026-10-25T16:30:00+00:00"


def test_schedule_weekdays_and_dst_gap_and_fold_are_explicit(tmp_path):
    from auto_fix.schedules import next_occurrence

    spec = {"frequency": "daily", "timezone": "Europe/Paris", "time": "02:30"}
    assert next_occurrence(spec, stamp("2026-03-28T02:00:00+00:00")) == "2026-03-30T00:30:00+00:00"
    assert next_occurrence(spec, stamp("2026-10-25T00:31:00+00:00")) == "2026-10-26T01:30:00+00:00"
    _, weekly = create(tmp_path, frequency="weekly", weekdays=[0, 2])
    assert weekly["next_run"] == "2026-10-26T16:30:00+00:00"


def test_schedule_missed_once_skip_overlap_and_enable_controls(tmp_path):
    store, scheduled = create(tmp_path)
    jobs = JobStore(tmp_path)
    store.tick(jobs, at=stamp("2026-10-27T19:00:00+00:00"))
    assert len(jobs.all()) == 1  # catch up once, rather than enqueue every missed day
    assert jobs.all()[0]["params"]["date"] == "today"
    store.tick(jobs, at=stamp("2026-10-28T16:30:01+00:00"))
    assert len(jobs.all()) == 1
    assert store.all()[0]["last_status"] == "skipped_overlap"
    store.toggle(scheduled["id"], False, at=stamp("2026-10-28T17:00:00+00:00"))
    store.tick(jobs, at=stamp("2026-10-30T17:00:00+00:00"))
    assert len(jobs.all()) == 1
    store.toggle(scheduled["id"], True, at=stamp("2026-10-30T17:00:00+00:00"))
    assert store.all()[0]["next_run"] == "2026-10-31T16:30:00+00:00"


def test_one_time_schedule_can_skip_a_missed_occurrence(tmp_path):
    store, _ = create(tmp_path, frequency="once", at="2026-10-24T17:30", missed="skip")
    jobs = JobStore(tmp_path)
    store.tick(jobs, at=stamp("2026-10-24T18:00:00+00:00"))
    assert not jobs.all()
    assert store.all()[0]["last_status"] == "skipped_missed"
    assert not store.all()[0]["enabled"]


@pytest.mark.parametrize(
    "patch",
    [
        {"timezone": "Moon/Base"},
        {"frequency": "cron"},
        {"time": "25:00"},
        {"frequency": "weekly", "weekdays": []},
        {"params": {"publish": "yes"}},
        {"kind": "repair"},
        {"overlap": "terminate"},
    ],
)
def test_invalid_schedules_are_not_saved(tmp_path, patch):
    with pytest.raises(JobError):
        create(tmp_path, **patch)
