# Dashboard P1 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the five P1 needs in their approved order.

**Architecture:** Extend the existing Python HTTP dashboard, file-backed queue and single
runner. Keep history summary queries separate from full LangGraph details. Store schedules
and batch relationships alongside jobs so both embedded and standalone workers behave alike.

**Tech Stack:** Python 3.11+, stdlib HTTP/zoneinfo/zipfile, FileLock, vanilla HTML/CSS/JavaScript,
pytest, existing LangGraph checkpoints. No new runtime dependencies.

**Spec:** `docs/dashboard-todo.md` (approved review and execution order).

## Global constraints

- Preserve local-only authorization, token/origin checks and read-only operation.
- Preserve existing CLI/history APIs where practical; no workflow or publication gate changes.
- UTF-8 files and Windows-compatible paths/processes. Never register real OS tasks during tests.
- Work on `codex/dashboard-p1`; leave existing untracked skills/configuration untouched.
- Implement in place on the feature branch; user explicitly requested immediate execution.
- Use a writable explicit pytest temporary directory in this sandbox.

## Review focus

- New live runs must not lose history filters or make old direct links stop working.
- Artifact traversal/symlinks, checkpoints and text secrets must remain protected in downloads.
- DST gaps/folds, a stopped worker and duplicate scheduler ticks must not double-launch work.
- A ready repair is actionable even though its native validation passed.
- An empty, deduplicated, interrupted or partially complete batch must retain an honest outcome.

## Task 1: Paginated history

Files: `history.py`, `dashboard.py`, `dashboard.html`, `tests/test_history.py`.

Interfaces: `history.run_page(root, *, page=1, page_size=25, workflow='', status='', q='',
since='', until='') -> dict`; `/api/runs` returns page metadata and workflow catalogue.
Keep `history.list_runs(root)` for internal/CLI compatibility. Summary validation comes from
stored result JSON; never reconstruct checkpoints just to display a history row.

- [ ] Write tests for filtered multi-page ordering/ties, empty and out-of-range pages, invalid
  sizes/dates/statuses, and summaries that need no checkpoint access.
- [ ] Run those tests and observe missing feature failures.
- [ ] Implement the query and bounded HTTP response, catalogue, URL-driven page/filter state,
  history return links and stale-request protection. Exact status options include ready/published.
- [ ] Verify focused history tests and a browser page with 54 sample runs and zero detail calls.

## Task 2: Artifact downloads

Files: new `artifacts.py`, `dashboard.py`, `dashboard.html`, `tests/test_artifacts.py`.

Interfaces: `artifacts.download(root, run_id, relative) -> (file, mime, filename) | None`
with a temporary seekable file suitable for streaming; `relative=''` requests a ZIP bundle.
`GET /api/download?id=...&path=...` serves an attachment; omitted path serves all evidence.

- [ ] Test large text, binary fidelity, secret redaction, ZIP entries, unknown paths/traversal,
  external symlinks and checkpoint exclusion; observe failure before implementation.
- [ ] Implement streaming attachments, safe filenames and history/artifact-browser actions.
- [ ] Verify backend tests and browser download controls.

## Task 3: Persistent schedules

Files: new `schedules.py`, `jobs.py`, `dashboard.py`, `dashboard.html`, `tests/test_schedules.py`.

Interfaces: `ScheduleStore(state_dir, timezone='Europe/Paris')` with `save`, `all`, `toggle`,
`remove`, `tick(job_store, at=None)`. Runner calls tick only while holding its existing runner
lock. Store schedules with FileLock/atomic replace; deterministic occurrence job IDs close the
crash window between enqueue and recording the trigger.

- [ ] Test once/daily/weekly recurrence, timezone, DST gap/fold, validation, enable/disable,
  restart deduplication, relative dates, missed-run skip/catch-up and overlapping occurrences.
- [ ] Observe feature failures; implement schedule storage and runner integration.
- [ ] Add protected schedule endpoints, timezone-aware forms, upcoming/last outcomes and
  pause/edit/delete actions. Defaults: catch up once, skip an already active occurrence's
  workflow; missed skipped occurrences stay recorded. No raw cron requirement for P1.
- [ ] Verify focused schedule/job/API tests and browser forms.

## Task 4: Attention and workflow overview

