# GPT-6 Luna native evaluation report

This report contains36 completed runs and288 DEVELOPMENT trials over24 unique defects. It preserves original native grades; it does not pool different oracle versions as one comparable experiment.

| Cohort | Arms | Trials | Oracle |
| --- | ---: | ---: | --- |
| Original pure prompts |3|72| Original selected upstream native suites, before supplemental semantic guard |
| Enriched V3 |4|96| Original frozen suites plus4-check duration guard where applicable |
| Evidence lifecycle V4 |2|48| Same original frozen guarded native rules; refreshed evidence/inspection lifecycle |
| Source context V5 |3|72| Same original frozen guarded native rules; larger context/definition controls and adaptive budget |

The9 guarded arms select recipe parameters for a separate, pending V6 development confirmation with2 stable native baselines and stronger versioned duration/fmt guards. Confirmed semantic false greens remain separate annotations. No holdout outcome was read.

Wilson 95% on the first completed listed trial per unique (project, case); repeats are separate, not independent cases.

No model grader or automatic arm selection. Incomplete trials are reported separately.

| Arm | Split | Project | Completed/planned | Fixes | First attempt | Unique | Repeats |
| --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | development | fmt | 6/6 | 0 | 0 | 6 | 0 |
| baseline | development | Abseil C++ Common Libraries | 18/18 | 7 | 5 | 18 | 0 |
| evidence | development | fmt | 6/6 | 1 | 0 | 6 | 0 |
| evidence | development | Abseil C++ Common Libraries | 18/18 | 7 | 4 | 18 | 0 |
| contract | development | fmt | 6/6 | 1 | 0 | 6 | 0 |
| contract | development | Abseil C++ Common Libraries | 18/18 | 7 | 6 | 18 | 0 |
| structured-v3 | development | fmt | 6/6 | 1 | 1 | 6 | 0 |
| structured-v3 | development | abseil | 18/18 | 6 | 5 | 18 | 0 |
| investigation-baseline-v3 | development | fmt | 6/6 | 4 | 3 | 6 | 0 |
| investigation-baseline-v3 | development | abseil | 18/18 | 9 | 8 | 18 | 0 |
| investigation-evidence-v3 | development | fmt | 6/6 | 5 | 4 | 6 | 0 |
| investigation-evidence-v3 | development | abseil | 18/18 | 11 | 10 | 18 | 0 |
| investigation-contract-v3 | development | fmt | 6/6 | 4 | 4 | 6 | 0 |
| investigation-contract-v3 | development | abseil | 18/18 | 14 | 13 | 18 | 0 |
| evidence-lifecycle-v4-medium | development | fmt | 6/6 | 3 | 2 | 6 | 0 |
| evidence-lifecycle-v4-medium | development | abseil | 18/18 | 12 | 9 | 18 | 0 |
| evidence-lifecycle-v4-high | development | fmt | 6/6 | 5 | 3 | 6 | 0 |
| evidence-lifecycle-v4-high | development | abseil | 18/18 | 15 | 13 | 18 | 0 |
| source-budget-v5-high | development | fmt | 6/6 | 6 | 6 | 6 | 0 |
| source-definitions-v5-high | development | fmt | 6/6 | 6 | 6 | 6 | 0 |
| source-definitions-v5-adaptive-high | development | fmt | 6/6 | 6 | 5 | 6 | 0 |
| source-budget-v5-high | development | abseil | 18/18 | 16 | 12 | 18 | 0 |
| source-definitions-v5-high | development | abseil | 18/18 | 18 | 15 | 18 | 0 |
| source-definitions-v5-adaptive-high | development | abseil | 18/18 | 18 | 15 | 18 | 0 |

**baseline / development / fmt**

Calls: `{"repair": 10}`. Tokens: `{"input_tokens": 303107, "cached_input_tokens": 125568, "cache_write_input_tokens": 0, "output_tokens": 1986, "reasoning_output_tokens": 202}`. Wilson 95%: `[2.7755575615628914e-17, 0.3903342879021653]`. Failure stages: `{"context_budget_before_model": 1, "model_proposal": 2, "native_tests": 3}`.
Baseline checks: unrecorded in historical baseline-check counter; original baseline reports retained.

**baseline / development / Abseil C++ Common Libraries**

Calls: `{"repair": 23}`. Tokens: `{"input_tokens": 703615, "cached_input_tokens": 286080, "cache_write_input_tokens": 0, "output_tokens": 5357, "reasoning_output_tokens": 1195}`. Wilson 95%: `[0.2030524657216362, 0.613809583977621]`. Failure stages: `{"model_proposal": 3, "context_budget_before_model": 4, "native_tests": 4}`.
Baseline checks: unrecorded in historical baseline-check counter; original baseline reports retained.

**evidence / development / fmt**

Calls: `{"repair": 10}`. Tokens: `{"input_tokens": 301731, "cached_input_tokens": 123264, "cache_write_input_tokens": 0, "output_tokens": 3195, "reasoning_output_tokens": 492}`. Wilson 95%: `[0.030053369748306635, 0.5635028221864702]`. Failure stages: `{"context_budget_before_model": 1, "model_proposal": 3, "native_tests": 1}`.
Baseline checks: unrecorded in historical baseline-check counter; original baseline reports retained.

**evidence / development / Abseil C++ Common Libraries**

Calls: `{"repair": 24}`. Tokens: `{"input_tokens": 743544, "cached_input_tokens": 334848, "cache_write_input_tokens": 0, "output_tokens": 6202, "reasoning_output_tokens": 232}`. Wilson 95%: `[0.2030524657216362, 0.613809583977621]`. Failure stages: `{"model_proposal": 3, "context_budget_before_model": 4, "native_tests": 4}`.
Baseline checks: unrecorded in historical baseline-check counter; original baseline reports retained.

**contract / development / fmt**

Calls: `{"repair": 10}`. Tokens: `{"input_tokens": 298479, "cached_input_tokens": 139008, "cache_write_input_tokens": 0, "output_tokens": 2828, "reasoning_output_tokens": 294}`. Wilson 95%: `[0.030053369748306635, 0.5635028221864702]`. Failure stages: `{"context_budget_before_model": 1, "model_proposal": 3, "native_tests": 1}`.
Baseline checks: unrecorded in historical baseline-check counter; original baseline reports retained.

**contract / development / Abseil C++ Common Libraries**

Calls: `{"repair": 22}`. Tokens: `{"input_tokens": 677978, "cached_input_tokens": 262528, "cache_write_input_tokens": 0, "output_tokens": 6546, "reasoning_output_tokens": 1490}`. Wilson 95%: `[0.2030524657216362, 0.613809583977621]`. Failure stages: `{"model_proposal": 4, "context_budget_before_model": 4, "native_tests": 3}`.
Baseline checks: unrecorded in historical baseline-check counter; original baseline reports retained.

**structured-v3 / development / fmt**

Calls: `{"repair": 11}`. Tokens: `{"input_tokens": 324091, "cached_input_tokens": 153216, "cache_write_input_tokens": 0, "output_tokens": 2833, "reasoning_output_tokens": 516}`. Wilson 95%: `[0.030053369748306635, 0.5635028221864702]`. Failure stages: `{"model_proposal": 3, "native_tests": 2}`.
Baseline checks: unrecorded in historical baseline-check counter; original baseline reports retained.

**structured-v3 / development / abseil**

Calls: `{"repair": 31}`. Tokens: `{"input_tokens": 934749, "cached_input_tokens": 423040, "cache_write_input_tokens": 0, "output_tokens": 9698, "reasoning_output_tokens": 563}`. Wilson 95%: `[0.1627877475083369, 0.5625053270405489]`. Failure stages: `{"model_proposal": 5, "native_tests": 7}`.
Baseline checks: unrecorded in historical baseline-check counter; original baseline reports retained.

**investigation-baseline-v3 / development / fmt**

Calls: `{"investigation": 18, "repair": 9}`. Tokens: `{"input_tokens": 825580, "cached_input_tokens": 246400, "cache_write_input_tokens": 0, "output_tokens": 7295, "reasoning_output_tokens": 1374}`. Wilson 95%: `[0.299993315138392, 0.9032285888942195]`. Failure stages: `{"model_proposal": 1, "native_build": 1}`.
Baseline checks: unrecorded in historical baseline-check counter; original baseline reports retained.

**investigation-baseline-v3 / development / abseil**

Calls: `{"investigation": 51, "repair": 28}`. Tokens: `{"input_tokens": 2439666, "cached_input_tokens": 990848, "cache_write_input_tokens": 0, "output_tokens": 20650, "reasoning_output_tokens": 2997}`. Wilson 95%: `[0.29031021505169974, 0.7096897849483003]`. Failure stages: `{"model_proposal": 3, "native_tests": 6}`.
Baseline checks: unrecorded in historical baseline-check counter; original baseline reports retained.

**investigation-evidence-v3 / development / fmt**

Calls: `{"investigation": 15, "repair": 8}`. Tokens: `{"input_tokens": 705243, "cached_input_tokens": 304768, "cache_write_input_tokens": 0, "output_tokens": 7821, "reasoning_output_tokens": 2752}`. Wilson 95%: `[0.43649717781352987, 0.9699466302516935]`. Failure stages: `{"native_tests": 1}`.
Baseline checks: unrecorded in historical baseline-check counter; original baseline reports retained.

**investigation-evidence-v3 / development / abseil**

Calls: `{"investigation": 45, "repair": 24}`. Tokens: `{"input_tokens": 2126376, "cached_input_tokens": 923264, "cache_write_input_tokens": 0, "output_tokens": 21728, "reasoning_output_tokens": 3982}`. Wilson 95%: `[0.3861904160223791, 0.7969475342783638]`. Failure stages: `{"native_tests": 5, "model_proposal": 1, "baseline_reproduction": 1}`.
Baseline checks: unrecorded in historical baseline-check counter; original baseline reports retained.

**investigation-contract-v3 / development / fmt**

Calls: `{"investigation": 18, "repair": 8}`. Tokens: `{"input_tokens": 794505, "cached_input_tokens": 356224, "cache_write_input_tokens": 0, "output_tokens": 7547, "reasoning_output_tokens": 823}`. Wilson 95%: `[0.299993315138392, 0.9032285888942195]`. Failure stages: `{"native_tests": 2}`.
Baseline checks: unrecorded in historical baseline-check counter; original baseline reports retained.

**investigation-contract-v3 / development / abseil**

Calls: `{"investigation": 51, "repair": 23}`. Tokens: `{"input_tokens": 2276586, "cached_input_tokens": 981248, "cache_write_input_tokens": 0, "output_tokens": 23522, "reasoning_output_tokens": 4921}`. Wilson 95%: `[0.5478541568378739, 0.9099907189139831]`. Failure stages: `{"native_tests": 3, "model_proposal": 1}`.
Baseline checks: unrecorded in historical baseline-check counter; original baseline reports retained.

**evidence-lifecycle-v4-medium / development / fmt**

Calls: `{"investigation": 20, "repair": 10}`. Tokens: `{"input_tokens": 907406, "cached_input_tokens": 383872, "cache_write_input_tokens": 0, "output_tokens": 9272, "reasoning_output_tokens": 2124}`. Wilson 95%: `[0.1876163064826506, 0.8123836935173494]`. Failure stages: `{"native_tests": 1, "native_build": 1, "model_proposal": 1}`.
Baseline checks: unrecorded in historical baseline-check counter; original baseline reports retained.

**evidence-lifecycle-v4-medium / development / abseil**

Calls: `{"investigation": 50, "repair": 27}`. Tokens: `{"input_tokens": 2358326, "cached_input_tokens": 1046784, "cache_write_input_tokens": 0, "output_tokens": 24065, "reasoning_output_tokens": 5492}`. Wilson 95%: `[0.43749467295945105, 0.837212252491663]`. Failure stages: `{"model_proposal": 3, "native_tests": 3}`.
Baseline checks: unrecorded in historical baseline-check counter; original baseline reports retained.

**evidence-lifecycle-v4-high / development / fmt**

Calls: `{"investigation": 18, "repair": 9}`. Tokens: `{"input_tokens": 814209, "cached_input_tokens": 272512, "cache_write_input_tokens": 0, "output_tokens": 26795, "reasoning_output_tokens": 20559}`. Wilson 95%: `[0.43649717781352987, 0.9699466302516935]`. Failure stages: `{"native_tests": 1}`.
Baseline checks: unrecorded in historical baseline-check counter; original baseline reports retained.

**evidence-lifecycle-v4-high / development / abseil**

Calls: `{"investigation": 45, "repair": 23}`. Tokens: `{"input_tokens": 2073442, "cached_input_tokens": 930048, "cache_write_input_tokens": 0, "output_tokens": 53809, "reasoning_output_tokens": 38099}`. Wilson 95%: `[0.6077796189608428, 0.9416342319413856]`. Failure stages: `{"model_proposal": 2, "native_tests": 1}`.
Baseline checks: unrecorded in historical baseline-check counter; original baseline reports retained.

**source-budget-v5-high / development / fmt**

Calls: `{"investigation": 10, "repair": 6}`. Tokens: `{"input_tokens": 652710, "cached_input_tokens": 39552, "cache_write_input_tokens": 0, "output_tokens": 12969, "reasoning_output_tokens": 9481}`. Wilson 95%: `[0.6096657120978346, 1.0]`. Failure stages: `{}`.
Baseline checks: unrecorded in historical baseline-check counter; original baseline reports retained.

**source-definitions-v5-high / development / fmt**

Calls: `{"investigation": 10, "repair": 6}`. Tokens: `{"input_tokens": 649421, "cached_input_tokens": 67456, "cache_write_input_tokens": 0, "output_tokens": 13729, "reasoning_output_tokens": 10181}`. Wilson 95%: `[0.6096657120978346, 1.0]`. Failure stages: `{}`.
Baseline checks: unrecorded in historical baseline-check counter; original baseline reports retained.

**source-definitions-v5-adaptive-high / development / fmt**

Calls: `{"investigation": 12, "repair": 8}`. Tokens: `{"input_tokens": 787961, "cached_input_tokens": 125568, "cache_write_input_tokens": 0, "output_tokens": 13663, "reasoning_output_tokens": 9519}`. Wilson 95%: `[0.6096657120978346, 1.0]`. Failure stages: `{}`.
Baseline checks: unrecorded in historical baseline-check counter; original baseline reports retained.

**source-budget-v5-high / development / abseil**

Calls: `{"investigation": 41, "repair": 24}`. Tokens: `{"input_tokens": 2743033, "cached_input_tokens": 894208, "cache_write_input_tokens": 0, "output_tokens": 49779, "reasoning_output_tokens": 35708}`. Wilson 95%: `[0.672002348698212, 0.9689804773543876]`. Failure stages: `{"native_tests": 2}`.
Baseline checks: unrecorded in historical baseline-check counter; original baseline reports retained.

**source-definitions-v5-high / development / abseil**

Calls: `{"investigation": 36, "repair": 21}`. Tokens: `{"input_tokens": 2385623, "cached_input_tokens": 704768, "cache_write_input_tokens": 0, "output_tokens": 39134, "reasoning_output_tokens": 25520}`. Wilson 95%: `[0.8241207763533425, 1.0]`. Failure stages: `{}`.
Baseline checks: unrecorded in historical baseline-check counter; original baseline reports retained.

**source-definitions-v5-adaptive-high / development / abseil**

Calls: `{"investigation": 37, "repair": 21}`. Tokens: `{"input_tokens": 2390857, "cached_input_tokens": 746496, "cache_write_input_tokens": 0, "output_tokens": 41127, "reasoning_output_tokens": 27948}`. Wilson 95%: `[0.8241207763533425, 1.0]`. Failure stages: `{}`.
Baseline checks: unrecorded in historical baseline-check counter; original baseline reports retained.

