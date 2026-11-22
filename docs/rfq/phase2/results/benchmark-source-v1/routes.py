import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Form
from pydantic import BaseModel, ConfigDict, Field
from psycopg.types.json import Jsonb

from api.rfq.auth import Identity, authenticate
from api.rfq.db import connection
from api.rfq.repository import load_rfq, items
from .core import NORMALIZATION, parse_catalog, group_products
from .embedding import Embeddings
from .service import audit, owned, retrieve

router = APIRouter(prefix="/api", tags=["catalog"])


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CatalogCreate(Closed):
    name: str = Field(min_length=1, max_length=160)
    license: str = Field(min_length=1, max_length=300)


class Confirm(Closed):
    version_id: UUID
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class Search(Closed):
    revision: int = Field(ge=0)
    versions: list[UUID] = Field(min_length=1, max_length=10)


class Review(Closed):
    decision: str = Field(pattern=r"^(select|reject|no_match)$")
    product_id: str | None = Field(default=None, max_length=64)
    note: str = Field(min_length=1, max_length=1000)


def dispatch(version):
    from .worker import index_catalog

    try:
        index_catalog.apply_async(args=[str(version)])
    except Exception:
        # PostgreSQL is the durable outbox; beat retries queued jobs.
        pass


@router.get("/catalog-health")
def health(identity: Identity = Depends(authenticate)):
    try:
        return {
            "provider": Embeddings().health(),
            "index_readiness": "per catalog; provider health alone is insufficient",
        }
    except Exception:
        return {"provider": {"available": False}, "index_readiness": "unavailable"}


@router.post("/catalogs", status_code=201)
def create(payload: CatalogCreate, identity: Identity = Depends(authenticate)):
    identity.require_write()
    with connection() as conn:
        row = conn.execute(
            "insert into procurement.product_catalogs(workspace_id,name,license) values(%s,%s,%s) returning *",
            (identity.workspace_id, payload.name, payload.license),
        ).fetchone()
        audit(
            conn, identity.workspace_id, identity.user_id, "catalog_created", row["id"]
        )
        return row


@router.get("/catalogs")
def catalogs(
    identity: Identity = Depends(authenticate), limit: int = 25, offset: int = 0
):
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(422, "Invalid pagination")
    with connection() as conn:
        return conn.execute(
            "select c.*,v.state,v.metadata,v.error,v.finished_at from procurement.product_catalogs c left join procurement.catalog_versions v on v.id=c.active_version where c.workspace_id=%s order by c.created_at desc limit %s offset %s",
            (identity.workspace_id, limit, offset),
        ).fetchall()


@router.get("/catalogs/{catalog_id}")
def detail(catalog_id: UUID, identity: Identity = Depends(authenticate)):
    with connection() as conn:
        catalog = owned(conn, "product_catalogs", catalog_id, identity.workspace_id)
        versions = conn.execute(
            "select id,fingerprint,state,generation,attempts,model,digest,metadata,error,created_at,finished_at,specification from procurement.catalog_versions where catalog_id=%s and workspace_id=%s order by created_at desc limit 100",
            (catalog_id, identity.workspace_id),
        ).fetchall()
        return {"catalog": catalog, "versions": versions}


@router.post("/catalogs/{catalog_id}/imports/preview")
async def preview(
    catalog_id: UUID,
    file: UploadFile = File(...),
    mapping: str = Form("{}"),
    identity: Identity = Depends(authenticate),
):
    identity.require_write()
    with connection() as conn:
        owned(conn, "product_catalogs", catalog_id, identity.workspace_id)
    content = await file.read(10 * 1024 * 1024 + 1)
    try:
        mappings = json.loads(mapping)
        if not isinstance(mappings, dict) or len(mappings) > 40:
            raise ValueError("Invalid mapping")
        rows, detected = parse_catalog(file.filename or "", content, mappings)
    except Exception as exc:
        raise HTTPException(
            422, "Catalog validation failed: " + str(exc)[:300]
        ) from None
    spec = {
        "mapping": detected,
        "mapping_version": "catalog-mapping/1",
        "normalization": NORMALIZATION,
        "source_hash": hashlib.sha256(content).hexdigest(),
    }
    fingerprint = hashlib.sha256(
        content + json.dumps(spec, sort_keys=True).encode()
    ).hexdigest()
    grouped = group_products(rows)
    preview_counts = {
        "source_rows": len(rows),
        "canonical_products": len(grouped),
        "grouped_offers": len(rows) - len(grouped),
        "warning": "Same identifiers with differing specifications remain separate; review variant collisions.",
    }
    with connection() as conn:
        row = conn.execute(
            "insert into procurement.catalog_versions(catalog_id,workspace_id,fingerprint,specification,rows,requested_by,metadata) values(%s,%s,%s,%s,%s,%s,%s) on conflict(catalog_id,fingerprint) do update set fingerprint=excluded.fingerprint returning id,state",
            (
                catalog_id,
                identity.workspace_id,
                fingerprint,
                Jsonb(spec),
                Jsonb(rows),
                identity.user_id,
                Jsonb(preview_counts),
            ),
        ).fetchone()
        audit(
            conn,
            identity.workspace_id,
            identity.user_id,
            "import_preview",
            row["id"],
            preview_counts,
        )
    return {
        **row,
        "fingerprint": fingerprint,
        "specification": spec,
        "counts": preview_counts,
        "sample": rows[:5],
    }


