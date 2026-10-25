"""What the dashboard may do to a run, decided from the run's state on disk.

The page only shows the actions ``available`` returns; ``perform`` checks again, because the
run may have moved on since the page was drawn.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from auto_fix import control, history, triage
from auto_fix.jobs import REPLAYABLE, JobError, JobStore, run_dir
from auto_fix.jobs import now as jobs_now

# Jobs that act on an existing run; while one is queued or running, the run takes no others.
RUN_JOBS = {"resume", "replay", "repair", "retry"}


class Actions:
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.store = JobStore(state_dir)

    def _run(self, run_id: str) -> Path:
        # Only runs of this state directory can be controlled, not evaluation case runs.
        name = run_id.removeprefix("runs/")
        run = run_dir(self.state_dir, name) if run_id.startswith("runs/") else None
        if run is None:
            raise JobError("This run cannot be controlled from here")
        return run

    def _pending_job(self, name: str) -> dict[str, Any] | None:
        for job in self.store.all():
            if job.get("status") in {"queued", "running"} and job["kind"] in RUN_JOBS:
                if job["params"].get("run") == name or job.get("run_id") == name:
                    return job
        return None

    def _publishing(self, run: Path) -> bool:
        events = history.read_events(run)
        if events and events[-1].get("node") == "publish_pr":
            return True
        try:
            journal = json.loads((run / "publication.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        return journal.get("status") == "intent"

    def available(self, run_id: str) -> dict[str, Any]:
        """The actions the run page offers, and why some are missing."""
        try:
            run = self._run(run_id)
        except JobError:
            return {"actions": [], "note": ""}
        summary = history.summarize(run_id, run)
        status, live = summary["status"], summary["live"]
        job = self._pending_job(run.name)
        if job and job.get("status") == "queued":
            return {"actions": [], "note": f"Queued: {job['title']}", "job": job["id"]}
        actions: list[str] = []
        if status == "in_progress":
            if live:
                actions += [] if summary["request"] else ["pause", "cancel"]
                if not self._publishing(run):
                    actions.append("stop")
            else:
                # The process is gone without writing an outcome: record one.
                actions.append("cancel")
        elif status == "paused":
            actions += ["resume", "cancel", "replay"]
        elif status in {"blocked", "cancelled"}:
            actions += ["retry", "replay"]
        elif status == "ready":
            # A reviewer rejected this candidate: it is not published until someone reopens it.
            rejected = triage.load(self.state_dir).get(run_id, {}).get("state") == "rejected"
            actions += ["replay"] if rejected else ["publish", "replay"]
            if rejected:
                return {"actions": actions, "note": "Fix rejected: reopen it to publish"}
        elif status == "publication_unknown":
            actions.append("reconcile")
        return {"actions": actions, "note": ""}

    def perform(self, run_id: str, action: str, by: str, step: Any = None) -> dict[str, Any]:
        run = self._run(run_id)
        if action not in self.available(run_id)["actions"]:
            raise JobError("That action is not available for this run any more")
        name = run.name
        if action in {"pause", "cancel"} and control.process(run):
            return {"request": control.request(run, action, by)}
        if action == "cancel":
            reason = f"Cancelled by {by}"
            return {"result": control.mark_stopped(run, "cancelled", reason, by, idle=True)}
        if action == "stop":
            live = control.process(run)
            if live is None:
                raise JobError("The run's process has already ended")
            events = history.read_events(run)
            node = next(
                (e["node"] for e in reversed(events) if e.get("node") not in {"model_call"}), "?"
            )
            control.kill_tree(live["pid"])
            reason = f"Stopped by {by} during {node}"
            return {"result": control.mark_stopped(run, "cancelled", reason, by)}
        if action == "resume":
            return {"job": self.store.add("resume", {"run": name}, by)}
        if action == "retry":
            return {"job": self.store.add("retry", {"run": name}, by)}
        if action in {"publish", "reconcile"}:
            return {"job": self.store.add("repair", {"run": name, "mode": action}, by)}
        if action == "replay":
            if isinstance(step, bool) or not isinstance(step, int):
                raise JobError("Choose the step to re-run from")
            saved, executed = history.run_steps(run)
            if not saved:
                raise JobError("This run has no checkpoints to re-run from")
            if not 0 < step < len(executed) or executed[step]["node"] not in REPLAYABLE:
                raise JobError("A re-run can start at baseline, investigate, repair or verify")
            return {"job": self.store.add("replay", {"run": name, "step": step}, by)}
        raise JobError(f"Unknown action: {action}")

    def stop_job(self, job_id: str, by: str) -> dict[str, Any]:
        """Kill a running job, such as an evaluation, that has no run page of its own to stop."""
        job = self.store.get(job_id)
        if job is None or job.get("status") != "running":
            raise JobError("Only a running job can be stopped")
        run = run_dir(self.state_dir, job.get("run_id") or "")
        if run is not None and self._publishing(run):
            raise JobError("The job is publishing a pull request; let it finish")
        if job.get("pid") and control.alive(job["pid"]):
            control.kill_tree(job["pid"])
        if run is not None and history.summarize(run.name, run)["status"] == "in_progress":
            control.mark_stopped(run, "cancelled", f"Stopped by {by} with its job", by)
        return {
            "job": self.store.update(
                job_id, status="cancelled", ended=jobs_now(), error=f"Stopped by {by}"
            )
        }
