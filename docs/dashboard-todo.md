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
