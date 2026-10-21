# Frozen V7 holdout evaluation

All 84 preregistered trials across 21 unique synthetic C++ defects completed with genuine GPT-6 Luna responses. The frozen implementation was `7cf4c3536c1bd7f7bdfc4d9f2e151d1bbff0b4f0`; no holdout tuning or replacement trials were performed.

| Run | Trials | Native publications (95% Wilson) | Confirmed semantic false greens | Reviewed publications without confirmed functional error (95% Wilson) | Luna calls |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 21 | 3 (5.0%–34.6%) | 0 | 3 (5.0%–34.6%) | 31 |
| selected-r1 | 21 | 21 (84.5%–100.0%) | 2 | 19 (71.1%–97.3%) | 68 |
| selected-r2 | 21 | 21 (84.5%–100.0%) | 3 | 18 (65.4%–95.0%) | 77 |
| selected-r3 | 21 | 21 (84.5%–100.0%) | 4 | 17 (60.0%–92.3%) | 63 |

The primary comparison uses the baseline and selected-r1 rows. Selected-r2 and selected-r3 repeat the same 21 defects to measure repeatability. A native publication means the unchanged full selected native suites and configured trusted guards passed and the tested, pushed and PR heads matched. Independent semantic failures preserve those original native grades.

The independent audit checked all 84 outcomes, protected test/configuration trees, real JUnit identities, original failing tests, full baseline outcome pairs, source snapshots, genuine model records and publication receipts. All published patches received closed semantic review. The audit started no model calls. Known measured performance regressions in this holdout: 0.

The width property audit found concrete documented counterexamples in published candidates using actual public `fmt::format` calls. Assigned neutral nonemoji U+1F700 (ALCHEMICAL SYMBOL FOR QUINTESSENCE) and U+1F800 (LEFTWARDS ARROW WITH SMALL TRIANGLE ARROWHEAD) must remain one column; one variant also miscounts ordinary Japanese Hiragana あ and Katakana ア. Unicode 17 original data, corrected assigned-range metadata,132 raw native calls, exact candidate hashes, portable probe source and build logs are preserved. Those132 native validation calls are not additional model evaluations. The separate widening of Unicode-wide ROCKET U+1F680 is a contract-consistent extension and is not itself treated as a regression.

[Independent audit](independent-native-semantic-audit.json) · [Detailed outcomes](report.json) · [Review notes](semantic-review-notes.json)

Limitations:

- These are 21 unique synthetic injected defects in two public C++ codebases, not historical production incidents or an estimate of general repair accuracy.
- The first selected round versus baseline is the preregistered primary comparison. Three selected rounds contain63 trials across the same 21 defects, not63 unique defects. No heldout recipe tuning, replacement trials, grader rewrites or extra model calls were introduced by this audit.
- Raw native publication grades are preserved. Independent post-publication semantic findings are separate and can expose cases that passed the unchanged upstream tests and trusted guards. Closed review without a confirmed regression is not a proof of all-input correctness or performance equivalence.
- Live model evaluation and supplemental public API audits ran on macOS. Separate recorded replay CI is deterministic reuse of genuine saved responses; it is not additional inference or evidence that every live trial ran on Windows.
- Operational TeamCity, Bitbucket and Jira inputs are synthetic. Tests, repository history, C++ compilation, Git publication receipts and actual GPT-6 Luna responses are real. No production integration, private repository or Qwen endpoint has been exercised.
- Baseline and selected policy differ in prompt, reasoning effort, context, investigation budget and repair budget; this comparison evaluates the combined workflow recipe, not an isolated causal effect of one setting. Wilson intervals are descriptive for the fixed synthetic sample; repeated rounds are not 63 independent defects.

Confirmed semantic failure subtypes (trial counts, with original native grades retained):

- documented_public_formatting_contract: 3.
- internal_object_invariant: 1.
- documented_public_escaping_contract: 3.
- retained_documented_internal_utf8_return_value_defect: 2.

The public CHexEscape counterexample emits high-bit bytes raw instead of hexadecimal escapes. The independent native audit checks all 256 bytes across four APIs, with clean 1,024 passes and candidate 128 CHexEscape failures; the three published variants have identical complete source. Existing roundtrip-only tests allow this representation error.

The UTF16 finding is an internal converter object-invariant failure after valid move assignment, reproduced in independent native builds. It is distinct from a demonstrated public fmt or actual Windows application failure. The retained internal UTF8 byte-count defect is separately confirmed by the unchanged additional upstream UTF8 suite: clean25/25; both published affected candidates24pass/1fail. The two current public CUnescape callers are workarounded and the independent WideToUtf8 encoder is unaffected; no public StrFormat/CUnescape failure is claimed.
