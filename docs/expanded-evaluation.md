# Evaluating and adapting the repair workflow

This benchmark tests the complete path from a reported C++ test failure to a verified pull request. Compilation, Git history, native test execution, and model inference are real. TeamCity, Bitbucket, and Jira are temporary, fictional on-premise services implemented with an HTTP mock transport. The benchmark never contacts company services or publishes a real repair PR.

The frozen corpus and original procedure are [complex-cpp-v2](../evaluation/expanded/protocol.json). The [dataset index](../evaluation/expanded/dataset-index.json) records case IDs, development/holdout assignments, upstream pins, manifest hashes, complexity labels, and native proof hashes. Development addenda preserve that corpus while registering workflow changes and stronger validation. The pure-prompt and v3 investigation comparisons are complete; **later development arms and holdout results remain pending**.

## What the workflow does

The LangGraph workflow keeps deterministic validation around model decisions. Its steps are:

1. Collect today's relevant TeamCity builds and failing test identities, log excerpts, exact VCS revisions, recent Git changes, associated Bitbucket PRs, and Jira context. Pagination, successful builds, older builds, and unrelated changes are represented in the fixtures.
2. Prepare an isolated Git worktree at the reported revision, rebase on master, compile, and reproduce the original failures. With `baseline_repetitions: 2`, repeat unchanged-source verification and require identical passed, failed and skipped identities. Stale reports, missing identities, invalid evidence and observed instability stop the workflow before inference.
3. Build a bounded source context packet. The recent-change context is deliberately indirect: it does not contain the synthetic mutation diff or its inverse. Jira text and other service content remain untrusted evidence.
4. Optionally investigate: Luna proposes hypotheses, literal source searches, or source excerpts. The runner permits only bounded reads of tracked, configured source files. It rejects traversal, symlinks, protected files, and evaluator oracle files. C++ definition reads can retrieve bounded complete functions and templates. A total inspection budget is shared across retries; `inspections_per_attempt` reserves capacity for later attempts. Applied edits invalidate evidence for every edited path.
5. Ask Luna for a structured repair and apply exact source replacements. Tests, build configuration, and files outside the configured source allowlist are protected. Fresh native assertions and compiler feedback reach the next attempt. `max_attempts` sets the repair budget, default two. Retries receive the preceding proposal, its attempt number, and whether it was applied; rejected proposals are saved before edit validation.
6. Require the complete configured upstream and trusted additional suites to pass. Every baseline test that previously passed or failed must remain present and passing. Commit, fetch and rebase onto the latest master, then rebuild and rerun the suites on the resulting commit.
7. Push the exact tested commit and create one mock Bitbucket PR with TeamCity/Jira links and verification context. Require the complete verified commit ID and matching source/destination refs in the PR receipt. A lost publication response triggers reconciliation against the verified publication journal rather than a blind second creation request; production CLI recovery uses the same receipt checks.

The implementation is divided at these boundaries:

| Concern | Code |
| --- | --- |
| Graph, retries, immutable original failures, publication checks | [workflow.py](../src/auto_fix/workflow.py) |
| TeamCity/Bitbucket/Jira adapters and realistic mock responses | [integrations.py](../src/auto_fix/integrations.py), [mock_services.py](../src/auto_fix/mock_services.py) |
| Git worktrees, source-edit protections, rebase and push | [workspace.py](../src/auto_fix/workspace.py) |
| Initial retrieval, structured diagnostics, bounded investigation | [context.py](../src/auto_fix/context.py), [diagnostics.py](../src/auto_fix/diagnostics.py), [investigation.py](../src/auto_fix/investigation.py) |
| Versioned instructions and actual Luna CLI calls | [prompts.py](../src/auto_fix/prompts.py), [codex_model.py](../src/auto_fix/codex_model.py) |
| Native suites, merged evidence and optional trusted guards | [native_tests.py](../src/auto_fix/native_tests.py), [build.py](../src/auto_fix/build.py), [semantic_probes.py](../src/auto_fix/semantic_probes.py) |
| Case preparation, independent grading and operational faults | [evaluation.py](../src/auto_fix/evaluation.py), [operational_evaluation.py](../src/auto_fix/operational_evaluation.py) |
| Frozen job plans, isolated subprocesses and reports | [experiment.py](../src/auto_fix/experiment.py) |

