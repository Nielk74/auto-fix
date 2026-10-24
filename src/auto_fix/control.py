"""Requests to pause or cancel a run between steps, and the process that is running it.

The dashboard writes a request into the run directory; ``Workflow.run`` reads it after every
checkpoint, so a run only ever stops on a clean step boundary. ``process.json`` names the live
process so that "Stop now" can reach a run whoever started it.
"""

from __future__ import annotations

import ctypes
import json
import os
import signal
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL = "control.json"
PROCESS = "process.json"
REQUESTS = {"pause", "cancel"}


def now() -> str:
    return datetime.now(UTC).isoformat()


def _read(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write(path: Path, data: dict[str, Any]) -> None:
    from auto_fix.workflow import write_json

    write_json(path, data)


def request(run: Path, action: str, by: str) -> dict[str, Any]:
    """Ask the run to pause or cancel after its current step."""
    if action not in REQUESTS:
        raise ValueError(f"Unknown request: {action}")
    record = {"request": action, "by": by, "at": now()}
    _write(run / CONTROL, record)
    return record


def pending(run: Path) -> dict[str, Any] | None:
    record = _read(run / CONTROL)
    return record if record and record.get("request") in REQUESTS else None


def clear(run: Path) -> None:
    (run / CONTROL).unlink(missing_ok=True)


def mark_process(run: Path) -> None:
    _write(run / PROCESS, {"pid": os.getpid(), "started": now()})


def clear_process(run: Path) -> None:
    record = _read(run / PROCESS)
    # A resumed run in another process may own the marker by now.
    if record and record.get("pid") == os.getpid():
        (run / PROCESS).unlink(missing_ok=True)


def process(run: Path) -> dict[str, Any] | None:
    """The live process running this run, or None when it ended or was killed."""
    record = _read(run / PROCESS)
    if record and isinstance(record.get("pid"), int) and alive(record["pid"]):
        return record
    return None


def alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def kill_tree(pid: int) -> None:
    """Kill a process and everything it started: builds and test runners included."""
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, check=False, timeout=30
        )
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except ProcessLookupError:
        pass


def receipt_key(run_name: str) -> str:
    return run_name.rsplit("-r", 1)[0] if "-r" in run_name else run_name


def mark_stopped(
    run: Path, status: str, reason: str, by: str, idle: bool = False
) -> dict[str, Any]:
    """Record a terminal status for a run whose process is gone: result, event and receipt.

    ``idle`` marks a run that was not working when stopped (paused, or its process long gone),
    so the time until now does not count as its duration.
    """
    result = _read(run / "result.json") or {}
    result.update(status=status, reason=reason)
    _write(run / "result.json", result)
    event = {"time": now(), "node": "stopped", "status": status, "reason": reason, "by": by}
    if idle:
        event["idle"] = True
    with (run / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")
    # The receipt keeps the next scheduled run from reading the leftover directory as a crash.
    receipt = {**result, "run_id": run.name}
    _write(run.parent.parent / "receipts" / f"{receipt_key(run.name)}.json", receipt)
    clear(run)
    (run / PROCESS).unlink(missing_ok=True)
    return result
