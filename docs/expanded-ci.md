# Expanded native replay CI

[Expanded native replay](../.github/workflows/expanded.yml) is manually triggered. It validates `evaluation/recordings/expanded/index.json` and the original Luna recording hashes before generating jobs. An absent or invalid index fails validation; this workflow does not create recordings, replace missing responses, or call a live model.

Linux runs every accepted index entry, with up to six jobs and a 30-minute limit per case. Windows runs entries explicitly tagged `windows-representative`, with up to three jobs and a 45-minute limit per case. An empty Windows selection skips those jobs. Both platforms use Python 3.12 and a short native output directory under `runner.temp/af` to limit Windows build paths. Job outputs feed the matrices using GitHub's [documented output-matrix pattern](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/run-job-variations#using-an-output-to-define-two-matrices).

The index is populated only after selecting and freezing the measured workflow. When exporting accepted recordings, tag diverse portable cases from both Abseil and fmt, including multi-file repairs. To verify the additional duration guard on Windows, include a genuinely accepted `absl_time_test` case whose recorded project manifest enables `duration-min-unit`; tagging a case alone does not enable that guard. The index and recordings remain pending until genuine accepted runs are exported.

Validate locally before dispatching:

```sh
uv run --no-sync python scripts/replay-expanded.py validate
uv run --no-sync python scripts/replay-expanded.py matrix --platform linux
uv run --no-sync python scripts/replay-expanded.py matrix --platform windows
```

After committing the genuine index and recordings, an authorized operator can trigger the workflow:

```sh
gh workflow run expanded.yml --ref main
```

Each job retains `replay-result.json`, evaluator manifests, source snapshots, original/final JUnit, compiler and test logs, recorded-call provenance, and mock PR receipts. Artifacts are uploaded after failures too. Generated build trees, source checkouts, bare remotes, candidate worktrees, and upstream caches are excluded. Git branch/head and protected-source checks execute before those local directories are excluded from the upload. Downloaded artifact evidence and passing native results must be checked before reporting completion.

These are mechanical native replays of saved Luna responses. They do not add fresh inference runs, unique defects, or holdout successes. The initial four-control CI workflow remains separate; passing it does not establish expanded-case or Windows duration-guard coverage.