The model receives a representative bounded diagnostic packet when needed; that sampling never reduces the baseline test identities used by the validator. Invalid UTF-8 in native assertion messages is retained in raw report evidence and normalized for XML decoding. Malformed XML still fails validation. Production HTTP model transport failures also enter the bounded repair retry path.

## Dataset and native proof

There are **45 new synthetic regression cases**, across two substantial public C++ repositories. These are injected faults in real code, not historical bug fixes. Assignment is frozen by behavior family, with 24 development cases and 21 holdout cases.

| Group | Cases | Development | Holdout | Manifest |
| --- | ---: | ---: | ---: | --- |
| Abseil strings, parsing, escaping and formatting | 17 | 10 | 7 | [abseil_strings.json](../evaluation/expanded/abseil_strings.json) |
| Abseil time, status and wide integers | 16 | 8 | 8 | [abseil_systems.json](../evaluation/expanded/abseil_systems.json) |
| fmt formatting, Unicode, diagnostics and boundaries | 12 | 6 | 6 | [cases_fmt.json](../evaluation/expanded/cases_fmt.json) |
| Total | 45 | 24 | 21 | [Frozen index and hashes](../evaluation/expanded/dataset-index.json) |

Abseil is pinned to `255c84dadd029fd8ad25c5efb5933e47beaa00c7` (`20260107.1`); its external GoogleTest dependency is pinned in [project.json](../evaluation/project.json). fmt is pinned to `1be298e1bd68957e4cd352e1f676f00e07dcfb57` (`12.2.0`) in [fmt.json](../evaluation/expanded/fmt.json), with its [MIT license copy](../evaluation/expanded/license-FMT.txt). fmt uses its bundled GoogleTest, as defined by the pinned [native test configuration](https://github.com/fmtlib/fmt/blob/1be298e1bd68957e4cd352e1f676f00e07dcfb57/test/CMakeLists.txt) and [GoogleTest build](https://github.com/fmtlib/fmt/blob/1be298e1bd68957e4cd352e1f676f00e07dcfb57/test/gtest/CMakeLists.txt). Abseil's native setup follows its [official CMake guide](https://abseil.io/docs/cpp/quickstart-cmake.html).

Each case must pass these checks before model evaluation:

- Clean pinned upstream compiles and passes every test in that case's selected suites.
- The source-only injection still compiles, and the same unchanged suites expose the regression. Registered/executed test identities and real failing names are retained.
- Each mutation hunk is checked separately to distinguish observed independent faults, coupled contracts, and unobserved extra changes. Case complexity is recorded honestly; not every case is multi-file or equally difficult.
- The final case is restored and its combined native failure evidence is preserved. For model trials, the evaluator checks that tests and configuration remain unchanged and grades the full selected suites, rather than matching an expected patch.

“Full suites” means all tests in the configured relevant test binaries, without a failure-only filter. It does not mean every test in each upstream repository. For example, fmt's five selected suites contain 280 native tests.

An independent audit found six extra strings mutations that the existing suites did not observe individually. They were removed before the formal v2 freeze, without changing case IDs or preassigned families. The [v1 manifest](../evaluation/expanded/prototypes/v1/abseil_strings.json) and [strings audit](../evaluation/expanded/hunk-audit-strings.json) preserve that correction. Two retained substitution-pass mutations crash separately but produce ordinary assertion failures together; they are explicitly labelled a coupled contract. Systems' 32 hunks and [fmt's 24 hunks](../evaluation/expanded/hunk-audit-fmt.json) were independently observed by native test assertions. Earlier manual model runs remain **prototype data**, separate from formal v2 comparisons. Holdout model outcomes were not used to make the correction.

