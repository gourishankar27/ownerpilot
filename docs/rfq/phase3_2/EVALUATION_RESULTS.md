# Phase 3.2 evaluation results

**Functionally validated — research-quality target unmet.** Selected D/four completed 52/60 held-out cases, with 324/324 source-covered lines (100.0%). The completion target is 57/60; source coverage target is 99%.

| Variant | Development | Validation | Held-out | Held-out source-covered lines | Native / backend RPCs (held-out) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Frozen Phase 3.1 | 2/16 | 4/20 | 4/60 (6.7%) | 51/324 | 183 / 0 |
| A: native batching | 14/16 | 17/20 | 51/60 (85.0%) | 323/324 | 156 / 0 |
| B: coverage-aware native | 14/16 | 19/20 | 56/60 (93.3%) | 324/324 | 156 / 0 |
| D: bounded hybrid | 16/16 | 19/20 | 52/60 (86.7%) | 324/324 | 120 / 36 |

C mandatory scheduling completed 13/16 development cases after backend-only required source collection; all 82 development lines were inspected, with 0 native-selected RPCs and 41 backend RPCs. Its optional native planning/finalization still used actual model calls. C has no held-out score. The separate zero-model deterministic baseline passed 96/96 (including 60/60 held-out); it is not agent planning evidence.

## Line-count strata

| Lines | A complete | B complete | D complete | D source-covered lines |
| --- | ---: | ---: | ---: | ---: |
| 1 | 12/12 | 12/12 | 12/12 | 12/12 |
| 2 | 12/12 | 12/12 | 12/12 | 24/24 |
| 4 | 12/12 | 12/12 | 12/12 | 48/48 |
| 8 | 7/12 | 11/12 | 7/12 | 96/96 |
| 12 | 8/12 | 9/12 | 9/12 | 144/144 |

Across 240 held-out executions, the independent oracle inspected 5274 materialized facts and 651 tool receipts: 0 unsupported/misbound accepted facts and 0 unauthorized successful tools. These are observed finite-sample results, not guarantees of universal safety.

For selected D, authored unknown sets matched in 60/60 cases and quote-readiness classification matched in 60/60. Unsupported output references were rejected before publication. Full required/supported fact counts, source-pair counts, per-run references and error details are in `results/evaluation/final-plan7/summary.json` and raw case records.

## Performance and attribution

| Variant | Median / p95 all (s) | Median / p95 completed (s) | Planning / final / correction calls | Prompt / output tokens |
| --- | ---: | ---: | ---: | ---: |
| Frozen Phase 3.1 | 8.54 / 11.45 | 7.79 / 8.76 | 180 / 60 / 0 | 272439 / 18016 |
| A: native batching | 14.31 / 74.92 | 12.96 / 46.93 | 144 / 59 / 11 | 373795 / 99899 |
| B: coverage-aware native | 14.72 / 54.29 | 14.50 / 51.50 | 156 / 60 / 8 | 435645 / 89845 |
| D: bounded hybrid | 14.71 / 67.72 | 13.97 / 66.34 | 120 / 60 / 13 | 351476 / 98716 |

These are all first-trial timings, including known regression overlap. The backend suite contains real qwen3:4b inference; treating it as CPU-only was a measurement mistake. All original quality trials and failures remain in the sixty-case denominator.

### Timings excluding recorded regression windows

| Variant | Retained timing cases | Median / p95 all (s) | Completed timing cases | Median / p95 completed (s) |
| --- | ---: | ---: | ---: | ---: |
| Frozen Phase 3.1 | 48 | 8.36 / 11.45 | 3 | 6.95 / 8.76 |
| A: native batching | 48 | 14.23 / 78.73 | 41 | 12.72 / 44.77 |
| B: coverage-aware native | 48 | 14.52 / 54.29 | 44 | 13.70 / 50.30 |
| D: bounded hybrid | 48 | 14.66 / 66.34 | 41 | 12.86 / 46.40 |

