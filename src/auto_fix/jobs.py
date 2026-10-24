"""Workflow jobs started from the dashboard: the queue, the catalogue and the runner.

A job is one JSON file in ``state_dir/jobs``. The dashboard adds jobs, the runner starts the
first queued one as ``auto-fix job --id …`` when nothing else runs, and the job process reports
its own outcome. Jobs run one at a time; repair-type jobs also take ``worker.lock`` like the
scheduled ``run`` command, so the two never touch worktrees at the same time.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import threading
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from filelock import FileLock, Timeout

from auto_fix import control

LOCK_BUSY = 3
# The runner's heartbeat goes stale after this many seconds without a pass.
STALE_SECONDS = 15
# Kinds that touch the state directory's worktrees and must hold worker.lock.
LOCKED = {"repair", "resume", "replay"}
FINISHED = {"done", "failed", "cancelled", "paused"}
PROMPTS = ["repair-v1", "evidence-v2", "contract-v3", "assertion-v4"]
REPLAYABLE = {"baseline", "investigate", "repair", "verify"}


class JobError(ValueError):
    """A request the queue refuses; ``fields`` maps form fields to messages."""

    def __init__(self, message: str, fields: dict[str, str] | None = None):
        super().__init__(message)
        self.fields = fields or {}


def _param(name, label, kind, default=None, **extra) -> dict[str, Any]:
    return {"name": name, "label": label, "type": kind, "default": default, **extra}


# Ranges match the checks in run_evaluation and run_operational_evaluation.
EVALUATION_TUNING = [
    _param(
        "inspections_per_attempt", "Inspections per attempt", "int", 6, min=1, max=6, advanced=True
    ),
    _param("baseline_repetitions", "Baseline repetitions", "int", 1, min=1, max=3, advanced=True),
    _param(
        "context_chars", "Context characters", "int", 60000, min=4000, max=200000, advanced=True
    ),
    _param(
        "reasoning_effort",
        "Reasoning effort",
        "choice",
        "medium",
        choices=["medium", "high"],
        advanced=True,
    ),
    _param("definition_reads", "Read symbol definitions", "bool", False, advanced=True),
]

# What the start panel offers. Each entry's parameters drive the form, validation and the
# equivalent command line.
WORKFLOWS: dict[str, dict[str, Any]] = {
    "batch": {
        "title": "Daily repair batch",
        "icon": "context",
        "description": "Find a day's failed TeamCity tests and queue one repair per failure.",
        "params": [
            _param(
                "date",
                "Failures from",
                "date",
                "today",
                help="TeamCity builds that finished on this day, in the configured timezone.",
            ),
            _param("publish", "Publish verified fixes as pull requests", "bool", False),
            _param("retry_blocked", "Retry failures whose last run stopped", "bool", False),
        ],
    },
    "retry": {
        "title": "Retry a run",
        "icon": "wrench",
        "description": "Repair one failure again in a fresh worktree, keeping the old evidence.",
        "params": [
            _param(
                "run",
                "Run",
                "run",
                None,
                statuses=["blocked", "cancelled"],
                help="Blocked or cancelled runs of this state directory.",
            ),
        ],
    },
    "evaluation": {
        "title": "Evaluation",
        "icon": "flask",
        "description": "Repair the C++ fixture cases with a live or replayed model.",
        "params": [
            _param(
                "profile",
                "Profile",
                "choice",
                "focused",
                choices=["legacy", "focused"],
                advanced=True,
            ),
            _param(
                "backend",
                "Model backend",
                "choice",
                "codex",
                choices=["codex", "endpoint", "replay"],
                advanced=True,
            ),
            _param("model", "Model", "text", "gpt-6-luna", advanced=True),
            _param(
                "cases",
                "Cases",
                "text",
                "",
                help="Comma-separated case names; empty runs every case.",
            ),
            _param(
                "split",
                "Split",
                "choice",
                "",
                choices=["", "development", "holdout"],
                advanced=True,
            ),
            _param("prompt", "Prompt", "choice", "repair-v1", choices=PROMPTS),
            _param("max_attempts", "Repair attempts", "int", 2, min=1, max=10),
            _param("max_inspections", "Source inspections", "int", 0, min=0, max=50, advanced=True),
            *EVALUATION_TUNING,
            _param(
                "structured_diagnostics", "Structured diagnostics", "bool", False, advanced=True
            ),
            _param("upstream_cache", "Upstream cache", "text", ".auto-fix/upstream", advanced=True),
            _param(
                "endpoint_config",
                "Endpoint config",
                "text",
                "",
                advanced=True,
                help="Configuration file for the endpoint backend.",
            ),
            _param("recordings", "Recordings", "text", "", advanced=True),
            _param("project_file", "Project file", "text", "", advanced=True),
            _param("cases_file", "Cases file", "text", "", advanced=True),
        ],
    },
    "operations": {
        "title": "Operations evaluation",
        "icon": "branch",
        "description": "Exercise real Git and native workflow fault scenarios.",
        "params": [
            _param("prompt", "Prompt", "choice", "contract-v3", choices=PROMPTS),
            _param("max_inspections", "Source inspections", "int", 1, min=0, max=6),
            _param(
                "cases",
                "Cases",
                "text",
                "",
                help="Comma-separated scenario names; empty runs every scenario.",
            ),
            *EVALUATION_TUNING,
            _param("upstream_cache", "Upstream cache", "text", "", advanced=True),
        ],
    },
    "demo": {
        "title": "Demo",
        "icon": "start",
        "description": "The offline sample repair with mock services. Needs Git and CMake.",
        "params": [],
    },
}

# Kinds created by run actions rather than the start panel.
INTERNAL: dict[str, list[dict[str, Any]]] = {
    "repair": [
        _param("run", "Run", "run", None),
        _param("failure", "Failure", "object", None),
        _param("mode", "Mode", "choice", "new", choices=["new", "retry", "publish", "reconcile"]),
        _param("publish", "Publish", "bool", False),
        _param("retry_blocked", "Retry blocked", "bool", False),
    ],
    "resume": [_param("run", "Run", "run", None)],
    "replay": [_param("run", "Run", "run", None), _param("step", "Step", "int", 0, min=0)],
}


def now() -> str:
    return datetime.now(UTC).isoformat()


def run_dir(state_dir: Path, name: str) -> Path | None:
    """A run directly below this state directory's ``runs``; never a path outside it."""
    if not name or "/" in name or "\\" in name or name in {".", ".."}:
        return None
    run = state_dir / "runs" / name
    return run if run.is_dir() else None


