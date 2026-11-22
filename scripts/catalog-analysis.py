"""Additional accounting on frozen outputs plus uncached local query timings."""

import itertools
import json
import math
import os
from pathlib import Path
import statistics
import time

import httpx
from api.catalog.core import group_products, canonical_text
from api.catalog.service import retrieve
from api.catalog.embedding import Embeddings
from api.rfq.db import connection


def main():
    if "phase2_test" not in os.environ.get("DATABASE_URL", ""):
        raise SystemExit("Isolated synthetic test DB only")
    root = Path("docs/rfq/phase2/results")
    samples = [
        json.loads(line)
        for line in (root / "final/retrieval.jsonl").read_text().splitlines()
    ]
    selected = [
        r for r in samples if r["split"] == "heldout" and r["method"] == "reranked"
    ]
    exact_queries = [r for r in selected if r["kind"] in {"exact", "alias"}]
    exact_correct = sum(
        r["relevance"].get(r["result"]["candidates"][0]["id"]) == 3
        for r in exact_queries
    )
    exact = [
        (r, c)
        for r in selected
        for c in r["result"]["candidates"]
        if c["compatibility"]["status"] == "exact"
    ]
    compatible = [
        (r, c)
        for r in selected
        for c in r["result"]["candidates"]
        if c["compatibility"]["status"] == "compatible_alternative"
    ]
    rows = json.loads(Path("data/evaluation/product-catalog/catalog.json").read_text())
    grouped = group_products(rows)
    predicted = {
        frozenset(pair)
        for p in grouped
        for pair in itertools.combinations([o["source_id"] for o in p["offers"]], 2)
    }
    expected = {
        frozenset((f"source-{f}-{v}", f"offer-{f}-{v}"))
        for f in range(17)
        for v in range(0, 60, 5)
    }
    result = {
        "clean_exact_top1": {"correct": exact_correct, "total": len(exact_queries)},
        "false_exact": {
            "incorrect": sum(r["relevance"].get(c["id"], 0) != 3 for r, c in exact),
            "total": len(exact),
        },
        "false_compatible": {
            "incorrect": sum(r["relevance"].get(c["id"], 0) < 2 for r, c in compatible),
            "total": len(compatible),
        },
        "deduplication": {
            "true_positive_pairs": len(predicted & expected),
            "predicted_pairs": len(predicted),
            "expected_pairs": len(expected),
            "false_variant_merges": len(predicted - expected),
            "source_offers_preserved": sum(len(p["offers"]) for p in grouped),
            "source_offers_expected": len(rows),
        },
    }
    state = json.loads(Path(".local/rfq/phase2-evaluation-state.json").read_text())
    provider = Embeddings()
    queries = [
        q
        for q in json.loads(
            Path("data/evaluation/product-catalog/queries.json").read_text()
        )
        if q["split"] in {"dev", "validation"}
    ][:12]
    times = []
    for q in queries:
        measured = retrieve(
            state["workspace"], [state["version"]], q["query"], "reranked", provider
        )
        times.append({"id": q["id"], "timings": measured["timings"]})
    values = sorted(r["timings"]["total_ms"] for r in times)
    result["uncached_hybrid"] = {
        "queries": times,
        "actual_query_embedding_calls": len(times),
        "median_ms": statistics.median(values),
        "p95_ms": values[math.ceil(0.95 * len(values)) - 1],
        "scope": "fresh real embeddings per query, dev queries only; no query-vector cache",
    }
    client = httpx.Client(timeout=120, trust_env=False)
    model = provider.model
    client.post(
        "http://localhost:11434/api/generate", json={"model": model, "keep_alive": 0}
    ).raise_for_status()
    model_runs = []
    for batch in [1, 32, 32]:
        started = time.perf_counter()
        response = client.post(
            "http://localhost:11434/api/embed",
            json={
                "model": model,
                "input": [
                    "search_document: " + canonical_text(rows[i]) for i in range(batch)
                ],
                "truncate": False,
            },
        )
        response.raise_for_status()
        payload = response.json()
        assert len(payload["embeddings"]) == batch and all(
            len(v) == 768 for v in payload["embeddings"]
        )
        model_runs.append(
            {
                "batch_size": batch,
                "cold": len(model_runs) == 0,
                "wall_ms": (time.perf_counter() - started) * 1000,
                **{
                    k: payload.get(k)
                    for k in ["total_duration", "load_duration", "prompt_eval_count"]
                },
            }
        )
    result["embedding_cold_warm"] = model_runs
    with connection() as conn:
        result["vector_storage"] = conn.execute(
            "select count(*) as vectors,sum(pg_column_size(embedding)) as vector_bytes from procurement.catalog_products where version_id=%s",
            (state["version"],),
        ).fetchone()
    (root / "final/additional-analysis.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k not in ["uncached_hybrid", "embedding_cold_warm"]
            }
        )
    )
    print(
        "uncached median/P95:",
        result["uncached_hybrid"]["median_ms"],
        result["uncached_hybrid"]["p95_ms"],
    )


if __name__ == "__main__":
    main()
