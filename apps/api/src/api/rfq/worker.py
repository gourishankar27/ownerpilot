from __future__ import annotations

import asyncio
import json
import logging
import time
import psycopg

from celery import Celery
from psycopg.types.json import Jsonb

from .config import settings
from .contracts import ParsedDocument
from .db import connection
from .extraction import extract
from .parsers import PARSER_VERSION, parse_document
from .provider import ProviderError
from .repository import ACTIVE_STATES, publish
from .storage import DocumentError, LocalStorage, fingerprint

cfg = settings()
celery = Celery("ownerpilot_rfq", broker=cfg.redis_url)
celery.conf.update(
    task_ignore_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=2,
    broker_transport_options={
        "visibility_timeout": cfg.job_timeout + 300,
        "socket_connect_timeout": 2,
        "socket_timeout": 2,
        "retry_on_timeout": False,
    },
    task_time_limit=cfg.job_timeout + 30,
    task_soft_time_limit=cfg.job_timeout,
    beat_schedule={"recover-rfq-outbox": {"task": "rfq.dispatch", "schedule": 15.0}},
)
logger = logging.getLogger("ownerpilot.rfq")


def log_stage(job, stage, **metadata):
    logger.info(
        json.dumps(
            {
                "rfq_id": str(job["rfq_id"]),
                "job_id": str(job["id"]),
                "stage": stage,
                **metadata,
            }
        )
    )


def stage(job, state, completed=0):
    with connection() as conn:
        row = conn.execute(
            "update procurement.rfq_processing_jobs set state=%s,stage_started_at=now(),completed_documents=%s where id=%s and state <> 'cancelled' returning id",
            (state, completed, job["id"]),
        ).fetchone()
    if not row:
        raise ProviderError("job_cancelled")
    log_stage(job, state, completed_documents=completed)