| Run | Arm | Split | Case | Outcome | Attempts | Baselines observed/requested | Failed stage |
| --- | --- | --- | --- | --- | --- | --- | --- |
| baseline-fmt | baseline | development | fmt_utf8_validation_boundaries | blocked | 1 | unrecorded/1 | context_budget_before_model |
| baseline-fmt | baseline | development | fmt_debug_control_escapes | blocked | 2 | unrecorded/1 | model_proposal |
| baseline-fmt | baseline | development | fmt_printf_dynamic_field_sign | blocked | 2 | unrecorded/1 | native_tests |
| baseline-fmt | baseline | development | fmt_integer_precision_padding | blocked | 2 | unrecorded/1 | model_proposal |
| baseline-fmt | baseline | development | fmt_pre_epoch_fraction_normalization | blocked | 2 | unrecorded/1 | native_tests |
| baseline-fmt | baseline | development | fmt_diagnostic_fallback_capacity | blocked | 2 | unrecorded/1 | native_tests |
| baseline-strings | baseline | development | absl_escape_byte_overflow | blocked | 2 | unrecorded/1 | model_proposal |
| baseline-strings | baseline | development | absl_escape_hex_continuation | published | 1 | unrecorded/1 | success |
| baseline-strings | baseline | development | absl_base64_tail_codec | blocked | 1 | unrecorded/1 | context_budget_before_model |
| baseline-strings | baseline | development | absl_base64_optional_padding_whitespace | blocked | 1 | unrecorded/1 | context_budget_before_model |
| baseline-strings | baseline | development | absl_integer_bare_prefixes | blocked | 2 | unrecorded/1 | model_proposal |
| baseline-strings | baseline | development | absl_integer_partial_results | blocked | 2 | unrecorded/1 | model_proposal |
| baseline-strings | baseline | development | absl_integer_signed_boundaries | blocked | 1 | unrecorded/1 | context_budget_before_model |
| baseline-strings | baseline | development | absl_replace_overlap_and_progress | blocked | 2 | unrecorded/1 | native_tests |
| baseline-strings | baseline | development | absl_split_literal_and_chunk_boundaries | published | 2 | unrecorded/1 | success |
| baseline-strings | baseline | development | absl_base64_alphabet_contract | blocked | 1 | unrecorded/1 | context_budget_before_model |
| baseline-systems | baseline | development | duration_negative_unit_rounding | published | 1 | unrecorded/1 | success |
| baseline-systems | baseline | development | duration_composite_parse_accumulator | published | 1 | unrecorded/1 | success |
| baseline-systems | baseline | development | duration_posix_negative_fraction_rounding | blocked | 2 | unrecorded/1 | native_tests |
| baseline-systems | baseline | development | time_negative_unix_precision_floor | published | 1 | unrecorded/1 | success |
| baseline-systems | baseline | development | status_update_first_failure_contract | blocked | 2 | unrecorded/1 | native_tests |
| baseline-systems | baseline | development | status_payload_clone_write_retention | published | 2 | unrecorded/1 | success |
| baseline-systems | baseline | development | status_lookup_conflict_dispatch | published | 1 | unrecorded/1 | success |
| baseline-systems | baseline | development | status_copy_on_write_mutation_boundary | blocked | 2 | unrecorded/1 | native_tests |
| evidence-fmt | evidence | development | fmt_utf8_validation_boundaries | blocked | 1 | unrecorded/1 | context_budget_before_model |
| evidence-fmt | evidence | development | fmt_debug_control_escapes | blocked | 2 | unrecorded/1 | model_proposal |
| evidence-fmt | evidence | development | fmt_printf_dynamic_field_sign | blocked | 2 | unrecorded/1 | model_proposal |
| evidence-fmt | evidence | development | fmt_integer_precision_padding | blocked | 2 | unrecorded/1 | model_proposal |
| evidence-fmt | evidence | development | fmt_pre_epoch_fraction_normalization | blocked | 2 | unrecorded/1 | native_tests |
| evidence-fmt | evidence | development | fmt_diagnostic_fallback_capacity | published | 2 | unrecorded/1 | success |
| evidence-strings | evidence | development | absl_escape_byte_overflow | blocked | 2 | unrecorded/1 | model_proposal |
| evidence-strings | evidence | development | absl_escape_hex_continuation | published | 1 | unrecorded/1 | success |
| evidence-strings | evidence | development | absl_base64_tail_codec | blocked | 1 | unrecorded/1 | context_budget_before_model |
| evidence-strings | evidence | development | absl_base64_optional_padding_whitespace | blocked | 1 | unrecorded/1 | context_budget_before_model |
| evidence-strings | evidence | development | absl_integer_bare_prefixes | blocked | 2 | unrecorded/1 | model_proposal |
| evidence-strings | evidence | development | absl_integer_partial_results | blocked | 2 | unrecorded/1 | model_proposal |
| evidence-strings | evidence | development | absl_integer_signed_boundaries | blocked | 1 | unrecorded/1 | context_budget_before_model |
| evidence-strings | evidence | development | absl_replace_overlap_and_progress | blocked | 2 | unrecorded/1 | native_tests |
| evidence-strings | evidence | development | absl_split_literal_and_chunk_boundaries | published | 1 | unrecorded/1 | success |
| evidence-strings | evidence | development | absl_base64_alphabet_contract | blocked | 1 | unrecorded/1 | context_budget_before_model |
| evidence-systems | evidence | development | duration_negative_unit_rounding | published | 2 | unrecorded/1 | success |
| evidence-systems | evidence | development | duration_composite_parse_accumulator | published | 1 | unrecorded/1 | success |
| evidence-systems | evidence | development | duration_posix_negative_fraction_rounding | blocked | 2 | unrecorded/1 | native_tests |
| evidence-systems | evidence | development | time_negative_unix_precision_floor | blocked | 2 | unrecorded/1 | native_tests |
| evidence-systems | evidence | development | status_update_first_failure_contract | published | 2 | unrecorded/1 | success |
| evidence-systems | evidence | development | status_payload_clone_write_retention | published | 2 | unrecorded/1 | success |
| evidence-systems | evidence | development | status_lookup_conflict_dispatch | published | 1 | unrecorded/1 | success |
| evidence-systems | evidence | development | status_copy_on_write_mutation_boundary | blocked | 2 | unrecorded/1 | native_tests |
| contract-fmt | contract | development | fmt_utf8_validation_boundaries | blocked | 1 | unrecorded/1 | context_budget_before_model |
| contract-fmt | contract | development | fmt_debug_control_escapes | blocked | 2 | unrecorded/1 | model_proposal |
| contract-fmt | contract | development | fmt_printf_dynamic_field_sign | blocked | 2 | unrecorded/1 | model_proposal |
| contract-fmt | contract | development | fmt_integer_precision_padding | blocked | 2 | unrecorded/1 | model_proposal |
| contract-fmt | contract | development | fmt_pre_epoch_fraction_normalization | blocked | 2 | unrecorded/1 | native_tests |
| contract-fmt | contract | development | fmt_diagnostic_fallback_capacity | published | 2 | unrecorded/1 | success |
| contract-strings | contract | development | absl_escape_byte_overflow | blocked | 2 | unrecorded/1 | model_proposal |
| contract-strings | contract | development | absl_escape_hex_continuation | published | 1 | unrecorded/1 | success |
| contract-strings | contract | development | absl_base64_tail_codec | blocked | 1 | unrecorded/1 | context_budget_before_model |
| contract-strings | contract | development | absl_base64_optional_padding_whitespace | blocked | 1 | unrecorded/1 | context_budget_before_model |
| contract-strings | contract | development | absl_integer_bare_prefixes | blocked | 2 | unrecorded/1 | model_proposal |
| contract-strings | contract | development | absl_integer_partial_results | blocked | 2 | unrecorded/1 | model_proposal |
| contract-strings | contract | development | absl_integer_signed_boundaries | blocked | 1 | unrecorded/1 | context_budget_before_model |
| contract-strings | contract | development | absl_replace_overlap_and_progress | published | 2 | unrecorded/1 | success |
| contract-strings | contract | development | absl_split_literal_and_chunk_boundaries | published | 1 | unrecorded/1 | success |
| contract-strings | contract | development | absl_base64_alphabet_contract | blocked | 1 | unrecorded/1 | context_budget_before_model |
| contract-systems | contract | development | duration_negative_unit_rounding | published | 1 | unrecorded/1 | success |
| contract-systems | contract | development | duration_composite_parse_accumulator | published | 1 | unrecorded/1 | success |
| contract-systems | contract | development | duration_posix_negative_fraction_rounding | blocked | 2 | unrecorded/1 | native_tests |
| contract-systems | contract | development | time_negative_unix_precision_floor | published | 1 | unrecorded/1 | success |
| contract-systems | contract | development | status_update_first_failure_contract | blocked | 2 | unrecorded/1 | native_tests |
| contract-systems | contract | development | status_payload_clone_write_retention | blocked | 2 | unrecorded/1 | model_proposal |
| contract-systems | contract | development | status_lookup_conflict_dispatch | published | 1 | unrecorded/1 | success |
| contract-systems | contract | development | status_copy_on_write_mutation_boundary | blocked | 2 | unrecorded/1 | native_tests |
| structured-v3-fmt | structured-v3 | development | fmt_utf8_validation_boundaries | published | 1 | unrecorded/1 | success |
| structured-v3-fmt | structured-v3 | development | fmt_debug_control_escapes | blocked | 2 | unrecorded/1 | model_proposal |
| structured-v3-fmt | structured-v3 | development | fmt_printf_dynamic_field_sign | blocked | 2 | unrecorded/1 | model_proposal |
| structured-v3-fmt | structured-v3 | development | fmt_integer_precision_padding | blocked | 2 | unrecorded/1 | model_proposal |
| structured-v3-fmt | structured-v3 | development | fmt_pre_epoch_fraction_normalization | blocked | 2 | unrecorded/1 | native_tests |
| structured-v3-fmt | structured-v3 | development | fmt_diagnostic_fallback_capacity | blocked | 2 | unrecorded/1 | native_tests |
| structured-v3-strings | structured-v3 | development | absl_escape_byte_overflow | blocked | 2 | unrecorded/1 | model_proposal |
| structured-v3-strings | structured-v3 | development | absl_escape_hex_continuation | published | 1 | unrecorded/1 | success |
| structured-v3-strings | structured-v3 | development | absl_base64_tail_codec | blocked | 2 | unrecorded/1 | native_tests |
| structured-v3-strings | structured-v3 | development | absl_base64_optional_padding_whitespace | published | 1 | unrecorded/1 | success |
| structured-v3-strings | structured-v3 | development | absl_integer_bare_prefixes | blocked | 2 | unrecorded/1 | model_proposal |
| structured-v3-strings | structured-v3 | development | absl_integer_partial_results | blocked | 2 | unrecorded/1 | model_proposal |
| structured-v3-strings | structured-v3 | development | absl_integer_signed_boundaries | blocked | 2 | unrecorded/1 | model_proposal |
| structured-v3-strings | structured-v3 | development | absl_replace_overlap_and_progress | published | 2 | unrecorded/1 | success |
| structured-v3-strings | structured-v3 | development | absl_split_literal_and_chunk_boundaries | published | 1 | unrecorded/1 | success |
| structured-v3-strings | structured-v3 | development | absl_base64_alphabet_contract | blocked | 2 | unrecorded/1 | native_tests |
| structured-v3-systems | structured-v3 | development | duration_negative_unit_rounding | blocked | 2 | unrecorded/1 | native_tests |
| structured-v3-systems | structured-v3 | development | duration_composite_parse_accumulator | published | 1 | unrecorded/1 | success |
| structured-v3-systems | structured-v3 | development | duration_posix_negative_fraction_rounding | blocked | 2 | unrecorded/1 | native_tests |
| structured-v3-systems | structured-v3 | development | time_negative_unix_precision_floor | blocked | 2 | unrecorded/1 | native_tests |
| structured-v3-systems | structured-v3 | development | status_update_first_failure_contract | blocked | 2 | unrecorded/1 | native_tests |
| structured-v3-systems | structured-v3 | development | status_payload_clone_write_retention | blocked | 2 | unrecorded/1 | model_proposal |
| structured-v3-systems | structured-v3 | development | status_lookup_conflict_dispatch | published | 1 | unrecorded/1 | success |
| structured-v3-systems | structured-v3 | development | status_copy_on_write_mutation_boundary | blocked | 2 | unrecorded/1 | native_tests |
| investigation-baseline-v3-fmt | investigation-baseline-v3 | development | fmt_utf8_validation_boundaries | published | 1 | unrecorded/1 | success |
| investigation-baseline-v3-fmt | investigation-baseline-v3 | development | fmt_debug_control_escapes | published | 1 | unrecorded/1 | success |
| investigation-baseline-v3-fmt | investigation-baseline-v3 | development | fmt_printf_dynamic_field_sign | blocked | 2 | unrecorded/1 | model_proposal |
| investigation-baseline-v3-fmt | investigation-baseline-v3 | development | fmt_integer_precision_padding | published | 1 | unrecorded/1 | success |
| investigation-baseline-v3-fmt | investigation-baseline-v3 | development | fmt_pre_epoch_fraction_normalization | blocked | 2 | unrecorded/1 | native_build |
| investigation-baseline-v3-fmt | investigation-baseline-v3 | development | fmt_diagnostic_fallback_capacity | published | 2 | unrecorded/1 | success |
| investigation-baseline-v3-strings | investigation-baseline-v3 | development | absl_escape_byte_overflow | blocked | 2 | unrecorded/1 | model_proposal |
| investigation-baseline-v3-strings | investigation-baseline-v3 | development | absl_escape_hex_continuation | published | 1 | unrecorded/1 | success |
| investigation-baseline-v3-strings | investigation-baseline-v3 | development | absl_base64_tail_codec | blocked | 2 | unrecorded/1 | native_tests |
| investigation-baseline-v3-strings | investigation-baseline-v3 | development | absl_base64_optional_padding_whitespace | published | 1 | unrecorded/1 | success |
| investigation-baseline-v3-strings | investigation-baseline-v3 | development | absl_integer_bare_prefixes | blocked | 2 | unrecorded/1 | model_proposal |
| investigation-baseline-v3-strings | investigation-baseline-v3 | development | absl_integer_partial_results | published | 1 | unrecorded/1 | success |
| investigation-baseline-v3-strings | investigation-baseline-v3 | development | absl_integer_signed_boundaries | published | 1 | unrecorded/1 | success |
| investigation-baseline-v3-strings | investigation-baseline-v3 | development | absl_replace_overlap_and_progress | blocked | 2 | unrecorded/1 | native_tests |
| investigation-baseline-v3-strings | investigation-baseline-v3 | development | absl_split_literal_and_chunk_boundaries | published | 1 | unrecorded/1 | success |
| investigation-baseline-v3-strings | investigation-baseline-v3 | development | absl_base64_alphabet_contract | published | 2 | unrecorded/1 | success |
| investigation-baseline-v3-systems | investigation-baseline-v3 | development | duration_negative_unit_rounding | blocked | 2 | unrecorded/1 | native_tests |
| investigation-baseline-v3-systems | investigation-baseline-v3 | development | duration_composite_parse_accumulator | published | 1 | unrecorded/1 | success |
| investigation-baseline-v3-systems | investigation-baseline-v3 | development | duration_posix_negative_fraction_rounding | blocked | 2 | unrecorded/1 | native_tests |
| investigation-baseline-v3-systems | investigation-baseline-v3 | development | time_negative_unix_precision_floor | blocked | 2 | unrecorded/1 | native_tests |
| investigation-baseline-v3-systems | investigation-baseline-v3 | development | status_update_first_failure_contract | published | 1 | unrecorded/1 | success |
| investigation-baseline-v3-systems | investigation-baseline-v3 | development | status_payload_clone_write_retention | blocked | 2 | unrecorded/1 | model_proposal |
| investigation-baseline-v3-systems | investigation-baseline-v3 | development | status_lookup_conflict_dispatch | published | 1 | unrecorded/1 | success |
| investigation-baseline-v3-systems | investigation-baseline-v3 | development | status_copy_on_write_mutation_boundary | blocked | 2 | unrecorded/1 | native_tests |
| investigation-evidence-v3-fmt | investigation-evidence-v3 | development | fmt_utf8_validation_boundaries | published | 1 | unrecorded/1 | success |
| investigation-evidence-v3-fmt | investigation-evidence-v3 | development | fmt_debug_control_escapes | published | 1 | unrecorded/1 | success |
| investigation-evidence-v3-fmt | investigation-evidence-v3 | development | fmt_printf_dynamic_field_sign | published | 1 | unrecorded/1 | success |
| investigation-evidence-v3-fmt | investigation-evidence-v3 | development | fmt_integer_precision_padding | published | 2 | unrecorded/1 | success |
| investigation-evidence-v3-fmt | investigation-evidence-v3 | development | fmt_pre_epoch_fraction_normalization | published | 1 | unrecorded/1 | success |
| investigation-evidence-v3-fmt | investigation-evidence-v3 | development | fmt_diagnostic_fallback_capacity | blocked | 2 | unrecorded/1 | native_tests |
| investigation-evidence-v3-strings | investigation-evidence-v3 | development | absl_escape_byte_overflow | published | 1 | unrecorded/1 | success |
| investigation-evidence-v3-strings | investigation-evidence-v3 | development | absl_escape_hex_continuation | published | 1 | unrecorded/1 | success |
| investigation-evidence-v3-strings | investigation-evidence-v3 | development | absl_base64_tail_codec | blocked | 2 | unrecorded/1 | native_tests |
| investigation-evidence-v3-strings | investigation-evidence-v3 | development | absl_base64_optional_padding_whitespace | published | 1 | unrecorded/1 | success |
| investigation-evidence-v3-strings | investigation-evidence-v3 | development | absl_integer_bare_prefixes | blocked | 2 | unrecorded/1 | model_proposal |
| investigation-evidence-v3-strings | investigation-evidence-v3 | development | absl_integer_partial_results | published | 1 | unrecorded/1 | success |
| investigation-evidence-v3-strings | investigation-evidence-v3 | development | absl_integer_signed_boundaries | blocked | 0 | unrecorded/1 | baseline_reproduction |
| investigation-evidence-v3-strings | investigation-evidence-v3 | development | absl_replace_overlap_and_progress | blocked | 2 | unrecorded/1 | native_tests |
| investigation-evidence-v3-strings | investigation-evidence-v3 | development | absl_split_literal_and_chunk_boundaries | published | 1 | unrecorded/1 | success |
| investigation-evidence-v3-strings | investigation-evidence-v3 | development | absl_base64_alphabet_contract | blocked | 2 | unrecorded/1 | native_tests |
| investigation-evidence-v3-systems | investigation-evidence-v3 | development | duration_negative_unit_rounding | published | 2 | unrecorded/1 | success |
| investigation-evidence-v3-systems | investigation-evidence-v3 | development | duration_composite_parse_accumulator | published | 1 | unrecorded/1 | success |
| investigation-evidence-v3-systems | investigation-evidence-v3 | development | duration_posix_negative_fraction_rounding | blocked | 2 | unrecorded/1 | native_tests |
| investigation-evidence-v3-systems | investigation-evidence-v3 | development | time_negative_unix_precision_floor | blocked | 2 | unrecorded/1 | native_tests |
| investigation-evidence-v3-systems | investigation-evidence-v3 | development | status_update_first_failure_contract | published | 1 | unrecorded/1 | success |
| investigation-evidence-v3-systems | investigation-evidence-v3 | development | status_payload_clone_write_retention | published | 1 | unrecorded/1 | success |
| investigation-evidence-v3-systems | investigation-evidence-v3 | development | status_lookup_conflict_dispatch | published | 1 | unrecorded/1 | success |
| investigation-evidence-v3-systems | investigation-evidence-v3 | development | status_copy_on_write_mutation_boundary | published | 1 | unrecorded/1 | success |
| investigation-contract-v3-fmt | investigation-contract-v3 | development | fmt_utf8_validation_boundaries | published | 1 | unrecorded/1 | success |
| investigation-contract-v3-fmt | investigation-contract-v3 | development | fmt_debug_control_escapes | published | 1 | unrecorded/1 | success |
| investigation-contract-v3-fmt | investigation-contract-v3 | development | fmt_printf_dynamic_field_sign | published | 1 | unrecorded/1 | success |
| investigation-contract-v3-fmt | investigation-contract-v3 | development | fmt_integer_precision_padding | blocked | 2 | unrecorded/1 | native_tests |
| investigation-contract-v3-fmt | investigation-contract-v3 | development | fmt_pre_epoch_fraction_normalization | published | 1 | unrecorded/1 | success |
| investigation-contract-v3-fmt | investigation-contract-v3 | development | fmt_diagnostic_fallback_capacity | blocked | 2 | unrecorded/1 | native_tests |
| investigation-contract-v3-strings | investigation-contract-v3 | development | absl_escape_byte_overflow | published | 1 | unrecorded/1 | success |
| investigation-contract-v3-strings | investigation-contract-v3 | development | absl_escape_hex_continuation | published | 1 | unrecorded/1 | success |
| investigation-contract-v3-strings | investigation-contract-v3 | development | absl_base64_tail_codec | blocked | 2 | unrecorded/1 | native_tests |
| investigation-contract-v3-strings | investigation-contract-v3 | development | absl_base64_optional_padding_whitespace | published | 1 | unrecorded/1 | success |
| investigation-contract-v3-strings | investigation-contract-v3 | development | absl_integer_bare_prefixes | blocked | 2 | unrecorded/1 | model_proposal |
| investigation-contract-v3-strings | investigation-contract-v3 | development | absl_integer_partial_results | published | 1 | unrecorded/1 | success |
| investigation-contract-v3-strings | investigation-contract-v3 | development | absl_integer_signed_boundaries | published | 1 | unrecorded/1 | success |
| investigation-contract-v3-strings | investigation-contract-v3 | development | absl_replace_overlap_and_progress | published | 2 | unrecorded/1 | success |
| investigation-contract-v3-strings | investigation-contract-v3 | development | absl_split_literal_and_chunk_boundaries | published | 1 | unrecorded/1 | success |
| investigation-contract-v3-strings | investigation-contract-v3 | development | absl_base64_alphabet_contract | published | 1 | unrecorded/1 | success |
| investigation-contract-v3-systems | investigation-contract-v3 | development | duration_negative_unit_rounding | published | 1 | unrecorded/1 | success |
| investigation-contract-v3-systems | investigation-contract-v3 | development | duration_composite_parse_accumulator | published | 1 | unrecorded/1 | success |
| investigation-contract-v3-systems | investigation-contract-v3 | development | duration_posix_negative_fraction_rounding | published | 1 | unrecorded/1 | success |
| investigation-contract-v3-systems | investigation-contract-v3 | development | time_negative_unix_precision_floor | blocked | 2 | unrecorded/1 | native_tests |
| investigation-contract-v3-systems | investigation-contract-v3 | development | status_update_first_failure_contract | published | 1 | unrecorded/1 | success |
| investigation-contract-v3-systems | investigation-contract-v3 | development | status_payload_clone_write_retention | published | 1 | unrecorded/1 | success |
| investigation-contract-v3-systems | investigation-contract-v3 | development | status_lookup_conflict_dispatch | published | 1 | unrecorded/1 | success |
| investigation-contract-v3-systems | investigation-contract-v3 | development | status_copy_on_write_mutation_boundary | blocked | 2 | unrecorded/1 | native_tests |
| evidence-lifecycle-v4-medium-fmt | evidence-lifecycle-v4-medium | development | fmt_utf8_validation_boundaries | published | 1 | unrecorded/1 | success |
| evidence-lifecycle-v4-medium-fmt | evidence-lifecycle-v4-medium | development | fmt_debug_control_escapes | published | 1 | unrecorded/1 | success |
| evidence-lifecycle-v4-medium-fmt | evidence-lifecycle-v4-medium | development | fmt_printf_dynamic_field_sign | blocked | 2 | unrecorded/1 | native_tests |
| evidence-lifecycle-v4-medium-fmt | evidence-lifecycle-v4-medium | development | fmt_integer_precision_padding | blocked | 2 | unrecorded/1 | native_build |
| evidence-lifecycle-v4-medium-fmt | evidence-lifecycle-v4-medium | development | fmt_pre_epoch_fraction_normalization | blocked | 2 | unrecorded/1 | model_proposal |
| evidence-lifecycle-v4-medium-fmt | evidence-lifecycle-v4-medium | development | fmt_diagnostic_fallback_capacity | published | 2 | unrecorded/1 | success |
| evidence-lifecycle-v4-medium-strings | evidence-lifecycle-v4-medium | development | absl_escape_byte_overflow | published | 2 | unrecorded/1 | success |
| evidence-lifecycle-v4-medium-strings | evidence-lifecycle-v4-medium | development | absl_escape_hex_continuation | published | 1 | unrecorded/1 | success |
| evidence-lifecycle-v4-medium-strings | evidence-lifecycle-v4-medium | development | absl_base64_tail_codec | blocked | 2 | unrecorded/1 | model_proposal |
| evidence-lifecycle-v4-medium-strings | evidence-lifecycle-v4-medium | development | absl_base64_optional_padding_whitespace | blocked | 2 | unrecorded/1 | native_tests |
| evidence-lifecycle-v4-medium-strings | evidence-lifecycle-v4-medium | development | absl_integer_bare_prefixes | blocked | 2 | unrecorded/1 | model_proposal |
| evidence-lifecycle-v4-medium-strings | evidence-lifecycle-v4-medium | development | absl_integer_partial_results | published | 1 | unrecorded/1 | success |
| evidence-lifecycle-v4-medium-strings | evidence-lifecycle-v4-medium | development | absl_integer_signed_boundaries | published | 1 | unrecorded/1 | success |
| evidence-lifecycle-v4-medium-strings | evidence-lifecycle-v4-medium | development | absl_replace_overlap_and_progress | published | 2 | unrecorded/1 | success |
| evidence-lifecycle-v4-medium-strings | evidence-lifecycle-v4-medium | development | absl_split_literal_and_chunk_boundaries | published | 1 | unrecorded/1 | success |
| evidence-lifecycle-v4-medium-strings | evidence-lifecycle-v4-medium | development | absl_base64_alphabet_contract | published | 2 | unrecorded/1 | success |
| evidence-lifecycle-v4-medium-systems | evidence-lifecycle-v4-medium | development | duration_negative_unit_rounding | published | 1 | unrecorded/1 | success |
| evidence-lifecycle-v4-medium-systems | evidence-lifecycle-v4-medium | development | duration_composite_parse_accumulator | published | 1 | unrecorded/1 | success |
| evidence-lifecycle-v4-medium-systems | evidence-lifecycle-v4-medium | development | duration_posix_negative_fraction_rounding | blocked | 2 | unrecorded/1 | model_proposal |
| evidence-lifecycle-v4-medium-systems | evidence-lifecycle-v4-medium | development | time_negative_unix_precision_floor | blocked | 2 | unrecorded/1 | native_tests |
| evidence-lifecycle-v4-medium-systems | evidence-lifecycle-v4-medium | development | status_update_first_failure_contract | published | 1 | unrecorded/1 | success |
| evidence-lifecycle-v4-medium-systems | evidence-lifecycle-v4-medium | development | status_payload_clone_write_retention | published | 1 | unrecorded/1 | success |
| evidence-lifecycle-v4-medium-systems | evidence-lifecycle-v4-medium | development | status_lookup_conflict_dispatch | published | 1 | unrecorded/1 | success |
| evidence-lifecycle-v4-medium-systems | evidence-lifecycle-v4-medium | development | status_copy_on_write_mutation_boundary | blocked | 2 | unrecorded/1 | native_tests |
| evidence-lifecycle-v4-high-fmt | evidence-lifecycle-v4-high | development | fmt_utf8_validation_boundaries | published | 1 | unrecorded/1 | success |
| evidence-lifecycle-v4-high-fmt | evidence-lifecycle-v4-high | development | fmt_debug_control_escapes | published | 1 | unrecorded/1 | success |
| evidence-lifecycle-v4-high-fmt | evidence-lifecycle-v4-high | development | fmt_printf_dynamic_field_sign | published | 2 | unrecorded/1 | success |
| evidence-lifecycle-v4-high-fmt | evidence-lifecycle-v4-high | development | fmt_integer_precision_padding | published | 2 | unrecorded/1 | success |
| evidence-lifecycle-v4-high-fmt | evidence-lifecycle-v4-high | development | fmt_pre_epoch_fraction_normalization | blocked | 2 | unrecorded/1 | native_tests |
| evidence-lifecycle-v4-high-fmt | evidence-lifecycle-v4-high | development | fmt_diagnostic_fallback_capacity | published | 1 | unrecorded/1 | success |
| evidence-lifecycle-v4-high-strings | evidence-lifecycle-v4-high | development | absl_escape_byte_overflow | published | 1 | unrecorded/1 | success |
| evidence-lifecycle-v4-high-strings | evidence-lifecycle-v4-high | development | absl_escape_hex_continuation | published | 1 | unrecorded/1 | success |
| evidence-lifecycle-v4-high-strings | evidence-lifecycle-v4-high | development | absl_base64_tail_codec | blocked | 2 | unrecorded/1 | model_proposal |
| evidence-lifecycle-v4-high-strings | evidence-lifecycle-v4-high | development | absl_base64_optional_padding_whitespace | blocked | 2 | unrecorded/1 | model_proposal |
| evidence-lifecycle-v4-high-strings | evidence-lifecycle-v4-high | development | absl_integer_bare_prefixes | blocked | 2 | unrecorded/1 | native_tests |
| evidence-lifecycle-v4-high-strings | evidence-lifecycle-v4-high | development | absl_integer_partial_results | published | 1 | unrecorded/1 | success |
| evidence-lifecycle-v4-high-strings | evidence-lifecycle-v4-high | development | absl_integer_signed_boundaries | published | 1 | unrecorded/1 | success |
| evidence-lifecycle-v4-high-strings | evidence-lifecycle-v4-high | development | absl_replace_overlap_and_progress | published | 2 | unrecorded/1 | success |
| evidence-lifecycle-v4-high-strings | evidence-lifecycle-v4-high | development | absl_split_literal_and_chunk_boundaries | published | 1 | unrecorded/1 | success |
| evidence-lifecycle-v4-high-strings | evidence-lifecycle-v4-high | development | absl_base64_alphabet_contract | published | 1 | unrecorded/1 | success |
| evidence-lifecycle-v4-high-systems | evidence-lifecycle-v4-high | development | duration_negative_unit_rounding | published | 1 | unrecorded/1 | success |
| evidence-lifecycle-v4-high-systems | evidence-lifecycle-v4-high | development | duration_composite_parse_accumulator | published | 1 | unrecorded/1 | success |
| evidence-lifecycle-v4-high-systems | evidence-lifecycle-v4-high | development | duration_posix_negative_fraction_rounding | published | 1 | unrecorded/1 | success |
| evidence-lifecycle-v4-high-systems | evidence-lifecycle-v4-high | development | time_negative_unix_precision_floor | published | 1 | unrecorded/1 | success |
| evidence-lifecycle-v4-high-systems | evidence-lifecycle-v4-high | development | status_update_first_failure_contract | published | 1 | unrecorded/1 | success |
| evidence-lifecycle-v4-high-systems | evidence-lifecycle-v4-high | development | status_payload_clone_write_retention | published | 2 | unrecorded/1 | success |
| evidence-lifecycle-v4-high-systems | evidence-lifecycle-v4-high | development | status_lookup_conflict_dispatch | published | 1 | unrecorded/1 | success |
| evidence-lifecycle-v4-high-systems | evidence-lifecycle-v4-high | development | status_copy_on_write_mutation_boundary | published | 1 | unrecorded/1 | success |
| source-budget-v5-high-fmt | source-budget-v5-high | development | fmt_utf8_validation_boundaries | published | 1 | unrecorded/1 | success |
| source-budget-v5-high-fmt | source-budget-v5-high | development | fmt_debug_control_escapes | published | 1 | unrecorded/1 | success |
| source-budget-v5-high-fmt | source-budget-v5-high | development | fmt_printf_dynamic_field_sign | published | 1 | unrecorded/1 | success |
| source-budget-v5-high-fmt | source-budget-v5-high | development | fmt_integer_precision_padding | published | 1 | unrecorded/1 | success |
| source-budget-v5-high-fmt | source-budget-v5-high | development | fmt_pre_epoch_fraction_normalization | published | 1 | unrecorded/1 | success |
| source-budget-v5-high-fmt | source-budget-v5-high | development | fmt_diagnostic_fallback_capacity | published | 1 | unrecorded/1 | success |
| source-definitions-v5-high-fmt | source-definitions-v5-high | development | fmt_utf8_validation_boundaries | published | 1 | unrecorded/1 | success |
| source-definitions-v5-high-fmt | source-definitions-v5-high | development | fmt_debug_control_escapes | published | 1 | unrecorded/1 | success |
| source-definitions-v5-high-fmt | source-definitions-v5-high | development | fmt_printf_dynamic_field_sign | published | 1 | unrecorded/1 | success |
| source-definitions-v5-high-fmt | source-definitions-v5-high | development | fmt_integer_precision_padding | published | 1 | unrecorded/1 | success |
| source-definitions-v5-high-fmt | source-definitions-v5-high | development | fmt_pre_epoch_fraction_normalization | published | 1 | unrecorded/1 | success |
| source-definitions-v5-high-fmt | source-definitions-v5-high | development | fmt_diagnostic_fallback_capacity | published | 1 | unrecorded/1 | success |
| source-definitions-v5-adaptive-high-fmt | source-definitions-v5-adaptive-high | development | fmt_utf8_validation_boundaries | published | 1 | unrecorded/1 | success |
| source-definitions-v5-adaptive-high-fmt | source-definitions-v5-adaptive-high | development | fmt_debug_control_escapes | published | 1 | unrecorded/1 | success |
| source-definitions-v5-adaptive-high-fmt | source-definitions-v5-adaptive-high | development | fmt_printf_dynamic_field_sign | published | 1 | unrecorded/1 | success |
| source-definitions-v5-adaptive-high-fmt | source-definitions-v5-adaptive-high | development | fmt_integer_precision_padding | published | 1 | unrecorded/1 | success |
| source-definitions-v5-adaptive-high-fmt | source-definitions-v5-adaptive-high | development | fmt_pre_epoch_fraction_normalization | published | 1 | unrecorded/1 | success |
| source-definitions-v5-adaptive-high-fmt | source-definitions-v5-adaptive-high | development | fmt_diagnostic_fallback_capacity | published | 3 | unrecorded/1 | success |
| source-budget-v5-high-strings | source-budget-v5-high | development | absl_escape_byte_overflow | published | 2 | unrecorded/1 | success |
| source-budget-v5-high-strings | source-budget-v5-high | development | absl_escape_hex_continuation | published | 1 | unrecorded/1 | success |
| source-budget-v5-high-strings | source-budget-v5-high | development | absl_base64_tail_codec | blocked | 2 | unrecorded/1 | native_tests |
| source-budget-v5-high-strings | source-budget-v5-high | development | absl_base64_optional_padding_whitespace | published | 1 | unrecorded/1 | success |
| source-budget-v5-high-strings | source-budget-v5-high | development | absl_integer_bare_prefixes | blocked | 2 | unrecorded/1 | native_tests |
| source-budget-v5-high-strings | source-budget-v5-high | development | absl_integer_partial_results | published | 1 | unrecorded/1 | success |
| source-budget-v5-high-strings | source-budget-v5-high | development | absl_integer_signed_boundaries | published | 1 | unrecorded/1 | success |
| source-budget-v5-high-strings | source-budget-v5-high | development | absl_replace_overlap_and_progress | published | 2 | unrecorded/1 | success |
| source-budget-v5-high-strings | source-budget-v5-high | development | absl_split_literal_and_chunk_boundaries | published | 1 | unrecorded/1 | success |
| source-budget-v5-high-strings | source-budget-v5-high | development | absl_base64_alphabet_contract | published | 1 | unrecorded/1 | success |
| source-definitions-v5-high-strings | source-definitions-v5-high | development | absl_escape_byte_overflow | published | 1 | unrecorded/1 | success |
| source-definitions-v5-high-strings | source-definitions-v5-high | development | absl_escape_hex_continuation | published | 1 | unrecorded/1 | success |
| source-definitions-v5-high-strings | source-definitions-v5-high | development | absl_base64_tail_codec | published | 1 | unrecorded/1 | success |
| source-definitions-v5-high-strings | source-definitions-v5-high | development | absl_base64_optional_padding_whitespace | published | 1 | unrecorded/1 | success |
| source-definitions-v5-high-strings | source-definitions-v5-high | development | absl_integer_bare_prefixes | published | 2 | unrecorded/1 | success |
| source-definitions-v5-high-strings | source-definitions-v5-high | development | absl_integer_partial_results | published | 1 | unrecorded/1 | success |
| source-definitions-v5-high-strings | source-definitions-v5-high | development | absl_integer_signed_boundaries | published | 1 | unrecorded/1 | success |
| source-definitions-v5-high-strings | source-definitions-v5-high | development | absl_replace_overlap_and_progress | published | 2 | unrecorded/1 | success |
| source-definitions-v5-high-strings | source-definitions-v5-high | development | absl_split_literal_and_chunk_boundaries | published | 1 | unrecorded/1 | success |
| source-definitions-v5-high-strings | source-definitions-v5-high | development | absl_base64_alphabet_contract | published | 1 | unrecorded/1 | success |
| source-definitions-v5-adaptive-high-strings | source-definitions-v5-adaptive-high | development | absl_escape_byte_overflow | published | 1 | unrecorded/1 | success |
| source-definitions-v5-adaptive-high-strings | source-definitions-v5-adaptive-high | development | absl_escape_hex_continuation | published | 1 | unrecorded/1 | success |
| source-definitions-v5-adaptive-high-strings | source-definitions-v5-adaptive-high | development | absl_base64_tail_codec | published | 1 | unrecorded/1 | success |
| source-definitions-v5-adaptive-high-strings | source-definitions-v5-adaptive-high | development | absl_base64_optional_padding_whitespace | published | 1 | unrecorded/1 | success |
| source-definitions-v5-adaptive-high-strings | source-definitions-v5-adaptive-high | development | absl_integer_bare_prefixes | published | 1 | unrecorded/1 | success |
| source-definitions-v5-adaptive-high-strings | source-definitions-v5-adaptive-high | development | absl_integer_partial_results | published | 1 | unrecorded/1 | success |
| source-definitions-v5-adaptive-high-strings | source-definitions-v5-adaptive-high | development | absl_integer_signed_boundaries | published | 1 | unrecorded/1 | success |
| source-definitions-v5-adaptive-high-strings | source-definitions-v5-adaptive-high | development | absl_replace_overlap_and_progress | published | 2 | unrecorded/1 | success |
| source-definitions-v5-adaptive-high-strings | source-definitions-v5-adaptive-high | development | absl_split_literal_and_chunk_boundaries | published | 1 | unrecorded/1 | success |
| source-definitions-v5-adaptive-high-strings | source-definitions-v5-adaptive-high | development | absl_base64_alphabet_contract | published | 1 | unrecorded/1 | success |
| source-budget-v5-high-systems | source-budget-v5-high | development | duration_negative_unit_rounding | published | 1 | unrecorded/1 | success |
| source-budget-v5-high-systems | source-budget-v5-high | development | duration_composite_parse_accumulator | published | 1 | unrecorded/1 | success |
| source-budget-v5-high-systems | source-budget-v5-high | development | duration_posix_negative_fraction_rounding | published | 1 | unrecorded/1 | success |
| source-budget-v5-high-systems | source-budget-v5-high | development | time_negative_unix_precision_floor | published | 2 | unrecorded/1 | success |
| source-budget-v5-high-systems | source-budget-v5-high | development | status_update_first_failure_contract | published | 1 | unrecorded/1 | success |
| source-budget-v5-high-systems | source-budget-v5-high | development | status_payload_clone_write_retention | published | 1 | unrecorded/1 | success |
| source-budget-v5-high-systems | source-budget-v5-high | development | status_lookup_conflict_dispatch | published | 1 | unrecorded/1 | success |
| source-budget-v5-high-systems | source-budget-v5-high | development | status_copy_on_write_mutation_boundary | published | 2 | unrecorded/1 | success |
| source-definitions-v5-high-systems | source-definitions-v5-high | development | duration_negative_unit_rounding | published | 2 | unrecorded/1 | success |
| source-definitions-v5-high-systems | source-definitions-v5-high | development | duration_composite_parse_accumulator | published | 1 | unrecorded/1 | success |
| source-definitions-v5-high-systems | source-definitions-v5-high | development | duration_posix_negative_fraction_rounding | published | 1 | unrecorded/1 | success |
| source-definitions-v5-high-systems | source-definitions-v5-high | development | time_negative_unix_precision_floor | published | 1 | unrecorded/1 | success |
| source-definitions-v5-high-systems | source-definitions-v5-high | development | status_update_first_failure_contract | published | 1 | unrecorded/1 | success |
| source-definitions-v5-high-systems | source-definitions-v5-high | development | status_payload_clone_write_retention | published | 1 | unrecorded/1 | success |
| source-definitions-v5-high-systems | source-definitions-v5-high | development | status_lookup_conflict_dispatch | published | 1 | unrecorded/1 | success |
| source-definitions-v5-high-systems | source-definitions-v5-high | development | status_copy_on_write_mutation_boundary | published | 1 | unrecorded/1 | success |
| source-definitions-v5-adaptive-high-systems | source-definitions-v5-adaptive-high | development | duration_negative_unit_rounding | published | 2 | unrecorded/1 | success |
| source-definitions-v5-adaptive-high-systems | source-definitions-v5-adaptive-high | development | duration_composite_parse_accumulator | published | 1 | unrecorded/1 | success |
| source-definitions-v5-adaptive-high-systems | source-definitions-v5-adaptive-high | development | duration_posix_negative_fraction_rounding | published | 1 | unrecorded/1 | success |
| source-definitions-v5-adaptive-high-systems | source-definitions-v5-adaptive-high | development | time_negative_unix_precision_floor | published | 1 | unrecorded/1 | success |
| source-definitions-v5-adaptive-high-systems | source-definitions-v5-adaptive-high | development | status_update_first_failure_contract | published | 1 | unrecorded/1 | success |
| source-definitions-v5-adaptive-high-systems | source-definitions-v5-adaptive-high | development | status_payload_clone_write_retention | published | 1 | unrecorded/1 | success |
| source-definitions-v5-adaptive-high-systems | source-definitions-v5-adaptive-high | development | status_lookup_conflict_dispatch | published | 1 | unrecorded/1 | success |
| source-definitions-v5-adaptive-high-systems | source-definitions-v5-adaptive-high | development | status_copy_on_write_mutation_boundary | published | 2 | unrecorded/1 | success |

