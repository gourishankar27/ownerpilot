from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from psycopg.types.json import Jsonb
from starlette.concurrency import run_in_threadpool

from .auth import Identity, authenticate
from .config import settings
from .contracts import (
    AuditDto,
    DetailDto,
    DocumentDto,
    JobDto,
    ListDto,
    RfqDto,
    CreateRfq,
    EditRequest,
    FieldValue,
    HEADER_FIELDS,
    ITEM_FIELDS,
    LineItem,
    ProcessRequest,
    RevisionRequest,
)
from .db import audit, connection
from .provider import OllamaProvider, ProviderError
from .repository import ACTIVE_STATES, editable, items, load_rfq, save_item
from .storage import DocumentError, LocalStorage, fingerprint, safe_name
from .parsers import validate_upload
from .validation import approval_issues, normalize

router = APIRouter(
    prefix="/api",
    tags=["RFQ Intelligence"],
    responses={
        401: {"description": "Authenticated session required"},
        403: {"description": "Workspace membership or role denied"},
        404: {"description": "Resource not visible in workspace"},
        409: {
            "description": "Stale revision, duplicate, active processing or immutable approval"
        },
        413: {"description": "Upload byte limit exceeded"},
        422: {"description": "Invalid fields, document or approval requirements"},
        503: {"description": "Required local service unavailable"},
    },
)


@router.get("/rfq-health")
async def health(identity: Identity = Depends(authenticate)):
    import asyncio
    from redis import Redis
    from .worker import celery

    try:
        with connection() as conn:
            conn.execute("select 1")
        database = True
    except Exception:
        database = False

    def infrastructure():
        try:
            redis = bool(
                Redis.from_url(
                    settings().redis_url, socket_timeout=2, socket_connect_timeout=2
                ).ping()
            )
            workers = bool(celery.control.ping(timeout=1)) if redis else False
            return redis, workers
        except Exception:
            return False, False

    redis, worker = await asyncio.to_thread(infrastructure)
    try:
        model = await OllamaProvider().health()
    except ProviderError:
        model = {
            "available": False,
            "reason": "Only local Ollama endpoints are allowed.",
        }
    return {"database": database, "redis": redis, "worker": worker, "model": model}


@router.post("/rfqs", status_code=201, response_model=RfqDto)
def create(payload: CreateRfq, identity: Identity = Depends(authenticate)):
    identity.require_write()
    header = {}
    if payload.customer_name:
        header["customer_name"] = normalize(
            "customer_name", payload.customer_name, corrected=True
        ).model_dump(mode="json")
    with connection() as conn:
        rfq = conn.execute(
            "insert into procurement.rfqs(id,workspace_id,title,created_by,header) values(%s,%s,%s,%s,%s) returning *",
            (
                uuid4(),
                identity.workspace_id,
                payload.title.strip(),
                identity.user_id,
                Jsonb(header),
            ),
        ).fetchone()
        audit(conn, rfq, identity.user_id, "rfq_created")
        return rfq


@router.get("/rfqs", response_model=ListDto)
def listing(
    search: str = Query("", max_length=160),
    status: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
    identity: Identity = Depends(authenticate),
):
    with connection() as conn:
        where = "workspace_id=%s and title ilike %s and (%s::text is null or status=%s)"
        args = (identity.workspace_id, "%" + search + "%", status, status)
        rows = conn.execute(
            "select * from procurement.rfqs where "
            + where
            + " order by updated_at desc limit %s offset %s",
            (*args, limit, offset),
        ).fetchall()
        total = conn.execute(
            "select count(*) as count from procurement.rfqs where " + where, args
        ).fetchone()["count"]
        counts = conn.execute(
            "select status,count(*) as count from procurement.rfqs where workspace_id=%s group by status",
            (identity.workspace_id,),
        ).fetchall()
        jobs = conn.execute(
            "select state,count(*) as count from procurement.rfq_processing_jobs where workspace_id=%s group by state",
            (identity.workspace_id,),
        ).fetchall()
    return {
        "items": rows,
        "total": total,
        "counts": {r["status"]: r["count"] for r in counts},
        "jobs": {r["state"]: r["count"] for r in jobs},
        "limit": limit,
        "offset": offset,
    }