@router.post("/catalogs/{catalog_id}/imports/confirm", status_code=202)
def confirm(
    catalog_id: UUID, payload: Confirm, identity: Identity = Depends(authenticate)
):
    identity.require_write()
    with connection() as conn:
        owned(conn, "product_catalogs", catalog_id, identity.workspace_id)
        version = owned(
            conn, "catalog_versions", payload.version_id, identity.workspace_id, True
        )
        if (
            version["catalog_id"] != catalog_id
            or version["fingerprint"] != payload.fingerprint
        ):
            raise HTTPException(409, "Preview/source specification changed")
        if version["state"] == "preview":
            conn.execute(
                "update procurement.catalog_versions set state='queued' where id=%s",
                (payload.version_id,),
            )
            audit(
                conn,
                identity.workspace_id,
                identity.user_id,
                "import_confirmed",
                payload.version_id,
            )
    dispatch(payload.version_id)
    return {
        "job_id": payload.version_id,
        "state": version["state"] if version["state"] != "preview" else "queued",
    }


@router.get("/catalog-import-jobs/{job_id}")
def job(job_id: UUID, identity: Identity = Depends(authenticate)):
    with connection() as conn:
        version = owned(conn, "catalog_versions", job_id, identity.workspace_id)
        return {k: v for k, v in version.items() if k != "rows"}


@router.post("/catalogs/{catalog_id}/rebuild-index", status_code=202)
def rebuild(catalog_id: UUID, identity: Identity = Depends(authenticate)):
    from uuid import uuid4

    identity.require_write()
    with connection() as conn:
        catalog = owned(
            conn, "product_catalogs", catalog_id, identity.workspace_id, True
        )
        if not catalog["active_version"]:
            raise HTTPException(409, "No published catalog")
        old = owned(
            conn, "catalog_versions", catalog["active_version"], identity.workspace_id
        )
        new = conn.execute(
            "insert into procurement.catalog_versions(catalog_id,workspace_id,fingerprint,specification,rows,requested_by,state,generation) values(%s,%s,%s,%s,%s,%s,'queued',%s) returning id",
            (
                catalog_id,
                identity.workspace_id,
                hashlib.sha256(
                    (old["fingerprint"] + str(uuid4())).encode()
                ).hexdigest(),
                Jsonb(old["specification"]),
                Jsonb(old["rows"]),
                identity.user_id,
                old["generation"] + 1,
            ),
        ).fetchone()
        audit(
            conn,
            identity.workspace_id,
            identity.user_id,
            "rebuild_requested",
            new["id"],
        )
    dispatch(new["id"])
    return {"job_id": new["id"]}


def approved_query(conn, rfq_id, item_id, identity, revision=None):
    rfq = load_rfq(conn, rfq_id, identity.workspace_id)
    if rfq["status"] != "approved" or (
        revision is not None and rfq["revision"] != revision
    ):
        raise HTTPException(409, "Search requires the current approved RFQ revision")
    item = next((i for i in items(conn, rfq) if i.id == str(item_id)), None)
    if not item:
        raise HTTPException(404, "Approved line item not found")
    if item.review_status != "reviewed":
        raise HTTPException(409, "Line must be reviewed")
    values = {name: field.value for name, field in item.fields.items()}
    for key in ("description", "mpn", "manufacturer"):
        field = item.fields.get(key)
        if field and field.value is not None and field.status != "validated":
            raise HTTPException(409, "Unresolved approved query field")
    specs = {}
    if values.get("specifications"):
        try:
            parsed = json.loads(values["specifications"])
            if isinstance(parsed, dict) and len(parsed) <= 40:
                specs = parsed
        except ValueError:
            pass  # Unstructured specifications stay explicit in the description.
    return rfq, {
        "manufacturer": values.get("manufacturer"),
        "mpn": values.get("mpn"),
        "description": (values.get("description") or "")
        + " "
        + (values.get("specifications") or ""),
        "specs": specs,
        "quantity": values.get("quantity"),
        "unit": values.get("unit"),
        "source_run": str(rfq["current_run_id"]),
    }


