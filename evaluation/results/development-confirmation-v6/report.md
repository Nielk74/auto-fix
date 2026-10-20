# GPT-6 Luna native evaluation report

Wilson 95% on the first completed listed trial per unique (project, case); repeats are separate, not independent cases.

No model grader or automatic arm selection. Incomplete trials are reported separately.

| Arm | Split | Project | Completed/planned | Fixes | First attempt | Unique | Repeats |
| --- | --- | --- | --- | --- | --- | --- | --- |
| selected-recipe-v6-confirmation | development | fmt | 6/6 | 5 | 5 | 6 | 0 |
| selected-recipe-v6-confirmation | development | abseil | 18/18 | 17 | 17 | 18 | 0 |

**selected-recipe-v6-confirmation / development / fmt**

Calls: `{"investigation": 13, "repair": 7}`. Tokens: `{"input_tokens": 833386, "cached_input_tokens": 251136, "cache_write_input_tokens": 0, "output_tokens": 19939, "reasoning_output_tokens": 14676}`. Wilson 95%: `[0.43649717781352987, 0.9699466302516935]`. Failure stages: `{"native_build": 1}`.
Observed baseline checks: 12.

**selected-recipe-v6-confirmation / development / abseil**

Calls: `{"investigation": 33, "repair": 19}`. Tokens: `{"input_tokens": 2180773, "cached_input_tokens": 644864, "cache_write_input_tokens": 0, "output_tokens": 35558, "reasoning_output_tokens": 23572}`. Wilson 95%: `[0.7424269921812741, 0.990124809021697]`. Failure stages: `{"native_tests": 1}`.
Observed baseline checks: 36.

| Run | Arm | Split | Case | Outcome | Attempts | Baselines observed/requested | Failed stage |
| --- | --- | --- | --- | --- | --- | --- | --- |
| confirmation-v6-fmt | selected-recipe-v6-confirmation | development | fmt_utf8_validation_boundaries | published | 1 | 2/2 | success |
| confirmation-v6-fmt | selected-recipe-v6-confirmation | development | fmt_debug_control_escapes | published | 1 | 2/2 | success |
| confirmation-v6-fmt | selected-recipe-v6-confirmation | development | fmt_printf_dynamic_field_sign | published | 1 | 2/2 | success |
| confirmation-v6-fmt | selected-recipe-v6-confirmation | development | fmt_integer_precision_padding | published | 1 | 2/2 | success |
| confirmation-v6-fmt | selected-recipe-v6-confirmation | development | fmt_pre_epoch_fraction_normalization | blocked | 2 | 2/2 | native_build |
| confirmation-v6-fmt | selected-recipe-v6-confirmation | development | fmt_diagnostic_fallback_capacity | published | 1 | 2/2 | success |
| confirmation-v6-strings | selected-recipe-v6-confirmation | development | absl_escape_byte_overflow | published | 1 | 2/2 | success |
| confirmation-v6-strings | selected-recipe-v6-confirmation | development | absl_escape_hex_continuation | published | 1 | 2/2 | success |
| confirmation-v6-strings | selected-recipe-v6-confirmation | development | absl_base64_tail_codec | published | 1 | 2/2 | success |
| confirmation-v6-strings | selected-recipe-v6-confirmation | development | absl_base64_optional_padding_whitespace | published | 1 | 2/2 | success |
| confirmation-v6-strings | selected-recipe-v6-confirmation | development | absl_integer_bare_prefixes | blocked | 2 | 2/2 | native_tests |
| confirmation-v6-strings | selected-recipe-v6-confirmation | development | absl_integer_partial_results | published | 1 | 2/2 | success |
| confirmation-v6-strings | selected-recipe-v6-confirmation | development | absl_integer_signed_boundaries | published | 1 | 2/2 | success |
| confirmation-v6-strings | selected-recipe-v6-confirmation | development | absl_replace_overlap_and_progress | published | 1 | 2/2 | success |
| confirmation-v6-strings | selected-recipe-v6-confirmation | development | absl_split_literal_and_chunk_boundaries | published | 1 | 2/2 | success |
| confirmation-v6-strings | selected-recipe-v6-confirmation | development | absl_base64_alphabet_contract | published | 1 | 2/2 | success |
| confirmation-v6-systems | selected-recipe-v6-confirmation | development | duration_negative_unit_rounding | published | 1 | 2/2 | success |
| confirmation-v6-systems | selected-recipe-v6-confirmation | development | duration_composite_parse_accumulator | published | 1 | 2/2 | success |
| confirmation-v6-systems | selected-recipe-v6-confirmation | development | duration_posix_negative_fraction_rounding | published | 1 | 2/2 | success |
| confirmation-v6-systems | selected-recipe-v6-confirmation | development | time_negative_unix_precision_floor | published | 1 | 2/2 | success |
| confirmation-v6-systems | selected-recipe-v6-confirmation | development | status_update_first_failure_contract | published | 1 | 2/2 | success |
| confirmation-v6-systems | selected-recipe-v6-confirmation | development | status_payload_clone_write_retention | published | 1 | 2/2 | success |
| confirmation-v6-systems | selected-recipe-v6-confirmation | development | status_lookup_conflict_dispatch | published | 1 | 2/2 | success |
| confirmation-v6-systems | selected-recipe-v6-confirmation | development | status_copy_on_write_mutation_boundary | published | 1 | 2/2 | success |
