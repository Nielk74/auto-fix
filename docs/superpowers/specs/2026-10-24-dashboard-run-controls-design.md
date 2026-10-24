# Dashboard run controls

Date: 2026-10-24. Status: approved in conversation (sections 1–3); section 4 written for implementation.

## Goal

Let the dashboard user start workflows with parameters, and pause, resume, cancel, stop, retry,
publish or re-run a repair from a chosen step, without leaving the browser. The dashboard stays
read-only when it is started without `--config`.

Decisions taken with the user:

- Launchable: daily repair batch, retry one run, evaluations, operations evaluations, the demo,
  and re-running a run from a step.
- Access: local only for now (loopback), with an authorisation hook ready for a team setup.
- Concurrency: jobs queue and run one at a time.
- Cancel: safe by default (after the current step), plus "Stop now" which kills the process.
- Architecture: a shared runner that runs inside the dashboard or as `auto-fix worker`.

## 1. Components

- `auto_fix/control.py` — per-run control requests and process markers.
  - `runs/<id>/control.json`: `{"request": "pause" | "cancel", "by", "at"}`.
  - `runs/<id>/process.json`: `{"pid", "started"}`, written by `Workflow.run` while it executes,
    so "Stop now" works for runs started by the dashboard or by the scheduled `run` command.
  - `mark_stopped()` writes a terminal `cancelled` result, event and receipt for a run whose
    process is gone (paused-then-cancelled, or stopped).
- `auto_fix/jobs.py` — the queue, the job catalogue and the runner.
  - A job is `state_dir/jobs/<id>.json`: kind, params, status (`queued`, `running`, `done`,
    `failed`, `cancelled`), queue position, who and when, pid, run id, log path.
    Writes go through a `FileLock` on `jobs/.lock` because the dashboard, the runner and job
    processes all update job files.
  - `WORKFLOWS` describes the kinds the start panel offers, with a parameter schema used for
    the form, server-side validation and the equivalent CLI command.
  - `Runner` starts the first queued job as `python -m auto_fix.cli job --config … --id …` when
    no job is running, and marks a running job `failed` when its process died without reporting.
    Only one runner works at a time (`jobs/runner.lock`); it runs as a thread inside
    `auto-fix dashboard --config …` or in the foreground as `auto-fix worker --config …`.
  - The job process reports its own outcome. Repair-type jobs take `worker.lock` like `run`
    does; when it is busy the job puts itself back at the front of the queue and exits.
- `auto_fix/cli.py`
  - The per-failure body of `run` becomes `process_failure()`, shared by `run` and repair jobs,
    so the scheduled command behaves as before.
  - New commands: `job` (internal, runs one job) and `worker`.
- `auto_fix/workflow.py`
  - `Workflow.run(None)` resumes the thread from its last checkpoint.
  - Between steps it honours `control.json`; it records `prepared_head` after `prepare`.
  - `fork()` builds a re-run from a step (section 2).
- `auto_fix/dashboard.py` — `GET /api/workflows`, `GET /api/jobs`, `GET /api/jobs/log`,
  `POST /api/jobs`, `POST /api/jobs/preview`, `POST /api/jobs/remove`, `POST /api/jobs/move`,
  `POST /api/runs/action`.

Job kinds: `batch` (scan TeamCity for a date and queue one `repair` per failure), `repair`
(one failure, with `mode` retry, publish or reconcile through the existing receipt logic),
`resume`, `replay` (re-run from step), `evaluation`, `operations`, `demo`. Evaluation and demo
output goes to `state_dir/evaluations/<job>` and `state_dir/demos/<job>` so it appears in the
run history.

## 2. States and actions

Runs gain `paused` and `cancelled`.

| Run state | Actions |
|---|---|
| Running | Pause, Cancel (after the current step) · Stop now |
| Pausing / Cancelling | Stop now |
| Paused | Resume · Cancel · Re-run from step |
| Blocked, Cancelled | Retry · Re-run from step |
| Ready | Publish PR · Re-run from step |
| Publication unknown | Reconcile |
| Published | — |

- Pause and Cancel write `control.json`. After the current step's checkpoint `Workflow.run`
  writes `paused` or `cancelled`, logs who asked, clears the request and returns. A request
  that arrives after the run ended is discarded. Resume streams the same thread from its last
  checkpoint; the receipt of a paused run is removed when it resumes.
- Stop now kills the run's process tree (`taskkill /T /F` on Windows, the process group
  elsewhere) and marks the run `cancelled` with "Stopped by <user> during <step>". It is refused
  while `publish_pr` runs or `publication.json` holds an intent. Resume is not offered after
  Stop now; Re-run from step is.
- Evaluations and the demo have no per-step checkpoints of their own, so their only stop is
  Stop now on the job.
- Re-run from step (allowed for `baseline`, `investigate`, `repair`, `verify`) forks into
  `<key>-rN`:
  1. read the source checkpoint taken just before the chosen step;
  2. create a worktree at the source's `prepared_head` (older runs without it rebase onto the
     current base, and the fork's event says so);
  3. re-apply the edits of the repairs applied before that step, from `proposal-N.json`;
  4. load the checkpoint into the new thread with `update_state(as_node=<previous step>)` and
     continue;
  5. log a `forked` event `{source, step, node}`; the run page shows "Re-run of … from step …".
- A job that exits with an error is `failed`; its output stays in `jobs/<id>.log`.

## 3. Dashboard UI

- Header: "Start workflow" button with `--config`; a "Read-only" badge without it.
- Start panel slides in from the right (non-modal, focus moves in and returns, Esc closes):
  workflows listed on the left, a form generated from the schema on the right with an
  Advanced section, inline validation, the equivalent CLI command, and "Add to queue" ("Start"
  when idle).
- Queue at the top of the sidebar: the running job with its step, elapsed time and pending
  request; queued jobs with Remove and move up/down; a failed job with View log and Dismiss.
- Run page: the state's main action as a filled button, the others as plain buttons, Stop now
  in a "⋯" menu. Cancel and Stop now confirm in a popover that states the consequence.
  A pending request shows a notice, and the page refreshes every second while it is pending.
- Re-run from here: a row action in the Steps table, and in an opened attempt row.
- `paused` (pause icon, amber) counts as Needs attention; `cancelled` (grey) gets a filter.

## 4. Security, errors and testing

- Write endpoints accept only `POST` with a JSON body under 64 KB, a loopback `Host`, an
  `Origin` (when sent) matching the dashboard's own, and an `X-Auto-Fix-Token` header equal to
  a random token generated at start and embedded in the served page. Cross-site pages cannot
  read the token, so they cannot forge actions. The CSP stays as it is (`form-action 'none'`):
  the page uses `fetch`, never form posts.
- `authorize(handler)` returns the acting user (the local account today). A team setup replaces
  it with real authentication without touching the endpoints. Jobs and control requests record
  the user.
- Every action is validated against the run's current state on the server; the UI only hides
  what the server would refuse. Unknown kinds, bad parameters and invalid state transitions
  return 400 with a message the UI shows next to the control.
- Tests (pytest, fake services like the existing workflow tests):
  - pause and cancel between steps, resume to completion from the checkpoint;
  - fork from `verify` re-applies the earlier edit and continues from that step;
  - `process_failure` keeps the `run` command's receipt behaviour;
  - job store ordering, removal, moves and catalogue validation; runner start and crash
    detection with a stub command;
  - dashboard: token, origin and host checks on every write endpoint; read-only mode without
    `--config`; actions refused in the wrong state.
