# Implementation plan

1. Audit, preserve tree, branch, establish baseline and disposable services.
2. Isolated typed parser, storage, validation and actual Ollama provider modules.
3. Additive procurement schema; workspace-authenticated API; immutable extraction
   versions; durable DB outbox with Celery/Redis; review and approval transactions.
4. Existing-shell Procurement dashboard, creation, uploads, jobs, editable fields,
   source evidence, review reasons, optimistic concurrency and explicit approval.
5. Frozen synthetic dataset, deterministic/LLM/hybrid evaluation; unit, database,
   worker, security and browser validation; regression checks and runbook.

Phase 2 is planning only: catalog ingestion with vendor/version provenance, learned
embedding provider with model/dimension/version tracking, pgvector vector search,
BM25 lexical search, exact manufacturer+MPN candidates, fused retrieval and reranker,
careful deduplication, relevance labels and held-out retrieval benchmarks. No Phase 2
implementation, automated purchasing, supplier communication or quote submission.