def validate(kind: str, params: dict[str, Any], state_dir: Path) -> dict[str, Any]:
    """Check parameters against the kind's schema and return them with defaults filled in."""
    schema = WORKFLOWS[kind]["params"] if kind in WORKFLOWS else INTERNAL.get(kind)
    if schema is None:
        raise JobError(f"Unknown workflow: {kind}")
    if not isinstance(params, dict):
        raise JobError("Parameters must be an object")
    unknown = set(params) - {field["name"] for field in schema}
    if unknown:
        raise JobError("Unknown parameters: " + ", ".join(sorted(unknown)))
    clean: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for field in schema:
        name, value = field["name"], params.get(field["name"], field["default"])
        kind_of = field["type"]
        try:
            if kind_of == "bool":
                if not isinstance(value, bool):
                    raise ValueError("Expected true or false")
            elif kind_of == "int":
                if isinstance(value, bool) or not isinstance(value, int | str):
                    raise ValueError("Expected a whole number")
                value = int(value)
                if not field.get("min", value) <= value <= field.get("max", value):
                    raise ValueError(f"Between {field.get('min')} and {field.get('max')}")
            elif kind_of == "choice":
                if value not in field["choices"]:
                    raise ValueError(
                        "Choose one of: " + ", ".join(c or "(none)" for c in field["choices"])
                    )
            elif kind_of == "date":
                value = date.today().isoformat() if value in (None, "", "today") else str(value)
                date.fromisoformat(value)
            elif kind_of == "text":
                value = "" if value is None else str(value).strip()
                if len(value) > 2000:
                    raise ValueError("Too long")
            elif kind_of == "run":
                if value is not None:
                    run = run_dir(state_dir, str(value))
                    if run is None:
                        raise ValueError("No such run in this state directory")
                    wanted = field.get("statuses")
                    if wanted:
                        from auto_fix import history

                        status = history.summarize(run.name, run)["status"]
                        if status not in wanted:
                            raise ValueError(f"This run is {status}")
            elif kind_of == "object":
                if value is not None and not isinstance(value, dict):
                    raise ValueError("Expected an object")
        except ValueError as exc:
            errors[name] = str(exc) or "Invalid value"
            continue
        clean[name] = value
    if kind == "retry" and not clean.get("run") and "run" not in errors:
        errors["run"] = "Choose a run to retry"
    if kind in {"resume", "replay"} and not clean.get("run") and "run" not in errors:
        errors["run"] = "A run is required"
    if kind == "repair" and not (clean.get("run") or clean.get("failure")) and not errors:
        errors["run"] = "A run or a failure is required"
    if errors:
        raise JobError("Some parameters are not valid", errors)
    return clean