@router.get("/rfqs/{rfq_id}", response_model=DetailDto)
def detail(rfq_id: UUID, identity: Identity = Depends(authenticate)):
    with connection() as conn:
        rfq = load_rfq(conn, rfq_id, identity.workspace_id)
        lines = items(conn, rfq)
        rfq["items"] = [i.model_dump(mode="json") for i in lines]
        rfq["documents"] = conn.execute(
            "select * from procurement.rfq_documents where rfq_id=%s order by created_at limit 50",
            (rfq_id,),
        ).fetchall()
        rfq["jobs"] = conn.execute(
            "select * from procurement.rfq_processing_jobs where rfq_id=%s order by created_at desc limit 20",
            (rfq_id,),
        ).fetchall()
        rfq["runs"] = conn.execute(
            "select id,job_id,schema_version,metadata,created_at from procurement.rfq_extraction_runs where rfq_id=%s order by created_at desc limit 20",
            (rfq_id,),
        ).fetchall()
        rfq["approval_issues"] = approval_issues(
            {k: FieldValue.model_validate(v) for k, v in rfq["header"].items()}, lines
        )
        rfq["role"] = identity.role
        return rfq


def store_upload(rfq_id, identity, revision, filename, mime, content):
    try:
        extension = validate_upload(filename, mime, content)
    except DocumentError as exc:
        raise HTTPException(422, str(exc)) from None
    digest = fingerprint(content)
    with connection() as conn:
        rfq = load_rfq(conn, rfq_id, identity.workspace_id, True)
        editable(conn, rfq, revision)
        duplicate = conn.execute(
            "select id from procurement.rfq_documents where workspace_id=%s and fingerprint=%s",
            (identity.workspace_id, digest),
        ).fetchone()
        if duplicate:
            raise HTTPException(409, "This document already exists in your workspace.")
        count = conn.execute(
            "select count(*) as count from procurement.rfq_documents where rfq_id=%s",
            (rfq_id,),
        ).fetchone()["count"]
        if count >= settings().max_documents:
            raise HTTPException(422, "Document count limit reached.")
        identifier = uuid4()
        # Files are immutable and never web served. Failed commits may leave an orphan,
        # but cannot expose an uncommitted file or corrupt an existing document.
        LocalStorage().put(identity.workspace_id, str(identifier), content)
        doc = conn.execute(
            "insert into procurement.rfq_documents(id,rfq_id,workspace_id,filename,extension,fingerprint,size_bytes,uploaded_by) values(%s,%s,%s,%s,%s,%s,%s,%s) returning *",
            (
                identifier,
                rfq_id,
                identity.workspace_id,
                safe_name(filename),
                extension,
                digest,
                len(content),
                identity.user_id,
            ),
        ).fetchone()
        conn.execute(
            "update procurement.rfqs set revision=revision+1,updated_at=now() where id=%s",
            (rfq_id,),
        )
        audit(
            conn,
            rfq,
            identity.user_id,
            "document_uploaded",
            {"document_id": str(identifier), "fingerprint": digest},
        )
        return doc


@router.post("/rfqs/{rfq_id}/documents", status_code=201, response_model=DocumentDto)
async def upload(
    rfq_id: UUID,
    revision: int = Form(...),
    file: UploadFile = File(...),
    identity: Identity = Depends(authenticate),
):
    identity.require_write()
    content = bytearray()
    while part := await file.read(1024 * 1024):
        content.extend(part)
        if len(content) > settings().max_file_bytes:
            raise HTTPException(413, "File exceeds the configured upload limit.")
    return await run_in_threadpool(
        store_upload,
        rfq_id,
        identity,
        revision,
        file.filename or "document",
        file.content_type,
        bytes(content),
    )


