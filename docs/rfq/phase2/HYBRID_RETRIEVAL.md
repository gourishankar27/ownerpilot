# Hybrid retrieval

Exact manufacturer/MPN, genuine BM25 and real pgvector channels retain independent raw scores/ranks. RRF adds1/(60+rank), equal weights, stable ID ties. Genuine exact identities protected before compatibility reranking; cosine is not an accuracy probability.

Server reads persisted approved revision/current run/reviewed item. Clients submit only revision/version UUIDs; critical nonnull fields must be validated. Missing MPN stays lower-certainty description/spec search. Search snapshots record query/revision/versions/model/digest/policy/evidence/timings. Offline evaluator is isolated from application approval.

Exact matching scans the bounded authorized collection; shared BM25 reconstruction also runs in exact-only baseline. Do not claim optimized indexed exact-lookup scalability. Benchmark methods:exact,SQL FTS,BM25,vector,exact+BM25,BM25+vector,full hybrid,reranked.
