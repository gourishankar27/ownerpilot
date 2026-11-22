# Extraction ablations

Post-selection regression diagnostics: one clean pipe table and one table plus an unresolved prose row, three authored expected items across two documents. These are explicit development diagnostics outside v1/v2 and were not used to revise the frozen configuration. Same qwen3:4b, full schema, context8192/output4096. TXT parsing avoids OCR as a confounder.

| Configuration | MPN | Quantity | F1 | Model calls | P95 |
|---|---|---|---|---|---|
| phase1/deterministic | 66.67% | 66.67% | 80.00% | 0 | 0.041s |
| phase1/hybrid | 66.67% | 66.67% | 80.00% | 0 | 0.024s |
| selective-v2/deterministic | 66.67% | 66.67% | 80.00% | 0 | 0.002s |
| selective-v2/hybrid | 66.67% | 66.67% | 66.67% | 1 | 2.051s |

The old any-items fast path makes no model calls for the partial document. The new router selects its unresolved source block and makes a bounded call; real recovery quality is still poor. An empty generated row is preserved as unresolved and cannot be approved without review/correction. Fixture-provider merge tests separately prove that supported repairs retain reliable deterministic values; fixture results are excluded from measured quality.

OCR-only contribution is measured with deterministic extraction in OCR_EXPERIMENTS.md; geometry reconstruction and association changes are coupled there, so it is not a pure recognition-only causal estimate. Model-size and prompt/schema contributions are separated within the matched development experiments in MODEL_BENCHMARKS.md. Wrong-row/column verifier tests isolate association rejection using authored proposals; no stand-alone quantitative association ablation is claimed. No cascade was selected or measured. There is no unsupported assertion that every code change caused the aggregate quality delta.