def command(kind: str, params: dict[str, Any], config: Path) -> list[str]:
    """The command line that does the same as this job, shown in the start panel."""
    base = ["auto-fix"]
    if kind == "batch":
        argv = [*base, "run", "--config", str(config), "--date", params["date"]]
        return (
            argv + ["--publish"] * params["publish"] + ["--retry-blocked"] * params["retry_blocked"]
        )
    if kind in {"evaluation", "operations"}:
        argv = [*base, "evaluate" if kind == "evaluation" else "evaluate-operations"]
        argv += ["--directory", "<state_dir>/evaluations/<job>"]
        flags = {"endpoint_config": "--config"}
        for name, value in params.items():
            if name == "cases":
                for case in filter(None, (c.strip() for c in value.split(","))):
                    argv += ["--case", case]
            elif value is True:
                argv.append("--" + name.replace("_", "-"))
            elif value not in (False, "", None):
                argv += [flags.get(name, "--" + name.replace("_", "-")), str(value)]
        return argv
    if kind == "demo":
        return [*base, "demo", "--directory", "<state_dir>/demos/<job>"]
    argv = [*base, "queue", "--config", str(config), "--kind", kind]
    for name, value in params.items():
        if value not in (None, "", False) and name != "failure":
            argv += [
                "--param",
                f"{name}={json.dumps(value) if not isinstance(value, str) else value}",
            ]
    return argv