The timing-only subset retains 48 matched cases per variant. Whole regression suites, five minutes of configured model residence and five-second boundaries are excluded. All variants of a case are excluded if any overlaps, without using its outcome or observed latency. See `results/latency-without-regressions.json` for exact windows/cases and separate matched-success timings. Other CPU activity was not controlled; this is not an idle-host guarantee.

### Separately serialized development timing study

| Variant | Development timing trials | Median / p95 all (s) | Completed timing trials | Median / p95 completed (s) |
| --- | ---: | ---: | ---: | ---: |
| Frozen Phase 3.1 | 5 | 8.25 / 10.95 | 1 | 6.38 / 6.38 |
| A: native batching | 5 | 12.93 / 30.55 | 4 | 11.01 / 30.55 |
| B: coverage-aware native | 5 | 12.85 / 88.61 | 4 | 10.71 / 31.29 |
| D: bounded hybrid | 5 | 12.71 / 82.57 | 4 | 10.69 / 26.74 |

These twenty repeated development trials cover the predeclared first five cases (1/2/4/8/12 lines) after all other scheduled inference tests finished. Known non-target test models were unloaded if present, and setup confirmed only qwen3:8b was loaded; no weights were deleted. Model/cache state, native telemetry and identical configuration hashes are recorded in `results/performance-study-setup.json` and `results/evaluation/performance-plan7`. Variant order is fixed and cache-order effects remain possible. Five timing trials per variant cannot establish a production p95/SLA. These repetitions do not add independent quality successes or replace any held-out failure.

D source pairs attributed to native decisions: 360; backend source pairs: 288. Useful model required-read decisions: 120/120. This measures newly inspected required sources/global RFQ, not general planning intelligence. A batch is one decision. Backend completion is never counted as native success.

Summary JSON includes batch utilization/output-byte distributions, duplicate reads, optional calls, unused call capacity, early-finalization attempts, per-completed-run model/tool/token distributions and device-wide GPU samples. Matched-success latency is reported separately. Legacy source coverage is constrained by its unchanged eight-call limit, and failed short runs must not be presented as an equal-work speed baseline. The original timing interference is explicitly recorded; GPU samples are not peak/model-isolated measurements.

## Failure analysis

### Frozen Phase 3.1

56/60 failed verified completion. Error counts: `{"research_coverage_incomplete": 56}`.

Missing-source failures: 56; failures after complete source inspection: 0. Cases: v3-held-01, v3-held-02, v3-held-03, v3-held-04, v3-held-05, v3-held-07, v3-held-08, v3-held-09, v3-held-10, v3-held-11, v3-held-12, v3-held-13, v3-held-14, v3-held-15, v3-held-16, v3-held-17, v3-held-18, v3-held-19, v3-held-20, v3-held-21, v3-held-22, v3-held-23, v3-held-24, v3-held-25, v3-held-27, v3-held-28, v3-held-29, v3-held-30, v3-held-32, v3-held-33, v3-held-34, v3-held-35, v3-held-36, v3-held-37, v3-held-38, v3-held-39, v3-held-40, v3-held-41, v3-held-42, v3-held-43, v3-held-44, v3-held-45, v3-held-47, v3-held-48, v3-held-49, v3-held-50, v3-held-51, v3-held-52, v3-held-53, v3-held-54, v3-held-55, v3-held-56, v3-held-57, v3-held-58, v3-held-59, v3-held-60. These first frozen trials remain in the denominator.

- `v3-held-01` (1 line): sources 0/1, required facts 1/5, 3 planning / 1 initial finalization / 0 correction calls; actual finalization rejection counts `{}`. See its raw `v3-held-01-phase31.json` trace.
- `v3-held-02` (2 lines): sources 1/2, required facts 5/10, 3 planning / 1 initial finalization / 0 correction calls; actual finalization rejection counts `{}`. See its raw `v3-held-02-phase31.json` trace.
- `v3-held-03` (4 lines): sources 1/4, required facts 5/16, 3 planning / 1 initial finalization / 0 correction calls; actual finalization rejection counts `{}`. See its raw `v3-held-03-phase31.json` trace.

### A: native batching