## Aggregate arm results

| Arm | Trials | Native publications | First repair | Actual calls | Calls by kind | Known semantic false greens | Total trial seconds | Wilson95,24 distinct cases |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | --- |
| baseline | 24 | 7 | 5 | 33 | {"repair": 33} | 1 | 869.123 | [0.14914648196960875, 0.49167693664496637] |
| contract | 24 | 8 | 6 | 32 | {"repair": 32} | 1 | 850.48 | [0.1797219032729775, 0.5329368316186824] |
| evidence | 24 | 8 | 4 | 34 | {"repair": 34} | 1 | 891.335 | [0.1797219032729775, 0.5329368316186824] |
| source-definitions-v5-high | 24 | 24 | 21 | 73 | {"investigation": 46, "repair": 27} | 0 | 2860.863 | [0.8620237953250198, 1.0] |
| source-definitions-v5-adaptive-high | 24 | 24 | 20 | 78 | {"investigation": 49, "repair": 29} | 0 | 2964.537 | [0.8620237953250198, 1.0] |
| source-budget-v5-high | 24 | 22 | 18 | 81 | {"investigation": 51, "repair": 30} | 0 | 3022.854 | [0.741511978067893, 0.9768411847029567] |
| evidence-lifecycle-v4-high | 24 | 20 | 16 | 95 | {"investigation": 63, "repair": 32} | 2 | 3347.311 | [0.6414692935030095, 0.9332132367136705] |
| investigation-contract-v3 | 24 | 18 | 17 | 100 | {"investigation": 69, "repair": 31} | 1 | 3776.434 | [0.55100555994846, 0.8800063377140499] |
| investigation-evidence-v3 | 24 | 16 | 14 | 92 | {"investigation": 60, "repair": 32} | 1 | 3033.43 | [0.4670631683813174, 0.8202780967270225] |
| evidence-lifecycle-v4-medium | 24 | 15 | 11 | 107 | {"investigation": 70, "repair": 37} | 0 | 3747.634 | [0.42709962442674276, 0.7884063244045122] |
| investigation-baseline-v3 | 24 | 13 | 11 | 106 | {"investigation": 69, "repair": 37} | 0 | 2335.225 | [0.3507486535891948, 0.72108666268789] |
| structured-v3 | 24 | 7 | 6 | 42 | {"repair": 42} | 0 | 1202.393 | [0.14914648196960875, 0.49167693664496637] |

