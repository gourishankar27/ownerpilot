# Evaluation methodology

Frozen1224 fictional offers/1020 variants,17 categories,102 authored graded queries:36dev/24validation/42heldout. Category families split; templates/vocabulary shared, a generalization limitation. Grade3 exact,2 authored required-spec alternative,0 otherwise; explicit no-valid-match. Labels derive from authored requirements, never retrieval scores. Manifests/source snapshots retained; ranking parameters fixed before final scoring.

Standard Recall@K macro averages relevant identities retrieved/all relevant identities (grade>=2), answerable only. Hit-rate@K separately counts queries with any relevant result. Precision@K divides byK including unanswered queries. MRR@10 uses first grade>=2; nDCG gain2^grade-1. No-match precision/recall use explicit abstention. Multiple supplier offers never count as separate identities.

The preliminary run mislabeled hit rate as recall; retained as historical Phase 2 preliminary evidence. Corrected final run reports both, without label/ranker changes. Standard recall may fail95% while query hit rate is100%.

Latency nearest-rankP95 across successful requests. Vector baseline generates query embeddings; later paired methods reuse those genuine vectors. Cached hybrid timing is not uncached inference timing. Index build includes network/PG publication. Exact/lexical pipelines share reconstruction overhead. HNSW and continuous whole-system peaks are unmeasured, not zero. Synthetic-only corpus is not production retrieval proof.
