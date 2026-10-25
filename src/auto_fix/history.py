"""Read-only reconstruction of workflow runs from their evidence directories and checkpoints.

Nothing here writes to a run directory, so the dashboard can inspect a state directory while
the scheduled worker is still executing a graph.
"""

from __future__ import annotations

import json
import os
import sqlite3
import statistics
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any

from auto_fix import control, triage

TERMINAL = {"ready", "published", "blocked", "publication_unknown"}
# Runs stopped on a step boundary by a request; a paused run resumes from its checkpoint.
STOPPED = {"paused", "cancelled"}
RUN_MARKERS = ("events.jsonl", "checkpoints.sqlite", "result.json")
# Large evidence directories are listed, never inlined into API responses.
TEXT_LIMIT = 4000
FILE_LIMIT = 2_000_000
# Tail of a failed model call's raw output kept for the dashboard.
RAW_LIMIT = 20_000
SORTS = {"-started", "started", "-duration", "duration", "status"}
# Blocked reasons that mean the TeamCity failure did not reproduce locally.
NOT_REPRODUCED = ("not reproduced", "varied across repetitions")


def _json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return default


def _events(run: Path) -> list[dict[str, Any]]:
    events = []
    try:
        lines = (run / "events.jsonl").read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return events
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def read_events(run: Path) -> list[dict[str, Any]]:
    """A run's logged events in order; unreadable lines are skipped."""
    return _events(run)


