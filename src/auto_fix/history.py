"""Read-only reconstruction of workflow runs from their evidence directories and checkpoints.

Nothing here writes to a run directory, so the dashboard can inspect a state directory while
the scheduled worker is still executing a graph.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from auto_fix import control

TERMINAL = {"ready", "published", "blocked", "publication_unknown"}
# Runs stopped on a step boundary by a request; a paused run resumes from its checkpoint.
STOPPED = {"paused", "cancelled"}
RUN_MARKERS = ("events.jsonl", "checkpoints.sqlite", "result.json")
# Large evidence directories are listed, never inlined into API responses.
TEXT_LIMIT = 4000
FILE_LIMIT = 2_000_000


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
        "attempts": result.get("attempt", 0),
        "inspections": result.get("inspections", 0),
        "branch": result.get("branch", ""),
        "head": result.get("head", ""),
        "pr_url": _pr_url((receipt or {}).get("pr") or result.get("pr")),
        "model_calls": len(list(calls.glob("*.json"))) if calls.is_dir() else 0,
        # Run controls: a pending pause/cancel, whether a process still runs it, and its origin.
        "request": control.pending(run),
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
    runs = [summarize(run_id, run) for run_id, run in discover_runs(root).items()]
    return sorted(runs, key=lambda run: run["started"] or "", reverse=True)


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
        if path.is_file() and not path.name.startswith("checkpoints.sqlite"):
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
            }
        )
    return calls


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
        "summary": summarize(run_id, run),
        "result": clip(_json(run / "result.json", {})),
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
    if target.name.startswith("checkpoints.sqlite") or target.stat().st_size > FILE_LIMIT:
        return None
    kind = "application/json" if target.suffix == ".json" else "text/plain"
    return target.read_bytes(), kind