@router.get("/rfqs/{rfq_id}/documents", response_model=list[DocumentDto])
def documents(rfq_id: UUID, identity: Identity = Depends(authenticate)):
    with connection() as conn:
        load_rfq(conn, rfq_id, identity.workspace_id)
        return conn.execute(
            "select * from procurement.rfq_documents where rfq_id=%s order by created_at limit 50",
            (rfq_id,),
        ).fetchall()


@router.get("/rfqs/{rfq_id}/documents/{document_id}/download")
def download(
    rfq_id: UUID, document_id: UUID, identity: Identity = Depends(authenticate)
):
    with connection() as conn:
        load_rfq(conn, rfq_id, identity.workspace_id)
        doc = conn.execute(
            "select * from procurement.rfq_documents where id=%s and rfq_id=%s and workspace_id=%s",
            (document_id, rfq_id, identity.workspace_id),
        ).fetchone()
    if not doc:
        raise HTTPException(404, "Document not found.")
    return FileResponse(
        LocalStorage().path(identity.workspace_id, str(document_id)),
        media_type="application/octet-stream",
        filename=doc["filename"],
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
    )


def enqueue(rfq_id, payload, identity, reprocess=False):
    identity.require_write()
    with connection() as conn:
        rfq = load_rfq(conn, rfq_id, identity.workspace_id, True)
        editable(conn, rfq, payload.revision)
        if reprocess and not payload.reason.strip():
            raise HTTPException(
                422,
                "Explain why this RFQ is being reprocessed; previous versions and corrections remain in history.",
            )
        count = conn.execute(
            "select count(*) as count from procurement.rfq_documents where rfq_id=%s",
            (rfq_id,),
        ).fetchone()["count"]
        if not count:
            raise HTTPException(422, "Upload a document before processing.")
        identifier = uuid4()
        job = conn.execute(
            "insert into procurement.rfq_processing_jobs(id,rfq_id,workspace_id,mode,base_revision,total_documents,requested_by) values(%s,%s,%s,%s,%s,%s,%s) returning *",
            (
                identifier,
                rfq_id,
                identity.workspace_id,
                payload.mode,
                rfq["revision"],
                count,
                identity.user_id,
            ),
        ).fetchone()
        audit(
            conn,
            rfq,
            identity.user_id,
            "reprocess_queued" if reprocess else "processing_queued",
            {"job_id": str(identifier), "reason": payload.reason},
        )
    # Database outbox is authoritative. Broker outage cannot lose accepted work.
    try:
        from .worker import process

        process.apply_async(args=[str(identifier)], retry=False)
    except Exception:
        job["dispatch_warning"] = (
            "Broker unavailable. Job persisted; the dispatcher will recover it when services return."
        )
    return job


@router.post("/rfqs/{rfq_id}/process", status_code=202, response_model=JobDto)
def process(
    rfq_id: UUID, payload: ProcessRequest, identity: Identity = Depends(authenticate)
):
    return enqueue(rfq_id, payload, identity)


@router.post("/rfqs/{rfq_id}/reprocess", status_code=202, response_model=JobDto)
def reprocess(
    rfq_id: UUID, payload: ProcessRequest, identity: Identity = Depends(authenticate)
):
    return enqueue(rfq_id, payload, identity, True)


@router.get("/rfqs/{rfq_id}/jobs", response_model=list[JobDto])
def jobs(
    rfq_id: UUID,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    identity: Identity = Depends(authenticate),
):
    with connection() as conn:
        load_rfq(conn, rfq_id, identity.workspace_id)
        return conn.execute(
            "select * from procurement.rfq_processing_jobs where rfq_id=%s order by created_at desc limit %s offset %s",
            (rfq_id, limit, offset),
        ).fetchall()