def _time(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def _seconds(start: str | None, end: str | None) -> float | None:
    first, last = _time(start), _time(end)
    return round((last - first).total_seconds(), 3) if first and last else None


def clip(value: Any, limit: int = TEXT_LIMIT) -> Any:
    """Bound long strings recursively so a step diff stays readable in the browser."""
    if isinstance(value, str) and len(value) > limit:
        return (
            value[: limit // 2]
            + f"\n… [{len(value) - limit} characters clipped] …\n"
            + value[-limit // 2 :]
        )
    if isinstance(value, dict):
        return {key: clip(item, limit) for key, item in value.items()}
    if isinstance(value, list):
        return [clip(item, limit) for item in value]
    return value


def discover_runs(root: Path) -> dict[str, Path]:
    """Map stable ids to run directories below a state dir or an evaluation output tree.

    A run directory is a child of a ``runs`` folder holding workflow evidence. Git checkouts
    and worktrees are skipped so large C++ sources are never walked.
    """
    root = root.resolve()
    found: dict[str, Path] = {}
    for current, dirnames, _files in os.walk(root):
        here = Path(current)
        if here.name == "runs":
            for child in sorted(dirnames):
                run = here / child
                if any((run / marker).exists() for marker in RUN_MARKERS):
                    found[run.relative_to(root).as_posix()] = run
            dirnames.clear()
            continue
        dirnames[:] = [
            name
            for name in dirnames
            if name not in {".git", "worktrees", "node_modules", ".venv", "__pycache__"}
            and not (here / name / ".git").exists()
        ]
    return found


def _receipt(run: Path) -> dict[str, Any] | None:
    """The receipt records reconciliation that happens after the graph, e.g. a found PR."""
    key = run.name.rsplit("-r", 1)[0] if "-r" in run.name else run.name
    receipt = _json(run.parent.parent / "receipts" / f"{key}.json")
    if isinstance(receipt, dict) and receipt.get("run_id", run.name) == run.name:
        return receipt
    return None


def _pr_url(pr: Any) -> str:
    if not isinstance(pr, dict):
        return ""
    links = pr.get("links", {}).get("self", [])
    return links[0].get("href", "") if links and isinstance(links[0], dict) else ""


def _counts(report: dict[str, Any]) -> dict[str, int]:
    return {key: len(report.get(key, [])) for key in ("passed", "failed", "skipped")}


def compare(result: dict[str, Any]) -> dict[str, Any] | None:
    """The full suite before and after the edit: what the fix repaired, left and newly broke."""
    base = (result.get("baseline") or {}).get("report") or {}
    final = (result.get("verification") or {}).get("report") or {}
    if not isinstance(base, dict) or not isinstance(final, dict) or not final:
        return None
    before, after = set(base.get("failed", [])), set(final.get("failed", []))
    return {
        "fixed": sorted(before & set(final.get("passed", []))),
        "still_failing": sorted(before & after),
        # A test failing after the edit that did not fail before it is a regression.
        "regressions": sorted(after - before),
        "baseline": _counts(base),
        "final": _counts(final),
    }


def summarize(run_id: str, run: Path) -> dict[str, Any]:
    result = _json(run / "result.json", {}) or {}
    receipt = _receipt(run)
    events = _events(run)
    status = (receipt or {}).get("status") or result.get("status") or "unknown"
    failure = result.get("failure", {}) or {}
    started = events[0]["time"] if events else None
    updated = events[-1]["time"] if events else None
    # Cancelling a paused or abandoned run is logged when the user acts, long after any work.
    worked = [event for event in events if not event.get("idle")]
    finished = worked[-1]["time"] if worked else updated
    calls = run / "model-calls"
    # ``case/state/runs/<run>`` groups evaluation runs by their case directory.
    group = PurePosixPath(run_id).parent.parent
    group = (group.parent if group.name == "state" else group).as_posix()
    report = (result.get("verification") or result.get("baseline") or {}).get("report")
    comparison = compare(result)
    return {
        "id": run_id,
        "name": run.name,
        "group": "" if group == "." else group,
        "status": status if status in TERMINAL | STOPPED else "in_progress",
        "graph_status": result.get("status", ""),
        "reason": (receipt or {}).get("reason") or result.get("reason", ""),
        "started": started,
        "updated": updated,
        "duration_seconds": _seconds(started, finished),
        "build_id": failure.get("build_id", ""),
        "build_type": failure.get("build_type", ""),
        "build_url": failure.get("build_url", ""),
        "revision": failure.get("revision", ""),
        "tests": [test.get("name", "") for test in failure.get("tests", [])],
        "validation": {key: len(report.get(key, [])) for key in ("passed", "failed", "skipped")}
        if isinstance(report, dict)
        else None,
        "regressions": len(comparison["regressions"]) if comparison else 0,
        "attempts": result.get("attempt", 0),
        "inspections": result.get("inspections", 0),
        "branch": result.get("branch", ""),
        "head": result.get("head", ""),
        "pr_url": _pr_url((receipt or {}).get("pr") or result.get("pr")),
        "model_calls": len(list(calls.glob("*.json"))) if calls.is_dir() else 0,
        "output_files": [
            name for name in ("fix.diff", "result.json", "events.jsonl") if (run / name).is_file()
        ],
        # Run controls: a pending pause/cancel, whether a process still runs it, and its origin.
        "request": control.pending(run),
        # The step a running run is in, for the run list.
        "current": next(
            (e["node"] for e in reversed(events) if e.get("node") not in {"model_call", "stopped"}),
            "",
        ),
        "live": control.process(run) is not None,
        "forked_from": next(
            (
                {
                    "source": event.get("source"),
                    "step": event.get("step"),
                    "node": event.get("from_node"),
                }
                for event in events
                if event.get("node") == "forked"
            ),
            None,
        ),
    }


def list_runs(root: Path) -> list[dict[str, Any]]:
    decisions = triage.load(root)
    runs = [
        {**summarize(run_id, run), "triage": decisions.get(run_id) or None}
        for run_id, run in discover_runs(root).items()
    ]
    return sorted(runs, key=lambda run: (run["started"] or "", run["id"]), reverse=True)


def workflow_key(run: dict[str, Any]) -> str:
    if run["id"].startswith("runs/"):
        return "bt:" + (run["build_type"] or "unknown")
    if run["id"].startswith("evaluations/"):
        return "operations" if "-operations-" in run["id"] else "evaluation"
    if run["id"].startswith("demos/"):
        return "demo"
    return "other:" + (run["group"] or "State directory")


def run_page(
    root: Path,
    *,
    page: int = 1,
    page_size: int = 25,
    workflow: str = "",
    status: str = "",
    q: str = "",
    since: str = "",
    until: str = "",
    sort: str = "-started",
) -> dict[str, Any]:
    """Filter lightweight evidence summaries before slicing a bounded history page."""
    if page < 1 or not 1 <= page_size <= 100:
        raise ValueError("Page must be positive and page size between 1 and 100")
    if status and status not in TERMINAL | STOPPED | {"in_progress", "attention", "triaged"}:
        raise ValueError("Unknown run status")
    if sort not in SORTS:
        raise ValueError("Unknown sort order")
    for value in (since, until):
        if value:
            date.fromisoformat(value)
    if since and until and since > until:
        raise ValueError("From date must not be after the until date")
    all_runs = list_runs(root)
    catalog: dict[str, Any] = {}
    for run in all_runs:
        key = workflow_key(run)
        entry = catalog.setdefault(key, {"key": key, "count": 0, "last": run})
        entry["count"] += 1
    needle = q.strip().casefold()
    runs = [
        run
        for run in all_runs
        if (
            (not workflow or workflow_key(run) == workflow)
            and (
                not status
                or (
                    needs_attention(run)
                    if status == "attention"
                    else triage.active(run["triage"])
                    if status == "triaged"
                    else run["status"] == status
                )
            )
            and (not since or (run["started"] or "")[:10] >= since)
            and (not until or bool(run["started"]) and run["started"][:10] <= until)
            and (
                not needle
                or needle
                in " ".join(
                    str(run.get(key, ""))
                    for key in (
                        "id",
                        "build_type",
                        "build_id",
                        "revision",
                        "branch",
                        "reason",
                        "tests",
                    )
                ).casefold()
            )
        )
    ]
    if sort in {"duration", "-duration"}:
        runs.sort(key=lambda run: run["duration_seconds"] or 0, reverse=sort == "-duration")
    elif sort == "started":
        runs.reverse()
    elif sort == "status":
        runs.sort(key=lambda run: run["status"])
    total = len(runs)
    pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, pages)
    attention = [run for run in all_runs if needs_attention(run)]
    return {
        "runs": runs[(page - 1) * page_size : page * page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "all_total": len(all_runs),
        "catalog": list(catalog.values()),
        "attention": attention[:25],
        "attention_total": len(attention),
        "active": [run for run in all_runs if run["status"] == "in_progress" and run["live"]][:10],
    }


def needs_attention(run: dict[str, Any]) -> bool:
    if triage.active(run.get("triage")):
        return False
    return run["status"] in {"ready", "paused", "blocked", "publication_unknown"} or (
        run["status"] == "in_progress" and not run["live"]
    )


def checkpoints(run: Path) -> list[dict[str, Any]]:
    """Every saved super-step in order, read from the run's LangGraph SqliteSaver."""
    database = run / "checkpoints.sqlite"
    if not database.is_file():
        return []
    from langgraph.checkpoint.sqlite import SqliteSaver

    try:
        conn = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    except sqlite3.Error:
        return []
    try:
        saved = list(SqliteSaver(conn).list(None))
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    ordered = []
    for item in reversed(saved):
        values = item.checkpoint.get("channel_values", {})
        ordered.append(
            {
                "id": item.config["configurable"]["checkpoint_id"],
                "step": item.metadata.get("step"),
                "source": item.metadata.get("source"),
                "time": item.checkpoint.get("ts"),
                "next": sorted(
                    name.removeprefix("branch:to:")
                    for name in values
                    if name.startswith("branch:to:")
                ),
                "values": {
                    key: value
                    for key, value in values.items()
                    if not key.startswith("branch:to:") and key != "__start__"
                },
            }
        )
    return ordered


def steps(
    saved: list[dict[str, Any]], events: list[dict[str, Any]], stopped: bool = False
) -> list[dict[str, Any]]:
    """Node executions with the state keys each one changed.

    Checkpoint ``n`` names the node scheduled next; checkpoint ``n + 1`` holds the state after
    that node returns. Older runs without checkpoints fall back to logged node events.
    """
    if not saved:
        return [
            {
                "index": index,
                "node": event["node"],
                "started": event.get("time"),
                "ended": events[index + 1].get("time") if index + 1 < len(events) else None,
                "details": {k: v for k, v in event.items() if k not in {"time", "node"}},
                "changes": {},
                "status": "",
                "checkpoint": None,
            }
            for index, event in enumerate(events)
            if event.get("node") != "model_call"
        ]
    result = []
    for before, after in zip(saved, saved[1:], strict=False):
        for node in before["next"] or ["__input__"]:
            changes = {
                key: value
                for key, value in after["values"].items()
                if before["values"].get(key) != value
            }
            result.append(
                {
                    "index": len(result),
                    "node": node,
                    "started": before["time"],
                    "ended": after["time"],
                    "duration_seconds": _seconds(before["time"], after["time"]),
                    "changes": clip(changes),
                    "status": after["values"].get("status", ""),
                    "checkpoint": after["step"],
                    # The state this step started from: what a re-run from it is seeded with.
                    "from_checkpoint": before["step"],
                }
            )
    last = saved[-1]
    # A paused or cancelled run has not started its next node; it is not an interrupted step.
    for node in [] if stopped else last["next"]:
        # A scheduled node with no later checkpoint was running or stopped with an exception.
        result.append(
            {
                "index": len(result),
                "node": node,
                "started": last["time"],
                "ended": None,
                "duration_seconds": None,
                "changes": {},
                "status": "interrupted",
                "checkpoint": None,
                "from_checkpoint": last["step"],
            }
        )
    executed = [step for step in result if step["node"] != "__input__"]
    for index, step in enumerate(executed):
        step["index"] = index
    return executed


def run_steps(run: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """A run's checkpoints and the steps it completed, for re-running it from one of them."""
    saved = checkpoints(run)
    return saved, steps(saved, _events(run), stopped=True)


def topology() -> dict[str, Any]:
    """Nodes and edges of the production graph, taken from the compiled LangGraph."""
    from auto_fix.workflow import Workflow

    # Graph construction only binds node methods; routing lambdas read settings at runtime.
    drawn = Workflow.__new__(Workflow).graph().get_graph()
    return {
        "nodes": list(drawn.nodes),
        "edges": [
            {"source": edge.source, "target": edge.target, "conditional": edge.conditional}
            for edge in drawn.edges
        ],
    }


def files(run: Path) -> list[dict[str, Any]]:
    listed = []
    for path in sorted(run.rglob("*")):
        if (
            path.is_file()
            and not path.is_symlink()
            and path.resolve().is_relative_to(run.resolve())
            and not path.name.casefold().startswith("checkpoints.sqlite")
        ):
            listed.append({"path": path.relative_to(run).as_posix(), "size": path.stat().st_size})
    return listed


def model_calls(run: Path) -> list[dict[str, Any]]:
    calls = []
    folder = run / "model-calls"
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        record = _json(path, {}) or {}
        calls.append(
            {
                "file": path.relative_to(run).as_posix(),
                **{
                    key: record.get(key)
                    for key in ("index", "kind", "attempt", "model", "started")
                    + ("elapsed_seconds", "usage", "error")
                },
                "context_chars": len(json.dumps(record.get("context", ""))),
                "response": clip(record.get("response")),
                # What a failed call returned before it was rejected, e.g. truncated output.
                "raw": clip(record.get("raw"), RAW_LIMIT),
            }
        )
    return calls


def builds(run: Path) -> list[dict[str, Any]]:
    """Each native build and test check, oldest first, with the log files it wrote."""
    evidence = run / "evidence"
    found = []
    for folder in evidence.iterdir() if evidence.is_dir() else []:
        if not folder.is_dir() or folder.is_symlink():
            continue
        logs = [
            {"path": path.relative_to(run).as_posix(), "size": path.stat().st_size}
            for path in sorted(folder.rglob("*"))
            if path.is_file() and not path.is_symlink()
        ]
        # Folders are named <label>-<12 hex digits>; the label says which check it was.
        label, _, suffix = folder.name.rpartition("-")
        found.append(
            {
                "label": label if len(suffix) == 12 else folder.name,
                "folder": folder.relative_to(run).as_posix(),
                "time": datetime.fromtimestamp(folder.stat().st_mtime, UTC).isoformat(),
                "files": logs,
            }
        )
    return sorted(found, key=lambda item: item["time"])


def run_detail(root: Path, run_id: str) -> dict[str, Any] | None:
    run = discover_runs(root).get(run_id)
    if run is None:
        return None
    events = _events(run)
    saved = checkpoints(run)
    result = _json(run / "result.json", {}) or {}
    stopped = result.get("status") in STOPPED
    executed = steps(saved, events, stopped)
    path = ["__start__", *(step["node"] for step in executed)]
    # A node stopped by an exception never reaches END even though result.json is terminal.
    if executed and executed[-1]["status"] != "interrupted":
        if _json(run / "result.json", {}).get("status") in TERMINAL:
            path.append("__end__")
    visits: dict[str, int] = {}
    for node in path:
        visits[node] = visits.get(node, 0) + 1
    transitions: dict[str, int] = {}
    for source, target in zip(path, path[1:], strict=False):
        transitions[f"{source}>{target}"] = transitions.get(f"{source}>{target}", 0) + 1
    return {
        "summary": {**summarize(run_id, run), "triage": triage.load(root).get(run_id) or None},
        "result": clip(_json(run / "result.json", {})),
        "comparison": compare(result),
        "builds": builds(run),
        "steps": executed,
        "checkpoint_count": len(saved),
        # Where a paused run resumes, and which step a re-run may start from.
        "next": saved[-1]["next"] if saved and stopped else [],
        "events": events,
        "model_calls": model_calls(run),
        "files": files(run),
        "graph": {**topology(), "visits": visits, "transitions": transitions},
    }


def state_at(root: Path, run_id: str, checkpoint: int) -> dict[str, Any] | None:
    """Complete graph state saved after a super-step, for time-travel inspection."""
    run = discover_runs(root).get(run_id)
    if run is None:
        return None
    for saved in checkpoints(run):
        if saved["step"] == checkpoint:
            return {"step": checkpoint, "time": saved["time"], "values": saved["values"]}
    return None


def read_file(root: Path, run_id: str, relative: str) -> tuple[bytes, str] | None:
    """Return a run artifact if it stays inside that run directory."""
    run = discover_runs(root).get(run_id)
    if run is None:
        return None
    target = (run / relative).resolve()
    if not target.is_relative_to(run.resolve()) or not target.is_file():
        return None
    if (
        target.name.casefold().startswith("checkpoints.sqlite")
        or target.stat().st_size > FILE_LIMIT
    ):
        return None
    kind = "application/json" if target.suffix == ".json" else "text/plain"
    return target.read_bytes(), kind


def failing_tests(root: Path, q: str = "", limit: int = 200) -> dict[str, Any]:
    """Every failing test seen by a run: how often it failed, was fixed or did not reproduce."""
    tests: dict[str, dict[str, Any]] = {}
    for run in list_runs(root):
        for name in dict.fromkeys(run["tests"]):
            if not name:
                continue
            entry = tests.setdefault(
                name, {"name": name, "runs": 0, "statuses": Counter(), "build_types": set()}
            )
            entry["runs"] += 1
            entry["statuses"][run["status"]] += 1
            entry["build_types"].add(run["build_type"])
            # Runs arrive newest first: the first one seen is the latest, the last the oldest.
            entry.setdefault("last", run)
            entry["first_seen"] = run["started"]
            if any(marker in run["reason"] for marker in NOT_REPRODUCED):
                entry["statuses"]["not_reproduced"] += 1
    needle = q.strip().casefold()
    rows = [
        {
            "name": entry["name"],
            "runs": entry["runs"],
            "statuses": dict(entry["statuses"]),
            "fixed": entry["statuses"]["ready"] + entry["statuses"]["published"],
            "not_reproduced": entry["statuses"]["not_reproduced"],
            "build_types": sorted(item for item in entry["build_types"] if item),
            "first_seen": entry["first_seen"],
            "last": {
                key: entry["last"][key] for key in ("id", "name", "status", "started", "live")
            },
        }
        for entry in tests.values()
        if not needle or needle in entry["name"].casefold()
    ]
    rows.sort(key=lambda row: (row["last"]["started"] or "", row["name"]), reverse=True)
    return {"tests": rows[:limit], "total": len(rows)}


def runs_for_test(root: Path, name: str) -> dict[str, Any]:
    """The runs that tried to repair one test, newest first."""
    return {"name": name, "runs": [run for run in list_runs(root) if name in run["tests"]]}


def _usage(run: Path) -> tuple[int, int]:
    tokens_in = tokens_out = 0
    folder = run / "model-calls"
    for path in folder.glob("*.json") if folder.is_dir() else []:
        usage = (_json(path, {}) or {}).get("usage") or {}
        if isinstance(usage, dict):
            tokens_in += int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
            tokens_out += int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    return tokens_in, tokens_out


def metrics(root: Path, days: int = 30, now: datetime | None = None) -> dict[str, Any]:
    """Outcome rates, durations and model use per workflow over the last ``days`` days."""
    if not 1 <= days <= 366:
        raise ValueError("Days must be between 1 and 366")
    now = now or datetime.now(UTC)
    since = (now - timedelta(days=days - 1)).date().isoformat()
    found = discover_runs(root)
    window = [run for run in list_runs(root) if (run["started"] or "")[:10] >= since]
    groups: dict[str, list[dict[str, Any]]] = {}
    for run in window:
        groups.setdefault(workflow_key(run), []).append(run)

    def aggregate(runs: list[dict[str, Any]]) -> dict[str, Any]:
        statuses = Counter(run["status"] for run in runs)
        decided = sum(statuses[key] for key in TERMINAL)
        candidates = [
            run["duration_seconds"]
            for run in runs
            if run["status"] in {"ready", "published"} and run["duration_seconds"]
        ]
        durations = [run["duration_seconds"] for run in runs if run["duration_seconds"]]
        calls = failed_calls = tokens_in = tokens_out = 0
        for run in runs:
            for event in _events(found[run["id"]]):
                if event.get("node") == "model_call":
                    calls += 1
                    failed_calls += event.get("ok") is False
            used_in, used_out = _usage(found[run["id"]])
            tokens_in, tokens_out = tokens_in + used_in, tokens_out + used_out
        return {
            "runs": len(runs),
            "statuses": dict(statuses),
            # Of the runs that reached a decision, the share that produced a verified fix.
            "fix_rate": round((statuses["ready"] + statuses["published"]) / decided, 3)
            if decided
            else None,
            "median_duration": statistics.median(durations) if durations else None,
            "median_time_to_candidate": statistics.median(candidates) if candidates else None,
            "model_calls": calls,
            "failed_model_calls": failed_calls,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        }

    first = date.fromisoformat(since)
    daily = []
    for offset in range(days):
        day = (first + timedelta(days=offset)).isoformat()
        daily.append(
            {"date": day, **Counter(run["status"] for run in window if run["started"][:10] == day)}
        )
    return {
        "days": days,
        "since": since,
        "total": aggregate(window),
        "workflows": [{"key": key, **aggregate(runs)} for key, runs in sorted(groups.items())],
        "daily": daily,
    }