Files: `history.py`, `dashboard.py`, `dashboard.html`, `tests/test_history.py`.

Interfaces: global attention summaries returned separately from the bounded history page;
run details retain the existing graph/steps/controls contract.

- [ ] Test attention includes ready, paused, blocked, publication-unknown and abandoned runs,
  excludes published/cancelled and does not depend on the selected history page.
- [ ] Observe failures; implement home attention list, purpose-based workflow labels, executed
  node path with repeated attempts, outputs and validation separation. Use existing actions.
- [ ] Verify browser navigation and keyboard controls on desktop and small viewports.

## Task 5: Durable batch summaries

Files: `jobs.py`, `dashboard.py`, `dashboard.html`, `tests/test_jobs.py`, `README.md`.

Interfaces: add optional `parent_id`/`schedule_id` to job metadata; retain completed jobs in a
paginated job history API. `JobStore.batch_summary(job_id) -> dict` reports discovery and
child outcomes, resolving receipt-backed run states when a child reused an existing run.

- [ ] Test multiple children, already-handled repairs, empty discovery, errors, interrupted
  discovery/retries and status changes after publication. Observe failures.
- [ ] Record child IDs incrementally and prevent duplicate children if discovery resumes;
  show retained batches/results and links to child runs/logs. Dismiss is visibility, not deletion
  of completed batch evidence.
- [ ] Update README and TODO checkboxes; run lint, full pytest suite and browser verification.
- [ ] Request one independent final review, address material findings, rerun affected checks.

## Execution record

- Initial baseline attempt failed in pytest's sandbox temp setup, before product tests.
- Ruling: use an explicit writable basetemp; this is environment setup, not a product change.
- Ruling: keep work in the current checkout on a feature branch, preserving the user's workspace.
- Pre-flight: tasks 1/4 share the history summary contract; tasks 3/5 share job metadata.
  Schedule occurrence identifiers and batch-parent metadata remain optional for old jobs.
- User approved execution in chat; proceed sequentially without another approval gate.
- Task 1: implemented; pagination/filter summaries RED then GREEN, HTTP tests pass, browser
  confirms bounded pages and zero initial detail requests, Back and filter reload work.
- Task 2: implemented; large/redacted text and binary/ZIP/traversal tests RED then GREEN;
  HTTP attachment and browser ZIP download pass.
- Task 3: implemented; 11 schedule cases RED then GREEN, protected HTTP endpoints pass;
  browser creates, edits to one-time and disables schedules.
- Task 4: implemented; global attention test RED then GREEN; browser checks executed path,
  outputs, validation, attention pagination and artifact links across reload.
- Task 5: implemented; parent/child/retention/idempotence cases RED then GREEN; browser shows
  retained batches and child outcomes. README updated. Independent review in progress.
- Focused verification: 57 passed; ruff clean. Browser has no JavaScript errors and no
  horizontal page overflow at 390 px. Full-suite baseline: 604 passed, 12 skipped, one
  pre-existing Windows symlink-privilege fixture failure (WinError 1314).
- Final review: independent reviewer identified five material issues. All reproduced with
  failing tests, then fixed in one pass: checkpoint-name casing, unknown text formats,
  off-page detail refresh, Home navigation and relative schedule dates at execution time.
- Final focused verification: 66 passed. Browser rechecked Home/reload, off-page refresh,
  history and artifact deep links, schedule edits, ZIP downloads and light/dark/mobile views.
- Final ruling: reused repair jobs are counted as already handled; their linked original runs
  remain actionable in the global attention list. Cost: inspect that link for its current state.
- Final ruling: keep the prior DST/missed-run/overlap defaults documented above. Daily/weekly
  and one-time schedules cover P1; cron expressions and server/service installation remain out
  of scope. Cost: advanced recurrence needs a later extension and workers must be kept running.
- Verification limitation: Windows file symlinks require a privilege unavailable to this
  account. The existing full-suite fixture fails with WinError 1314; no tests were removed or
  marked skipped to conceal this. Pre-review full run: 623 passed, 12 skipped, 1 environment failure.
- Final full-suite run after all review fixes: 632 passed, 12 skipped, 1 failure in the same
  existing symlink-privilege fixture. Lint and diff whitespace checks pass. Changes remain
  uncommitted on `codex/dashboard-p1` for review; no publication or release was attempted.