@router.get("/rfq-jobs/{job_id}", response_model=JobDto)
def job_detail(job_id: UUID, identity: Identity = Depends(authenticate)):
    with connection() as conn:
        job = conn.execute(
            "select * from procurement.rfq_processing_jobs where id=%s and workspace_id=%s",
            (job_id, identity.workspace_id),
        ).fetchone()
    if not job:
        raise HTTPException(404, "Processing job not found.")
    return job


@router.post("/rfq-jobs/{job_id}/cancel")
def cancel(job_id: UUID, identity: Identity = Depends(authenticate)):
    identity.require_write()
    with connection() as conn:
        job = conn.execute(
            "select * from procurement.rfq_processing_jobs where id=%s and workspace_id=%s",
            (job_id, identity.workspace_id),
        ).fetchone()
        if not job:
            raise HTTPException(404, "Processing job not found.")
        rfq = load_rfq(conn, job["rfq_id"], identity.workspace_id, True)
        conn.execute(
            "update procurement.rfq_processing_jobs set state='cancelled',finished_at=now() where id=%s and state=any(%s)",
            (job_id, list(ACTIVE_STATES)),
        )
        audit(conn, rfq, identity.user_id, "job_cancelled", {"job_id": str(job_id)})
    return {"cancelled": True}


@router.get("/rfqs/{rfq_id}/line-items", response_model=list[LineItem])
def line_items(
    rfq_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    identity: Identity = Depends(authenticate),
):
    with connection() as conn:
        rfq = load_rfq(conn, rfq_id, identity.workspace_id)
        return [
            i.model_dump(mode="json") for i in items(conn, rfq)[offset : offset + limit]
        ]


@router.patch("/rfqs/{rfq_id}/header")
def edit_header(
    rfq_id: UUID, payload: EditRequest, identity: Identity = Depends(authenticate)
):
    identity.require_write()
    if set(payload.fields) - set(HEADER_FIELDS) or not payload.reason.strip():
        raise HTTPException(
            422, "Use supported header fields and provide a review reason."
        )
    with connection() as conn:
        rfq = load_rfq(conn, rfq_id, identity.workspace_id, True)
        editable(conn, rfq, payload.revision)
        original = dict(rfq["header"])
        for name, raw in payload.fields.items():
            if raw is not None and len(raw) > 4000:
                raise HTTPException(422, "Field too long.")
            previous = FieldValue.model_validate(rfq["header"].get(name, {}))
            corrected = normalize(name, raw, previous.evidence, True)
            corrected.raw = previous.raw
            corrected.corrected = (
                previous.corrected
                or corrected.value != previous.value
                or (previous.raw is not None and corrected.value is None)
            )
            rfq["header"][name] = corrected.model_dump(mode="json")
        conn.execute(
            "update procurement.rfqs set header=%s,revision=revision+1,updated_at=now() where id=%s",
            (Jsonb(rfq["header"]), rfq_id),
        )
        audit(
            conn,
            rfq,
            identity.user_id,
            "header_reviewed",
            {"before": original, "after": rfq["header"], "reason": payload.reason},
            rfq["current_run_id"],
        )
    return {"saved": True, "revision": payload.revision + 1}


def review_item(conn, rfq, item, payload, identity):
    original = item.model_dump(mode="json")
    if set(payload.fields) - set(ITEM_FIELDS) or not payload.reason.strip():
        raise HTTPException(
            422, "Use supported item fields and provide a review reason."
        )
    for name, raw in payload.fields.items():
        if raw is not None and len(raw) > 4000:
            raise HTTPException(422, "Field too long.")
        previous = item.fields.get(name, FieldValue())
        corrected = normalize(name, raw, previous.evidence, True)
        if item.extraction_method != "human":
            corrected.raw = previous.raw
        corrected.corrected = (
            previous.corrected
            or corrected.value != previous.value
            or (previous.raw is not None and corrected.value is None)
        )
        item.fields[name] = corrected
    item.review_status = payload.review_status
    save_item(conn, rfq, item)
    conn.execute(
        "update procurement.rfqs set revision=revision+1,updated_at=now() where id=%s",
        (rfq["id"],),
    )
    audit(
        conn,
        rfq,
        identity.user_id,
        "line_reviewed",
        {
            "before": original,
            "after": item.model_dump(mode="json"),
            "reason": payload.reason,
        },
        rfq["current_run_id"],
    )
    return {"saved": True, "revision": payload.revision + 1}