class JobStore:
    """The job files of one state directory. Every write holds ``jobs/.lock``."""

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.dir = state_dir / "jobs"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.lock = FileLock(str(self.dir / ".lock"), timeout=10)

    def _path(self, job_id: str) -> Path:
        if not job_id or not all(c.isalnum() or c in "-_" for c in job_id):
            raise JobError("Unknown job")
        return self.dir / f"{job_id}.json"

    def _read(self, path: Path) -> dict[str, Any] | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def _write(self, job: dict[str, Any]) -> None:
        temporary = self._path(job["id"]).with_suffix(".tmp")
        temporary.write_text(json.dumps(job, indent=2), encoding="utf-8")
        temporary.replace(self._path(job["id"]))

    def get(self, job_id: str) -> dict[str, Any] | None:
        return self._read(self._path(job_id))

    def all(self) -> list[dict[str, Any]]:
        # runner.json lives here too; a job file is named after its id.
        jobs = [
            job
            for path in self.dir.glob("*.json")
            if (job := self._read(path)) and job.get("id") == path.stem
        ]
        order = {"running": 0, "queued": 1}
        return sorted(
            jobs,
            key=lambda job: (
                order.get(job.get("status"), 2),
                job.get("position", 0) if job.get("status") == "queued" else 0,
                "" if job.get("status") in order else _desc(job.get("ended") or ""),
            ),
        )

    def add(
        self,
        kind: str,
        params: dict[str, Any],
        by: str,
        *,
        front: bool = False,
        title: str | None = None,
    ) -> dict[str, Any]:
        clean = validate(kind, params, self.state_dir)
        with self.lock:
            queued = [job["position"] for job in self.all() if job.get("status") == "queued"]
            position = (min(queued, default=1) - 1) if front else (max(queued, default=-1) + 1)
            stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
            job = {
                "id": f"{stamp}-{kind}-{secrets.token_hex(2)}",
                "kind": kind,
                "title": title or describe(kind, clean),
                "params": clean,
                "status": "queued",
                "position": position,
                "created": now(),
                "created_by": by,
            }
            self._write(job)
            return job

    def update(self, job_id: str, **fields: Any) -> dict[str, Any]:
        with self.lock:
            job = self.get(job_id)
            if job is None:
                raise JobError("Unknown job")
            job.update(fields)
            self._write(job)
            return job

    def remove(self, job_id: str) -> None:
        with self.lock:
            job = self.get(job_id)
            if job is None:
                raise JobError("Unknown job")
            if job["status"] == "running":
                raise JobError("A running job cannot be removed; stop its run instead")
            self._path(job_id).unlink(missing_ok=True)

    def move(self, job_id: str, delta: int) -> None:
        with self.lock:
            queued = [job for job in self.all() if job.get("status") == "queued"]
            index = next((i for i, job in enumerate(queued) if job["id"] == job_id), None)
            if index is None:
                raise JobError("Only queued jobs can be moved")
            other = index + (1 if delta > 0 else -1)
            if not 0 <= other < len(queued):
                return
            first, second = queued[index], queued[other]
            first["position"], second["position"] = second["position"], first["position"]
            self._write(first)
            self._write(second)

    def requeue_front(self, job_id: str, note: str) -> None:
        with self.lock:
            queued = [job["position"] for job in self.all() if job.get("status") == "queued"]
            job = self.get(job_id)
            if job:
                job.update(
                    status="queued", position=min(queued, default=1) - 1, pid=None, note=note
                )
                self._write(job)

    def for_run(self, run_name: str) -> dict[str, Any] | None:
        return next(
            (
                job
                for job in self.all()
                if job.get("status") == "running" and job.get("run_id") == run_name
            ),
            None,
        )


def _desc(stamp: str) -> str:
    # Newest finished jobs first inside an ascending sort.
    return "".join(chr(0x10FFFF - ord(c)) for c in stamp)


def describe(kind: str, params: dict[str, Any]) -> str:
    if kind == "batch":
        return f"Repair batch for {params['date']}" + (" · publish" if params["publish"] else "")
    if kind == "retry" or (kind == "repair" and params.get("mode") == "retry"):
        return f"Retry {params.get('run')}"
    if kind == "repair":
        if params.get("run"):
            return {"publish": "Publish", "reconcile": "Reconcile"}.get(
                params.get("mode", ""), "Repair"
            ) + f" {params['run']}"
        failure = params.get("failure") or {}
        tests = ", ".join(test.get("name", "") for test in failure.get("tests", [])[:2])
        return f"Repair build {failure.get('build_id', '?')}" + (f" · {tests}" if tests else "")
    if kind == "resume":
        return f"Resume {params['run']}"
    if kind == "replay":
        return f"Re-run {params['run']} from step {params['step'] + 1}"
    return WORKFLOWS.get(kind, {}).get("title", kind)


