# Final evaluation results

All six executions completed: 192 document/configuration attempts, zero failed jobs and zero skipped samples. A valid completed job can contain empty or erroneous rows; success is not extraction accuracy. Each set has 32 documents and 160 expected items. Configurations were frozen before final evaluation; final labels were never supplied to prompts.

The independent v2 results expose substantial generalization failures. Milestone performance targets are unmet. Assignment/2.0 is the primary evaluator; the historical matcher is reported separately. Every subset below comes from the same full execution, without combining rechecks.

| Set | Mode | Subset | Docs/items | MPN correct | Qty correct | F1 | Matches/predictions | Calls | P95 | Failures/skips |
|---|---|---|---|---|---|---|---|---|---|---|
| rfq | deterministic | all | 32/160 | 98/160 (61.25%) | 86/160 (53.75%) | 81.92% | 111/111 | 0 | 0.633s | 0/0 |
| rfq | deterministic | clean | 16/80 | 79/80 (98.75%) | 75/80 (93.75%) | 99.37% | 79/79 | 0 | 0.130s | 0/0 |
| rfq | deterministic | scanned/mixed | 8/40 | 19/40 (47.50%) | 11/40 (27.50%) | 88.89% | 32/32 | 0 | 0.776s | 0/0 |
| rfq | deterministic | adversarial | 4/20 | 0/20 (0.00%) | 0/20 (0.00%) | 0.00% | 0/0 | 0 | 0.017s | 0/0 |
| rfq | deterministic | matched-eight | 8/40 | 24/40 (60.00%) | 23/40 (57.50%) | 82.35% | 28/28 | 0 | 0.776s | 0/0 |
| rfq | llm | all | 32/160 | 76/160 (47.50%) | 53/160 (33.12%) | 68.27% | 85/89 | 32 | 25.090s | 0/0 |
| rfq | llm | clean | 16/80 | 45/80 (56.25%) | 29/80 (36.25%) | 70.31% | 45/48 | 16 | 21.552s | 0/0 |
| rfq | llm | scanned/mixed | 8/40 | 11/40 (27.50%) | 19/40 (47.50%) | 65.57% | 20/21 | 8 | 28.416s | 0/0 |
| rfq | llm | adversarial | 4/20 | 10/20 (50.00%) | 0/20 (0.00%) | 66.67% | 10/10 | 4 | 17.601s | 0/0 |
| rfq | llm | matched-eight | 8/40 | 12/40 (30.00%) | 9/40 (22.50%) | 53.57% | 15/16 | 8 | 22.399s | 0/0 |
| rfq | hybrid | all | 32/160 | 98/160 (61.25%) | 86/160 (53.75%) | 78.87% | 112/124 | 13 | 2.987s | 0/0 |
| rfq | hybrid | clean | 16/80 | 79/80 (98.75%) | 75/80 (93.75%) | 100.00% | 80/80 | 1 | 4.662s | 0/0 |
| rfq | hybrid | scanned/mixed | 8/40 | 19/40 (47.50%) | 11/40 (27.50%) | 84.21% | 32/36 | 4 | 2.987s | 0/0 |
| rfq | hybrid | adversarial | 4/20 | 0/20 (0.00%) | 0/20 (0.00%) | 0.00% | 0/4 | 4 | 1.912s | 0/0 |
| rfq | hybrid | matched-eight | 8/40 | 24/40 (60.00%) | 23/40 (57.50%) | 78.87% | 28/31 | 3 | 2.987s | 0/0 |
| rfq-v2 | deterministic | all | 32/160 | 78/160 (48.75%) | 96/160 (60.00%) | 73.96% | 98/105 | 0 | 1.098s | 0/0 |
| rfq-v2 | deterministic | clean | 16/80 | 78/80 (97.50%) | 78/80 (97.50%) | 98.73% | 78/78 | 0 | 0.171s | 0/0 |
| rfq-v2 | deterministic | scanned/mixed | 8/40 | 0/40 (0.00%) | 18/40 (45.00%) | 59.70% | 20/27 | 0 | 1.142s | 0/0 |
| rfq-v2 | deterministic | adversarial | 4/20 | 0/20 (0.00%) | 0/20 (0.00%) | 0.00% | 0/0 | 0 | 0.029s | 0/0 |
| rfq-v2 | llm | all | 32/160 | 30/160 (18.75%) | 30/160 (18.75%) | 27.91% | 30/55 | 46 | 29.978s | 0/0 |
| rfq-v2 | llm | clean | 16/80 | 0/80 (0.00%) | 0/80 (0.00%) | 0.00% | 0/20 | 24 | 3.851s | 0/0 |
| rfq-v2 | llm | scanned/mixed | 8/40 | 0/40 (0.00%) | 0/40 (0.00%) | 0.00% | 0/3 | 14 | 4.198s | 0/0 |
| rfq-v2 | llm | adversarial | 4/20 | 10/20 (50.00%) | 10/20 (50.00%) | 62.50% | 10/12 | 4 | 32.366s | 0/0 |
| rfq-v2 | hybrid | all | 32/160 | 78/160 (48.75%) | 97/160 (60.62%) | 71.68% | 100/119 | 14 | 5.270s | 0/0 |
| rfq-v2 | hybrid | clean | 16/80 | 78/80 (97.50%) | 79/80 (98.75%) | 100.00% | 80/80 | 2 | 5.599s | 0/0 |
| rfq-v2 | hybrid | scanned/mixed | 8/40 | 0/40 (0.00%) | 18/40 (45.00%) | 56.34% | 20/31 | 4 | 3.043s | 0/0 |
| rfq-v2 | hybrid | adversarial | 4/20 | 0/20 (0.00%) | 0/20 (0.00%) | 0.00% | 0/4 | 4 | 2.206s | 0/0 |