The original pure prompt arms are excluded from guarded selection. The preregistered guarded ranking selects **source-definitions-v5-high** for fresh V6 development confirmation. Actual calls include every failed call; output token counts are never a ranking tie-break. Latency is descriptive and confounded.

## Independent semantic annotations

| Arm | Case | Native-confirmed regression |
| --- | --- | --- |
| baseline | duration_negative_unit_rounding | Original native publication preserved; independent native counterexample |
| contract | duration_negative_unit_rounding | Original native publication preserved; independent native counterexample |
| evidence | duration_negative_unit_rounding | Original native publication preserved; independent native counterexample |
| evidence-lifecycle-v4-high | fmt_integer_precision_padding | Original native publication preserved; independent native counterexample |
| evidence-lifecycle-v4-high | fmt_printf_dynamic_field_sign | Original native publication preserved; independent native counterexample |
| investigation-contract-v3 | fmt_pre_epoch_fraction_normalization | Original native publication preserved; independent native counterexample |
| investigation-evidence-v3 | duration_negative_unit_rounding | Original native publication preserved; independent native counterexample |

V4-high and three V5 duration candidates have confirmed pinned-upstream compatibility differences at the minimum negative unit. Native contract probes support finite mathematical floor results; these are reported without claiming a contract violation. V5 escaping variants also strengthen rejection of oversized hex values while retaining valid decodings. These finite input checks are not additional model trials or unique defects.

## Full unsuccessful trials

Every unsuccessful trial below remains in the denominators, call totals and token totals. Full failure reasons are retained; original packets and native logs are in the release assets.

### baseline-fmt / fmt_utf8_validation_boundaries

Stage: `context_budget_before_model`; attempts: 1; calls: 0.

```text
Context exceeds configured model budget
```

### baseline-fmt / fmt_debug_control_escapes

Stage: `model_proposal`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Edit makes no change: include/fmt/format.h
```

### baseline-fmt / fmt_printf_dynamic_field_sign

Stage: `native_tests`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Expected old text exactly once in include/fmt/printf.h; found 0
```

### baseline-fmt / fmt_integer_precision_padding

Stage: `model_proposal`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Unsafe repository-relative path: ''
```

### baseline-fmt / fmt_pre_epoch_fraction_normalization

Stage: `native_tests`; attempts: 2; calls: 2.

```text
Repair budget exhausted:  (0 ms)
[ RUN      ] chrono_test.timestamp_sub_seconds
/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-prompts/jobs/baseline-fmt/run/fmt_pre_epoch_fraction_normalization/state/worktrees/tc-284765-9a8794455dc0/test/chrono-test.cc:869: Failure
Expected equality of these values:
  fmt::format("{:%S}", t5)
    Which is: "08.500000"
  "09"
/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-prompts/jobs/baseline-fmt/run/fmt_pre_epoch_fraction_normalization/state/worktrees/tc-284765-9a8794455dc0/test/chrono-test.cc:886: Failure
Expected equality of these values:
  fmt::format("{:%S}", t9)
    Which is: "01.500"
  "02.000"
/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-prompts/jobs/baseline-fmt/run/fmt_pre_epoch_fraction_normalization/state/worktrees/tc-284765-9a8794455dc0/test/chrono-test.cc:890: Failure
Expected equality of these values:
  fmt::format("{:%S}", epoch - d)
    Which is: "00.750"
  "59.750"
/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-prompts/jobs/baseline-fmt/run/fmt_pre_epoch_fraction_normalization/state/worktrees/tc-284765-9a8794455dc0/test/chrono-test.cc:891: Failure
Expected equality of these values:
  fmt::format("{:%S}", epoch)
    Which is: "59.500"
  "00.000"
[  FAILED  ] chrono_test.timestamp_sub_seconds (0 ms)
[ RUN      ] chrono_test.glibc_extensions
[       OK ] chrono_test.glibc_extensions (0 ms)
[ RUN      ] chrono_test.out_of_range
[       OK ] chrono_test.out_of_range (0 ms)
[ RUN      ] chrono_test.year_month_day
[       OK ] chrono_test.year_month_day (0 ms)
[----------] 35 tests from chrono_test (23 ms total)

[----------] Global test environment tear-down
[==========] 35 tests from 1 test suite ran. (23 ms total)
[  PASSED  ] 32 tests.
[  FAILED  ] 3 tests, listed below:
[  FAILED  ] chrono_test.tp_align
[  FAILED  ] chrono_test.timestamp_ratios
[  FAILED  ] chrono_test.timestamp_sub_seconds

 3 FAILED TESTS

Test command failed with exit code 1.
```

### baseline-fmt / fmt_diagnostic_fallback_capacity

Stage: `native_tests`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Path must be an existing worktree file: src/format-inl.h
```

### baseline-strings / absl_escape_byte_overflow

Stage: `model_proposal`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Edit makes no change: absl/strings/escaping.cc
```

### baseline-strings / absl_base64_tail_codec

Stage: `context_budget_before_model`; attempts: 1; calls: 0.

```text
Context exceeds configured model budget
```

### baseline-strings / absl_base64_optional_padding_whitespace

Stage: `context_budget_before_model`; attempts: 1; calls: 0.

```text
Context exceeds configured model budget
```

### baseline-strings / absl_integer_bare_prefixes

Stage: `model_proposal`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Edit makes no change: absl/strings/numbers.cc
```

### baseline-strings / absl_integer_partial_results

Stage: `model_proposal`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Expected old text exactly once in absl/strings/numbers.cc; found 0
```

### baseline-strings / absl_integer_signed_boundaries

Stage: `context_budget_before_model`; attempts: 1; calls: 0.

```text
Context exceeds configured model budget
```

### baseline-strings / absl_replace_overlap_and_progress

Stage: `native_tests`; attempts: 2; calls: 2.

```text
Repair budget exhausted: ess/state/worktrees/tc-284768-ddb2f133ee8c/absl/strings/str_replace_test.cc:311: Failure
Expected equality of these values:
  s
    Which is: "Abz;"
  "Ayz?"

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-prompts/jobs/baseline-strings/run/absl_replace_overlap_and_progress/state/worktrees/tc-284768-ddb2f133ee8c/absl/strings/str_replace_test.cc:316: Failure
Expected equality of these values:
  reps
    Which is: 3
  5

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-prompts/jobs/baseline-strings/run/absl_replace_overlap_and_progress/state/worktrees/tc-284768-ddb2f133ee8c/absl/strings/str_replace_test.cc:317: Failure
Expected equality of these values:
  s
    Which is: "aXXXXaXXXXxxx"
  "xxxXXXXxxxXXXXxxx"

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-prompts/jobs/baseline-strings/run/absl_replace_overlap_and_progress/state/worktrees/tc-284768-ddb2f133ee8c/absl/strings/str_replace_test.cc:343: Failure
Expected equality of these values:
  reps
    Which is: 1
  8

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-prompts/jobs/baseline-strings/run/absl_replace_overlap_and_progress/state/worktrees/tc-284768-ddb2f133ee8c/absl/strings/str_replace_test.cc:344: Failure
Expected equality of these values:
  s
    Which is: "the quick brown fox jumped over the lazy jugs"
  "pack my box with five dozen liquor jugs"

[  FAILED  ] StrReplaceAll.Inplace (0 ms)
[----------] 7 tests from StrReplaceAll (0 ms total)

[----------] Global test environment tear-down
[==========] 7 tests from 1 test suite ran. (0 ms total)
[  PASSED  ] 1 test.
[  FAILED  ] 6 tests, listed below:
[  FAILED  ] StrReplaceAll.ManyReplacements
[  FAILED  ] StrReplaceAll.ManyReplacementsInMap
[  FAILED  ] StrReplaceAll.ReplacementsInPlace
[  FAILED  ] StrReplaceAll.ReplacementsInPlaceInMap
[  FAILED  ] StrReplaceAll.VariableNumber
[  FAILED  ] StrReplaceAll.Inplace

 6 FAILED TESTS

Test command failed with exit code 1.
```

### baseline-strings / absl_base64_alphabet_contract

Stage: `context_budget_before_model`; attempts: 1; calls: 0.

```text
Context exceeds configured model budget
```

### baseline-systems / duration_posix_negative_fraction_rounding

Stage: `native_tests`; attempts: 2; calls: 2.

```text
Repair budget exhausted: [       OK ] ParseTime.NullErrorString (0 ms)
[ RUN      ] ParseTime.WithTimeZone
[       OK ] ParseTime.WithTimeZone (0 ms)
[ RUN      ] ParseTime.ErrorCases
[       OK ] ParseTime.ErrorCases (0 ms)
[ RUN      ] ParseTime.ExtendedSeconds
[       OK ] ParseTime.ExtendedSeconds (0 ms)
[ RUN      ] ParseTime.ExtendedOffsetErrors
[       OK ] ParseTime.ExtendedOffsetErrors (0 ms)
[ RUN      ] ParseTime.InfiniteTime
[       OK ] ParseTime.InfiniteTime (0 ms)
[ RUN      ] ParseTime.FailsOnUnrepresentableTime
[       OK ] ParseTime.FailsOnUnrepresentableTime (0 ms)
[----------] 8 tests from ParseTime (0 ms total)

[----------] 3 tests from FormatParse
[ RUN      ] FormatParse.RoundTrip
[       OK ] FormatParse.RoundTrip (0 ms)
[ RUN      ] FormatParse.RoundTripDistantFuture
[       OK ] FormatParse.RoundTripDistantFuture (0 ms)
[ RUN      ] FormatParse.RoundTripDistantPast
[       OK ] FormatParse.RoundTripDistantPast (0 ms)
[----------] 3 tests from FormatParse (0 ms total)

[----------] 8 tests from TimeZone
[ RUN      ] TimeZone.ValueSemantics
[       OK ] TimeZone.ValueSemantics (0 ms)
[ RUN      ] TimeZone.Equality
[       OK ] TimeZone.Equality (0 ms)
[ RUN      ] TimeZone.CCTZConversion
[       OK ] TimeZone.CCTZConversion (0 ms)
[ RUN      ] TimeZone.DefaultTimeZones
[       OK ] TimeZone.DefaultTimeZones (0 ms)
[ RUN      ] TimeZone.FixedTimeZone
[       OK ] TimeZone.FixedTimeZone (0 ms)
[ RUN      ] TimeZone.LocalTimeZone
[       OK ] TimeZone.LocalTimeZone (0 ms)
[ RUN      ] TimeZone.NamedTimeZones
[       OK ] TimeZone.NamedTimeZones (0 ms)
[ RUN      ] TimeZone.Failures
[       OK ] TimeZone.Failures (0 ms)
[----------] 8 tests from TimeZone (0 ms total)

[----------] Global test environment tear-down
[==========] 133 tests from 8 test suites ran. (5067 ms total)
[  PASSED  ] 131 tests.
[  FAILED  ] 2 tests, listed below:
[  FAILED  ] Duration.TruncConversions
[  FAILED  ] Duration.ConversionSaturation

 2 FAILED TESTS

Test command failed with exit code 1.
```

### baseline-systems / status_update_first_failure_contract

Stage: `native_tests`; attempts: 2; calls: 2.

```text
Repair budget exhausted:     ] Status.OstreamEqStringify
[       OK ] Status.OstreamEqStringify (0 ms)
[ RUN      ] Status.CopyOnWriteForErasePayload
[       OK ] Status.CopyOnWriteForErasePayload (0 ms)
[ RUN      ] Status.CopyConstructor
[       OK ] Status.CopyConstructor (0 ms)
[ RUN      ] Status.CopyAssignment
[       OK ] Status.CopyAssignment (0 ms)
[ RUN      ] Status.CopyAssignmentIsNotRef
[       OK ] Status.CopyAssignmentIsNotRef (0 ms)
[ RUN      ] Status.MoveConstructor
[       OK ] Status.MoveConstructor (0 ms)
[ RUN      ] Status.MoveAssignment
[       OK ] Status.MoveAssignment (0 ms)
[ RUN      ] Status.Update
/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-prompts/jobs/baseline-systems/run/status_update_first_failure_contract/state/worktrees/tc-284765-9256b301006f/absl/status/status_test.cc:515: Failure
Expected equality of these values:
  s
    Which is: INTERNAL: other message
  a
    Which is: CANCELLED: message

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-prompts/jobs/baseline-systems/run/status_update_first_failure_contract/state/worktrees/tc-284765-9256b301006f/absl/status/status_test.cc:517: Failure
Expected equality of these values:
  s
    Which is: INTERNAL: other message
  a
    Which is: CANCELLED: message

[  FAILED  ] Status.Update (0 ms)
[ RUN      ] Status.Equality
[       OK ] Status.Equality (0 ms)
[ RUN      ] Status.Swap
[       OK ] Status.Swap (0 ms)
[----------] 25 tests from Status (0 ms total)

[----------] 2 tests from StatusErrno
[ RUN      ] StatusErrno.ErrnoToStatusCode
[       OK ] StatusErrno.ErrnoToStatusCode (0 ms)
[ RUN      ] StatusErrno.ErrnoToStatus
[       OK ] StatusErrno.ErrnoToStatus (0 ms)
[----------] 2 tests from StatusErrno (0 ms total)

