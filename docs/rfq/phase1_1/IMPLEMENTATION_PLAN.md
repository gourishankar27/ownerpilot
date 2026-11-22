# Implementation plan

1. Preserve released artifacts and code, verify actual branch/runtime, execute baseline.
2. Freeze independently designed v2 source/labels, with separate dev/evaluation families.
3. Measure grayscale/resolution/deskew/TSV geometry and targeted OCR on development data.
   Add bounded image transforms, real word boxes, disagreement metadata and cache identity.
4. Add selective-v2 page/row/field routing, structural association checks and conservative
   source-anchor merging. Retain phase1 as an explicitly selectable historical policy.
5. Measure installed/authorized models and compact prompts on the same development
   inputs, separate cold/warm runs, then freeze the selected configuration.
6. Run resumable full v1 and independent v2 deterministic/LLM/hybrid comparisons using
   a versioned maximum-weight evaluator alongside historical-compatible metrics.
7. Add focused tests, safe public-schema compatibility reconciliation, job metadata,
   evidence/review filters, real worker/recovery/security and browser checks.
8. Verify historical hashes, produce measured reports and exact reproduction commands.

No Phase 2 catalog, retrieval, embeddings, reranker, purchasing or communication code.
