# Fresh V7 DEVELOPMENT comparison

72 fresh trials cover the same 24 synthetic development defects in three arms. No holdout outcomes or model grader are used.

The registered rank uses native publications without an independently confirmed functional contract regression, then every actual Luna call, measured trial latency, and arm ID. Raw native grades are preserved alongside semantic review. This functional review is not a general regression-free quality grade; the control refactor has a separately measured performance regression.

| Rank | Arm | Native publications | Confirmed false greens | Publications without confirmed functional contract regression | First repair publications | Calls | Trial seconds |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | assertion-grounded-v7 | 24/24 | 0 | 24/24 | 22/24; reviewed 22/24 | 70 | 1666.221 |
| 2 | expanded-budget-v7 | 24/24 | 0 | 24/24 | 20/24; reviewed 20/24 | 72 | 1647.713 |
| 3 | confirmation-budget-v7 | 23/24 | 0 | 23/24 | 18/24; reviewed 18/24 | 75 | 1729.475 |

`assertion-grounded-v7`: recipe `{"backend": "codex", "baseline_repetitions": 2, "context_chars": 160000, "definition_reads": true, "inspections_per_attempt": 2, "max_attempts": 4, "max_inspections": 6, "model": "gpt-6-luna", "profile": "focused", "prompt": "assertion-v4", "prompt_sha256": "4476f20128351696ff80169f895d2e011b8dbefd19a652a8e39e415e1b2c93d5", "reasoning_effort": "high", "structured_diagnostics": true}`; calls `{"investigation": 44, "repair": 26}`; return codes `{"0": 70}`; tokens `{"cache_write_input_tokens": 0, "cached_input_tokens": 921600, "input_tokens": 2908512, "output_tokens": 56304, "reasoning_output_tokens": 37609}`. Model-reaching trials: 24/24 (descriptive only); pre-model nonpublications retained: 0.


`expanded-budget-v7`: recipe `{"backend": "codex", "baseline_repetitions": 2, "context_chars": 160000, "definition_reads": true, "inspections_per_attempt": 2, "max_attempts": 4, "max_inspections": 6, "model": "gpt-6-luna", "profile": "focused", "prompt": "contract-v3", "prompt_sha256": "34b980f105a63191f6e388221c600aba9e53dda9f257dbeaf7d6ad741cd927dd", "reasoning_effort": "high", "structured_diagnostics": true}`; calls `{"investigation": 44, "repair": 28}`; return codes `{"0": 72}`; tokens `{"cache_write_input_tokens": 0, "cached_input_tokens": 930432, "input_tokens": 2971846, "output_tokens": 51792, "reasoning_output_tokens": 35584}`. Model-reaching trials: 24/24 (descriptive only); pre-model nonpublications retained: 0.


`confirmation-budget-v7`: recipe `{"backend": "codex", "baseline_repetitions": 2, "context_chars": 160000, "definition_reads": true, "inspections_per_attempt": 2, "max_attempts": 2, "max_inspections": 4, "model": "gpt-6-luna", "profile": "focused", "prompt": "contract-v3", "prompt_sha256": "34b980f105a63191f6e388221c600aba9e53dda9f257dbeaf7d6ad741cd927dd", "reasoning_effort": "high", "structured_diagnostics": true}`; calls `{"investigation": 47, "repair": 28}`; return codes `{"0": 75}`; tokens `{"cache_write_input_tokens": 0, "cached_input_tokens": 979584, "input_tokens": 3129399, "output_tokens": 61373, "reasoning_output_tokens": 43195}`. Model-reaching trials: 23/24 (descriptive only); pre-model nonpublications retained: 1.

## Every trial