[----------] Global test environment tear-down
[==========] 28 tests from 3 test suites ran. (0 ms total)
[  PASSED  ] 27 tests.
[  FAILED  ] 1 test, listed below:
[  FAILED  ] Status.Update

 1 FAILED TEST

Test command failed with exit code 1.
```

### baseline-systems / status_copy_on_write_mutation_boundary

Stage: `native_tests`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Unsafe repository-relative path: ''
```

### evidence-fmt / fmt_utf8_validation_boundaries

Stage: `context_budget_before_model`; attempts: 1; calls: 0.

```text
Context exceeds configured model budget
```

### evidence-fmt / fmt_debug_control_escapes

Stage: `model_proposal`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Expected old text exactly once in include/fmt/format.h; found 0
```

### evidence-fmt / fmt_printf_dynamic_field_sign

Stage: `model_proposal`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Expected old text exactly once in include/fmt/printf.h; found 0
```

### evidence-fmt / fmt_integer_precision_padding

Stage: `model_proposal`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Expected old text exactly once in include/fmt/printf.h; found 0
```

### evidence-fmt / fmt_pre_epoch_fraction_normalization

Stage: `native_tests`; attempts: 2; calls: 2.

```text
Repair budget exhausted:  (0 ms)
[ RUN      ] chrono_test.timestamp_sub_seconds
/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-prompts/jobs/evidence-fmt/run/fmt_pre_epoch_fraction_normalization/state/worktrees/tc-284765-3eabf6436336/test/chrono-test.cc:869: Failure
Expected equality of these values:
  fmt::format("{:%S}", t5)
    Which is: "08.500000"
  "09"
/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-prompts/jobs/evidence-fmt/run/fmt_pre_epoch_fraction_normalization/state/worktrees/tc-284765-3eabf6436336/test/chrono-test.cc:886: Failure
Expected equality of these values:
  fmt::format("{:%S}", t9)
    Which is: "01.500"
  "02.000"
/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-prompts/jobs/evidence-fmt/run/fmt_pre_epoch_fraction_normalization/state/worktrees/tc-284765-3eabf6436336/test/chrono-test.cc:890: Failure
Expected equality of these values:
  fmt::format("{:%S}", epoch - d)
    Which is: "00.750"
  "59.750"
/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-prompts/jobs/evidence-fmt/run/fmt_pre_epoch_fraction_normalization/state/worktrees/tc-284765-3eabf6436336/test/chrono-test.cc:891: Failure
Expected equality of these values:
  fmt::format("{:%S}", epoch)
    Which is: "59.500"
  "00.000"
[  FAILED  ] chrono_test.timestamp_sub_seconds (0 ms)
[ RUN      ] chrono_test.glibc_extensions
[       OK ] chrono_test.glibc_extensions (0 ms)
[ RUN      ] chrono_test.out_of_range
[       OK ] chrono_test.out_of_range (0 ms)
[ RUN      ] chrono_test.year_month_day
[       OK ] chrono_test.year_month_day (0 ms)
[----------] 35 tests from chrono_test (22 ms total)

[----------] Global test environment tear-down
[==========] 35 tests from 1 test suite ran. (22 ms total)
[  PASSED  ] 32 tests.
[  FAILED  ] 3 tests, listed below:
[  FAILED  ] chrono_test.tp_align
[  FAILED  ] chrono_test.timestamp_ratios
[  FAILED  ] chrono_test.timestamp_sub_seconds

 3 FAILED TESTS

Test command failed with exit code 1.
```

### evidence-strings / absl_escape_byte_overflow

Stage: `model_proposal`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Expected old text exactly once in absl/strings/escaping.cc; found 0
```

### evidence-strings / absl_base64_tail_codec

Stage: `context_budget_before_model`; attempts: 1; calls: 0.

```text
Context exceeds configured model budget
```

### evidence-strings / absl_base64_optional_padding_whitespace

Stage: `context_budget_before_model`; attempts: 1; calls: 0.

```text
Context exceeds configured model budget
```

### evidence-strings / absl_integer_bare_prefixes

Stage: `model_proposal`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Edit makes no change: absl/strings/numbers.cc
```

### evidence-strings / absl_integer_partial_results

Stage: `model_proposal`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Edit makes no change: absl/strings/numbers.cc
```

### evidence-strings / absl_integer_signed_boundaries

Stage: `context_budget_before_model`; attempts: 1; calls: 0.

```text
Context exceeds configured model budget
```

### evidence-strings / absl_replace_overlap_and_progress

Stage: `native_tests`; attempts: 2; calls: 2.

```text
Repair budget exhausted: values:
  s
    Which is: "Ayz;"
  "Ayz?"

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-prompts/jobs/evidence-strings/run/absl_replace_overlap_and_progress/state/worktrees/tc-284768-56478964a8dc/absl/strings/str_replace_test.cc:322: Failure
Expected equality of these values:
  reps
    Which is: 3
  2

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-prompts/jobs/evidence-strings/run/absl_replace_overlap_and_progress/state/worktrees/tc-284768-56478964a8dc/absl/strings/str_replace_test.cc:323: Failure
Expected equality of these values:
  s
    Which is: "XXX"
  "xX"

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-prompts/jobs/evidence-strings/run/absl_replace_overlap_and_progress/state/worktrees/tc-284768-56478964a8dc/absl/strings/str_replace_test.cc:326: Failure
Expected equality of these values:
  reps
    Which is: 3
  2

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-prompts/jobs/evidence-strings/run/absl_replace_overlap_and_progress/state/worktrees/tc-284768-56478964a8dc/absl/strings/str_replace_test.cc:327: Failure
Expected equality of these values:
  s
    Which is: "XXX"
  "xX"

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-prompts/jobs/evidence-strings/run/absl_replace_overlap_and_progress/state/worktrees/tc-284768-56478964a8dc/absl/strings/str_replace_test.cc:344: Failure
Expected equality of these values:
  s
    Which is: "pack my box with five dozen pack lazy jugs"
  "pack my box with five dozen liquor jugs"

[  FAILED  ] StrReplaceAll.Inplace (0 ms)
[----------] 7 tests from StrReplaceAll (0 ms total)

[----------] Global test environment tear-down
[==========] 7 tests from 1 test suite ran. (0 ms total)
[  PASSED  ] 4 tests.
[  FAILED  ] 3 tests, listed below:
[  FAILED  ] StrReplaceAll.ManyReplacements
[  FAILED  ] StrReplaceAll.VariableNumber
[  FAILED  ] StrReplaceAll.Inplace

 3 FAILED TESTS

Test command failed with exit code 1.
```

### evidence-strings / absl_base64_alphabet_contract

Stage: `context_budget_before_model`; attempts: 1; calls: 0.

```text
Context exceeds configured model budget
```

### evidence-systems / duration_posix_negative_fraction_rounding

Stage: `native_tests`; attempts: 2; calls: 2.

```text
Repair budget exhausted: [       OK ] ParseTime.NullErrorString (0 ms)
[ RUN      ] ParseTime.WithTimeZone
[       OK ] ParseTime.WithTimeZone (0 ms)
[ RUN      ] ParseTime.ErrorCases
[       OK ] ParseTime.ErrorCases (0 ms)
[ RUN      ] ParseTime.ExtendedSeconds
[       OK ] ParseTime.ExtendedSeconds (0 ms)
[ RUN      ] ParseTime.ExtendedOffsetErrors
[       OK ] ParseTime.ExtendedOffsetErrors (0 ms)
[ RUN      ] ParseTime.InfiniteTime
[       OK ] ParseTime.InfiniteTime (0 ms)
[ RUN      ] ParseTime.FailsOnUnrepresentableTime
[       OK ] ParseTime.FailsOnUnrepresentableTime (0 ms)
[----------] 8 tests from ParseTime (0 ms total)

[----------] 3 tests from FormatParse
[ RUN      ] FormatParse.RoundTrip
[       OK ] FormatParse.RoundTrip (0 ms)
[ RUN      ] FormatParse.RoundTripDistantFuture
[       OK ] FormatParse.RoundTripDistantFuture (0 ms)
[ RUN      ] FormatParse.RoundTripDistantPast
[       OK ] FormatParse.RoundTripDistantPast (0 ms)
[----------] 3 tests from FormatParse (0 ms total)

[----------] 8 tests from TimeZone
[ RUN      ] TimeZone.ValueSemantics
[       OK ] TimeZone.ValueSemantics (0 ms)
[ RUN      ] TimeZone.Equality
[       OK ] TimeZone.Equality (0 ms)
[ RUN      ] TimeZone.CCTZConversion
[       OK ] TimeZone.CCTZConversion (0 ms)
[ RUN      ] TimeZone.DefaultTimeZones
[       OK ] TimeZone.DefaultTimeZones (0 ms)
[ RUN      ] TimeZone.FixedTimeZone
[       OK ] TimeZone.FixedTimeZone (0 ms)
[ RUN      ] TimeZone.LocalTimeZone
[       OK ] TimeZone.LocalTimeZone (0 ms)
[ RUN      ] TimeZone.NamedTimeZones
[       OK ] TimeZone.NamedTimeZones (0 ms)
[ RUN      ] TimeZone.Failures
[       OK ] TimeZone.Failures (0 ms)
[----------] 8 tests from TimeZone (0 ms total)

[----------] Global test environment tear-down
[==========] 133 tests from 8 test suites ran. (5067 ms total)
[  PASSED  ] 131 tests.
[  FAILED  ] 2 tests, listed below:
[  FAILED  ] Duration.TruncConversions
[  FAILED  ] Duration.ConversionSaturation

 2 FAILED TESTS

Test command failed with exit code 1.
```

### evidence-systems / time_negative_unix_precision_floor

Stage: `native_tests`; attempts: 2; calls: 2.

```text
Repair budget exhausted: ics (0 ms)
[ RUN      ] ParseTime.NullErrorString
[       OK ] ParseTime.NullErrorString (0 ms)
[ RUN      ] ParseTime.WithTimeZone
[       OK ] ParseTime.WithTimeZone (0 ms)
[ RUN      ] ParseTime.ErrorCases
[       OK ] ParseTime.ErrorCases (0 ms)
[ RUN      ] ParseTime.ExtendedSeconds
[       OK ] ParseTime.ExtendedSeconds (0 ms)
[ RUN      ] ParseTime.ExtendedOffsetErrors
[       OK ] ParseTime.ExtendedOffsetErrors (0 ms)
[ RUN      ] ParseTime.InfiniteTime
[       OK ] ParseTime.InfiniteTime (0 ms)
[ RUN      ] ParseTime.FailsOnUnrepresentableTime
[       OK ] ParseTime.FailsOnUnrepresentableTime (0 ms)
[----------] 8 tests from ParseTime (0 ms total)

[----------] 3 tests from FormatParse
[ RUN      ] FormatParse.RoundTrip
[       OK ] FormatParse.RoundTrip (0 ms)
[ RUN      ] FormatParse.RoundTripDistantFuture
[       OK ] FormatParse.RoundTripDistantFuture (0 ms)
[ RUN      ] FormatParse.RoundTripDistantPast
[       OK ] FormatParse.RoundTripDistantPast (0 ms)
[----------] 3 tests from FormatParse (0 ms total)

[----------] 8 tests from TimeZone
[ RUN      ] TimeZone.ValueSemantics
[       OK ] TimeZone.ValueSemantics (0 ms)
[ RUN      ] TimeZone.Equality
[       OK ] TimeZone.Equality (0 ms)
[ RUN      ] TimeZone.CCTZConversion
[       OK ] TimeZone.CCTZConversion (0 ms)
[ RUN      ] TimeZone.DefaultTimeZones
[       OK ] TimeZone.DefaultTimeZones (0 ms)
[ RUN      ] TimeZone.FixedTimeZone
[       OK ] TimeZone.FixedTimeZone (0 ms)
[ RUN      ] TimeZone.LocalTimeZone
[       OK ] TimeZone.LocalTimeZone (0 ms)
[ RUN      ] TimeZone.NamedTimeZones
[       OK ] TimeZone.NamedTimeZones (0 ms)
[ RUN      ] TimeZone.Failures
[       OK ] TimeZone.Failures (0 ms)
[----------] 8 tests from TimeZone (0 ms total)

[----------] Global test environment tear-down
[==========] 133 tests from 8 test suites ran. (5067 ms total)
[  PASSED  ] 132 tests.
[  FAILED  ] 1 test, listed below:
[  FAILED  ] Time.FloorConversion

 1 FAILED TEST

Test command failed with exit code 1.
```

### evidence-systems / status_copy_on_write_mutation_boundary

Stage: `native_tests`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Edit makes no change: absl/status/internal/status_internal.cc
```

### contract-fmt / fmt_utf8_validation_boundaries

Stage: `context_budget_before_model`; attempts: 1; calls: 0.

```text
Context exceeds configured model budget
```

### contract-fmt / fmt_debug_control_escapes

Stage: `model_proposal`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Edit makes no change: include/fmt/format.h
```

### contract-fmt / fmt_printf_dynamic_field_sign

Stage: `model_proposal`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Edit makes no change: include/fmt/printf.h
```

### contract-fmt / fmt_integer_precision_padding

Stage: `model_proposal`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Edit makes no change: include/fmt/format.h
```

### contract-fmt / fmt_pre_epoch_fraction_normalization

Stage: `native_tests`; attempts: 2; calls: 2.

```text
Repair budget exhausted: s: "00:00:00.623456789"
  "00:00:00.123456789"
/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-prompts/jobs/contract-fmt/run/fmt_pre_epoch_fraction_normalization/state/worktrees/tc-284765-2d35eb4bb261/test/chrono-test.cc:886: Failure
Expected equality of these values:
  fmt::format("{:%S}", t9)
    Which is: "02.500"
  "02.000"
/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-prompts/jobs/contract-fmt/run/fmt_pre_epoch_fraction_normalization/state/worktrees/tc-284765-2d35eb4bb261/test/chrono-test.cc:890: Failure
Expected equality of these values:
  fmt::format("{:%S}", epoch - d)
    Which is: "00.250"
  "59.750"
/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-prompts/jobs/contract-fmt/run/fmt_pre_epoch_fraction_normalization/state/worktrees/tc-284765-2d35eb4bb261/test/chrono-test.cc:891: Failure
Expected equality of these values:
  fmt::format("{:%S}", epoch)
    Which is: "00.500"
  "00.000"
/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-prompts/jobs/contract-fmt/run/fmt_pre_epoch_fraction_normalization/state/worktrees/tc-284765-2d35eb4bb261/test/chrono-test.cc:892: Failure
Expected equality of these values:
  fmt::format("{:%S}", epoch + d)
    Which is: "00.750"
  "00.250"
[  FAILED  ] chrono_test.timestamp_sub_seconds (0 ms)
[ RUN      ] chrono_test.glibc_extensions
[       OK ] chrono_test.glibc_extensions (0 ms)
[ RUN      ] chrono_test.out_of_range
[       OK ] chrono_test.out_of_range (0 ms)
[ RUN      ] chrono_test.year_month_day
[       OK ] chrono_test.year_month_day (0 ms)
[----------] 35 tests from chrono_test (22 ms total)

[----------] Global test environment tear-down
[==========] 35 tests from 1 test suite ran. (22 ms total)
[  PASSED  ] 32 tests.
[  FAILED  ] 3 tests, listed below:
[  FAILED  ] chrono_test.tp_align
[  FAILED  ] chrono_test.timestamp_ratios
[  FAILED  ] chrono_test.timestamp_sub_seconds

 3 FAILED TESTS

Test command failed with exit code 1.
```

### contract-strings / absl_escape_byte_overflow

Stage: `model_proposal`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Edit makes no change: absl/strings/escaping.cc
```

### contract-strings / absl_base64_tail_codec

Stage: `context_budget_before_model`; attempts: 1; calls: 0.

```text
Context exceeds configured model budget
```

### contract-strings / absl_base64_optional_padding_whitespace

Stage: `context_budget_before_model`; attempts: 1; calls: 0.

```text
Context exceeds configured model budget
```

### contract-strings / absl_integer_bare_prefixes

Stage: `model_proposal`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Edit makes no change: absl/strings/numbers.cc
```

### contract-strings / absl_integer_partial_results

Stage: `model_proposal`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Unsafe repository-relative path: ''
```

### contract-strings / absl_integer_signed_boundaries

Stage: `context_budget_before_model`; attempts: 1; calls: 0.

```text
Context exceeds configured model budget
```

### contract-strings / absl_base64_alphabet_contract

Stage: `context_budget_before_model`; attempts: 1; calls: 0.

```text
Context exceeds configured model budget
```

### contract-systems / duration_posix_negative_fraction_rounding

Stage: `native_tests`; attempts: 2; calls: 2.

```text
Repair budget exhausted: 0 ms)
[ RUN      ] ParseTime.NullErrorString
[       OK ] ParseTime.NullErrorString (0 ms)
[ RUN      ] ParseTime.WithTimeZone
[       OK ] ParseTime.WithTimeZone (0 ms)
[ RUN      ] ParseTime.ErrorCases
[       OK ] ParseTime.ErrorCases (0 ms)
[ RUN      ] ParseTime.ExtendedSeconds
[       OK ] ParseTime.ExtendedSeconds (0 ms)
[ RUN      ] ParseTime.ExtendedOffsetErrors
[       OK ] ParseTime.ExtendedOffsetErrors (0 ms)
[ RUN      ] ParseTime.InfiniteTime
[       OK ] ParseTime.InfiniteTime (0 ms)
[ RUN      ] ParseTime.FailsOnUnrepresentableTime
[       OK ] ParseTime.FailsOnUnrepresentableTime (0 ms)
[----------] 8 tests from ParseTime (0 ms total)

[----------] 3 tests from FormatParse
[ RUN      ] FormatParse.RoundTrip
[       OK ] FormatParse.RoundTrip (0 ms)
[ RUN      ] FormatParse.RoundTripDistantFuture
[       OK ] FormatParse.RoundTripDistantFuture (0 ms)
[ RUN      ] FormatParse.RoundTripDistantPast
[       OK ] FormatParse.RoundTripDistantPast (0 ms)
[----------] 3 tests from FormatParse (0 ms total)

[----------] 8 tests from TimeZone
[ RUN      ] TimeZone.ValueSemantics
[       OK ] TimeZone.ValueSemantics (0 ms)
[ RUN      ] TimeZone.Equality
[       OK ] TimeZone.Equality (0 ms)
[ RUN      ] TimeZone.CCTZConversion
[       OK ] TimeZone.CCTZConversion (0 ms)
[ RUN      ] TimeZone.DefaultTimeZones
[       OK ] TimeZone.DefaultTimeZones (0 ms)
[ RUN      ] TimeZone.FixedTimeZone
[       OK ] TimeZone.FixedTimeZone (0 ms)
[ RUN      ] TimeZone.LocalTimeZone
[       OK ] TimeZone.LocalTimeZone (0 ms)
[ RUN      ] TimeZone.NamedTimeZones
[       OK ] TimeZone.NamedTimeZones (0 ms)
[ RUN      ] TimeZone.Failures
[       OK ] TimeZone.Failures (0 ms)
[----------] 8 tests from TimeZone (0 ms total)

