# Dashboard UI and UX TODO

Approved direction, 2026-10-24: adopt TeamCity's operational convenience while making
LangGraph workflows, their decisions, and their outputs the primary objects.

## P1 — implement in this order

1. [x] **Find an older run.** Server-side pagination (25/50/100), search, exact status and
   date filters; preserve filters/page in the URL and when returning from a run. Populate
   history from lightweight summaries without fetching every run's checkpoints/model calls.
2. [x] **Download evidence from history.** Per-row artifact actions, individual downloads,
   patches/logs/results and a ZIP evidence bundle. Keep bounded preview separate from full
   downloads; support large logs and binary evidence while retaining secret redaction.
3. [x] **Run workflows unattended.** Persistent one-time, daily and weekly schedules with
   saved parameters, timezone, upcoming occurrences, enable/disable, last outcome and explicit
   missed-run/overlap behavior. Resolve relative dates at execution time. Use the existing
   single runner, including the standalone worker; show when no runner is available.
4. [x] **Know whether intervention is needed.** Global attention list for ready candidates,
   paused/blocked runs, abandoned runs and uncertain publication, linking to state-appropriate
   actions. Lead the home screen with attention, active work, upcoming schedules and workflows.
   Make the run overview show outcome, workflow execution/loops, outputs and resource use;
   keep native tests as validation evidence. Name workflows by their purpose and show the
   TeamCity build configuration as scope.
5. [x] **Understand a complete batch.** Retain completed orchestration jobs, parent/child
   repair relationships and aggregate outcomes, including no failures found, already handled,
   failed discovery and partial completion. Preserve evidence/history when dismissing failures.

## P2

- [ ] Queue position, waiting duration, blocking reason and reorder controls.
- [ ] Persist effective inputs/model/prompt/configuration/source revisions for reproducibility.
- [ ] Compare original runs, retries and checkpoint forks (patches, validation and resource use).
- [ ] Completion/attention notifications and visible refresh freshness/worker health.
- [ ] Pin/retain important evidence and communicate expired or removed artifacts.
- [ ] Improve small-screen navigation so the workflow tree does not dominate the viewport.

## Acceptance and verification

- [x] History renders a bounded page and makes no detail requests until a run is opened.
- [x] Back/Forward and pasted URLs restore the same history, tab and selected artifact.
- [x] Downloads work from history and the artifact browser, including files larger than 2 MB.
- [x] Schedule execution is deduplicated across runner restarts and respects timezone/DST.
- [x] Read-only mode stays useful and refuses mutations.
- [x] Existing run-control/publication protections remain enforced by the server.
- [ ] Focused backend tests, full pytest suite, lint and browser verification pass.

Verification: 66 focused backend/client tests pass; lint and browser checks pass (54 sample
runs, 25 rows/page, zero initial detail requests, Back/filter/artifact deep links, ZIP downloads,
schedule create/edit/disable, batch history, light/dark themes and a 390 px viewport).
Final full suite: **632 passed, 12 skipped, 1 Windows environment failure**. The existing symlink fixture in
`test_rejects_symlinked_evidence_and_outside_result_pointer` needs a privilege this account
does not have (`WinError 1314`). No release or publication is part of this change.

Independent review completed; all five material findings have regression coverage and fixes:
Windows checkpoint-name casing, text redaction for unfamiliar extensions, off-page detail
refresh, Home navigation from global views, and relative dates across a queue crossing midnight.

Implementation steps and decisions: [P1 implementation plan](superpowers/plans/2026-10-24-dashboard-p1.md).

## UX/UI review, 2026-10-25

Findings from a review of `dashboard.html` and a browser walk-through of two sample state
directories at 1440 px and 375 px. The live-job path and the light theme were not exercised.

Verification, 2026-10-25: full suite **649 passed, 12 skipped, 1 known Windows environment failure**
(the symlink fixture above, `WinError 1314`); lint clean; browser walk-through of every page at
1440 px and 375 px on an enriched sample state with run controls. The README screenshots predate
this layout. Nothing was committed or released.

### Bugs

- [x] The whole page scrolls by 21 px and the header slides off on click/focus: the `.sr`
  labels are absolutely positioned with no positioned ancestor (`#content` needs `position: relative`).
- [x] A run whose worker died shows the spinning "running" icon and the text "Running" next to
  "Worker stopped unexpectedly", in the tree, workflow rows, history rows and the run page.
- [x] Switching run tabs keeps `call=`, `file=` and `open=` from other tabs in the URL.
- [x] The Delete schedule confirmation is not styled as destructive.
- [x] On a phone, a run page opens scrolled partway down with the title out of view. The tree now
  starts hidden on narrow windows and the figure sits at the end of the page.

### Missing features

