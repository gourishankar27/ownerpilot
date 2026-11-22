# Phase 3.1 final implementation report

**Functionally validated — research-quality target unmet.** Local functional gates pass. The frozen held-out score is **20/36 (55.6%)**, below 95%. No push, deployment or Phase 4 implementation occurred.

The model now selects subject-bound receipt/pointer groups without business values. The backend resolves original scalars, validates ownership/semantic types and binds them to RFQ/revision/line/product/catalog/offer fingerprints. Valid partial evidence survives, unknowns remain explicit, and research coverage is independent of quote readiness. Quote calculations and approval still use unchanged financial logic and human inputs.

Prompt 6, citation schema 2, verifier 2 and actual model digest are pinned. The prompt-5 provider/contract/verifier, original runner body and historical results remain usable. One separately recorded correction reuses existing receipts without business tools or a deadline extension. Durable pending calls, immutable receipts/finalizations, counters and atomic publication preserve safe recovery and cancellation. The UI distinguishes published, partial, staged and legacy evidence, source associations, unknowns and quote follow-up.

| New independent 60-case metric | Phase 3 protocol | Citation-only | Citation-only + repair |
|---|---:|---:|---:|
| Verified complete | 26/60 | 35/60 | 36/60 |
| Held-out complete | 16/36 | 20/36 | 20/36 |
| Valid candidate pointers | 863/886 exact copies | 252/256 typed references | 256 final facts; zero remaining invalid references |
| Accepted unsupported facts | 0 | 0 | 0 |
| Authorized successful tools | 190/190 | 180/180 | 180/180, shared tools |
| Median / P95 research latency | 15.856 / 19.041 s | 6.326 / 7.610 s, n=59 | 6.334 / 7.610 s, n=60 |
| Corrections | N/A | N/A | One successful |

Initial-only quality still uses sixty cases. Its latency excludes the one repaired trace because a separate no-repair total was not executed. Citation cardinality differs by schema and is not a completeness percentage. The deterministic source report completed 60/60 without a model and is not an agent score. [Evaluation results](EVALUATION_RESULTS.md) includes raw artifacts, full methodology, resource observations and error analysis.

Separately, fresh citation-only runs on the original sources completed **10/10, including 8/8 held-out**, versus recorded historical **6/10 and 4/8**. All four malformed-price scenarios completed. Median/P95 was 6.150/6.297 seconds versus historical 16.787/18.824 seconds. Sources/fingerprints matched in a migrated clone; these results are not pooled with the larger corpus.

The new configuration regressed required source-tool coverage from 59/60 legacy to 36/60 new. It generally made one tool call per planning turn, omitting later lines or supplier-offer reads despite unused tool-call capacity. All 24 final failures safely required attention. Correction fixed one invalid association but cannot compensate for unperformed research. The configuration stayed frozen; no held-out retuning was performed. Future work needs a development experiment for batching/remaining-line planning and fresh final evaluation.

Validation passed **386 backend tests plus the original strict JPY xfail; fifteen browser scenarios including the original eleven; 64 additive finance checks; workspace lint/typecheck/test/build, Ruff, compilation and lock validation.** The main benchmark used 120 actual native runs/481 model requests/370 successful read-only tools, plus ten fresh matched original-case runs/forty requests/thirty tools. No unsupported accepted facts, unauthorized successful tools, cross-workspace exposure, duplicate completion publication or quote approval bypass was observed in this tested scope.

Real SIGKILL recovery retained receipts/budgets and resumed on delivery two after 92.61 seconds, safely ending attention for missing coverage. Duplicate delivery made no change. Actual cancellation prevented publication; a refused local provider endpoint executed zero tools. Six controlled interruption stages and authorization/source/correction fixtures are separately identified in [recovery validation](RECOVERY_VALIDATION.md).

The populated migration clone preserved 1,363 original rows in 39 tables. All 525 protected old documentation/dataset/migration files and the original provider match their hashes. No financial calculation, quote approval behavior, extraction, catalog retrieval, released migration or historical evaluation label was changed. The independent rational finance-v2 oracle corrects only its new JPY label to **845 + 85 = 930**, preserving v1's 929 label and strict xfail.

Limitations: synthetic data and modest sample size; substantial planning failures; no live supplier feed or production readiness claim; attestations are human source claims; no cold full-research capacity study; sampled device-wide VRAM/one host RAM observation rather than per-run peaks; safe recovery does not guarantee completed research. [Validation](PHASE3_1_VALIDATION.md), [demo](DEMO_RUNBOOK.md) and [Windows setup](WINDOWS_SETUP.md) make the local scope reproducible.

Resume-ready evidence:

- Built versioned local tool-using procurement agents with subject-bound citation resolution and bounded correction; validated 130 native benchmark runs without accepting unsupported commercial facts.
- Implemented durable model/tool checkpoints and atomic publication; demonstrated real SIGKILL recovery, idempotent redelivery and cancellation while preserving authorization and quote immutability.
- Created frozen independent research and rational finance benchmarks; preserved historical artifacts/known oracle xfail while passing 386 backend tests, fifteen browser scenarios and 64 additive finance checks.