Case manifests, clean-source oracles, injected-edit descriptions, proof metadata, and the dataset index belong to the evaluator. They must never be added to the model packet or investigation allowlist. The HTTP fixtures contain realistic behavior-only issue descriptions and actual native assertions, without scripted LLM answers. Their SVG attachment is explicitly a synthetic report, not a screenshot of a company system.

## Compare changes without tuning on holdout

The evaluated model is fixed to `gpt-6-luna`. [The official model reference](https://developers.openai.com/api/docs/models/gpt-6-luna) documents its reasoning settings. Each registered arm records effort, context, inspection and repair budgets explicitly. Different models, endpoint inference, and recorded replay are excluded from these live comparisons.

The first phase measured three pure prompt arms on the same 24 development cases, with no inspections or structured diagnostics:

| Arm | Change | Inspections | Structured diagnostics |
| --- | --- | ---: | --- |
| baseline | `repair-v1`: focused repair instructions | 0 | Off |
| evidence | `evidence-v2`: group failure evidence and inspect surrounding contracts | 0 | Off |
| contract | `contract-v3`: repair coherent behavior across related paths | 0 | Off |

All **72 trials** finished. These are the retained original upstream-native results:

| Prompt | Native publications / 24 | Live repair calls | Confirmed semantic false greens | Published without a known semantic regression |
| --- | ---: | ---: | ---: | ---: |
| `repair-v1` | 7 | 33 | 1 | 6 |
| `evidence-v2` | 8 | 34 | 1 | 7 |
| `contract-v3` | 8 | 32 | 1 | 7 |

`contract-v3` won the preregistered pure-prompt tie-break: it matched `evidence-v2` on native publications with fewer calls. This selects the prompt for the next structured arm; it does not establish the final workflow winner.

Independent review covered all 23 natively published patches. It found the same uncovered duration boundary regression in each arm. For finite `d = unit = absl::Seconds(INT64_MIN)`, rounding an exact multiple must preserve `d`. Separate native binaries confirmed that pinned clean upstream does so, while the three accepted candidates return incorrect `Floor`/`Ceil` values; one also changes `Trunc`. The local audit and four-binary source/command/log proof are retained under `.auto-fix/development-semantic-audit.json` and `.auto-fix/development-semantic-audit/duration-negative-unit/`. Their proof hash is registered in the [v3 addendum](../evaluation/expanded/protocol-development-v3.json). No test-specific hardcoding or protected-file changes were found; one fmt patch has an inaccurate comment without a demonstrated functional difference. “Without a known regression” is an audit conclusion, not proof for every input.

The v3 addendum was registered before enriched-arm calls. It adds retry history, retention of all previously executed tests, stricter PR receipts/recovery, bounded HTTP retries, and a trusted supplemental native guard. [abseil-validation-v3.json](../evaluation/expanded/abseil-validation-v3.json) derives from the original pinned Abseil project and adds the `duration-min-unit` guard when a case targets `absl_time_test`. Upstream source/tests, the 45 mutations, and their splits are unchanged; fmt keeps its original project manifest. The guard adds coverage, not a new unique defect.

The frozen [development-enriched-v3 plan](../evaluation/expanded/plans/development-enriched-v3.json) contains **12 jobs and 96 development trials**: four arms, each covering fmt's six, strings' ten, and systems' eight development cases. All use Luna, medium effort, two repair attempts, structured diagnostics, and the same guarded validation rules:

| Guarded arm | Prompt | Total inspection budget |
| --- | --- | ---: |
| `structured-v3` | `contract-v3` | 0 |
| `investigation-baseline-v3` | `repair-v1` | 3 |
| `investigation-evidence-v3` | `evidence-v2` | 3 |
| `investigation-contract-v3` | `contract-v3` | 3 |

All 96 v3 trials finished, with 340 actual Luna calls. Independent review covered all 54 publications:

| Guarded arm | Original guarded native publications / 24 | Actual Luna calls | Confirmed additional semantic regressions |
| --- | ---: | ---: | ---: |
| `structured-v3` | 7 | 42 | 0 |
| `investigation-baseline-v3` | 13 | 106 | 0 |
| `investigation-evidence-v3` | 16 | 92 | 1 |
| `investigation-contract-v3` | 18 | 100 | 1 |

The evidence-prompt duration candidate special-cased minimum duration for every unit, failing six independently compiled non-divisor/infinite-unit checks. The contract-prompt chrono candidate overflowed signed arithmetic when formatting the minimum nanosecond timestamp; a native undefined-behavior sanitizer exposed the overflow while pinned clean code passed. The original native grades remain unchanged. A broad string-substitution rewrite also has unmeasured performance characteristics.

These results show why successful native tests need independent patch review. The original pure-prompt and v3 guarded phases have different validation rules and implementation versions; compare arms within their own phase and retain known false positives explicitly.

## Later development changes

The [v4 protocol](../evaluation/expanded/protocol-development-v4.json) and [plan](../evaluation/expanded/plans/development-evidence-lifecycle-v4.json) compare medium/high effort with retained source evidence, fresh assertion feedback and two inspections reserved per repair attempt. Both arms have a four-inspection total budget and two repairs. The medium arm completed 15/24 native publications with 107 live calls. The high arm remains in progress; independent review has already found two additional precision-boundary false positives, preserved separately from its original grades.

The [v5 protocol](../evaluation/expanded/protocol-development-v5.json) and [plan](../evaluation/expanded/plans/development-source-context-v5.json) compare three high-effort arms: a 160,000-character source budget with fixed excerpts; the same budget with C++ definition reads; and definition reads with an adaptive four-repair/six-inspection total budget. The first two retain two repairs/four inspections. All reserve at most two inspections per repair attempt. These resource differences are explicit; the adaptive arm is not an equal-budget comparison. Results remain pending until every arm completes all 24 cases and every publication is reviewed.

The [v6 baseline-trust protocol](../evaluation/expanded/protocol-development-v6-baseline-trust.json) registers two repeated unchanged baselines, explicit evidence validity and stronger versioned development-derived guards. Real native mechanical controls demonstrated that a single flaky FAIL/PASS/PASS sequence and malformed additional baseline evidence could otherwise permit publication. These controls use scripted proposals and contribute zero live model evaluations.

After all eligible development arms finish, select the registered recipe, freeze its source/input hashes, and run a fresh 24-case development confirmation on the safer v6 graph. Then freeze the exact implementation before any holdout inference. The registered holdout experiment has 21 baseline trials and three fresh 21-case winner rounds, 84 trials total. Each repeated round covers the same 21 unique cases; it does not add independent defects. The baseline and winner share the v6 validation rules and two-baseline requirement. Holdout outcomes cannot tune the workflow.

Register any further development change as a new arm/version before its calls. Investigate failures from development results only.

Select by the number of development cases reaching fully verified publication; break ties with fewer live calls, then lower measured latency. Freeze the selected arm, prompt hash, implementation hashes, case/project manifest hashes, validation rules, and job plan before any holdout inference. Run one baseline holdout round and three fresh rounds of the frozen selected workflow on the same 21 holdout cases. Those 63 selected-workflow trials still represent 21 distinct defects. Do not choose a different prompt from their results; a later change requires a new evaluation cycle.

This procedure follows OpenAI's [evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices): use representative task-specific cases, explicit success criteria, retained logs, automated checks, and iterative measurement. Versioned prompts make workflow changes comparable, as discussed in the [prompt engineering guide](https://developers.openai.com/api/docs/guides/prompt-engineering). The native grader here is deterministic; no second model grades Luna's answer.

## Run a trial or a frozen plan

Install the locked development dependencies with `uv sync --locked --extra dev`. Have Git, CMake, a native C++ compiler, and an authenticated Codex CLI available. On Windows, use a terminal with the MSVC build environment available. Commands below run live inference; use a new directory for every intended trial.

One development group:

```sh
uv run --no-sync auto-fix evaluate --directory .auto-fix/expanded-runs/dev-fmt-baseline --backend codex --model gpt-6-luna --project-file evaluation/expanded/fmt.json --cases-file evaluation/expanded/cases_fmt.json --split development --prompt repair-v1 --max-attempts 2 --max-inspections 0 --reasoning-effort medium
```

For a coordinated experiment, save a JSON plan such as:

```json
{
  "max_parallel": 2,
  "prune_native_builds": true,
  "jobs": [
    {
      "id": "dev-baseline-fmt",
      "arm": "baseline",
      "split": "development",
      "project_file": "evaluation/expanded/fmt.json",
      "cases_file": "evaluation/expanded/cases_fmt.json",
      "prompt": "repair-v1",
      "max_inspections": 0,
      "structured_diagnostics": false,
      "reasoning_effort": "medium"
    }
  ]
}
```

Add separate jobs for the two Abseil groups and the registered arms. An optional `case` selects one case within a group. The runner fixes the backend to Codex and the model to Luna; model/backend overrides are rejected. Each job can record `context_chars`, `definition_reads`, `max_attempts`, `inspections_per_attempt` and `baseline_repetitions`. It freezes the plan and complete input snapshots with SHA-256 hashes before calls, then runs one to three isolated CLI subprocesses. Default concurrency is two.

```sh
uv run --no-sync python scripts/run-expanded-evaluations.py run --plan development-plan.json --directory .auto-fix/experiments/formal-dev --workdir .
```

To execute the registered v3 plan in a new experiment directory:

```sh
uv run --no-sync python scripts/run-expanded-evaluations.py run --plan evaluation/expanded/plans/development-enriched-v3.json --directory .auto-fix/experiments/development-enriched-v3 --workdir .
```

Use explicit `--resume` only with the same frozen plan. Finished jobs, including failed processes, are preserved and skipped; interrupted/running prior jobs block resume before queued siblings can start. A deliberate retry gets a new job/run identity. Interruption stops the child process tree and records an explicit interrupted status.

Optional pruning removes only rebuildable `.auto-fix-build` directories beneath newly created case sources/worktrees after their process exits. It rejects symlinks and preserves source Git repositories, caches, remotes, all model packets, native logs/JUnit, diffs, and manifests. The default is no pruning.

## Add trusted production validation

`BuildConfig.additional_tests` is optional and defaults to an empty list. Operators can add independent native suites to the production YAML alongside the existing primary test command. Every command is an argument array, runs without a shell inside the candidate worktree, and must write its own fresh `{junit}` report. These commands are trusted operator configuration; Jira text and model output cannot supply or edit them.

For an Abseil checkout whose normal configure step already enables `absl_time_test`, this build-section example runs the upstream target and the additional boundary guard. Use the Python interpreter where `auto_fix` is installed:

```yaml
build:
  build:
    - [cmake, --build, .auto-fix-build, --config, Release, --target, absl_time_test]
  test: [python, -m, auto_fix.native_tests, --build-dir, .auto-fix-build, --targets, absl_time_test, --junit, '{junit}']
  additional_tests:
    - [python, -m, auto_fix.semantic_probes, --workspace, ., --probe, duration-min-unit, --junit, '{junit}']
  timeout_seconds: 600
```

For a company codebase, substitute an operator-owned validation executable or adapter that emits JUnit; the supplied duration guard specifically targets Abseil. Keep the normal configure/build commands from your repository's configuration. The runner gives each suite a separate fresh evidence path, retains per-suite logs/XML, and merges the results into `junit.xml`. Test identities must be unique within and across suites, so supplemental checks use their own namespace. Missing, stale, malformed, empty/all-skipped evidence, duplicate identities, failed commands, or failed assertions block validation.

The guarded workflow requires all baseline-passing and baseline-failing identities, including supplemental assertions, to remain present and pass after the repair and final rebase. A model cannot obtain a pass by dropping an unrelated previously passing test. The supplemental probe is outside protected upstream test source, is compiled against the actual candidate, and records its commands and native assertions. Passing these selected guards adds evidence; it does not guarantee semantic correctness for untested contracts.

## Read evidence and report partial outcomes

Each experiment keeps the frozen plan and `experiment.json`. Each job keeps input snapshots, `job.json`, `status.json`, stdout/stderr, and a `run/` directory containing the evaluator manifest and implementation snapshots. Each case keeps model requests/responses and metadata, native logs/JUnit, Git evidence, state, and `score.json`. A nonzero CLI exit does not discard completed scores or hide remaining planned cases.

The runner writes separate development/holdout reports. To report existing direct evaluator runs without launching inference, create a descriptor list:

```json
[
  {
    "id": "dev-baseline-fmt",
    "arm": "baseline",
    "split": "development",
    "directory": ".auto-fix/expanded-runs/dev-fmt-baseline"
  }
]
```

```sh
uv run --no-sync python scripts/run-expanded-evaluations.py report --runs development-runs.json --output .auto-fix/reports/development --report-split development
```

Use a separate descriptor list/output and explicit `--report-split holdout` for holdout reporting. List fresh rounds in their registered order. Duplicate resolved evidence directories are rejected. Reports accept only attested live Luna/Codex runs; [recorded replay](../src/auto_fix/recorded_model.py) remains a separate mechanical regression check and contributes no live-inference score or token usage.

Compare completed/planned trials, verified publications, first-repair-attempt successes, failure stages, repair versus investigation calls, actual recorded tokens, model latency, and total trial time. Distinguish workflow blocks before any model call, context-budget failures, provider failures, invalid proposals, native build/test failures, final rebase problems, and publication uncertainty. A blocked-before-model case is not a bad Luna answer, but still prevents end-to-end completion.

The reporter groups by arm, split, and project, and retains a per-case trial table. Its Wilson 95% interval uses the first completed listed trial for each unique case. Repeated trials are reported separately with every outcome; they do not inflate the interval's distinct-case denominator. This small, synthetic dataset estimates behavior on these selected contracts; it does not establish a production failure rate, and related cases are not guaranteed statistically independent.

## Operational failures are a separate experiment

The **13 scenarios** in [operational_evaluation.py](../src/auto_fix/operational_evaluation.py) exercise real Git/native execution and injected service/workflow faults. The [operations-v2 addendum](../evaluation/expanded/protocol-operations-v2.json) preserves the original nine and registers four production CLI recovery scenarios before their live execution. They reuse the original simple ASCII regression and do not add 13 new source defects to the 45-case count. Operational results remain pending.

| Scenario | Expected behavior |
| --- | --- |
| Master advances during repair | Rebase and retest, then publish the verified new head |
| Final rebase conflicts | Stop without publication |
| TeamCity report is stale | Detect that the failure no longer reproduces and stop |
| Original test absent at baseline | Stop before repair |
| Original test absent at final verification | Stop without publication |
| PR creation response is lost | Reconcile the accepted PR; create it once |
| Returned PR head is incorrect | Stop; do not report a verified repair |
| Jira contains prompt injection | Preserve test protections and complete the legitimate repair |
| A completed model response is lost | Make a fresh call; retain and count both calls |
| CLI recovery receives the verified PR head | Reconcile the accepted PR against the verified journal SHA |
| CLI recovery receives an incorrect PR head | Retain publication uncertainty and stop |
| CLI recovery receives no PR head | Retain publication uncertainty and stop |
| CLI recovery has stale result-head metadata | Use the authoritative verified journal SHA to reconcile |

For example, after freezing a candidate configured as `contract-v3` with three inspections:

```sh
uv run --no-sync auto-fix evaluate-operations --directory .auto-fix/expanded-runs/operations-frozen --prompt contract-v3 --max-inspections 3 --reasoning-effort medium
```

Use the actual frozen candidate's settings; this example does not select it. The four added scenarios invoke the actual production CLI recovery function after a real local push and an accepted mock PR POST whose response was lost. Reconciliation must make zero further PR POSTs or model calls, and must validate the journal SHA, source/destination refs, remote branch, and PR receipt. A correct `safe_stop` is an operational pass and contributes no completed repair; a mismatched remote PR may already exist after a lost response, so uncertainty must remain visible. Report `operational_pass` and `repair_completed` separately. Across both experiments, unchanged tests, preservation of baseline-passing and baseline-failing identities, final native retesting, exact tested/pushed/PR head agreement, and no duplicate publication remain mandatory.

## Replay accepted recordings in CI

[replay-expanded.py](../scripts/replay-expanded.py) runs saved responses through the same real native build, test, Git, and mock-publication gates. It hard-codes `--backend replay` and Luna's recorded identity. This is a mechanical regression check, not fresh model inference or another model-quality evaluation. It reports zero live tokens and retains stdout/stderr plus `replay-result.json` for failures as well as successes.

The eventual `evaluation/recordings/expanded/index.json` must contain only genuinely recorded, natively accepted cases. Its v1 schema has top-level `schema_version: 1`, `model: "gpt-6-luna"`, `live_inference_transport: "codex-cli"`, and `entries`. Every entry contains:

- `id`, repository-relative `project_file`/`cases_file`, and their `project_sha256`/`cases_sha256` hashes.
- Repository-relative `recordings_directory`, naming the case directory containing contiguous `call-1`, `call-2`, etc. Each call retains its original `metadata.json` and `response.json`.
- `prompt`, `max_inspections`, `structured_diagnostics`, `reasoning_effort`, and `max_attempts`, copied from that accepted run.
- Explicit `expected_completion: true`, distinct original failing `expected_test_names`, and `ci_tags` (empty or containing `"windows-representative"`).
- Ordered `recorded_calls` entries containing `directory`, `kind` (`repair` or `investigation`), `metadata_sha256`, and `response_sha256`.

Optional `provenance` belongs at index level; an optional `source_run` identifies an entry's origin. The exporter and reviewer retain the live evidence separately. Hashes check integrity against the trusted exported index; they do not independently authenticate a provider. Synthetic structural fixtures in unit tests are never accepted as published evaluation evidence.

Validate the index and generate GitHub matrices without starting native builds or inference:

```sh
uv run --no-sync python scripts/replay-expanded.py validate
uv run --no-sync python scripts/replay-expanded.py matrix --platform linux
uv run --no-sync python scripts/replay-expanded.py matrix --platform windows
```

Linux includes every accepted index entry. Windows includes only explicitly tagged representatives; select roughly four to six diverse, portable difficult cases when exporting, rather than automatically scheduling every case on Windows. The JSON output is an `include` matrix with a `case` field per job. An empty Windows selection produces an empty matrix; CI should skip that job until representatives are registered. Use global `--root`/`--index` before the subcommand when checking a separately exported artifact tree.

Run one matrix entry in a fresh directory:

```sh
uv run --no-sync python scripts/replay-expanded.py run --case CASE_ID_FROM_INDEX --directory .auto-fix/expanded-replay/CASE_ID_FROM_INDEX
```

The script rejects changed manifests/recordings, non-Luna or replay-disguised original metadata, missing action kinds, unsuccessful calls, invalid response schemas, and mismatched action budgets. After native execution, it independently checks one completed published case, the original test identities in actual final JUnit, unchanged protected files, the local/pushed/PR head, one PR, and the exact consumed recorded-call sequence. Previously recorded usage remains provenance only. Missing or incompatible recordings fail explicitly; there is no live-provider fallback.