@router.post("/rfqs/{rfq_id}/line-items/{item_id}/matches", status_code=201)
def search(
    rfq_id: UUID,
    item_id: UUID,
    payload: Search,
    identity: Identity = Depends(authenticate),
):
    with connection() as conn:
        rfq, query = approved_query(conn, rfq_id, item_id, identity, payload.revision)
    try:
        result = retrieve(identity.workspace_id, payload.versions, query)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(503, str(exc)) from None
    with connection() as conn:
        approved_query(conn, rfq_id, item_id, identity, payload.revision)
        row = conn.execute(
            "insert into procurement.catalog_match_runs(workspace_id,rfq_id,item_id,revision,query,versions,result,created_by) values(%s,%s,%s,%s,%s,%s,%s,%s) returning id",
            (
                identity.workspace_id,
                rfq_id,
                item_id,
                rfq["revision"],
                Jsonb(query),
                Jsonb([str(v) for v in payload.versions]),
                Jsonb(result),
                identity.user_id,
            ),
        ).fetchone()
        audit(
            conn,
            identity.workspace_id,
            identity.user_id,
            "search_completed",
            row["id"],
            {"policy": result["policy"], "candidate_count": len(result["candidates"])},
        )
    return {"id": row["id"], **result}


@router.get("/rfqs/{rfq_id}/line-items/{item_id}/matches")
def history(rfq_id: UUID, item_id: UUID, identity: Identity = Depends(authenticate)):
    with connection() as conn:
        approved_query(conn, rfq_id, item_id, identity)
        return conn.execute(
            "select id,revision,created_at from procurement.catalog_match_runs where rfq_id=%s and item_id=%s and workspace_id=%s order by created_at desc limit 50",
            (rfq_id, item_id, identity.workspace_id),
        ).fetchall()


@router.get("/catalog-match-runs/{run_id}")
def match_run(run_id: UUID, identity: Identity = Depends(authenticate)):
    with connection() as conn:
        run = owned(conn, "catalog_match_runs", run_id, identity.workspace_id)
        reviews = conn.execute(
            "select * from procurement.catalog_match_reviews where run_id=%s order by created_at",
            (run_id,),
        ).fetchall()
        return {**run, "reviews": reviews}


@router.post("/catalog-match-runs/{run_id}/review", status_code=201)
def review(run_id: UUID, payload: Review, identity: Identity = Depends(authenticate)):
    identity.require_approve()
    with connection() as conn:
        run = owned(conn, "catalog_match_runs", run_id, identity.workspace_id, True)
        approved_query(conn, run["rfq_id"], run["item_id"], identity, run["revision"])
        for v in run["versions"]:
            version = owned(conn, "catalog_versions", v, identity.workspace_id)
            if version["state"] != "published":
                raise HTTPException(409, "Catalog changed; run another search")
        candidate = next(
            (c for c in run["result"]["candidates"] if c["id"] == payload.product_id),
            None,
        )
        if payload.decision != "no_match" and candidate is None:
            raise HTTPException(422, "Candidate does not belong to this run")
        if payload.decision == "select" and candidate["compatibility"][
            "status"
        ] not in {"exact", "compatible_alternative"}:
            raise HTTPException(422, "Candidate compatibility is not established")
        if payload.decision == "no_match" and payload.product_id:
            raise HTTPException(422, "No-match decisions cannot select a product")
        if conn.execute(
            "select id from procurement.catalog_match_reviews where run_id=%s and actor=%s",
            (run_id, identity.user_id),
        ).fetchone():
            raise HTTPException(
                409, "Review already recorded; run another search for a new decision"
            )
        row = conn.execute(
            "insert into procurement.catalog_match_reviews(run_id,actor,decision,product_id,note) values(%s,%s,%s,%s,%s) returning *",
            (
                run_id,
                identity.user_id,
                payload.decision,
                payload.product_id,
                payload.note,
            ),
        ).fetchone()
        audit(
            conn,
            identity.workspace_id,
            identity.user_id,
            "match_reviewed",
            run_id,
            payload.model_dump(),
        )
        return row


@router.get("/catalog-match-runs/{run_id}/audit")
def events(run_id: UUID, identity: Identity = Depends(authenticate)):
    with connection() as conn:
        owned(conn, "catalog_match_runs", run_id, identity.workspace_id)
        return conn.execute(
            "select * from procurement.catalog_audit_events where workspace_id=%s and subject=%s order by id",
            (identity.workspace_id, run_id),
        ).fetchall()
