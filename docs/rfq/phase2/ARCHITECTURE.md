# Architecture

```mermaid
flowchart LR
 UI[Catalog Intelligence] --> Auth[Better Auth signed proxy]
 Auth --> API[Workspace roles and approved RFQ]
 API --> Preview[Validated preview and confirmation]
 Preview --> PG[(PostgreSQL source versions and outbox)]
 PG --> Worker[Celery advisory lock]
 Worker --> Embed[Local Nomic neural embeddings]
 Embed --> V[(pgvector 768D)]
 Worker --> Publish[Atomic publication]
 Publish --> PG
 API --> Exact[Exact manufacturer MPN]
 API --> BM25[Okapi BM25]
 API --> V
 Exact --> RRF[Rank fusion]
 BM25 --> RRF
 V --> RRF
 RRF --> Rules[Deterministic compatibility]
 Rules --> Review[Search snapshots and human audit]
 Review --> UI
```

Catalog tables are separate from inventory. Tenant/version SQL restrictions apply before fusion. Source/query/candidate snapshots preserve historical explanations after supersession. Offline ground-truth evaluation has no production endpoint and is restricted to a named disposable DB.