[----------] Global test environment tear-down
[==========] 133 tests from 8 test suites ran. (5061 ms total)
[  PASSED  ] 132 tests.
[  FAILED  ] 1 test, listed below:
[  FAILED  ] Duration.TruncConversions

 1 FAILED TEST

Test command failed with exit code 1.
```

### contract-systems / status_update_first_failure_contract

Stage: `native_tests`; attempts: 2; calls: 2.

```text
Repair budget exhausted:     ] Status.OstreamEqStringify
[       OK ] Status.OstreamEqStringify (0 ms)
[ RUN      ] Status.CopyOnWriteForErasePayload
[       OK ] Status.CopyOnWriteForErasePayload (0 ms)
[ RUN      ] Status.CopyConstructor
[       OK ] Status.CopyConstructor (0 ms)
[ RUN      ] Status.CopyAssignment
[       OK ] Status.CopyAssignment (0 ms)
[ RUN      ] Status.CopyAssignmentIsNotRef
[       OK ] Status.CopyAssignmentIsNotRef (0 ms)
[ RUN      ] Status.MoveConstructor
[       OK ] Status.MoveConstructor (0 ms)
[ RUN      ] Status.MoveAssignment
[       OK ] Status.MoveAssignment (0 ms)
[ RUN      ] Status.Update
/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-prompts/jobs/contract-systems/run/status_update_first_failure_contract/state/worktrees/tc-284765-bb31d39084d4/absl/status/status_test.cc:515: Failure
Expected equality of these values:
  s
    Which is: INTERNAL: other message
  a
    Which is: CANCELLED: message

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-prompts/jobs/contract-systems/run/status_update_first_failure_contract/state/worktrees/tc-284765-bb31d39084d4/absl/status/status_test.cc:517: Failure
Expected equality of these values:
  s
    Which is: INTERNAL: other message
  a
    Which is: CANCELLED: message

[  FAILED  ] Status.Update (0 ms)
[ RUN      ] Status.Equality
[       OK ] Status.Equality (0 ms)
[ RUN      ] Status.Swap
[       OK ] Status.Swap (0 ms)
[----------] 25 tests from Status (0 ms total)

[----------] 2 tests from StatusErrno
[ RUN      ] StatusErrno.ErrnoToStatusCode
[       OK ] StatusErrno.ErrnoToStatusCode (0 ms)
[ RUN      ] StatusErrno.ErrnoToStatus
[       OK ] StatusErrno.ErrnoToStatus (0 ms)
[----------] 2 tests from StatusErrno (0 ms total)

[----------] Global test environment tear-down
[==========] 28 tests from 3 test suites ran. (1 ms total)
[  PASSED  ] 27 tests.
[  FAILED  ] 1 test, listed below:
[  FAILED  ] Status.Update

 1 FAILED TEST

Test command failed with exit code 1.
```

### contract-systems / status_payload_clone_write_retention

Stage: `model_proposal`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Edit makes no change: absl/status/status.cc
```

### contract-systems / status_copy_on_write_mutation_boundary

Stage: `native_tests`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Edit makes no change: absl/status/internal/status_internal.cc
```

### structured-v3-fmt / fmt_debug_control_escapes

Stage: `model_proposal`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Expected old text exactly once in include/fmt/format.h; found 0
```

### structured-v3-fmt / fmt_printf_dynamic_field_sign

Stage: `model_proposal`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Edit makes no change: include/fmt/printf.h
```

### structured-v3-fmt / fmt_integer_precision_padding

Stage: `model_proposal`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Edit makes no change: include/fmt/format.h
```

### structured-v3-fmt / fmt_pre_epoch_fraction_normalization

Stage: `native_tests`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Expected old text exactly once in include/fmt/chrono.h; found 0
```

### structured-v3-fmt / fmt_diagnostic_fallback_capacity

Stage: `native_tests`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Expected old text exactly once in include/fmt/format-inl.h; found 0
```

### structured-v3-strings / absl_escape_byte_overflow

Stage: `model_proposal`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Edit makes no change: absl/strings/escaping.cc
```

### structured-v3-strings / absl_base64_tail_codec

Stage: `native_tests`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Expected old text exactly once in absl/strings/internal/escaping.cc; found 0
```

### structured-v3-strings / absl_integer_bare_prefixes

Stage: `model_proposal`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Edit makes no change: absl/strings/numbers.cc
```

### structured-v3-strings / absl_integer_partial_results

Stage: `model_proposal`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Edit makes no change: absl/strings/numbers.cc
```

### structured-v3-strings / absl_integer_signed_boundaries

Stage: `model_proposal`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Edit makes no change: absl/strings/numbers.cc
```

### structured-v3-strings / absl_base64_alphabet_contract

Stage: `native_tests`; attempts: 2; calls: 2.

```text
Repair budget exhausted: HVzdGVyOiB+MC41IG92ZXJoZWF0aW5nIH4xIFBEVSBmYWlsdXJlIH4xIHJhY2stbW92ZSB+MSBuZXR3b3JrIHJld2lyaW5nIH4yMCByYWNrIGZhaWx1cmVzIH41IHJhY2tzIGdvIHdvbmt5IH44IG5ldHdvcmsgbWFpbnRlbmFuY2VzIH4xMiByb3V0ZXIgcmVsb2FkcyB+MyByb3V0ZXIgZmFpbHVyZXMgfmRvemVucyBvZiBtaW5vciAzMC1zZWNvbmQgYmxpcHMgZm9yIGRucyB+MTAwMCBpbmRpdmlkdWFsIG1hY2hpbmUgZmFpbHVyZXMgfnRob3VzYW5kcyBvZiBoYXJkIGRyaXZlIGZhaWx1cmVzIHNsb3cgZGlza3MsIGJhZCBtZW1vcnksIG1pc2NvbmZpZ3VyZWQgbWFjaGluZXMsIGZsYWt5IG1hY2hpbmVzLCBldGMuIC0gSmVmZiBEZWFuLCBUaGUgSm95cyBvZiBSZWFsIEhhcmR3YXJlCg"
  tc.cyphertext
    Which is: "VHlwaWNhbCBmaXJzdCB5ZWFyIGZvciBhIG5ldyBjbHVzdGVyOiB-MC41IG92ZXJoZWF0aW5nIH4xIFBEVSBmYWlsdXJlIH4xIHJhY2stbW92ZSB-MSBuZXR3b3JrIHJld2lyaW5nIH4yMCByYWNrIGZhaWx1cmVzIH41IHJhY2tzIGdvIHdvbmt5IH44IG5ldHdvcmsgbWFpbnRlbmFuY2VzIH4xMiByb3V0ZXIgcmVsb2FkcyB-MyByb3V0ZXIgZmFpbHVyZXMgfmRvemVucyBvZiBtaW5vciAzMC1zZWNvbmQgYmxpcHMgZm9yIGRucyB-MTAwMCBpbmRpdmlkdWFsIG1hY2hpbmUgZmFpbHVyZXMgfnRob3VzYW5kcyBvZiBoYXJkIGRyaXZlIGZhaWx1cmVzIHNsb3cgZGlza3MsIGJhZCBtZW1vcnksIG1pc2NvbmZpZ3VyZWQgbWFjaGluZXMsIGZsYWt5IG1hY2hpbmVzLCBldGMuIC0gSmVmZiBEZWFuLCBUaGUgSm95cyBvZiBSZWFsIEhhcmR3YXJlCg"

[  FAILED  ] Base64.EscapeAndUnescape (2 ms)
[ RUN      ] Base64.Padding
[       OK ] Base64.Padding (0 ms)
[ DISABLED ] Base64.DISABLED_HugeData
[----------] 2 tests from Base64 (2 ms total)

[----------] 1 test from Escaping
[ RUN      ] Escaping.HexStringToBytesBackToHex
[       OK ] Escaping.HexStringToBytesBackToHex (0 ms)
[----------] 1 test from Escaping (0 ms total)

[----------] 1 test from HexAndBack
[ RUN      ] HexAndBack.HexStringToBytes_and_BytesToHexString
[       OK ] HexAndBack.HexStringToBytes_and_BytesToHexString (0 ms)
[----------] 1 test from HexAndBack (0 ms total)

[----------] Global test environment tear-down
[==========] 18 tests from 6 test suites ran. (3 ms total)
[  PASSED  ] 17 tests.
[  FAILED  ] 1 test, listed below:
[  FAILED  ] Base64.EscapeAndUnescape

 1 FAILED TEST
  YOU HAVE 1 DISABLED TEST


