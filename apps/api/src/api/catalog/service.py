import hashlib
import json
import time
import httpx

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from api.rfq.db import connection
from .core import (
    BM25,
    POLICY,
    TOKENIZER,
    canonical_text,
    comparison,
    manufacturer,
    compatibility,
    fuse,
    group_products,
)
from .embedding import Embeddings


def audit(conn, workspace, actor, event, subject, details=None):
    conn.execute(
        "insert into procurement.catalog_audit_events(workspace_id,actor,event,subject,details) values(%s,%s,%s,%s,%s)",
        (workspace, actor, event, subject, Jsonb(details or {})),
    )


def owned(conn, table, identifier, workspace, lock=False):
    # Table names are internal constants, never request input.
    if table not in {"product_catalogs", "catalog_versions", "catalog_match_runs"}:
        raise ValueError("Unknown internal catalog table")
    row = conn.execute(
        f"select * from procurement.{table} where id=%s and workspace_id=%s"
        + (" for update" if lock else ""),
        (identifier, workspace),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Catalog resource not found")
    return row


def build(version_id):
    started = time.perf_counter()
    with connection() as lock:
        acquired = lock.execute(
            "select pg_try_advisory_lock(hashtextextended(%s,0)) as ok",
            (str(version_id),),
        ).fetchone()["ok"]
        lock.commit()
        if not acquired:
            return "already_running"
        try:
            with connection() as conn:
                version = conn.execute(
                    "select * from procurement.catalog_versions where id=%s for update",
                    (version_id,),
                ).fetchone()
                if not version or version["state"] in {
                    "published",
                    "superseded",
                    "preview",
                }:
                    return "terminal"
                if version["attempts"] >= 3:
                    conn.execute(
                        "update procurement.catalog_versions set state='failed',error='attempt_limit' where id=%s",
                        (version_id,),
                    )
                    return "attempt_limit"
                conn.execute(
                    "update procurement.catalog_versions set state='building',attempts=attempts+1,started_at=now(),error=null where id=%s",
                    (version_id,),
                )
            try:
                provider = Embeddings()
                health = provider.health()
                products = group_products(version["rows"])
                vectors, calls = [], 0
                lexical_started = time.perf_counter()
                BM25([canonical_text(p["data"]) for p in products])
                bm25_ms = (time.perf_counter() - lexical_started) * 1000
                for offset in range(0, len(products), 32):
                    if time.perf_counter() - started > 1200:
                        raise ValueError("Index time limit")
                    batch = products[offset : offset + 32]
                    vectors.extend(
                        provider.encode(
                            [canonical_text(p["data"]) for p in batch],
                            digest=health["digest"],
                        )
                    )
                    calls += 1
                    with connection() as conn:
                        conn.execute(
                            "update procurement.catalog_versions set started_at=now() where id=%s",
                            (version_id,),
                        )
                with connection() as conn:
                    catalog = owned(
                        conn,
                        "product_catalogs",
                        version["catalog_id"],
                        version["workspace_id"],
                        True,
                    )
                    # A newer confirmed import wins; old work never supersedes it.
                    newer = conn.execute(
                        "select id from procurement.catalog_versions where catalog_id=%s and created_at>%s and state in ('queued','building','published') limit 1",
                        (version["catalog_id"], version["created_at"]),
                    ).fetchone()
                    if newer:
                        conn.execute(
                            "update procurement.catalog_versions set state='superseded',finished_at=now() where id=%s",
                            (version_id,),
                        )
                        return "superseded"
                    for product, vector in zip(products, vectors):
                        content_hash = hashlib.sha256(
                            canonical_text(product["data"]).encode()
                        ).hexdigest()
                        conn.execute(
                            "insert into procurement.catalog_products(version_id,id,workspace_id,identity_hash,data,offers,content_hash,embedding) values(%s,%s,%s,%s,%s,%s,%s,%s::vector) on conflict(version_id,id) do nothing",
                            (
                                version_id,
                                product["id"],
                                version["workspace_id"],
                                product["id"],
                                Jsonb(product["data"]),
                                Jsonb(product["offers"]),
                                content_hash,
                                json.dumps(vector),
                            ),
                        )
                    if catalog["active_version"]:
                        conn.execute(
                            "update procurement.catalog_versions set state='superseded' where id=%s",
                            (catalog["active_version"],),
                        )
                    metadata = {
                        **health,
                        "bm25": TOKENIZER,
                        "source_rows": len(version["rows"]),
                        "canonical_products": len(products),
                        "offers": sum(len(p["offers"]) for p in products),
                        "embedding_calls": calls,
                        "bm25_build_ms": bm25_ms,
                        "build_ms": (time.perf_counter() - started) * 1000,
                    }
                    conn.execute(
                        "update procurement.catalog_versions set state='published',model=%s,digest=%s,metadata=%s,finished_at=now() where id=%s",
                        (
                            health["model"],
                            health["digest"],
                            Jsonb(metadata),
                            version_id,
                        ),
                    )
                    conn.execute(
                        "update procurement.product_catalogs set active_version=%s where id=%s",
                        (version_id, version["catalog_id"]),
                    )
                    audit(
                        conn,
                        version["workspace_id"],
                        version["requested_by"],
                        "index_published",
                        version_id,
                        metadata,
                    )
                return "published"
            except Exception as exc:
                with connection() as conn:
                    conn.execute(
                        "update procurement.catalog_versions set state='failed',error=%s,finished_at=now() where id=%s",
                        (type(exc).__name__, version_id),
                    )
                return "failed"
        finally:
            lock.execute(
                "select pg_advisory_unlock(hashtextextended(%s,0))", (str(version_id),)
            )


def retrieve(workspace, versions, query, method="reranked", provider=None):
    started = time.perf_counter()
    vector_required = method not in {"exact", "bm25", "sql", "exact_bm25"}
    health = {"invoked": False, "reason": "retrieval method has no vector channel"}
    if vector_required:
        try:
            provider = provider or Embeddings()
            health = provider.health()
        except (ValueError, RuntimeError, httpx.HTTPError) as exc:
            raise RuntimeError(
                "Requested vector channel unavailable; no hybrid fallback executed"
            ) from exc
    if not versions or len(versions) > 10:
        raise HTTPException(422, "Select 1 to 10 published catalogs")
    with connection() as conn:
        selected = [
            owned(conn, "catalog_versions", version, workspace) for version in versions
        ]
        if any(
            v["state"] != "published"
            or (
                vector_required
                and (v["digest"] != health["digest"] or v["model"] != health["model"])
            )
            for v in selected
        ):
            raise HTTPException(
                409, "Index is stale, unpublished or uses another embedding model"
            )
        products = conn.execute(
            "select version_id,id,data,offers,content_hash from procurement.catalog_products where workspace_id=%s and version_id=any(%s::uuid[]) order by id,version_id limit 5001",
            (workspace, versions),
        ).fetchall()
        if len(products) > 5000:
            raise HTTPException(422, "Search collection limit: 5000 canonical records")
        # Collapse identical identities across sources while preserving all offer provenance.
        index = {}
        for p in products:
            p = dict(p)
            key = p["id"]
            if key not in index:
                index[key] = {**p, "sources": []}
                index[key]["offers"] = []
            index[key]["sources"].append(
                {"version_id": str(p["version_id"]), "content_hash": p["content_hash"]}
            )
            index[key]["offers"].extend(
                {**offer, "version_id": str(p["version_id"])} for offer in p["offers"]
            )
        timings = {}
        channel_started = time.perf_counter()
        exact = [
            (k, 1)
            for k, p in index.items()
            if method in {"exact", "exact_bm25", "hybrid", "reranked"}
            and query.get("mpn")
            and comparison(query["mpn"]) == comparison(p["data"]["mpn"])
            and query.get("manufacturer")
            and manufacturer(query["manufacturer"])
            == manufacturer(p["data"]["manufacturer"])
        ]
        timings["exact_ms"] = (time.perf_counter() - channel_started) * 1000
        text = (
            " ".join(
                str(query.get(k) or "")
                for k in ("manufacturer", "mpn", "description", "category")
            )
            + " "
            + json.dumps(query.get("specs", {}), sort_keys=True)
        )
        channel_started = time.perf_counter()
        lexical = (
            BM25(
                [
                    canonical_text(p["data"]) + " " + p["data"]["mpn"]
                    for p in index.values()
                ]
            ).scores(text)
            if method in {"bm25", "exact_bm25", "bm25_vector", "hybrid", "reranked"}
            else []
        )
        bm25 = sorted(
            [(k, s) for k, s in zip(index, lexical) if s > 0],
            key=lambda x: (-x[1], x[0]),
        )[:50]
        timings["bm25_ms"] = (time.perf_counter() - channel_started) * 1000
        channel_started = time.perf_counter()
        vector = []
        if method not in {"exact", "bm25", "sql", "exact_bm25"}:
            try:
                embedding = provider.encode(
                    [text], query=True, digest=health["digest"]
                )[0]
            except (ValueError, RuntimeError, httpx.HTTPError) as exc:
                raise RuntimeError(
                    "Requested vector channel failed; no hybrid fallback executed"
                ) from exc
            vector_rows = conn.execute(
                "select id,1-(embedding <=> %s::vector) as similarity from procurement.catalog_products where workspace_id=%s and version_id=any(%s::uuid[]) order by embedding <=> %s::vector,id limit 100",
                (json.dumps(embedding), workspace, versions, json.dumps(embedding)),
            ).fetchall()
            seen = set()
            for row in vector_rows:
                if row["id"] not in seen:
                    vector.append((row["id"], row["similarity"]))
                    seen.add(row["id"])
            vector = vector[:50]
        timings["vector_ms"] = (time.perf_counter() - channel_started) * 1000
        if method == "sql":
            sql_rows = conn.execute(
                "select id,ts_rank_cd(to_tsvector('simple',data->>'description'),plainto_tsquery('simple',%s)) as score from procurement.catalog_products where workspace_id=%s and version_id=any(%s::uuid[]) order by score desc,id limit 50",
                (query.get("description", ""), workspace, versions),
            ).fetchall()
            channels = {
                "sql_fts": [(r["id"], r["score"]) for r in sql_rows if r["score"] > 0]
            }
        else:
            channels = {
                k: v
                for k, v in {"exact": exact, "bm25": bm25, "vector": vector}.items()
                if k
                in {
                    "exact": {"exact"},
                    "bm25": {"bm25"},
                    "vector": {"vector"},
                    "exact_bm25": {"exact", "bm25"},
                    "bm25_vector": {"bm25", "vector"},
                    "hybrid": {"exact", "bm25", "vector"},
                    "reranked": {"exact", "bm25", "vector"},
                }[method]
            }
        channel_started = time.perf_counter()
        candidates = fuse(channels, 50)
        timings["fusion_ms"] = (time.perf_counter() - channel_started) * 1000
        channel_started = time.perf_counter()
        for candidate in candidates:
            product = index[candidate["id"]]
            candidate.update(
                {
                    "product": product["data"],
                    "offers": product["offers"],
                    "sources": product["sources"],
                    "compatibility": compatibility(query, product["data"]),
                }
            )
        if method == "reranked":
            order = {
                "exact": 0,
                "compatible_alternative": 1,
                "possible_alternative": 2,
                "insufficient_information": 3,
                "incompatible": 4,
            }
            candidates.sort(
                key=lambda c: (
                    order[c["compatibility"]["status"]],
                    -c["score"],
                    c["id"],
                )
            )
        timings["rerank_ms"] = (time.perf_counter() - channel_started) * 1000
        candidates = candidates[:20]
        reliable = [
            c
            for c in candidates
            if c["compatibility"]["status"] in {"exact", "compatible_alternative"}
        ]
        return {
            "policy": POLICY,
            "method": method,
            "executed_channels": list(channels),
            "execution_status": "complete",
            "model": health,
            "versions": [str(v) for v in versions],
            "query": query,
            "candidates": candidates,
            "outcome": "ambiguous"
            if len([c for c in reliable if c["compatibility"]["exact_identity"]]) > 1
            else "candidates_available"
            if reliable
            else "no_reliable_match",
            "timings": {**timings, "total_ms": (time.perf_counter() - started) * 1000},
            "bm25": TOKENIZER,
            "fusion": {"constant": 60, "weights": "equal", "candidate_limit": 50},
            "reranker": "deterministic-compatibility/1",
        }
