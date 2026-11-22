# Phase 3.1 measured research results

**Functionally validated — research-quality target unmet.** November 22, 2026. New held-out completion is **20/36 (55.6%)**, below 95%. Safety checks found no accepted unsupported commercial facts or unauthorized successful tools. Failed runs remain intact; no held-out tuning was performed.

## Separate original ten-case comparison

The original column is recorded historical evidence. Fresh prompt-6 runs used a populated migrated clone with identical RFQ/product/offer identities and commercial fingerprints. All ten source comparisons matched. This sample is not pooled with procurement-v2.

| Metric | Phase 3 original | Citation-only | Citation-only + repair |
|---|---:|---:|---:|
| Verified complete | 6/10 | 10/10 | 10/10 |
| Held-out complete | 4/8 | 8/8 | 8/8 |
| Valid candidate citations | 156/160 exact copies | 50/50 typed references | 50/50 typed references |
| Accepted unsupported claims | 0 | 0 | 0 |
| Authorized successful tools | 30/30 | 30/30 | 30/30 |
| Actual model requests | 40 | 40 | 40, shared trace |
| Median research latency | 16.787 s | 6.150 s | 6.150 s |
| P95 research latency | 18.824 s | 6.297 s | 6.297 s |
| Citation corrections | N/A | 0 | 0 |

All four corresponding malformed-price scenarios completed. The new model cannot submit a `value` field, so exact commercial scalar copying is no longer its responsibility. Historical files were not edited. The historical adapter initially stopped before `unavailable` because its enumerated freshness mapping omitted that existing classification. The mapping was corrected from frozen historical evidence, then the remaining two cases resumed without rerunning the first eight. This was a harness correction, not a model failure or changed label.

## Independent frozen 60-case comparison

These are 120 actual native runs: 60 legacy and 60 citation-only/repair traces. No-repair is the first-finalization ablation, sharing its real planning and initial output with the correction variant. Sources, human attestations and authored expectations are identical across variants.

| Metric | Frozen Phase 3 protocol | Citation-only | Citation-only + repair |
|---|---:|---:|---:|
| Independently complete | 26/60 (43.3%) | 35/60 (58.3%) | 36/60 (60.0%) |
| Development | 6/12 | 10/12 | 10/12 |
| Validation | 4/12 | 5/12 | 6/12 |
| Held-out | 16/36 (44.4%) | 20/36 (55.6%) | 20/36 (55.6%) |
| Valid selected citation pointers | 863/886 exact-copy candidates | 252/256 (98.4%) | 256 final facts, zero remaining invalid references |
| Accepted unsupported commercial/selection facts | 0 | 0 | 0 |
| Authorized successful tools | 190/190 | 180/180 | 180/180, shared tools |
| Required source-tool coverage | 59/60 | 36/60 | 36/60 |
| Actual model requests | 240 | 240 initial requests | 241 including correction |
| Median observed research latency | 15.856 s | 6.326 s, n=59 | 6.334 s, n=60 |
| P95 observed research latency | 19.041 s | 7.610 s, n=59 | 7.610 s, n=60 |
| Citation corrections | N/A | N/A | 1 successful |

Legacy backend status alone marked 36 cases complete. Ten missed the new independent required-fact oracle, leaving 26 independently complete; historical completion definitions were not rewritten. Citation cardinality differs by schema. Old output copies arbitrary supported scalars; new output selects required typed facts and backend coverage derives unknowns. Citation counts are not interchangeable completeness denominators.

The initial rejected group contained four pointers, so it counts as four invalid pointer attempts, not one merely because there was one group diagnostic. Final facts include safely retained partial evidence. All 147 held-out materialized references passed independent value/association checks, while missing source reads still blocked sixteen held-out reports. There were zero authored quote-readiness disagreements across all sixty source/quote cases.

For initial-only latency, 59 unrepaired traces have observed runner totals. The repaired trace has no separately executed no-repair total, so it is excluded from that latency distribution rather than assigning a fabricated counterfactual. Its initial completion still counts in the sixty-case quality denominator. Raw admission-origin initial checkpoint times are retained but are not mixed with runner-entry timing.

The separately executed deterministic source report completed **60/60**, materializing **336** required facts with no independent mismatch, no model calls, median 2.422 ms and P95 4.628 ms. It reads the same pinned facts and chooses required references programmatically. It is an offline source report, not autonomous model research. Embedded `deterministic_baseline` fields in native files describe fixture/source availability; measured execution is in [deterministic-source-baseline.json](results/deterministic-source-baseline.json).

## Failure analysis

All 24 final new failures were `research_coverage_incomplete`: two development, six validation and sixteen held-out. None were relabelled complete by discarding invalid facts. Single-line examples read selection and another authorized source but omitted supplier offers: `dev-04` no-match, `held-04` missing price, `held-23` wrong manufacturer, and `held-31` catalog injection. Multi-line cases `held-33`–`held-35` fully inspected only their first line.

The new configuration generally serialized one tool per planning turn. Each new run used four initial model calls and only three business reads, underutilizing the eight-tool budget. This **regressed tool coverage from 59/60 to 36/60** despite improving verified completion by removing scalar-copy failures. Citation correction cannot repair a source never inspected. Batching/remaining-line planning needs a new development experiment and fresh final evaluation, not post-hoc tuning on this held-out set.

`val-01` selected an incorrectly associated group. Four offer references were missing; valid selection evidence survived. One correction reused those receipts, took 2.012 s provider wall time and restored the references without another business tool. No held-out case used correction. New native runs had no remaining formatting failure, unsafe accepted reference, worker crash or wall-budget failure; those fault paths were tested separately.

Legacy failures included 22 exact-value mismatches, one missing/unsuccessful receipt reference and one source-tool failure, plus ten independent completeness failures among backend-complete runs. Missing commercial information is separate: a null price is a valid sourced fact rather than a copying error.

## Performance scope

Actual Ollama prompt/generated token totals: 568,500/53,514 legacy, 236,060/16,211 initial citation-only, and 236,894/16,374 including correction. Among fifteen identical cases where both variants independently completed, median total latency was 12.265 s legacy versus 6.326 s new. Faster incomplete reports are not presented as valid-summary speedups. CPU tests/builds overlapped some evaluation, so these are local observations, not a controlled production capacity study.

The model was loaded before 59/60 legacy and 60/60 new runs. The one unloaded legacy case took 19.041 s and reported a 2.156 s first-call load. A separate native smoke reported a 2.615 s load; that is not a cold full-research benchmark. Device-wide GPU before/after samples ranged 1,157–11,409 MiB, neither isolated model memory nor peaks. One host observation recorded 33,158,572 KiB total and 5,398,196 KiB free physical memory. Per-run peak RAM was not measured. Inline evaluation has no Celery queue-wait estimate; actual worker recovery is separate.

Evidence: [methodology](EVALUATION_METHODOLOGY.md), [frozen configuration](results/evaluation/dev-contract6/configuration.json), [summary](results/evaluation-summary.json), [native traces](results/evaluation/dev-contract6), [original matched cases](results/historical-comparison), [host sample](results/host-resource-sample.json), [Windows reproduction](WINDOWS_SETUP.md).
