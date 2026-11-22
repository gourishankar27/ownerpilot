"""Explicit offline synthetic evaluation, never a production approval bypass."""

import hashlib
import json
import math
import os
from pathlib import Path
import statistics
from uuid import uuid4

from psycopg.types.json import Jsonb
from api.rfq.db import connection
from api.catalog.service import build, retrieve
from api.catalog.embedding import Embeddings

ROOT = Path("data/evaluation/product-catalog")
OUT = Path(os.environ.get("CATALOG_EVAL_OUT", "docs/rfq/phase2/results"))
METHODS = [
    "exact",
    "sql",
    "bm25",
    "vector",
    "exact_bm25",
    "bm25_vector",
    "hybrid",
    "reranked",
]


class CachedRealEmbeddings(Embeddings):
    """Reuse actual query vectors across paired methods; never fabricate a vector."""

    def __init__(self):
        super().__init__()
        self.cache = {}
        self.calls = 0

    def encode(self, texts, **kwargs):
        key = json.dumps([texts, kwargs], sort_keys=True)
        if key not in self.cache:
            self.cache[key] = super().encode(texts, **kwargs)
            self.calls += 1
        return self.cache[key]


def metrics(records):
    answerable = [r for r in records if not r["no_valid_match"]]
    result = {"queries": len(records), "answerable": len(answerable)}
    for k in [1, 5, 10]:
        result[f"hit_rate@{k}"] = (
            sum(
                any(
                    r["relevance"].get(c["id"], 0) >= 2
                    for c in r["result"]["candidates"][:k]
                )
                for r in answerable
            )
            / len(answerable)
            if answerable
            else None
        )
        result[f"recall@{k}"] = (
            statistics.mean(
                sum(
                    r["relevance"].get(c["id"], 0) >= 2
                    for c in r["result"]["candidates"][:k]
                )
                / len([g for g in r["relevance"].values() if g >= 2])
                for r in answerable
            )
            if answerable
            else None
        )
        result[f"precision@{k}"] = sum(
            sum(
                r["relevance"].get(c["id"], 0) >= 2
                for c in r["result"]["candidates"][:k]
            )
            / k
            for r in records
        ) / len(records)
    reciprocal = []
    ndcg = []
    for r in answerable:
        grades = [
            r["relevance"].get(c["id"], 0) for c in r["result"]["candidates"][:10]
        ]
        reciprocal.append(
            next((1 / (i + 1) for i, g in enumerate(grades) if g >= 2), 0)
        )
        dcg = sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(grades))
        ideal = sum(
            (2**g - 1) / math.log2(i + 2)
            for i, g in enumerate(sorted(r["relevance"].values(), reverse=True)[:10])
        )
        ndcg.append(dcg / ideal if ideal else 0)
    times = sorted(r["result"]["timings"]["total_ms"] for r in records)
    exact = [
        c
        for r in records
        for c in r["result"]["candidates"]
        if c["compatibility"]["status"] == "exact"
    ]
    incorrect = sum(
        c["compatibility"]["status"] in {"exact", "compatible_alternative"}
        and r["relevance"].get(c["id"], 0) < 2
        for r in records
        for c in r["result"]["candidates"]
    )
    abstained = [r for r in records if r["result"]["outcome"] == "no_reliable_match"]
    no_match = [r for r in records if r["no_valid_match"]]
    result.update(
        mrr10=statistics.mean(reciprocal) if reciprocal else None,
        ndcg10=statistics.mean(ndcg) if ndcg else None,
        median_ms=statistics.median(times),
        p95_ms=times[math.ceil(0.95 * len(times)) - 1],
        exact_candidates=len(exact),
        false_compatible_or_exact=incorrect,
        no_match_precision=sum(r["no_valid_match"] for r in abstained) / len(abstained)
        if abstained
        else None,
        no_match_recall=sum(
            r["result"]["outcome"] == "no_reliable_match" for r in no_match
        )
        / len(no_match)
        if no_match
        else None,
        channel_timings={
            k: statistics.mean(r["result"]["timings"][k] for r in records)
            for k in ["exact_ms", "bm25_ms", "vector_ms", "fusion_ms", "rerank_ms"]
        },
    )
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if "phase2_test" not in os.environ.get("DATABASE_URL", ""):
        raise SystemExit("Offline evaluator requires isolated phase2_test database")
    manifest = json.loads((ROOT / "manifest.json").read_text())
    for name, digest in manifest["sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
    provider = CachedRealEmbeddings()
    health = provider.health()
    config = {
        "dataset": manifest,
        "model": health,
        "source": hashlib.sha256(
            b"".join(
                p.read_bytes()
                for p in sorted(Path("apps/api/src/api/catalog").glob("*.py"))
            )
        ).hexdigest(),
        "methods": METHODS,
        "policy": "catalog-rrf/1 fixed k=60, equal weights, compatibility order frozen before final",
    }
    configpath = OUT / "evaluation-config.json"
    if configpath.exists():
        old = json.loads(configpath.read_text())
        assert old == config, "Source/config mismatch; use a new result directory"
    configpath.write_text(json.dumps(config, indent=2) + "\n")
    statepath = Path(".local/rfq/phase2-evaluation-state.json")
    if statepath.exists():
        state = json.loads(statepath.read_text())
    else:
        workspace = str(uuid4())
        with connection() as conn:
            conn.execute(
                "insert into business_workspaces(id,name,slug) values(%s,'Synthetic catalog benchmark',%s)",
                (workspace, workspace),
            )
            catalog = conn.execute(
                "insert into procurement.product_catalogs(workspace_id,name,license) values(%s,'Synthetic IT catalog','CC0 fictional') returning id",
                (workspace,),
            ).fetchone()["id"]
            version = conn.execute(
                "insert into procurement.catalog_versions(catalog_id,workspace_id,fingerprint,specification,rows,requested_by,state) values(%s,%s,%s,%s,%s,'offline-benchmark','queued') returning id",
                (
                    catalog,
                    workspace,
                    manifest["sha256"]["catalog.json"],
                    Jsonb({"dataset": manifest}),
                    Jsonb(json.loads((ROOT / "catalog.json").read_text())),
                ),
            ).fetchone()["id"]
        state = {"workspace": workspace, "version": str(version)}
        statepath.write_text(json.dumps(state))
    print("Index:", build(state["version"]), flush=True)
    queries = json.loads((ROOT / "queries.json").read_text())
    records = []
    journal = OUT / "retrieval.jsonl"
    if journal.exists():
        records = [json.loads(line) for line in journal.read_text().splitlines()]
    completed = {(r["id"], r["method"]) for r in records}
    for split in ["dev", "validation", "heldout"]:
        for q in [q for q in queries if q["split"] == split]:
            for method in METHODS:
                if (q["id"], method) in completed:
                    continue
                result = retrieve(
                    state["workspace"], [state["version"]], q["query"], method, provider
                )
                r = {**q, "method": method, "result": result}
                records.append(r)
                with journal.open("a") as f:
                    f.write(json.dumps(r) + "\n")
            print(q["id"], flush=True)
    report = {
        "config": config,
        "state": state,
        "status": "complete",
        "actual_query_method_pairs": len(records),
        "real_query_embedding_calls_this_execution": provider.calls,
        "metrics": {
            f"{split}/{method}": metrics(
                [r for r in records if r["split"] == split and r["method"] == method]
            )
            for split in ["dev", "validation", "heldout"]
            for method in METHODS
        },
    }
    with connection() as conn:
        report["index"] = conn.execute(
            "select metadata from procurement.catalog_versions where id=%s",
            (state["version"],),
        ).fetchone()["metadata"]
        report["pgvector"] = conn.execute(
            "select extversion from pg_extension where extname='vector'"
        ).fetchone()["extversion"]
        report["stored_vectors"] = conn.execute(
            "select count(*) as n,min(vector_dims(embedding)) as dimensions from procurement.catalog_products where version_id=%s",
            (state["version"],),
        ).fetchone()
    (OUT / "evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "status": "complete",
                "pairs": len(records),
                "vectors": report["stored_vectors"],
            }
        )
    )


if __name__ == "__main__":
    main()
