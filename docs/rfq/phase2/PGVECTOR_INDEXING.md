# pgvector indexing

1020 actual learned768D vectors are stored with version/tenant/content hashes. PostgreSQL cosine operator<=> performs exact nearest-neighbor search with DB-side workspace/version restrictions. Version metadata pins model/digest/preprocessing. No HNSW/ANN was added or measured for this small corpus; no invented approximate recall or filtering claim.

Bounds:50 candidates/channel,20 results,5000 collection records,10 versions. Unpublished/superseded/digest-stale indexes409. Old runs remain readable. Rebuild creates a distinct staged version, preserving old active state until success. Duplicate source offers survive canonical fusion. [pgvector reference](https://github.com/pgvector/pgvector).