| Arm | Case | Native | Semantic review | Attempts | Inspections | Calls | Baselines |
| --- | --- | --- | --- | --- | --- | --- | --- |
| confirmation-budget-v7 | fmt_utf8_validation_boundaries | published | restores_pinned_upstream_source_exactly | 1 | 1 | 2 | 2/2 |
| confirmation-budget-v7 | fmt_debug_control_escapes | published | restores_pinned_upstream_source_exactly | 2 | 3 | 5 | 2/2 |
| confirmation-budget-v7 | fmt_printf_dynamic_field_sign | published | restores_pinned_upstream_source_exactly | 1 | 2 | 3 | 2/2 |
| confirmation-budget-v7 | fmt_integer_precision_padding | published | reviewed_equivalent_to_pinned_upstream | 1 | 2 | 3 | 2/2 |
| confirmation-budget-v7 | fmt_pre_epoch_fraction_normalization | published | reviewed_contract_consistent_extension | 1 | 2 | 3 | 2/2 |
| confirmation-budget-v7 | fmt_diagnostic_fallback_capacity | published | reviewed_equivalent_to_pinned_upstream | 1 | 1 | 2 | 2/2 |
| expanded-budget-v7 | fmt_utf8_validation_boundaries | published | reviewed_equivalent_to_pinned_upstream | 1 | 1 | 2 | 2/2 |
| expanded-budget-v7 | fmt_debug_control_escapes | published | restores_pinned_upstream_source_exactly | 1 | 2 | 3 | 2/2 |
| expanded-budget-v7 | fmt_printf_dynamic_field_sign | published | restores_pinned_upstream_source_exactly | 1 | 2 | 3 | 2/2 |
| expanded-budget-v7 | fmt_integer_precision_padding | published | restores_pinned_upstream_source_exactly | 1 | 2 | 3 | 2/2 |
| expanded-budget-v7 | fmt_pre_epoch_fraction_normalization | published | restores_pinned_upstream_source_exactly | 1 | 2 | 3 | 2/2 |
| expanded-budget-v7 | fmt_diagnostic_fallback_capacity | published | reviewed_equivalent_to_pinned_upstream | 1 | 1 | 2 | 2/2 |
| assertion-grounded-v7 | fmt_utf8_validation_boundaries | published | reviewed_equivalent_to_pinned_upstream | 1 | 1 | 2 | 2/2 |
| assertion-grounded-v7 | fmt_debug_control_escapes | published | restores_pinned_upstream_source_exactly | 1 | 2 | 3 | 2/2 |
| assertion-grounded-v7 | fmt_printf_dynamic_field_sign | published | restores_pinned_upstream_source_exactly | 1 | 2 | 3 | 2/2 |
| assertion-grounded-v7 | fmt_integer_precision_padding | published | restores_pinned_upstream_source_exactly | 1 | 2 | 3 | 2/2 |
| assertion-grounded-v7 | fmt_pre_epoch_fraction_normalization | published | restores_pinned_upstream_source_exactly | 1 | 2 | 3 | 2/2 |
| assertion-grounded-v7 | fmt_diagnostic_fallback_capacity | published | reviewed_equivalent_to_pinned_upstream | 1 | 1 | 2 | 2/2 |
| confirmation-budget-v7 | absl_escape_byte_overflow | published | reviewed_contract_consistent_extension | 1 | 2 | 3 | 2/2 |
| confirmation-budget-v7 | absl_escape_hex_continuation | published | restores_pinned_upstream_source_exactly | 1 | 2 | 3 | 2/2 |
| confirmation-budget-v7 | absl_base64_tail_codec | published | restores_pinned_upstream_source_exactly | 2 | 4 | 6 | 2/2 |
| confirmation-budget-v7 | absl_base64_optional_padding_whitespace | published | restores_pinned_upstream_source_exactly | 1 | 2 | 3 | 2/2 |
| confirmation-budget-v7 | absl_integer_bare_prefixes | published | reviewed_equivalent_to_pinned_upstream | 2 | 4 | 6 | 2/2 |
| confirmation-budget-v7 | absl_integer_partial_results | published | restores_pinned_upstream_source_exactly | 1 | 2 | 3 | 2/2 |
| confirmation-budget-v7 | absl_integer_signed_boundaries | blocked | not_published | 0 | 0 | 0 | 2/2 |
| confirmation-budget-v7 | absl_replace_overlap_and_progress | published | reviewed_contract_preserving_refactor | 2 | 3 | 5 | 2/2 |
| confirmation-budget-v7 | absl_split_literal_and_chunk_boundaries | published | restores_pinned_upstream_source_exactly | 1 | 1 | 2 | 2/2 |
| confirmation-budget-v7 | absl_base64_alphabet_contract | published | restores_pinned_upstream_source_exactly | 1 | 1 | 2 | 2/2 |
| expanded-budget-v7 | absl_escape_byte_overflow | published | reviewed_contract_consistent_extension | 1 | 2 | 3 | 2/2 |
| expanded-budget-v7 | absl_escape_hex_continuation | published | restores_pinned_upstream_source_exactly | 1 | 1 | 2 | 2/2 |
| expanded-budget-v7 | absl_base64_tail_codec | published | restores_pinned_upstream_source_exactly | 1 | 2 | 3 | 2/2 |
| expanded-budget-v7 | absl_base64_optional_padding_whitespace | published | restores_pinned_upstream_source_exactly | 1 | 2 | 3 | 2/2 |
| expanded-budget-v7 | absl_integer_bare_prefixes | published | reviewed_equivalent_to_pinned_upstream | 2 | 3 | 5 | 2/2 |
| expanded-budget-v7 | absl_integer_partial_results | published | restores_pinned_upstream_source_exactly | 1 | 2 | 3 | 2/2 |
| expanded-budget-v7 | absl_integer_signed_boundaries | published | restores_pinned_upstream_source_exactly | 1 | 2 | 3 | 2/2 |
| expanded-budget-v7 | absl_replace_overlap_and_progress | published | restores_pinned_upstream_source_exactly | 1 | 1 | 2 | 2/2 |
| expanded-budget-v7 | absl_split_literal_and_chunk_boundaries | published | restores_pinned_upstream_source_exactly | 1 | 1 | 2 | 2/2 |
| expanded-budget-v7 | absl_base64_alphabet_contract | published | restores_pinned_upstream_source_exactly | 1 | 2 | 3 | 2/2 |
| assertion-grounded-v7 | absl_escape_byte_overflow | published | reviewed_contract_consistent_extension | 1 | 2 | 3 | 2/2 |
| assertion-grounded-v7 | absl_escape_hex_continuation | published | restores_pinned_upstream_source_exactly | 1 | 2 | 3 | 2/2 |
| assertion-grounded-v7 | absl_base64_tail_codec | published | restores_pinned_upstream_source_exactly | 1 | 2 | 3 | 2/2 |
| assertion-grounded-v7 | absl_base64_optional_padding_whitespace | published | restores_pinned_upstream_source_exactly | 1 | 1 | 2 | 2/2 |
| assertion-grounded-v7 | absl_integer_bare_prefixes | published | reviewed_equivalent_to_pinned_upstream | 1 | 2 | 3 | 2/2 |
| assertion-grounded-v7 | absl_integer_partial_results | published | restores_pinned_upstream_source_exactly | 1 | 2 | 3 | 2/2 |
| assertion-grounded-v7 | absl_integer_signed_boundaries | published | restores_pinned_upstream_source_exactly | 1 | 2 | 3 | 2/2 |
| assertion-grounded-v7 | absl_replace_overlap_and_progress | published | restores_pinned_upstream_source_exactly | 2 | 3 | 5 | 2/2 |
| assertion-grounded-v7 | absl_split_literal_and_chunk_boundaries | published | restores_pinned_upstream_source_exactly | 2 | 2 | 4 | 2/2 |
| assertion-grounded-v7 | absl_base64_alphabet_contract | published | restores_pinned_upstream_source_exactly | 1 | 2 | 3 | 2/2 |
| confirmation-budget-v7 | duration_negative_unit_rounding | published | reviewed_contract_consistent_extension | 2 | 4 | 6 | 2/2 |
| confirmation-budget-v7 | duration_composite_parse_accumulator | published | restores_pinned_upstream_source_exactly | 1 | 1 | 2 | 2/2 |
| confirmation-budget-v7 | duration_posix_negative_fraction_rounding | published | reviewed_equivalent_to_pinned_upstream | 1 | 1 | 2 | 2/2 |
| confirmation-budget-v7 | time_negative_unix_precision_floor | published | reviewed_equivalent_to_pinned_upstream | 1 | 2 | 3 | 2/2 |
| confirmation-budget-v7 | status_update_first_failure_contract | published | reviewed_equivalent_to_pinned_upstream | 1 | 2 | 3 | 2/2 |
| confirmation-budget-v7 | status_payload_clone_write_retention | published | reviewed_equivalent_to_pinned_upstream | 1 | 2 | 3 | 2/2 |
| confirmation-budget-v7 | status_lookup_conflict_dispatch | published | restores_pinned_upstream_source_exactly | 1 | 1 | 2 | 2/2 |
| confirmation-budget-v7 | status_copy_on_write_mutation_boundary | published | restores_pinned_upstream_source_exactly | 1 | 2 | 3 | 2/2 |
| expanded-budget-v7 | duration_negative_unit_rounding | published | reviewed_contract_consistent_extension | 2 | 4 | 6 | 2/2 |
| expanded-budget-v7 | duration_composite_parse_accumulator | published | restores_pinned_upstream_source_exactly | 1 | 1 | 2 | 2/2 |
| expanded-budget-v7 | duration_posix_negative_fraction_rounding | published | reviewed_equivalent_to_pinned_upstream | 2 | 2 | 4 | 2/2 |
| expanded-budget-v7 | time_negative_unix_precision_floor | published | reviewed_equivalent_to_pinned_upstream | 1 | 2 | 3 | 2/2 |
| expanded-budget-v7 | status_update_first_failure_contract | published | reviewed_equivalent_to_pinned_upstream | 1 | 2 | 3 | 2/2 |
| expanded-budget-v7 | status_payload_clone_write_retention | published | reviewed_equivalent_to_pinned_upstream | 1 | 2 | 3 | 2/2 |
| expanded-budget-v7 | status_lookup_conflict_dispatch | published | restores_pinned_upstream_source_exactly | 1 | 1 | 2 | 2/2 |
| expanded-budget-v7 | status_copy_on_write_mutation_boundary | published | reviewed_equivalent_to_pinned_upstream | 2 | 2 | 4 | 2/2 |
| assertion-grounded-v7 | duration_negative_unit_rounding | published | reviewed_contract_consistent_extension | 1 | 2 | 3 | 2/2 |
| assertion-grounded-v7 | duration_composite_parse_accumulator | published | restores_pinned_upstream_source_exactly | 1 | 1 | 2 | 2/2 |
| assertion-grounded-v7 | duration_posix_negative_fraction_rounding | published | reviewed_equivalent_to_pinned_upstream | 1 | 2 | 3 | 2/2 |
| assertion-grounded-v7 | time_negative_unix_precision_floor | published | restores_pinned_upstream_source_exactly | 1 | 2 | 3 | 2/2 |
| assertion-grounded-v7 | status_update_first_failure_contract | published | reviewed_equivalent_to_pinned_upstream | 1 | 2 | 3 | 2/2 |
| assertion-grounded-v7 | status_payload_clone_write_retention | published | reviewed_equivalent_to_pinned_upstream | 1 | 2 | 3 | 2/2 |
| assertion-grounded-v7 | status_lookup_conflict_dispatch | published | restores_pinned_upstream_source_exactly | 1 | 1 | 2 | 2/2 |
| assertion-grounded-v7 | status_copy_on_write_mutation_boundary | published | reviewed_equivalent_to_pinned_upstream | 1 | 2 | 3 | 2/2 |

