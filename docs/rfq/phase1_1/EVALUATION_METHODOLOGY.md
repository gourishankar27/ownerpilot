# Evaluation methodology

Historical v1 remains a fixed regression set:48 synthetic documents/240 items,16 development and32 held-out. It was already inspected in Phase1 and cannot establish unbiased generalization. Frozen v2 adds48 documents/240 items with16 dev and32 independent evaluation documents across disjoint layout families. Manifest SHA256 is385f54af71904cbee6d51ed79adf61963fd5c30db99ec115a89b948da91e14aa. Shared fictional product vocabulary and a single generator limit independence from the broader synthetic design.

Development families are grid scan, low resolution, mild rotation and keyed prose. Final families are invoice grid, split tables, multi-sheet workbook, tab-separated CSV preamble, prose, mixed native/raster rotation, low-contrast scan and adversarial quoted output. Repeated products with differing quantities, similar ambiguous identifiers and missing manufacturers are included. There are no realistic handwritten documents, genuine multi-page continuation labels,90-degree pages, diverse languages or real customer data. These omissions are explicit.

The generator refuses to overwrite its manifest. Each source and truth has a SHA256 verified before processing. Source bytes alone enter parsers/prompts; labels are read only for post-extraction scoring. Selection records were frozen before final inference. No thresholds, prompts or model configuration were changed using final labels. A separate two-document post-selection diagnostic illustrates routing regression and is excluded from independent quality claims.

`assignment/2.0` uses maximum-weight Hungarian one-to-one assignment with dummy unmatched slots. Identity weights use independent description similarity, line number and observable page/sheet/row. MPN and quantity never choose identity. Description similarity below0.45 is rejected unless a line number agrees; incompatible page/sheet anchors are rejected; competing predictions within0.15 weight are marked ambiguous. Ambiguous matches count in detection but never earn field-correct credit. This is an engineered matching rule, not manually adjudicated truth, and line-number matching can be lenient for poor descriptions. Tests cover duplicate ambiguity, missing identities, sheet mismatch, global assignment, swapped quantities and unmatched states.

The old greedy matcher is preserved and applied to the same saved predictions for historical-compatible counts. Do not conflate assignment-v2 F1 with old F1. The fresh original baseline uses the original evaluator and original code, including old OCR and prompt. The historical published comparison combines different runs and is labeled separately.

| Metric | Numerator / denominator |
|---|---|
| MPN/manufacturer/quantity/unit | Exact labeled value on nonambiguous matched row / all expected items, including missing rows |
| Description | Exact description string / all expected items; similarity is used only for assignment |
| Header | Exact labeled header fields / number of labeled header fields |
| Precision / recall | Assigned pairs / predictions or expected items; F1 is harmonic mean |
| Missed / unexpected | Expected or predicted rows left unmatched |
| Required completeness | Nonnull predicted description/quantity/unit values /3×expected rows; not proof of correctness |
| Source occurrence | Verified literal evidence entries / all populated-field evidence entries |
| Structural verification rate | Verified row associations / observed nonunknown row associations; not label accuracy |
| Row/column accuracy | Evidence locations agreeing with labeled row/column / evidence entries with observable labels; PDF box labels do not masquerade as text row labels |
| Unsupported proposed | Populated raw/value fields lacking all verified literal evidence / all populated fields |
| Unsupported accepted | Validated nonnull fields lacking literal support / all validated nonnull fields |
| Erroneous item fields | Nonnull fields wrong, unmatched or ambiguously matched / all nonnull item fields; additional unlabeled fields conservatively count as erroneous |
| Unresolved / review proxy | Predicted rows with description/quantity/unit/MPN not validated / predicted rows; reviewer minutes unmeasured |
| Success / structured validity | Completed validated extraction payloads / attempted documents, including deterministic paths; raw generation JSON validity across failed attempts is unmeasured |
| Deterministic-only | Successful documents with zero recorded model runs / successful documents |
| Model calls / retry attempts | Recorded successful provider calls and sum(attempt-1); failed-job request attempts may not be retained |
| Escalation | Zero: no cascade selected or implemented |
| Latency | Median and nearest-rankP95 on successful attempts only, with explicit denominator and failed-attempt milliseconds separately |

Undefined ratios are null, not zero. Detection precision with zero predictions is defined0 for a nonempty task; zero correct count against expected labels is a measured0. Duplicate warnings include conservative duplicate-like warnings; no separate manually adjudicated duplicate count is claimed. Model throughput is actual returned token counts/runtime; context byte reservation is not a tokenizer count. Queue time comes from persisted application timestamps in separate real workflows, not direct evaluator runs.

Each run saves a source-tree fingerprint, manifest hash, exact IDs, model digest, selected config, policy/parser/evaluator, per-sample metadata/predictions and timings. JSONL journals flush after each attempt; JSON reports publish atomically. Resume requires identical source/config/digest/IDs and refuses damaged journal tails. No incomplete run is labeled complete. All six final runs have32/32 actual samples, no skips and zero job failures. The current final source fingerprint is ae593462a75cf0a2c86e849c53e515b9e456df7080e7b9dc8abb13cfce59c9f3.

GPU/RAM observations belong to the controlled model benchmarks, not every final sample. Final evaluation ran sequentially without another model workload. A deterministic worker-recovery check overlapped briefly with independent evaluation on CPU; no second GPU workload was introduced. No load-throughput or statistical-confidence claim is made from these sample sizes.