def process_job(job_id: str):
    start = time.perf_counter()
    # Session advisory lock lasts across stage commits and is released on worker death.
    with connection() as lock_conn:
        locked = lock_conn.execute(
            "select pg_try_advisory_lock(hashtextextended(%s,0)) as acquired",
            (str(job_id),),
        ).fetchone()["acquired"]
        lock_conn.commit()
        if not locked:
            return "already_running"
        try:
            with connection() as conn:
                job = conn.execute(
                    "select * from procurement.rfq_processing_jobs where id=%s for update",
                    (job_id,),
                ).fetchone()
                if not job or job["state"] not in ACTIVE_STATES:
                    return "terminal"
                if job["attempts"] >= cfg.max_attempts:
                    conn.execute(
                        "update procurement.rfq_processing_jobs set state='failed',error_category='attempt_limit',error_message='Worker recovery attempt limit reached.',finished_at=now(),retryable=false where id=%s",
                        (job_id,),
                    )
                    return "attempt_limit"
                conn.execute(
                    "update procurement.rfq_processing_jobs set attempts=attempts+1,state='validating',started_at=now(),stage_started_at=now() where id=%s",
                    (job_id,),
                )
                job["attempts"] += 1
                docs = conn.execute(
                    "select * from procurement.rfq_documents where rfq_id=%s and workspace_id=%s order by created_at,id",
                    (job["rfq_id"], job["workspace_id"]),
                ).fetchall()
            try:
                parsed = []
                for doc in docs:
                    if time.perf_counter() - start > cfg.job_timeout:
                        raise ProviderError("job_timeout", True)
                    stage(job, "parsing", len(parsed))
                    with connection() as conn:
                        cache = conn.execute(
                            "select content from procurement.rfq_document_pages where document_id=%s and parser_version=%s",
                            (doc["id"], PARSER_VERSION),
                        ).fetchone()
                    if cache:
                        page_data = ParsedDocument.model_validate(cache["content"])
                        page_data.duration_ms = 0
                        page_data.ocr_ms = 0
                    else:
                        content = LocalStorage().read(
                            str(doc["workspace_id"]), str(doc["id"])
                        )
                        if fingerprint(content) != doc["fingerprint"]:
                            raise DocumentError("Stored document fingerprint mismatch.")
                        page_data = parse_document(
                            doc["filename"], content, str(doc["id"])
                        )
                        with connection() as conn:
                            conn.execute(
                                "insert into procurement.rfq_document_pages(document_id,parser_version,content) values(%s,%s,%s) on conflict do nothing",
                                (
                                    doc["id"],
                                    PARSER_VERSION,
                                    Jsonb(page_data.model_dump(mode="json")),
                                ),
                            )
                            conn.execute(
                                "update procurement.rfq_documents set status='parsed' where id=%s",
                                (doc["id"],),
                            )
                    parsed.append(page_data)
                stage(job, "extracting", len(parsed))
                remaining = max(1, cfg.job_timeout - (time.perf_counter() - start))

                async def bounded():
                    return await asyncio.wait_for(
                        extract(parsed, job["mode"]), timeout=remaining
                    )

                result = asyncio.run(bounded())
                result.metadata.update(
                    {
                        "documents": [
                            {
                                "id": d.document_id,
                                "fingerprint": d.fingerprint,
                                "parser": d.parser,
                                "pages": d.pages,
                                "ocr_pages": d.ocr_pages,
                            }
                            for d in parsed
                        ],
                        "duration_ms": (time.perf_counter() - start) * 1000,
                        "attempt": job["attempts"],
                    }
                )
                stage(job, "validating_results", len(parsed))
                with connection() as conn:
                    published = publish(conn, job, result)
                if not published:
                    log_stage(job, "cancelled")
                    return "cancelled"
                log_stage(
                    job,
                    "awaiting_review",
                    duration_ms=(time.perf_counter() - start) * 1000,
                    parser=PARSER_VERSION,
                    model=cfg.ollama_model or None,
                )
                return "awaiting_review"
            except Exception as exc:
                if isinstance(exc, ProviderError) and exc.category == "job_cancelled":
                    log_stage(job, "cancelled")
                    return "cancelled"
                category = (
                    exc.category
                    if isinstance(exc, ProviderError)
                    else "document_error"
                    if isinstance(exc, DocumentError)
                    else "job_timeout"
                    if isinstance(exc, TimeoutError)
                    else "processing_error"
                )
                retryable = (
                    getattr(
                        exc,
                        "retryable",
                        isinstance(
                            exc,
                            (ConnectionError, TimeoutError, psycopg.OperationalError),
                        ),
                    )
                    and job["attempts"] < cfg.max_attempts
                )
                message = (
                    str(exc)
                    if isinstance(exc, DocumentError)
                    else {
                        "model_unavailable": "Local model unavailable. Check Ollama and RFQ_OLLAMA_MODEL.",
                        "model_timeout": "Local inference timed out.",
                        "invalid_structured_output": "Model output failed schema validation; no results were published.",
                    }.get(
                        category,
                        "Processing failed. Check service health and retry; diagnostic category: "
                        + category,
                    )
                )
                with connection() as conn:
                    conn.execute(
                        "update procurement.rfq_processing_jobs set state=%s,error_category=%s,error_message=%s,retryable=%s,finished_at=case when %s then null else now() end,stage_started_at=now() where id=%s and state <> 'cancelled'",
                        (
                            "queued" if retryable else "failed",
                            category,
                            message,
                            retryable,
                            retryable,
                            job_id,
                        ),
                    )
                log_stage(
                    job,
                    "queued" if retryable else "failed",
                    failure_category=category,
                    retry_count=job["attempts"],
                )
                return "retry_queued" if retryable else "failed"
        finally:
            lock_conn.execute(
                "select pg_advisory_unlock(hashtextextended(%s,0))", (str(job_id),)
            )


@celery.task(name="rfq.process")
def process(job_id: str):
    return process_job(job_id)


@celery.task(name="rfq.dispatch")
def dispatch():
    with connection() as conn:
        rows = conn.execute(
            "select id from procurement.rfq_processing_jobs where (state='queued' and (stage_started_at is null or stage_started_at < now()-interval '30 seconds')) or (state=any(%s) and stage_started_at < now()-interval '60 seconds') order by created_at limit 100",
            (list(ACTIVE_STATES[1:]),),
        ).fetchall()
    for row in rows:
        process.apply_async(args=[str(row["id"])], expires=cfg.job_timeout)
    return len(rows)
