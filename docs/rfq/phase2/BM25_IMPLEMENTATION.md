# BM25 implementation

Project-owned technical-bm25/1 implements genuine Okapi BM25: k1=1.5,b=.75; IDF=log(1+(N-df+.5)/(df+.5)); saturation=f*(k1+1)/(f+k1*(1-b+b\*dl/avgdl)). An independent equation test verifies scores. Apache2.0 repository code; no third-party index dependency or unsafe pickle.

Whole technical identifiers and component tokens remain, without generic stopword removal. PostgreSQL published snapshots are authoritative; requests reconstruct a bounded read-only index in stable ID order. Multi-worker consistency follows versioned PG state. BM25 latency includes reconstruction. PostgreSQL ts_rank_cd is a separately identified SQL FTS baseline, never mislabeled BM25. This design targets1020 products, not production-scale catalog throughput.