Clean means the four declared structured digital layout families per set. Scanned/mixed means eight raster/mixed pages per set. Adversarial means four instruction/quoted-output documents per set. Prose documents are included in all and matched-eight where selected, but excluded from clean. The complete per-layout/per-format breakdown and all raw numerators are in each report and summary.json.

| Set | Mode | Manufacturer | Unit | Description exact | Header exact | Missed/unexpected | Unsupported proposals/populated | Unsupported accepted/accepted | Unresolved/predicted |
|---|---|---|---|---|---|---|---|---|---|
| rfq | deterministic | 65.62% | 56.88% | 56.88% | 87.50% | 49/0 | 0/751 | 0/700 | 25/111 |
| rfq | llm | 52.50% | 53.12% | 40.62% | 53.12% | 75/4 | 15/541 | 0/458 | 57/89 |
| rfq | hybrid | 66.25% | 57.50% | 57.50% | 87.50% | 48/12 | 1/755 | 0/701 | 38/124 |
| rfq-v2 | deterministic | 54.37% | 56.88% | 55.62% | 85.00% | 62/7 | 0/685 | 0/665 | 18/105 |
| rfq-v2 | llm | 17.50% | 18.75% | 18.75% | 7.50% | 130/25 | 0/226 | 0/192 | 25/55 |
| rfq-v2 | hybrid | 55.62% | 58.13% | 56.88% | 85.00% | 60/19 | 2/694 | 0/669 | 32/119 |

Literal support is distinct from semantic correctness: unsupported accepted is zero by the recorded occurrence/status check, while erroneous_item_fields remains nonzero. An empty generated row can count as an unexpected prediction. Duplicate-warning counts are conservative warnings, not adjudicated duplicate truth. Human-review burden is unresolved-item count, not measured reviewer minutes.

## Historical-compatible rescore of the new predictions

| Mode | Subset | MPN | Quantity | F1 |
|---|---|---|---|---|
| deterministic | all | 61.25% | 53.75% | 76.75% |
| deterministic | matched-eight | 60.00% | 57.50% | 73.53% |
| llm | all | 47.50% | 29.38% | 63.45% |
| llm | matched-eight | 30.00% | 15.00% | 42.86% |
| hybrid | all | 61.25% | 53.75% | 73.94% |
| hybrid | matched-eight | 60.00% | 57.50% | 70.42% |

Fresh original Phase 1 hybrid, eight identical IDs: MPN 82.50%, quantity 95.00%, F1 97.44%, P95 117.643s. New hybrid P95 is 2.987s, a 97.46% reduction, with different and generally worse quality. This meets the elapsed-time target only; it is not an equivalent-quality throughput claim. The original published historical P95 (106.450s) is a separate mixed-origin historical reference, not this fresh baseline.

See performance-gates.json for every predeclared performance target. See EVALUATION_METHODOLOGY.md for denominators, missing measurements, label/split limitations and matching assumptions.