Test command (primary) failed with exit code 1.
```

### structured-v3-systems / duration_negative_unit_rounding

Stage: `native_tests`; attempts: 2; calls: 2.

```text
Repair budget exhausted: src/time_zone_impl.cc.o
[41/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time_zone.dir/internal/cctz/src/time_zone_libc.cc.o
[42/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time_zone.dir/internal/cctz/src/time_zone_posix.cc.o
[43/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time_zone.dir/internal/cctz/src/time_zone_lookup.cc.o
[44/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time_zone.dir/internal/cctz/src/time_zone_info.cc.o
[45/56] Linking CXX static library abseil/absl/strings/libabsl_strings.a
[46/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time_zone.dir/internal/cctz/src/zone_info_source.cc.o
[47/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time.dir/clock.cc.o
[48/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time.dir/civil_time.cc.o
[49/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time.dir/duration.cc.o
[50/56] Linking CXX static library abseil/absl/time/libabsl_civil_time.a
[51/56] Linking CXX static library abseil/absl/time/libabsl_time_zone.a
[52/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time.dir/format.cc.o
[53/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time.dir/time.cc.o
[54/56] Linking CXX static library abseil/absl/time/libabsl_time.a
[55/56] Building CXX object CMakeFiles/auto_fix_duration_min_unit.dir/probe.cc.o
[56/56] Linking CXX executable bin/auto_fix_duration_min_unit
Semantic probe command: ["/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-enriched-v3/jobs/structured-v3-systems/run/duration_negative_unit_rounding/state/worktrees/tc-284761-7184bcbc69e2/.auto-fix-build/semantic-probes/duration-min-unit/build/bin/auto_fix_duration_min_unit"]
AUTO_FIX_PROBE	InputFinite	PASS	-2562047788015215h30m8s
AUTO_FIX_PROBE	TruncExactMinimumUnit	PASS	-2562047788015215h30m8s
AUTO_FIX_PROBE	FloorExactMinimumUnit	FAIL	-inf
AUTO_FIX_PROBE	CeilExactMinimumUnit	FAIL	0

Test command (additional-1) failed with exit code 1.
```

### structured-v3-systems / duration_posix_negative_fraction_rounding

Stage: `native_tests`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Edit makes no change: absl/time/duration.cc
```

### structured-v3-systems / time_negative_unix_precision_floor

Stage: `native_tests`; attempts: 2; calls: 2.

```text
Repair budget exhausted: nal/cctz/src/time_zone_impl.cc.o
[41/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time_zone.dir/internal/cctz/src/time_zone_posix.cc.o
[42/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time_zone.dir/internal/cctz/src/time_zone_libc.cc.o
[43/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time_zone.dir/internal/cctz/src/time_zone_lookup.cc.o
[44/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time_zone.dir/internal/cctz/src/time_zone_info.cc.o
[45/56] Linking CXX static library abseil/absl/strings/libabsl_strings.a
[46/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time_zone.dir/internal/cctz/src/zone_info_source.cc.o
[47/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time.dir/clock.cc.o
[48/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time.dir/civil_time.cc.o
[49/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time.dir/duration.cc.o
[50/56] Linking CXX static library abseil/absl/time/libabsl_civil_time.a
[51/56] Linking CXX static library abseil/absl/time/libabsl_time_zone.a
[52/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time.dir/format.cc.o
[53/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time.dir/time.cc.o
[54/56] Linking CXX static library abseil/absl/time/libabsl_time.a
[55/56] Building CXX object CMakeFiles/auto_fix_duration_min_unit.dir/probe.cc.o
[56/56] Linking CXX executable bin/auto_fix_duration_min_unit
Semantic probe command: ["/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-enriched-v3/jobs/structured-v3-systems/run/time_negative_unix_precision_floor/state/worktrees/tc-284764-3c07e614f475/.auto-fix-build/semantic-probes/duration-min-unit/build/bin/auto_fix_duration_min_unit"]
AUTO_FIX_PROBE	InputFinite	PASS	-2562047788015215h30m8s
AUTO_FIX_PROBE	TruncExactMinimumUnit	PASS	-2562047788015215h30m8s
AUTO_FIX_PROBE	FloorExactMinimumUnit	PASS	-2562047788015215h30m8s
AUTO_FIX_PROBE	CeilExactMinimumUnit	PASS	-2562047788015215h30m8s

```

### structured-v3-systems / status_update_first_failure_contract

Stage: `native_tests`; attempts: 2; calls: 2.

```text
Repair budget exhausted: ify
[       OK ] Status.OstreamEqStringify (0 ms)
[ RUN      ] Status.CopyOnWriteForErasePayload
[       OK ] Status.CopyOnWriteForErasePayload (0 ms)
[ RUN      ] Status.CopyConstructor
[       OK ] Status.CopyConstructor (0 ms)
[ RUN      ] Status.CopyAssignment
[       OK ] Status.CopyAssignment (0 ms)
[ RUN      ] Status.CopyAssignmentIsNotRef
[       OK ] Status.CopyAssignmentIsNotRef (0 ms)
[ RUN      ] Status.MoveConstructor
[       OK ] Status.MoveConstructor (0 ms)
[ RUN      ] Status.MoveAssignment
[       OK ] Status.MoveAssignment (0 ms)
[ RUN      ] Status.Update
/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-enriched-v3/jobs/structured-v3-systems/run/status_update_first_failure_contract/state/worktrees/tc-284765-07e196331542/absl/status/status_test.cc:515: Failure
Expected equality of these values:
  s
    Which is: INTERNAL: other message
  a
    Which is: CANCELLED: message

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-enriched-v3/jobs/structured-v3-systems/run/status_update_first_failure_contract/state/worktrees/tc-284765-07e196331542/absl/status/status_test.cc:517: Failure
Expected equality of these values:
  s
    Which is: INTERNAL: other message
  a
    Which is: CANCELLED: message

[  FAILED  ] Status.Update (0 ms)
[ RUN      ] Status.Equality
[       OK ] Status.Equality (0 ms)
[ RUN      ] Status.Swap
[       OK ] Status.Swap (0 ms)
[----------] 25 tests from Status (0 ms total)

[----------] 2 tests from StatusErrno
[ RUN      ] StatusErrno.ErrnoToStatusCode
[       OK ] StatusErrno.ErrnoToStatusCode (0 ms)
[ RUN      ] StatusErrno.ErrnoToStatus
[       OK ] StatusErrno.ErrnoToStatus (0 ms)
[----------] 2 tests from StatusErrno (0 ms total)

[----------] Global test environment tear-down
[==========] 28 tests from 3 test suites ran. (0 ms total)
[  PASSED  ] 27 tests.
[  FAILED  ] 1 test, listed below:
[  FAILED  ] Status.Update

 1 FAILED TEST

Test command (primary) failed with exit code 1.
```

### structured-v3-systems / status_payload_clone_write_retention

Stage: `model_proposal`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Edit makes no change: absl/status/status.cc
```

### structured-v3-systems / status_copy_on_write_mutation_boundary

Stage: `native_tests`; attempts: 2; calls: 2.

```text
Repair budget exhausted: Edit makes no change: absl/status/status.h
```

### investigation-baseline-v3-fmt / fmt_printf_dynamic_field_sign

Stage: `model_proposal`; attempts: 2; calls: 5.

```text
Repair budget exhausted: Expected old text exactly once in include/fmt/printf.h; found 0
```

### investigation-baseline-v3-fmt / fmt_pre_epoch_fraction_normalization

Stage: `native_build`; attempts: 2; calls: 5.

```text
Repair budget exhausted: Expected old text exactly once in include/fmt/chrono.h; found 0
```

### investigation-baseline-v3-strings / absl_escape_byte_overflow

Stage: `model_proposal`; attempts: 2; calls: 5.

```text
Repair budget exhausted: Expected old text exactly once in absl/strings/escaping.cc; found 0
```

### investigation-baseline-v3-strings / absl_base64_tail_codec

Stage: `native_tests`; attempts: 2; calls: 5.

```text
Repair budget exhausted: Expected old text exactly once in absl/strings/internal/escaping.cc; found 0
```

### investigation-baseline-v3-strings / absl_integer_bare_prefixes

Stage: `model_proposal`; attempts: 2; calls: 5.

```text
Repair budget exhausted: Expected old text exactly once in absl/strings/numbers.cc; found 2
```

### investigation-baseline-v3-strings / absl_replace_overlap_and_progress

Stage: `native_tests`; attempts: 2; calls: 5.

```text
Repair budget exhausted: Expected old text exactly once in absl/strings/str_replace.cc; found 0
```

### investigation-baseline-v3-systems / duration_negative_unit_rounding

Stage: `native_tests`; attempts: 2; calls: 5.

```text
Repair budget exhausted: rnal/cctz/src/time_zone_impl.cc.o
[41/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time_zone.dir/internal/cctz/src/time_zone_libc.cc.o
[42/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time_zone.dir/internal/cctz/src/time_zone_posix.cc.o
[43/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time_zone.dir/internal/cctz/src/time_zone_lookup.cc.o
[44/56] Linking CXX static library abseil/absl/strings/libabsl_strings.a
[45/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time_zone.dir/internal/cctz/src/time_zone_info.cc.o
[46/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time_zone.dir/internal/cctz/src/zone_info_source.cc.o
[47/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time.dir/clock.cc.o
[48/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time.dir/civil_time.cc.o
[49/56] Linking CXX static library abseil/absl/time/libabsl_civil_time.a
[50/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time.dir/duration.cc.o
[51/56] Linking CXX static library abseil/absl/time/libabsl_time_zone.a
[52/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time.dir/format.cc.o
[53/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time.dir/time.cc.o
[54/56] Linking CXX static library abseil/absl/time/libabsl_time.a
[55/56] Building CXX object CMakeFiles/auto_fix_duration_min_unit.dir/probe.cc.o
[56/56] Linking CXX executable bin/auto_fix_duration_min_unit
Semantic probe command: ["/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-enriched-v3/jobs/investigation-baseline-v3-systems/run/duration_negative_unit_rounding/state/worktrees/tc-284761-57138516cdac/.auto-fix-build/semantic-probes/duration-min-unit/build/bin/auto_fix_duration_min_unit"]
AUTO_FIX_PROBE	InputFinite	PASS	-2562047788015215h30m8s
AUTO_FIX_PROBE	TruncExactMinimumUnit	FAIL	0
AUTO_FIX_PROBE	FloorExactMinimumUnit	FAIL	-inf
AUTO_FIX_PROBE	CeilExactMinimumUnit	FAIL	0

Test command (additional-1) failed with exit code 1.
```

### investigation-baseline-v3-systems / duration_posix_negative_fraction_rounding

Stage: `native_tests`; attempts: 2; calls: 5.

```text
Repair budget exhausted: Expected old text exactly once in absl/time/duration.cc; found 0
```

### investigation-baseline-v3-systems / time_negative_unix_precision_floor

Stage: `native_tests`; attempts: 2; calls: 5.

```text
Repair budget exhausted: Edit makes no change: absl/time/time.cc
```

### investigation-baseline-v3-systems / status_payload_clone_write_retention

Stage: `model_proposal`; attempts: 2; calls: 5.

```text
Repair budget exhausted: Edit makes no change: absl/status/internal/status_internal.h
```

### investigation-baseline-v3-systems / status_copy_on_write_mutation_boundary

Stage: `native_tests`; attempts: 2; calls: 5.

```text
Repair budget exhausted: Expected old text exactly once in absl/status/status.h; found 0
```

### investigation-evidence-v3-fmt / fmt_diagnostic_fallback_capacity

Stage: `native_tests`; attempts: 2; calls: 5.

```text
Repair budget exhausted: -1"
/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-enriched-v3/jobs/investigation-evidence-v3-fmt/run/fmt_diagnostic_fallback_capacity/state/worktrees/tc-284766-4190d9e9049f/test/format-impl-test.cc:238: Failure
Expected equality of these values:
  size
    Which is: 500
  buffer.size()
    Which is: 8
[  FAILED  ] format_impl_test.format_error_code (0 ms)
[ RUN      ] format_impl_test.count_digits
[       OK ] format_impl_test.count_digits (0 ms)
[ RUN      ] format_impl_test.countl_zero
[       OK ] format_impl_test.countl_zero (0 ms)
[ RUN      ] format_impl_test.write_double_double
[       OK ] format_impl_test.write_double_double (0 ms)
[ RUN      ] format_impl_test.write_dragon_even
[       OK ] format_impl_test.write_dragon_even (0 ms)
[ RUN      ] format_impl_test.utf8_decode_decode_all
[       OK ] format_impl_test.utf8_decode_decode_all (5 ms)
[ RUN      ] format_impl_test.utf8_decode_out_of_range
[       OK ] format_impl_test.utf8_decode_out_of_range (2 ms)
[ RUN      ] format_impl_test.utf8_decode_surrogate_halves
[       OK ] format_impl_test.utf8_decode_surrogate_halves (0 ms)
[ RUN      ] format_impl_test.utf8_decode_non_canonical_encodings
[       OK ] format_impl_test.utf8_decode_non_canonical_encodings (0 ms)
[ RUN      ] format_impl_test.utf8_decode_bogus_byte_sequences
[       OK ] format_impl_test.utf8_decode_bogus_byte_sequences (0 ms)
[ RUN      ] format_impl_test.to_utf8
[       OK ] format_impl_test.to_utf8 (0 ms)
[----------] 11 tests from format_impl_test (8 ms total)

[----------] 1 test from header_only_test
[ RUN      ] header_only_test.format
[       OK ] header_only_test.format (0 ms)
[----------] 1 test from header_only_test (0 ms total)

[----------] Global test environment tear-down
[==========] 26 tests from 4 test suites ran. (8 ms total)
[  PASSED  ] 25 tests.
[  FAILED  ] 1 test, listed below:
[  FAILED  ] format_impl_test.format_error_code

 1 FAILED TEST

Test command (primary) failed with exit code 1.
```

### investigation-evidence-v3-strings / absl_base64_tail_codec

Stage: `native_tests`; attempts: 2; calls: 5.

```text
Repair budget exhausted: ment-enriched-v3/jobs/investigation-evidence-v3-strings/run/absl_base64_tail_codec/state/worktrees/tc-284763-7171a45fa3e5/absl/strings/escaping_test.cc:651: Failure
Expected equality of these values:
  decoded
    Which is: "0"
  "a"

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-enriched-v3/jobs/investigation-evidence-v3-strings/run/absl_base64_tail_codec/state/worktrees/tc-284763-7171a45fa3e5/absl/strings/escaping_test.cc:654: Failure
Expected equality of these values:
  websafe_decoded
    Which is: "0"
  "a"

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-enriched-v3/jobs/investigation-evidence-v3-strings/run/absl_base64_tail_codec/state/worktrees/tc-284763-7171a45fa3e5/absl/strings/escaping_test.cc:651: Failure
Expected equality of these values:
  decoded
    Which is: "0"
  "a"

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-enriched-v3/jobs/investigation-evidence-v3-strings/run/absl_base64_tail_codec/state/worktrees/tc-284763-7171a45fa3e5/absl/strings/escaping_test.cc:654: Failure
Expected equality of these values:
  websafe_decoded
    Which is: "0"
  "a"

[  FAILED  ] Base64.Padding (0 ms)
[ DISABLED ] Base64.DISABLED_HugeData
[----------] 2 tests from Base64 (3 ms total)

[----------] 1 test from Escaping
[ RUN      ] Escaping.HexStringToBytesBackToHex
[       OK ] Escaping.HexStringToBytesBackToHex (0 ms)
[----------] 1 test from Escaping (0 ms total)

[----------] 1 test from HexAndBack
[ RUN      ] HexAndBack.HexStringToBytes_and_BytesToHexString
[       OK ] HexAndBack.HexStringToBytes_and_BytesToHexString (0 ms)
[----------] 1 test from HexAndBack (0 ms total)

[----------] Global test environment tear-down
[==========] 18 tests from 6 test suites ran. (5 ms total)
[  PASSED  ] 16 tests.
[  FAILED  ] 2 tests, listed below:
[  FAILED  ] Base64.EscapeAndUnescape
[  FAILED  ] Base64.Padding

 2 FAILED TESTS
  YOU HAVE 1 DISABLED TEST


Test command (primary) failed with exit code 1.
```

### investigation-evidence-v3-strings / absl_integer_bare_prefixes

Stage: `model_proposal`; attempts: 2; calls: 5.

```text
Repair budget exhausted: Edit makes no change: absl/strings/numbers.cc
```

### investigation-evidence-v3-strings / absl_integer_signed_boundaries

Stage: `baseline_reproduction`; attempts: 0; calls: 0.

```text
Corresponding TC test failures were not reproduced after rebase; check test_name_map or flaky tests
```

### investigation-evidence-v3-strings / absl_replace_overlap_and_progress

Stage: `native_tests`; attempts: 2; calls: 5.

```text
Repair budget exhausted: nriched-v3/jobs/investigation-evidence-v3-strings/run/absl_replace_overlap_and_progress/state/worktrees/tc-284768-692f5fbe9e4a/absl/strings/str_replace_test.cc:322: Failure
Expected equality of these values:
  reps
    Which is: 3
  2

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-enriched-v3/jobs/investigation-evidence-v3-strings/run/absl_replace_overlap_and_progress/state/worktrees/tc-284768-692f5fbe9e4a/absl/strings/str_replace_test.cc:323: Failure
Expected equality of these values:
  s
    Which is: "XXX"
  "xX"

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-enriched-v3/jobs/investigation-evidence-v3-strings/run/absl_replace_overlap_and_progress/state/worktrees/tc-284768-692f5fbe9e4a/absl/strings/str_replace_test.cc:326: Failure
Expected equality of these values:
  reps
    Which is: 3
  2

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-enriched-v3/jobs/investigation-evidence-v3-strings/run/absl_replace_overlap_and_progress/state/worktrees/tc-284768-692f5fbe9e4a/absl/strings/str_replace_test.cc:327: Failure
Expected equality of these values:
  s
    Which is: "XXX"
  "xX"

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-enriched-v3/jobs/investigation-evidence-v3-strings/run/absl_replace_overlap_and_progress/state/worktrees/tc-284768-692f5fbe9e4a/absl/strings/str_replace_test.cc:344: Failure
Expected equality of these values:
  s
    Which is: "pack my box with five dozen pack lazy jugs"
  "pack my box with five dozen liquor jugs"

[  FAILED  ] StrReplaceAll.Inplace (0 ms)
[----------] 7 tests from StrReplaceAll (0 ms total)

[----------] Global test environment tear-down
[==========] 7 tests from 1 test suite ran. (0 ms total)
[  PASSED  ] 4 tests.
[  FAILED  ] 3 tests, listed below:
[  FAILED  ] StrReplaceAll.ManyReplacements
[  FAILED  ] StrReplaceAll.VariableNumber
[  FAILED  ] StrReplaceAll.Inplace

 3 FAILED TESTS

Test command (primary) failed with exit code 1.
```

### investigation-evidence-v3-strings / absl_base64_alphabet_contract

Stage: `native_tests`; attempts: 2; calls: 5.

```text
Repair budget exhausted: Expected old text exactly once in absl/strings/escaping.cc; found 0
```

### investigation-evidence-v3-systems / duration_posix_negative_fraction_rounding

Stage: `native_tests`; attempts: 2; calls: 5.

```text
Repair budget exhausted: Expected old text exactly once in absl/time/duration.cc; found 0
```

### investigation-evidence-v3-systems / time_negative_unix_precision_floor

Stage: `native_tests`; attempts: 2; calls: 5.

```text
Repair budget exhausted: Expected old text exactly once in absl/time/time.cc; found 0
```

### investigation-contract-v3-fmt / fmt_integer_precision_padding

Stage: `native_tests`; attempts: 2; calls: 5.

```text
Repair budget exhausted: ion (0 ms)
[ RUN      ] printf_test.positional_width
[       OK ] printf_test.positional_width (0 ms)
[ RUN      ] printf_test.positional_precision
[       OK ] printf_test.positional_precision (0 ms)
[ RUN      ] printf_test.positional_width_and_precision
[       OK ] printf_test.positional_width_and_precision (0 ms)
[ RUN      ] printf_test.length
[       OK ] printf_test.length (0 ms)
[ RUN      ] printf_test.bool
[       OK ] printf_test.bool (0 ms)
[ RUN      ] printf_test.int
[       OK ] printf_test.int (0 ms)
[ RUN      ] printf_test.long_long
[       OK ] printf_test.long_long (0 ms)
[ RUN      ] printf_test.float
[       OK ] printf_test.float (0 ms)
[ RUN      ] printf_test.inf
[       OK ] printf_test.inf (0 ms)
[ RUN      ] printf_test.char
[       OK ] printf_test.char (0 ms)
[ RUN      ] printf_test.string
[       OK ] printf_test.string (0 ms)
[ RUN      ] printf_test.pointer
[       OK ] printf_test.pointer (0 ms)
[ RUN      ] printf_test.enum
[       OK ] printf_test.enum (0 ms)
[ RUN      ] printf_test.examples
[       OK ] printf_test.examples (0 ms)
[ RUN      ] printf_test.printf_error
[       OK ] printf_test.printf_error (0 ms)
[ RUN      ] printf_test.vprintf
[       OK ] printf_test.vprintf (0 ms)
[ RUN      ] printf_test.check_format_string_regression
[       OK ] printf_test.check_format_string_regression (0 ms)
[ RUN      ] printf_test.fixed_large_exponent
[       OK ] printf_test.fixed_large_exponent (0 ms)
[ RUN      ] printf_test.make_printf_args
[       OK ] printf_test.make_printf_args (0 ms)
[ RUN      ] printf_test.trailing_percent_non_nul_terminated
[       OK ] printf_test.trailing_percent_non_nul_terminated (0 ms)
[----------] 42 tests from printf_test (1 ms total)

[----------] Global test environment tear-down
[==========] 42 tests from 1 test suite ran. (1 ms total)
[  PASSED  ] 41 tests.
[  FAILED  ] 1 test, listed below:
[  FAILED  ] printf_test.int_precision

 1 FAILED TEST

Test command (primary) failed with exit code 1.
```

### investigation-contract-v3-fmt / fmt_diagnostic_fallback_capacity

Stage: `native_tests`; attempts: 2; calls: 5.

```text
Repair budget exhausted: -1"
/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-enriched-v3/jobs/investigation-contract-v3-fmt/run/fmt_diagnostic_fallback_capacity/state/worktrees/tc-284766-5bbe2724d10b/test/format-impl-test.cc:238: Failure
Expected equality of these values:
  size
    Which is: 500
  buffer.size()
    Which is: 8
[  FAILED  ] format_impl_test.format_error_code (0 ms)
[ RUN      ] format_impl_test.count_digits
[       OK ] format_impl_test.count_digits (0 ms)
[ RUN      ] format_impl_test.countl_zero
[       OK ] format_impl_test.countl_zero (0 ms)
[ RUN      ] format_impl_test.write_double_double
[       OK ] format_impl_test.write_double_double (0 ms)
[ RUN      ] format_impl_test.write_dragon_even
[       OK ] format_impl_test.write_dragon_even (0 ms)
[ RUN      ] format_impl_test.utf8_decode_decode_all
[       OK ] format_impl_test.utf8_decode_decode_all (5 ms)
[ RUN      ] format_impl_test.utf8_decode_out_of_range
[       OK ] format_impl_test.utf8_decode_out_of_range (2 ms)
[ RUN      ] format_impl_test.utf8_decode_surrogate_halves
[       OK ] format_impl_test.utf8_decode_surrogate_halves (0 ms)
[ RUN      ] format_impl_test.utf8_decode_non_canonical_encodings
[       OK ] format_impl_test.utf8_decode_non_canonical_encodings (0 ms)
[ RUN      ] format_impl_test.utf8_decode_bogus_byte_sequences
[       OK ] format_impl_test.utf8_decode_bogus_byte_sequences (0 ms)
[ RUN      ] format_impl_test.to_utf8
[       OK ] format_impl_test.to_utf8 (0 ms)
[----------] 11 tests from format_impl_test (8 ms total)

[----------] 1 test from header_only_test
[ RUN      ] header_only_test.format
[       OK ] header_only_test.format (0 ms)
[----------] 1 test from header_only_test (0 ms total)

[----------] Global test environment tear-down
[==========] 26 tests from 4 test suites ran. (8 ms total)
[  PASSED  ] 25 tests.
[  FAILED  ] 1 test, listed below:
[  FAILED  ] format_impl_test.format_error_code

 1 FAILED TEST

Test command (primary) failed with exit code 1.
```

### investigation-contract-v3-strings / absl_base64_tail_codec

Stage: `native_tests`; attempts: 2; calls: 5.

```text
Repair budget exhausted: Expected old text exactly once in absl/strings/internal/escaping.cc; found 0
```

### investigation-contract-v3-strings / absl_integer_bare_prefixes

Stage: `model_proposal`; attempts: 2; calls: 5.

```text
Repair budget exhausted: Expected old text exactly once in absl/strings/numbers.cc; found 2
```

### investigation-contract-v3-systems / time_negative_unix_precision_floor

Stage: `native_tests`; attempts: 2; calls: 5.

```text
Repair budget exhausted: /time_zone_impl.cc.o
[41/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time_zone.dir/internal/cctz/src/time_zone_libc.cc.o
[42/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time_zone.dir/internal/cctz/src/time_zone_posix.cc.o
[43/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time_zone.dir/internal/cctz/src/time_zone_lookup.cc.o
[44/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time_zone.dir/internal/cctz/src/time_zone_info.cc.o
[45/56] Linking CXX static library abseil/absl/strings/libabsl_strings.a
[46/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time_zone.dir/internal/cctz/src/zone_info_source.cc.o
[47/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time.dir/clock.cc.o
[48/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time.dir/civil_time.cc.o
[49/56] Linking CXX static library abseil/absl/time/libabsl_civil_time.a
[50/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time.dir/duration.cc.o
[51/56] Linking CXX static library abseil/absl/time/libabsl_time_zone.a
[52/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time.dir/format.cc.o
[53/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time.dir/time.cc.o
[54/56] Linking CXX static library abseil/absl/time/libabsl_time.a
[55/56] Building CXX object CMakeFiles/auto_fix_duration_min_unit.dir/probe.cc.o
[56/56] Linking CXX executable bin/auto_fix_duration_min_unit
Semantic probe command: ["/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-enriched-v3/jobs/investigation-contract-v3-systems/run/time_negative_unix_precision_floor/state/worktrees/tc-284764-7fa2cd82c765/.auto-fix-build/semantic-probes/duration-min-unit/build/bin/auto_fix_duration_min_unit"]
AUTO_FIX_PROBE	InputFinite	PASS	-2562047788015215h30m8s
AUTO_FIX_PROBE	TruncExactMinimumUnit	PASS	-2562047788015215h30m8s
AUTO_FIX_PROBE	FloorExactMinimumUnit	PASS	-2562047788015215h30m8s
AUTO_FIX_PROBE	CeilExactMinimumUnit	PASS	-2562047788015215h30m8s

```

### investigation-contract-v3-systems / status_copy_on_write_mutation_boundary

Stage: `native_tests`; attempts: 2; calls: 5.

```text
Repair budget exhausted: Expected old text exactly once in absl/status/status.h; found 0
```

### evidence-lifecycle-v4-medium-fmt / fmt_printf_dynamic_field_sign

Stage: `native_tests`; attempts: 2; calls: 6.

```text
Repair budget exhausted:  ms)
[ RUN      ] printf_test.bool
[       OK ] printf_test.bool (0 ms)
[ RUN      ] printf_test.int
[       OK ] printf_test.int (0 ms)
[ RUN      ] printf_test.long_long
[       OK ] printf_test.long_long (0 ms)
[ RUN      ] printf_test.float
[       OK ] printf_test.float (0 ms)
[ RUN      ] printf_test.inf
[       OK ] printf_test.inf (0 ms)
[ RUN      ] printf_test.char
[       OK ] printf_test.char (0 ms)
[ RUN      ] printf_test.string
[       OK ] printf_test.string (0 ms)
[ RUN      ] printf_test.pointer
[       OK ] printf_test.pointer (0 ms)
[ RUN      ] printf_test.enum
[       OK ] printf_test.enum (0 ms)
[ RUN      ] printf_test.examples
[       OK ] printf_test.examples (0 ms)
[ RUN      ] printf_test.printf_error
[       OK ] printf_test.printf_error (0 ms)
[ RUN      ] printf_test.vprintf
[       OK ] printf_test.vprintf (0 ms)
[ RUN      ] printf_test.check_format_string_regression
[       OK ] printf_test.check_format_string_regression (0 ms)
[ RUN      ] printf_test.fixed_large_exponent
/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-evidence-lifecycle-v4/jobs/evidence-lifecycle-v4-medium-fmt/run/fmt_printf_dynamic_field_sign/state/worktrees/tc-284763-9107b0a79de4/test/printf-test.cc:564: Failure
Expected equality of these values:
  "1000000000000000000000"
  fmt::sprintf("%.*f", -13, 1e21)
    Which is: "1000000000000000000000.000000"
[  FAILED  ] printf_test.fixed_large_exponent (0 ms)
[ RUN      ] printf_test.make_printf_args
[       OK ] printf_test.make_printf_args (0 ms)
[ RUN      ] printf_test.trailing_percent_non_nul_terminated
[       OK ] printf_test.trailing_percent_non_nul_terminated (0 ms)
[----------] 42 tests from printf_test (1 ms total)

[----------] Global test environment tear-down
[==========] 42 tests from 1 test suite ran. (1 ms total)
[  PASSED  ] 41 tests.
[  FAILED  ] 1 test, listed below:
[  FAILED  ] printf_test.fixed_large_exponent

 1 FAILED TEST

Test command (primary) failed with exit code 1.
```

### evidence-lifecycle-v4-medium-fmt / fmt_integer_precision_padding

Stage: `native_build`; attempts: 2; calls: 6.

```text
Repair budget exhausted: Expected old text exactly once in include/fmt/printf.h; found 0
```

### evidence-lifecycle-v4-medium-fmt / fmt_pre_epoch_fraction_normalization

Stage: `model_proposal`; attempts: 2; calls: 6.

```text
Repair budget exhausted: Expected old text exactly once in include/fmt/chrono.h; found 0
```

### evidence-lifecycle-v4-medium-strings / absl_base64_tail_codec

Stage: `model_proposal`; attempts: 2; calls: 6.

```text
Repair budget exhausted: Expected old text exactly once in absl/strings/internal/escaping.cc; found 0
```

### evidence-lifecycle-v4-medium-strings / absl_base64_optional_padding_whitespace

Stage: `native_tests`; attempts: 2; calls: 6.

```text
Repair budget exhausted: 8dbf0dc4e4/absl/strings/escaping_test.cc:650: Failure
Value of: absl::Base64Unescape(b64, &decoded)
  Actual: false
Expected: true

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-evidence-lifecycle-v4/jobs/evidence-lifecycle-v4-medium-strings/run/absl_base64_optional_padding_whitespace/state/worktrees/tc-284764-698dbf0dc4e4/absl/strings/escaping_test.cc:651: Failure
Expected equality of these values:
  decoded
    Which is: ""
  "a"

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-evidence-lifecycle-v4/jobs/evidence-lifecycle-v4-medium-strings/run/absl_base64_optional_padding_whitespace/state/worktrees/tc-284764-698dbf0dc4e4/absl/strings/escaping_test.cc:653: Failure
Value of: absl::WebSafeBase64Unescape(b64, &websafe_decoded)
  Actual: false
Expected: true

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-evidence-lifecycle-v4/jobs/evidence-lifecycle-v4-medium-strings/run/absl_base64_optional_padding_whitespace/state/worktrees/tc-284764-698dbf0dc4e4/absl/strings/escaping_test.cc:654: Failure
Expected equality of these values:
  websafe_decoded
    Which is: ""
  "a"

[  FAILED  ] Base64.Padding (0 ms)
[ DISABLED ] Base64.DISABLED_HugeData
[----------] 2 tests from Base64 (1 ms total)

[----------] 1 test from Escaping
[ RUN      ] Escaping.HexStringToBytesBackToHex
[       OK ] Escaping.HexStringToBytesBackToHex (0 ms)
[----------] 1 test from Escaping (0 ms total)

[----------] 1 test from HexAndBack
[ RUN      ] HexAndBack.HexStringToBytes_and_BytesToHexString
[       OK ] HexAndBack.HexStringToBytes_and_BytesToHexString (0 ms)
[----------] 1 test from HexAndBack (0 ms total)

[----------] Global test environment tear-down
[==========] 18 tests from 6 test suites ran. (3 ms total)
[  PASSED  ] 16 tests.
[  FAILED  ] 2 tests, listed below:
[  FAILED  ] Base64.EscapeAndUnescape
[  FAILED  ] Base64.Padding

 2 FAILED TESTS
  YOU HAVE 1 DISABLED TEST


Test command (primary) failed with exit code 1.
```

### evidence-lifecycle-v4-medium-strings / absl_integer_bare_prefixes

Stage: `model_proposal`; attempts: 2; calls: 6.

```text
Repair budget exhausted: Edit makes no change: absl/strings/numbers.cc
```

### evidence-lifecycle-v4-medium-systems / duration_posix_negative_fraction_rounding

Stage: `model_proposal`; attempts: 2; calls: 5.

```text
Repair budget exhausted: Edit makes no change: absl/time/duration.cc
```

### evidence-lifecycle-v4-medium-systems / time_negative_unix_precision_floor

Stage: `native_tests`; attempts: 2; calls: 6.

```text
Repair budget exhausted: pl.cc.o
[41/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time_zone.dir/internal/cctz/src/time_zone_libc.cc.o
[42/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time_zone.dir/internal/cctz/src/time_zone_posix.cc.o
[43/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time_zone.dir/internal/cctz/src/time_zone_lookup.cc.o
[44/56] Linking CXX static library abseil/absl/strings/libabsl_strings.a
[45/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time_zone.dir/internal/cctz/src/time_zone_info.cc.o
[46/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time_zone.dir/internal/cctz/src/zone_info_source.cc.o
[47/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time.dir/clock.cc.o
[48/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time.dir/civil_time.cc.o
[49/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time.dir/duration.cc.o
[50/56] Linking CXX static library abseil/absl/time/libabsl_civil_time.a
[51/56] Linking CXX static library abseil/absl/time/libabsl_time_zone.a
[52/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time.dir/format.cc.o
[53/56] Building CXX object abseil/absl/time/CMakeFiles/absl_time.dir/time.cc.o
[54/56] Linking CXX static library abseil/absl/time/libabsl_time.a
[55/56] Building CXX object CMakeFiles/auto_fix_duration_min_unit.dir/probe.cc.o
[56/56] Linking CXX executable bin/auto_fix_duration_min_unit
Semantic probe command: ["/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-evidence-lifecycle-v4/jobs/evidence-lifecycle-v4-medium-systems/run/time_negative_unix_precision_floor/state/worktrees/tc-284764-baa18f0cebb8/.auto-fix-build/semantic-probes/duration-min-unit/build/bin/auto_fix_duration_min_unit"]
AUTO_FIX_PROBE	InputFinite	PASS	-2562047788015215h30m8s
AUTO_FIX_PROBE	TruncExactMinimumUnit	PASS	-2562047788015215h30m8s
AUTO_FIX_PROBE	FloorExactMinimumUnit	PASS	-2562047788015215h30m8s
AUTO_FIX_PROBE	CeilExactMinimumUnit	PASS	-2562047788015215h30m8s

```

### evidence-lifecycle-v4-medium-systems / status_copy_on_write_mutation_boundary

Stage: `native_tests`; attempts: 2; calls: 6.

```text
Repair budget exhausted: Expected old text exactly once in absl/status/status.h; found 0
```

### evidence-lifecycle-v4-high-fmt / fmt_pre_epoch_fraction_normalization

Stage: `native_tests`; attempts: 2; calls: 6.

```text
Repair budget exhausted: valid_colons
[       OK ] chrono_test.invalid_colons (0 ms)
[ RUN      ] chrono_test.negative_durations
[       OK ] chrono_test.negative_durations (0 ms)
[ RUN      ] chrono_test.special_durations
[       OK ] chrono_test.special_durations (0 ms)
[ RUN      ] chrono_test.unsigned_duration
[       OK ] chrono_test.unsigned_duration (0 ms)
[ RUN      ] chrono_test.weekday
[       OK ] chrono_test.weekday (1 ms)
[ RUN      ] chrono_test.cpp20_duration_subsecond_support
[       OK ] chrono_test.cpp20_duration_subsecond_support (0 ms)
[ RUN      ] chrono_test.timestamp_ratios
[       OK ] chrono_test.timestamp_ratios (0 ms)
[ RUN      ] chrono_test.timestamp_sub_seconds
/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-evidence-lifecycle-v4/jobs/evidence-lifecycle-v4-high-fmt/run/fmt_pre_epoch_fraction_normalization/state/worktrees/tc-284765-1f8d11209236/test/chrono-test.cc:854: Failure
Expected equality of these values:
  fmt::format("{:%S}", t1)
    Which is: "02.000000"
  "01.333333"
/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-evidence-lifecycle-v4/jobs/evidence-lifecycle-v4-high-fmt/run/fmt_pre_epoch_fraction_normalization/state/worktrees/tc-284765-1f8d11209236/test/chrono-test.cc:865: Failure
Expected equality of these values:
  fmt::format("{:%S}", t4)
    Which is: "10"
  "09.500000"
[  FAILED  ] chrono_test.timestamp_sub_seconds (0 ms)
[ RUN      ] chrono_test.glibc_extensions
[       OK ] chrono_test.glibc_extensions (0 ms)
[ RUN      ] chrono_test.out_of_range
[       OK ] chrono_test.out_of_range (0 ms)
[ RUN      ] chrono_test.year_month_day
[       OK ] chrono_test.year_month_day (0 ms)
[----------] 35 tests from chrono_test (24 ms total)

[----------] Global test environment tear-down
[==========] 35 tests from 1 test suite ran. (24 ms total)
[  PASSED  ] 34 tests.
[  FAILED  ] 1 test, listed below:
[  FAILED  ] chrono_test.timestamp_sub_seconds

 1 FAILED TEST

Test command (primary) failed with exit code 1.
```

### evidence-lifecycle-v4-high-strings / absl_base64_tail_codec

Stage: `model_proposal`; attempts: 2; calls: 6.

```text
Repair budget exhausted: Unsafe repository-relative path: ''
```

### evidence-lifecycle-v4-high-strings / absl_base64_optional_padding_whitespace

Stage: `model_proposal`; attempts: 2; calls: 6.

```text
Repair budget exhausted: Unsafe repository-relative path: ''
```

### evidence-lifecycle-v4-high-strings / absl_integer_bare_prefixes

Stage: `native_tests`; attempts: 2; calls: 6.

```text
Repair budget exhausted: .status
    Which is: false
  status
    Which is: true
0x 0

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-evidence-lifecycle-v4/jobs/evidence-lifecycle-v4-high-strings/run/absl_integer_bare_prefixes/state/worktrees/tc-284765-b01f56a48d96/absl/strings/numbers_test.cc:2261: Failure
Expected equality of these values:
  line.status
    Which is: false
  status
    Which is: true
0x 16

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-evidence-lifecycle-v4/jobs/evidence-lifecycle-v4-high-strings/run/absl_integer_bare_prefixes/state/worktrees/tc-284765-b01f56a48d96/absl/strings/numbers_test.cc:2265: Failure
Expected equality of these values:
  line.status
    Which is: false
  status
    Which is: true
0x 16

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-evidence-lifecycle-v4/jobs/evidence-lifecycle-v4-high-strings/run/absl_integer_bare_prefixes/state/worktrees/tc-284765-b01f56a48d96/absl/strings/numbers_test.cc:2269: Failure
Expected equality of these values:
  line.status
    Which is: false
  status
    Which is: true
0x 16

[  FAILED  ] StrToUint64Base.PrefixOnly (0 ms)
[----------] 1 test from StrToUint64Base (0 ms total)

[----------] 1 test from FastHexToBufferZeroPad16
[ RUN      ] FastHexToBufferZeroPad16.Smoke
[       OK ] FastHexToBufferZeroPad16.Smoke (11 ms)
[----------] 1 test from FastHexToBufferZeroPad16 (11 ms total)

[----------] 1 test from FastIntToBuffer
[ RUN      ] FastIntToBuffer.WritesNull
[       OK ] FastIntToBuffer.WritesNull (0 ms)
[----------] 1 test from FastIntToBuffer (0 ms total)

[----------] Global test environment tear-down
[==========] 50 tests from 19 test suites ran. (1849 ms total)
[  PASSED  ] 46 tests.
[  FAILED  ] 4 tests, listed below:
[  FAILED  ] StrToInt32Base.PrefixOnly
[  FAILED  ] StrToUint32Base.PrefixOnly
[  FAILED  ] StrToInt64Base.PrefixOnly
[  FAILED  ] StrToUint64Base.PrefixOnly

 4 FAILED TESTS

Test command (primary) failed with exit code 1.
```

### source-budget-v5-high-strings / absl_base64_tail_codec

Stage: `native_tests`; attempts: 2; calls: 6.

```text
Repair budget exhausted: fix/.auto-fix/expanded-formal/development-source-context-v5/jobs/source-budget-v5-high-strings/run/absl_base64_tail_codec/state/worktrees/tc-284763-19d9a32fefa6/absl/strings/escaping_test.cc:610: Failure
Expected equality of these values:
  decoded
    Which is: "abcdefghijklmnopqrstu;;"
  tc.plaintext
    Which is: "abcdefghijklmnopqrstuvw"

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-source-context-v5/jobs/source-budget-v5-high-strings/run/absl_base64_tail_codec/state/worktrees/tc-284763-19d9a32fefa6/absl/strings/escaping_test.cc:586: Failure
Expected equality of these values:
  decoded
    Which is: "abcdefghijklmnopqrstuvwx<\xBD"
  tc.plaintext
    Which is: "abcdefghijklmnopqrstuvwxyz"

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-source-context-v5/jobs/source-budget-v5-high-strings/run/absl_base64_tail_codec/state/worktrees/tc-284763-19d9a32fefa6/absl/strings/escaping_test.cc:610: Failure
Expected equality of these values:
  decoded
    Which is: "abcdefghijklmnopqrstuvwx<\xBD"
  tc.plaintext
    Which is: "abcdefghijklmnopqrstuvwxyz"

[  FAILED  ] Base64.EscapeAndUnescape (1 ms)
[ RUN      ] Base64.Padding
[       OK ] Base64.Padding (0 ms)
[ DISABLED ] Base64.DISABLED_HugeData
[----------] 2 tests from Base64 (1 ms total)

[----------] 1 test from Escaping
[ RUN      ] Escaping.HexStringToBytesBackToHex
[       OK ] Escaping.HexStringToBytesBackToHex (0 ms)
[----------] 1 test from Escaping (0 ms total)

[----------] 1 test from HexAndBack
[ RUN      ] HexAndBack.HexStringToBytes_and_BytesToHexString
[       OK ] HexAndBack.HexStringToBytes_and_BytesToHexString (0 ms)
[----------] 1 test from HexAndBack (0 ms total)

[----------] Global test environment tear-down
[==========] 18 tests from 6 test suites ran. (2 ms total)
[  PASSED  ] 17 tests.
[  FAILED  ] 1 test, listed below:
[  FAILED  ] Base64.EscapeAndUnescape

 1 FAILED TEST
  YOU HAVE 1 DISABLED TEST


Test command (primary) failed with exit code 1.
```

### source-budget-v5-high-strings / absl_integer_bare_prefixes

Stage: `native_tests`; attempts: 2; calls: 6.

```text
Repair budget exhausted: ity of these values:
  line.status
    Which is: false
  status
    Which is: true
0x 0

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-source-context-v5/jobs/source-budget-v5-high-strings/run/absl_integer_bare_prefixes/state/worktrees/tc-284765-4f7b0ddd268f/absl/strings/numbers_test.cc:2261: Failure
Expected equality of these values:
  line.status
    Which is: false
  status
    Which is: true
0x 16

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-source-context-v5/jobs/source-budget-v5-high-strings/run/absl_integer_bare_prefixes/state/worktrees/tc-284765-4f7b0ddd268f/absl/strings/numbers_test.cc:2265: Failure
Expected equality of these values:
  line.status
    Which is: false
  status
    Which is: true
0x 16

/Users/antoine/projects/auto-fix/.auto-fix/expanded-formal/development-source-context-v5/jobs/source-budget-v5-high-strings/run/absl_integer_bare_prefixes/state/worktrees/tc-284765-4f7b0ddd268f/absl/strings/numbers_test.cc:2269: Failure
Expected equality of these values:
  line.status
    Which is: false
  status
    Which is: true
0x 16

[  FAILED  ] StrToUint64Base.PrefixOnly (0 ms)
[----------] 1 test from StrToUint64Base (0 ms total)

[----------] 1 test from FastHexToBufferZeroPad16
[ RUN      ] FastHexToBufferZeroPad16.Smoke
[       OK ] FastHexToBufferZeroPad16.Smoke (11 ms)
[----------] 1 test from FastHexToBufferZeroPad16 (11 ms total)

[----------] 1 test from FastIntToBuffer
[ RUN      ] FastIntToBuffer.WritesNull
[       OK ] FastIntToBuffer.WritesNull (0 ms)
[----------] 1 test from FastIntToBuffer (0 ms total)

[----------] Global test environment tear-down
[==========] 50 tests from 19 test suites ran. (1784 ms total)
[  PASSED  ] 46 tests.
[  FAILED  ] 4 tests, listed below:
[  FAILED  ] StrToInt32Base.PrefixOnly
[  FAILED  ] StrToUint32Base.PrefixOnly
[  FAILED  ] StrToInt64Base.PrefixOnly
[  FAILED  ] StrToUint64Base.PrefixOnly

 4 FAILED TESTS

Test command (primary) failed with exit code 1.
```

## Limits

- Every arm has24 distinct development defects;288 trials are not288 unique defects.
- Pure prompt arms use original selected upstream native suites without the later supplemental duration guard. V3/V4/V5 retain their own frozen guarded oracle. V6 stronger validation is a new confirmation cohort.
- Resources differ across arms: context, definitions, inspection and repair budgets and reasoning effort are explicit. No claim that cross-cohort improvement is caused by one component or uses equal inference/native cost.
- Latency is descriptive and confounded by concurrent scheduling/native builds/cache state.
- Independent source review and finite native probes do not prove universal semantic correctness.
- Full failed trials, reasons, actual calls, provider errors and all tokens remain counted. No model grader is used.

