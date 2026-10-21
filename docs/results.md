# Workflow improvements and measured results

The Windows-first LangGraph workflow now includes stable failure reproduction, bounded source investigation, repeated repair and native validation, a final rebase and retest, and publication reconciliation. The selected examples use `assertion-v4`, complete C++ definition reads, two unchanged baselines, up to four repairs and six inspections shared across those attempts. The framework decision and alternatives are documented in [the research](research.md).

The substantive changes extend beyond prompts:

- Reproduce failures twice before inference, retaining the same passed, failed and skipped identities. Reject invalid, missing, duplicate, incomplete or varying native evidence.
- Retrieve complete bounded C++ definitions, preserve distinct source evidence, reserve investigation capacity for later attempts, and invalidate edited files' cached evidence.
- Carry fresh assertions and compiler feedback into retries. Preserve GoogleTest's named operands instead of guessing that both `Which is` values are actual results.
- Protect tests and build configuration, require every previously executed test to remain present and pass, and support additional trusted native suites through configuration.
- Rebase and retest the final commit, then verify that tested, pushed and PR heads and branch refs agree. Reconcile lost responses without duplicate PR creation.
- Freeze evaluation inputs before calls, preserve failures and semantic counterexamples, and replay genuine accepted responses in native CI with no live fallback.

The [workflow guide](workflow.md) explains each node and how to add one. Production has one worker and one configured endpoint; ordinary Python handles APIs, Git and compilers.

## How much was evaluated

| Experiment | Workflow trials | Actual Luna calls | Distinct cases |
| --- | ---: | ---: | --- |
| Development, 16 arms across six phases | 384 | 1,162 | 24 synthetic defects |
| Frozen holdout, baseline plus three selected rounds | 84 | 239 | 21 synthetic defects |
| Operational faults, historical runs and confirmations | 41 | 73 | 13 scenarios reusing one simple defect |
| Total in the formal inventory | 509 | 1,474 | 45 C++ defects plus 13 operational scenarios |

The C++ corpus uses pinned real Abseil and fmt source. Forty cases have multiple mutation locations and eight span multiple production files. Trials include correct pre-model blocks and unsuccessful repairs. The 24 earlier fixture-authoring prototypes and 16 original four-case smoke trials remain separate historical evidence. Python tests, native property probes and saved-response replays add zero live model evaluations. The [inventory](../evaluation/results/final-inventory.json) checks original scores and actual saved call packets, including retries and discarded responses.

## Untouched holdout outcome

| Run on the same 21 held-out defects | Native publications | Reviewed without a confirmed functional defect | Actual Luna calls |
| --- | ---: | ---: | ---: |
| Baseline | 3/21 | 3/21 | 31 |
| Selected, first round | 21/21 | 19/21 | 68 |
| Selected, second round | 21/21 | 18/21 | 77 |
| Selected, third round | 21/21 | 17/21 | 63 |

The preregistered primary comparison is **19/21 versus 3/21** after independent review. The first selected round's descriptive Wilson 95% interval is 71.1%–97.3%; this small fixed sample does not establish a production repair rate. The comparison changes the combined workflow recipe, including context and inference resources. The repeat rounds use the same 21 defects and do not add independent defects.

Across the three selected rounds, **63/63 passed the configured native checks and 54/63 had no confirmed functional defect after review**. Nine patches passed tests but retained contract problems: six documented public output failures and three scoped internal helper failures. The [holdout report](../evaluation/results/holdout-v7/report.md) preserves every raw grade and details the native counterexamples. Closed review is finite evidence, not a proof of universal correctness.

The fresh operational confirmation passed **13/13 expected behaviors**: six verified publications, four correct blocks and three correctly retained uncertain-publication states. Its fixed harness permits three repairs while the delivered selected configuration permits four. See the [operational evidence](../evaluation/expanded/artifact-inputs-operations-v7.json).

## Portability and use

Saved-response native CI uses 43 reviewed accepted patches: all 24 selected development cases and 19 first-round holdout cases. The other two holdout cases remain explicit coverage gaps after all three patches failed review. Windows uses six fixed development representatives, including a two-file repair and the additional duration guard. See the [CI coverage and results](expanded-ci.md). Replays exercise native builds and publication checks; they add no fresh inference or holdout successes.

TeamCity, Bitbucket and Jira remain realistic mocks in these evaluations. Git, C++ builds, tests, model calls and local publication receipts execute for real. Actual on-premise access, the private C++ solution, Qwen quality and capacity, and Windows Task Scheduler registration remain unmeasured. Screenshot evidence links existing TeamCity artifacts; the tool does not generate new application captures.

Adapt the graph in ordinary Python and add relevant operator-owned checks through `build.additional_tests`. A model-facing change needs a new frozen comparison. If a change uses these holdout findings, treat those cases as development evidence and obtain new held-out cases for the next cycle. The [full procedure](expanded-evaluation.md) includes commands, budgets, evidence and versioning rules.