9/60 failed verified completion. Error counts: `{"citation_correction_exhausted": 8, "planning_budget_exhausted": 1}`.

Missing-source failures: 1; failures after complete source inspection: 8. Cases: v3-held-09, v3-held-20, v3-held-30, v3-held-34, v3-held-35, v3-held-40, v3-held-44, v3-held-54, v3-held-59. These first frozen trials remain in the denominator.

- `v3-held-09` (8 lines): sources 8/8, required facts 40/40, 3 planning / 1 initial finalization / 1 correction calls; actual finalization rejection counts `{"claim_schema_rejected": 2}`. See its raw `v3-held-09-native_batch.json` trace.
- `v3-held-20` (12 lines): sources 12/12, required facts 60/60, 2 planning / 1 initial finalization / 1 correction calls; actual finalization rejection counts `{"claim_schema_rejected": 2}`. See its raw `v3-held-20-native_batch.json` trace.
- `v3-held-30` (12 lines): sources 12/12, required facts 75/75, 4 planning / 1 initial finalization / 1 correction calls; actual finalization rejection counts `{"claim_schema_rejected": 2}`. See its raw `v3-held-30-native_batch.json` trace.

### B: coverage-aware native

4/60 failed verified completion. Error counts: `{"citation_correction_exhausted": 4}`.

Missing-source failures: 0; failures after complete source inspection: 4. Cases: v3-held-25, v3-held-29, v3-held-50, v3-held-55. These first frozen trials remain in the denominator.

- `v3-held-25` (12 lines): sources 12/12, required facts 60/60, 4 planning / 1 initial finalization / 1 correction calls; actual finalization rejection counts `{"claim_schema_rejected": 2}`. See its raw `v3-held-25-coverage_native.json` trace.
- `v3-held-29` (8 lines): sources 8/8, required facts 48/48, 3 planning / 1 initial finalization / 1 correction calls; actual finalization rejection counts `{"claim_schema_rejected": 2}`. See its raw `v3-held-29-coverage_native.json` trace.
- `v3-held-50` (12 lines): sources 12/12, required facts 60/60, 4 planning / 1 initial finalization / 1 correction calls; actual finalization rejection counts `{"incorrect_claim_association": 1}`. See its raw `v3-held-50-coverage_native.json` trace.

### D: bounded hybrid

8/60 failed verified completion. Error counts: `{"citation_correction_exhausted": 8}`.

Missing-source failures: 0; failures after complete source inspection: 8. Cases: v3-held-04, v3-held-05, v3-held-14, v3-held-29, v3-held-30, v3-held-34, v3-held-55, v3-held-59. These first frozen trials remain in the denominator.

- `v3-held-04` (8 lines): sources 8/8, required facts 36/40, 2 planning / 1 initial finalization / 1 correction calls; actual finalization rejection counts `{"claim_schema_rejected": 2}`. See its raw `v3-held-04-hybrid.json` trace.
- `v3-held-05` (12 lines): sources 12/12, required facts 72/72, 2 planning / 1 initial finalization / 1 correction calls; actual finalization rejection counts `{"claim_schema_rejected": 2}`. See its raw `v3-held-05-hybrid.json` trace.
- `v3-held-14` (8 lines): sources 8/8, required facts 40/40, 2 planning / 1 initial finalization / 1 correction calls; actual finalization rejection counts `{"claim_schema_rejected": 2}`. See its raw `v3-held-14-hybrid.json` trace.

Source-read coverage and citation completion are separate. New runs with complete sources may still omit, misassociate or add invalid references and exhaust the single correction. Some failures already cover every required fact after merging valid references, but additional invalid references still block publication under the strict zero-invalid-citation gate. Such runs retain valid partial facts and stop needing attention. No configuration was changed after selection or tuned against held-out failures. Initial development experiments and batch-two comparisons remain separately archived, not pooled into held-out scores.

Raw experiment records contain actual local inference acknowledgements, model identity, source hashes, immutable receipts, native/backend origin, finalization attempts and resource samples. `selection.json` and archived source files make the first frozen final experiment reviewable. Historical Phase 3.1 files and scores remain unchanged.