- [x] **Failure context.** Failure messages, the failing build's commits and authors, their
  Bitbucket PRs, Jira issues and the end of the TeamCity log, from what `collect_context` saved.
- [x] **Patch review.** `fix.diff` as a unified diff with line numbers per file on the run's
  overview, with copyable `git switch <branch>` and `git apply fix.diff` commands.
- [x] **Triage loop.** Dismiss, reject, "handled manually", snooze and reopen; notes; a good/bad
  fix rating. Decisions live in `triage.json` in the state directory, a decided run leaves Needs
  attention, and a rejected fix cannot be published until reopened (enforced by the server).
- [x] **Build and test output.** A Build log tab lists every check's `evidence/` folder and shows
  its logs, failure lines marked; a blocked run shows the last check's output.
- [x] **Regressions in validation.** The run detail compares the baseline report with the last
  verification: fixed, still failing and newly failing tests, with a callout for regressions and
  a "newly failing" count in run lists.
- [x] **Freshness and health.** "Updated 12s ago" in the header, a banner while the server does
  not answer, the attention count in the nav and tab title, and opt-in browser notifications.
- [x] **Test history.** A Tests page (runs, fixes, failures that did not reproduce, "possibly
  flaky") and a page per test listing its runs.
- [x] **Outcome metrics.** A Metrics page: runs, fix rate, median time to a verified fix,
  failed-model-call rate and tokens, per workflow and per day (7/30/90 days).
- [x] **Configuration and connectivity.** A Settings page with the effective configuration
  (token variables by name and whether set, never values) and a connection check for TeamCity,
  Bitbucket, Jira, the model endpoint and the Git repository.
- [x] **Unused endpoints.** Queued jobs move up and down; the Run dialog shows the equivalent
  command line.
- [x] **Failed model calls.** Failed calls keep the model's raw answer (`raw`, last 20,000
  characters) and the finish reason; the page shows both.

### Navigation and layout

- [x] Run history, Tests, Metrics, Schedules, Batches and Settings are a top navigation bar with
  the current page marked.
- [x] The tree can be hidden (remembered per browser) and starts hidden on narrow windows.
- [x] The state directory moved from the header to Settings.
- [x] The run page has a separate "Back to …" link above a plain Home / project / workflow path.
- [x] The TeamCity id moved to the workflow name's tooltip.

### Home page

- [x] Needs attention rows show the failing test, workflow and waiting time.
- [x] Attention actions act in place (Publish…, Resume, Reconcile, Retry) beside Review/Open and
  Dismiss; read-only mode only offers Open.
- [x] Jobs that failed to start are in Needs attention; the Queue shows only queued and running jobs.
- [x] Each workflow has one "Run…" button and a schedule button; every run goes through the dialog.
- [x] Upcoming schedules show in browser time, with the schedule's own time on hover.
- [ ] Recent batches still use `<details>` inside table cells (kept: low impact).

### Run page

- [x] The page leads with "The fix" (Ready, Published) or "Why it stopped" (Blocked, Cancelled,
  Paused, abandoned), then Validation, The failure, Attempts and Review.
- [x] The duplicate Outcome section is gone; known stop reasons read in plain words, with the
  workflow's own text kept as detail.
- [x] Attempts without an edit read "No usable edit: <cause>" everywhere.
- [x] Steps read "done", "tests pass", "candidate verified", "not published: local candidate".
- [ ] The figure moved to the end of the page and "Replay" became "Animate"; its overlapping
  labels on narrow screens remain.
- [x] "Execution log" is now "Checkpoints", next to a real Build log.
- [x] Attempt edits render as removed and added lines (edits carry no line numbers).
- [x] Model calls say "characters of JSON context". Cost is not shown: there is no price data
  for a self-hosted model (skipped).
- [x] Artifacts group into folders, use icon downloads, truncate long names and open `fix.diff`
  or `result.json` by default.

### Run history

- [x] Workflow and failing-test columns; Result, Started and Duration sort.
- [x] Search applies as you type; "Today", "7 days" and "30 days" presets. Date inputs keep the
  browser's native format.
- [x] The validation cell is green only for verified fixes, red only for regressions.
- [x] Row actions are icons.

### Dialogs and schedules

- [x] Run dialog: equivalent command line; the retry option reads "Also repair failures whose last
  run was blocked or cancelled" with help.
- [x] Schedule dialog: When first, then Parameters; timezone suggestions; the relative-date switch
  sits above the date it hides; the next five runs preview before saving; styled headings.
- [x] Schedules page is a table.

### Visual consistency

- [ ] Home, history, schedules, the run page and the new pages share classes and icons; the
  Batches page keeps its older markup (low impact).
- [x] Run statuses are capitalised, step outcomes lowercase, consistently.
- [x] A theme switch (System, Light, Dark) in the header and in Settings, remembered per browser
  and applied before the first paint.