@router.patch("/rfqs/{rfq_id}/line-items/{item_id}")
def edit_item(
    rfq_id: UUID,
    item_id: UUID,
    payload: EditRequest,
    identity: Identity = Depends(authenticate),
):
    identity.require_write()
    with connection() as conn:
        rfq = load_rfq(conn, rfq_id, identity.workspace_id, True)
        editable(conn, rfq, payload.revision)
        item = next((i for i in items(conn, rfq) if i.id == str(item_id)), None)
        if not item:
            raise HTTPException(
                404, "Line item not found in current extraction version."
            )
        return review_item(conn, rfq, item, payload, identity)


@router.post("/rfqs/{rfq_id}/line-items", status_code=201)
def add_item(
    rfq_id: UUID, payload: EditRequest, identity: Identity = Depends(authenticate)
):
    identity.require_write()
    with connection() as conn:
        rfq = load_rfq(conn, rfq_id, identity.workspace_id, True)
        editable(conn, rfq, payload.revision)
        if not rfq["current_run_id"]:
            raise HTTPException(
                409, "Process the documents before adding a reviewed row."
            )
        if len(items(conn, rfq)) >= 2000:
            raise HTTPException(422, "Line item limit reached.")
        item = LineItem(
            id=str(uuid4()),
            fields={name: FieldValue() for name in ITEM_FIELDS},
            extraction_method="human",
        )
        return review_item(conn, rfq, item, payload, identity)


@router.get("/rfqs/{rfq_id}/evidence")
def evidence(rfq_id: UUID, identity: Identity = Depends(authenticate)):
    with connection() as conn:
        rfq = load_rfq(conn, rfq_id, identity.workspace_id)
        fields = [
            ("header", name, FieldValue.model_validate(value))
            for name, value in rfq["header"].items()
        ]
        fields += [
            (item.id, name, field)
            for item in items(conn, rfq)
            for name, field in item.fields.items()
        ]
        return [
            {"item_id": item_id, "field": name, **e.model_dump(mode="json")}
            for item_id, name, field in fields
            for e in field.evidence
        ]


@router.post("/rfqs/{rfq_id}/approve")
def approve(
    rfq_id: UUID, payload: RevisionRequest, identity: Identity = Depends(authenticate)
):
    identity.require_approve()
    with connection() as conn:
        rfq = load_rfq(conn, rfq_id, identity.workspace_id, True)
        editable(conn, rfq, payload.revision)
        issues = approval_issues(
            {k: FieldValue.model_validate(v) for k, v in rfq["header"].items()},
            items(conn, rfq),
        )
        if issues or not rfq["current_run_id"]:
            raise HTTPException(
                422,
                {
                    "message": "Resolve review requirements before approval.",
                    "issues": issues,
                },
            )
        conn.execute(
            "update procurement.rfqs set status='approved',approved_by=%s,approved_at=now(),revision=revision+1,updated_at=now() where id=%s",
            (identity.user_id, rfq_id),
        )
        audit(
            conn,
            rfq,
            identity.user_id,
            "rfq_approved",
            {"revision": payload.revision, "reason": payload.reason},
            rfq["current_run_id"],
        )
    return {"approved": True, "revision": payload.revision + 1}


@router.get("/rfqs/{rfq_id}/audit", response_model=list[AuditDto])
def audit_history(
    rfq_id: UUID,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    identity: Identity = Depends(authenticate),
):
    with connection() as conn:
        load_rfq(conn, rfq_id, identity.workspace_id)
        return conn.execute(
            "select * from procurement.rfq_audit_events where rfq_id=%s order by id desc limit %s offset %s",
            (rfq_id, limit, offset),
        ).fetchall()