class Runner:
    """Starts queued jobs one at a time and notices job processes that died.

    Only the process holding ``jobs/runner.lock`` schedules; another runner (an embedded one
    while ``auto-fix worker`` runs, say) stays idle. ``command`` is replaceable for tests.
    """

    def __init__(
        self,
        config: Path,
        state_dir: Path,
        *,
        poll: float = 1.0,
        command: Any = None,
        cwd: Path | None = None,
    ):
        self.config = config.resolve()
        self.store = JobStore(state_dir)
        self.state_dir = state_dir
        self.poll = poll
        self.cwd = cwd or Path.cwd()
        self.command = command or (
            lambda job: [
                sys.executable,
                "-m",
                "auto_fix.cli",
                "job",
                "--config",
                str(self.config),
                "--id",
                job["id"],
            ]
        )
        self.lock = FileLock(str(self.store.dir / "runner.lock"), timeout=0)
        self.children: dict[str, subprocess.Popen] = {}
        self.active = False
        self._stop = threading.Event()

    def heartbeat(self, waiting: str = "") -> None:
        record = {"pid": os.getpid(), "beat": time.time(), "waiting": waiting}
        temporary = self.store.dir / "runner.tmp"
        temporary.write_text(json.dumps(record), encoding="utf-8")
        temporary.replace(self.store.dir / "runner.json")

    def tick(self) -> None:
        if not self.active:
            try:
                self.lock.acquire()
            except Timeout:
                return
            self.active = True
        waiting = ""
        running = [job for job in self.store.all() if job.get("status") == "running"]
        for job in running:
            child = self.children.get(job["id"])
            ended = child.poll() is not None if child else not control.alive(job.get("pid") or 0)
            if ended:
                self.children.pop(job["id"], None)
                self._died(job["id"])
        if not any(job.get("status") == "running" for job in self.store.all()):
            queued = [job for job in self.store.all() if job.get("status") == "queued"]
            if queued:
                job = queued[0]
                if job["kind"] in LOCKED and not self._worker_free():
                    waiting = "Waiting for the worker lock: another repair run is in progress"
                else:
                    self._start(job)
        self.heartbeat(waiting)

    def _worker_free(self) -> bool:
        lock = FileLock(str(self.state_dir / "worker.lock"), timeout=0)
        try:
            lock.acquire()
        except Timeout:
            return False
        lock.release()
        return True

    def _start(self, job: dict[str, Any]) -> None:
        log = self.store.dir / f"{job['id']}.log"
        extra: dict[str, Any] = (
            {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
            if sys.platform == "win32"
            else {"start_new_session": True}
        )
        with log.open("ab") as handle:
            child = subprocess.Popen(
                self.command(job),
                stdout=handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                cwd=self.cwd,
                env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"},
                **extra,
            )
        self.children[job["id"]] = child
        self.store.update(
            job["id"], status="running", started=now(), pid=child.pid, log=log.name, note=""
        )

    def _died(self, job_id: str) -> None:
        """A job process ended; if it did not report an outcome it died or was killed."""
        job = self.store.get(job_id)
        if not job or job.get("status") != "running":
            return
        run = run_dir(self.state_dir, job.get("run_id") or "")
        result = {}
        if run:
            try:
                result = json.loads((run / "result.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                result = {}
        if result.get("status") == "cancelled":
            self.store.update(
                job_id, status="cancelled", ended=now(), error=result.get("reason", "")
            )
        else:
            self.store.update(
                job_id,
                status="failed",
                ended=now(),
                error="The job process ended without reporting a result",
            )

    def serve_forever(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as exc:  # A bad job file must not stop the queue.
                print(f"runner: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            self._stop.wait(self.poll)

    def start_thread(self) -> threading.Thread:
        thread = threading.Thread(target=self.serve_forever, name="auto-fix-runner", daemon=True)
        thread.start()
        return thread

    def stop(self) -> None:
        self._stop.set()
        if self.active:
            self.lock.release()
            self.active = False


def runner_state(state_dir: Path) -> dict[str, Any]:
    """Whether some runner is scheduling jobs, for the dashboard's queue header."""
    try:
        record = json.loads((state_dir / "jobs" / "runner.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"alive": False, "waiting": ""}
    alive = time.time() - record.get("beat", 0) < STALE_SECONDS and control.alive(
        record.get("pid", 0)
    )
    return {"alive": alive, "waiting": record.get("waiting", "") if alive else ""}


class LockBusy(RuntimeError):
    """Another process holds worker.lock; the job waits at the front of the queue."""


def _services(settings: Any) -> tuple[tuple[Any, Any, Any, Any], list[Any]]:
    from auto_fix.integrations import Bitbucket, Jira, TeamCity
    from auto_fix.llm import RepairModel

    teamcity, bitbucket = TeamCity(settings.teamcity), Bitbucket(settings.bitbucket)
    model = RepairModel(settings.llm)
    jira = Jira(settings.jira) if settings.jira else None
    opened = [teamcity, bitbucket, model] + ([jira] if jira else [])
    return (teamcity, bitbucket, jira, model), opened


def _outcome(result: dict[str, Any]) -> dict[str, Any]:
    """A job's status from the run it drove: the run's own status is shown on the run."""
    status = result.get("status", "")
    job = {"paused": "paused", "cancelled": "cancelled"}.get(status, "done")
    return {"status": job, "result": status, "run_id": result.get("run_id")}


def _repair(settings: Any, store: JobStore, job: dict[str, Any], services: Any) -> dict[str, Any]:
    from auto_fix.cli import process_failure
    from auto_fix.models import Failure

    params = job["params"]
    failure = params.get("failure")
    if failure is None:
        run = run_dir(settings.state_dir, params["run"])
        if run is None:
            raise JobError(f"Run {params['run']} no longer exists")
        failure = json.loads((run / "result.json").read_text(encoding="utf-8"))["failure"]
    publish, retry = {
        "retry": (False, True),
        "publish": (True, False),
        "reconcile": (False, False),
    }.get(params["mode"], (params["publish"], params["retry_blocked"]))
    result = process_failure(
        settings,
        Failure.model_validate(failure),
        services,
        publish=publish,
        retry_blocked=retry,
        on_run=lambda run_id: store.update(job["id"], run_id=run_id),
    )
    return _outcome(result)


def _continue(settings: Any, store: JobStore, job: dict[str, Any], services: Any) -> dict[str, Any]:
    """Resume a paused run, or fork a run from a step, and record the outcome as its receipt."""
    from auto_fix.workflow import Workflow, fork, write_json

    params = job["params"]
    source = run_dir(settings.state_dir, params["run"])
    if source is None:
        raise JobError(f"Run {params['run']} no longer exists")
    key = control.receipt_key(source.name)
    receipt = settings.state_dir / "receipts" / f"{key}.json"
    if job["kind"] == "resume":
        run_id = source.name
        try:
            saved = json.loads(receipt.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = {}
        # The paused receipt would otherwise hide the resumed run's progress.
        if saved.get("run_id") == run_id:
            receipt.unlink(missing_ok=True)
    else:
        attempt, run_id = 1, f"{key}-r1"
        while (settings.state_dir / "runs" / run_id).exists():
            attempt += 1
            run_id = f"{key}-r{attempt}"
    store.update(job["id"], run_id=run_id)
    teamcity, bitbucket, jira, model = services
    # A resumed or re-run repair never publishes on its own; publish a ready run afterwards.
    flow = Workflow(settings, run_id, teamcity, bitbucket, jira, model, publish=False)
    if job["kind"] == "replay":
        fork(flow, source, params["step"])
    result = flow.run(None)
    write_json(receipt, {**result, "run_id": run_id})
    return _outcome({**result, "run_id": run_id})


def _evaluate(settings: Any, job: dict[str, Any]) -> dict[str, Any]:
    kind, params = job["kind"], job["params"]
    folder = settings.state_dir / ("demos" if kind == "demo" else "evaluations") / job["id"]
    cases = [case.strip() for case in params.get("cases", "").split(",") if case.strip()]

    def path(name: str) -> Path | None:
        return Path(params[name]) if params.get(name) else None

    if kind == "demo":
        from auto_fix.demo import run_demo

        code = run_demo(folder)
    elif kind == "evaluation":
        from auto_fix.evaluation import run_evaluation

        code = run_evaluation(
            folder,
            profile=params["profile"],
            backend=params["backend"],
            model_name=params["model"],
            selected=cases or None,
            upstream_cache=path("upstream_cache"),
            endpoint_config=path("endpoint_config"),
            recordings=path("recordings"),
            project_file=path("project_file"),
            cases_file=path("cases_file"),
            split=params["split"] or None,
            prompt_version=params["prompt"],
            max_inspections=params["max_inspections"],
            inspections_per_attempt=params["inspections_per_attempt"],
            max_attempts=params["max_attempts"],
            baseline_repetitions=params["baseline_repetitions"],
            reasoning_effort=params["reasoning_effort"],
            structured_diagnostics=params["structured_diagnostics"],
            context_chars=params["context_chars"],
            definition_reads=params["definition_reads"],
        )
    else:
        from auto_fix.operational_evaluation import run_operational_evaluation

        code = run_operational_evaluation(
            folder,
            prompt_version=params["prompt"],
            max_inspections=params["max_inspections"],
            inspections_per_attempt=params["inspections_per_attempt"],
            context_chars=params["context_chars"],
            definition_reads=params["definition_reads"],
            reasoning_effort=params["reasoning_effort"],
            upstream_cache=path("upstream_cache"),
            selected=cases or None,
            baseline_repetitions=params["baseline_repetitions"],
        )
    if code == 0:
        return {"status": "done", "result": "exit code 0"}
    return {"status": "failed", "result": f"exit code {code}", "error": "See the job log"}


def _dispatch(settings: Any, store: JobStore, job: dict[str, Any]) -> dict[str, Any]:
    kind, params = job["kind"], job["params"]
    if kind == "batch":
        from auto_fix.integrations import TeamCity

        teamcity = TeamCity(settings.teamcity)
        try:
            failures = teamcity.failures(date.fromisoformat(params["date"]), settings.timezone)
        finally:
            teamcity.close()
        # Front of the queue in reverse keeps TeamCity's order ahead of jobs queued later.
        for failure in reversed(failures):
            store.add(
                "repair",
                {
                    "failure": failure.model_dump(),
                    "mode": "new",
                    "publish": params["publish"],
                    "retry_blocked": params["retry_blocked"],
                },
                job.get("created_by", ""),
                front=True,
            )
        return {"status": "done", "result": f"Queued {len(failures)} repairs"}
    if kind in {"evaluation", "operations", "demo"}:
        return _evaluate(settings, job)
    if kind == "retry":
        retry = {"mode": "retry", "failure": None, "publish": False, "retry_blocked": True}
        job = {**job, "kind": "repair", "params": {**params, **retry}}
    # Every other kind changes worktrees and checkpoints: one at a time, like ``run``.
    lock = FileLock(str(settings.state_dir / "worker.lock"), timeout=0)
    try:
        lock.acquire()
    except Timeout as exc:
        raise LockBusy() from exc
    services, opened = _services(settings)
    try:
        if job["kind"] == "repair":
            return _repair(settings, store, job, services)
        if job["kind"] in {"resume", "replay"}:
            return _continue(settings, store, job, services)
        raise JobError(f"Unknown workflow: {job['kind']}")
    finally:
        for service in reversed(opened):
            service.close()
        lock.release()


def execute(config: Path, job_id: str) -> int:
    """Run one queued job in this process and record its outcome in the job file."""
    from dotenv import load_dotenv

    from auto_fix import tracing
    from auto_fix.config import load_settings
    from auto_fix.workflow import redact

    load_dotenv(config.resolve().parent / ".env", override=False)
    settings = load_settings(config)
    store = JobStore(settings.state_dir)
    job = store.get(job_id)
    if job is None:
        print(f"No job {job_id}")
        return 2
    store.update(job_id, status="running", pid=os.getpid(), started=job.get("started") or now())
    if settings.tracing:
        tracing.configure(settings.tracing.endpoint, settings.tracing.project)
    try:
        outcome = _dispatch(settings, store, job)
    except LockBusy:
        store.requeue_front(job_id, "Waiting for the worker lock")
        print("worker.lock is busy; the job waits at the front of the queue")
        return LOCK_BUSY
    except Exception as exc:
        message = redact(f"{type(exc).__name__}: {exc}")
        store.update(job_id, status="failed", ended=now(), error=message)
        print(message)
        return 1
    finally:
        tracing.shutdown()
    store.update(job_id, ended=now(), **outcome)
    print(json.dumps(outcome))
    return 0 if outcome["status"] != "failed" else 1