## Unsuccessful trials and confirmed semantic regressions

### confirmation-budget-v7-strings / absl_integer_signed_boundaries

Native status: `blocked`. Stage: `baseline_stability`. Semantic classification: `not_published`.

```text
Baseline outcomes varied across repetitions; test suite is unstable
```

## Independent native quality observations

### confirmation-budget-v7-strings / absl_replace_overlap_and_progress

Measured performance regression in this specific sparse-match benchmark; this patch is not generally regression-free.

Both sources passed 114,303 finite contract configurations. A separate native Release `-O3` timing used 1,048,640 input bytes, an unchanged 1 MiB prefix and 8 distinct patterns present near the end. After one warmup, three batches of ten API calls produced median times of 0.0001502709 s/call for pinned upstream and 0.0169978335 s/call for the candidate: 113.1 times slower in this benchmark. Equality checks ran after the timing stopped.

The sources produced identical expected benchmark outputs. The input is one modest sparse-match sample; concurrent native builds, caches and thermal state can affect exact timings. No universal performance ratio or production bound is claimed.

Both implementations can have similar worst-case bounds; the concrete timing does not establish a worse general asymptotic complexity class.

Finite functional/native correctness and production quality are different measures. The registered semantic ranking preserves this functional publication and reports the observed performance regression separately; no retrospective grade rule is added.

Native timing proof: `.auto-fix/v7-replace-residual-independent/performance/proof.json` SHA256 `b3f447aaf375ad50dcc7ad5a6f2e232ad769484389759751a03df6954bcd3306`. Functional proof: `.auto-fix/v7-replace-residual-independent/proof.json` SHA256 `0637be428ff6ee0d4b5b679590929ad119955b67a7c899e89507cfd33dae1cd3`.

Undocumented duplicate-key tie observation: pinned `YXYXY`, candidate `YYYYY`. No documented tie priority is asserted.

## Limits

- 72 trials are 24 distinct synthetic injected development defects in two real C++ repositories; no production effectiveness is measured.
- Independent source review and finite trusted native guards do not prove universal semantic correctness. Semantic-valid means no independently confirmed regression in the completed review.
- The 2-repair/4-inspection control versus 4-repair/6-inspection arms differs in allowed inference resources. Only expanded-budget-v7 versus assertion-grounded-v7 isolates prompt at equal resource ceilings.
- V7 versus prior V6 also includes a shared assertion-value diagnostic correction; historical confirmation is not a pure budget comparison.
- All 24 trials per arm remain in the primary denominator, including pre-model safe stops. A randomized native baseline mismatch before inference is not evidence that extra budget or a different prompt caused another arm to succeed. Model-reaching counts are descriptive only; no registered trial is rerun, reseeded or excluded.
- Latency is descriptive and confounded by concurrent scheduling, native compilation and caches. Token fields include cached/reasoning subcounts and must not be naively added into a single token count.
- Raw native publications, unsuccessful trials, provider errors, actual calls, and tokens remain unchanged and counted. No model grader is used.
- A reviewed contract-preserving refactor can retain a measured performance regression. Functional/native correctness and production quality are separate measures; see the explicit native quality observations.
- The selected configuration is a development choice. Holdout performance, repeated winner stability, Windows recorded replay, and on-premise integrations remain separate unmeasured work.
