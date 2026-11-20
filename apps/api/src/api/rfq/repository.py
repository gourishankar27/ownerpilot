from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from .contracts import Extraction, FieldValue, LineItem
from .db import audit

ACTIVE_STATES = ("queued", "validating", "parsing", "extracting", "validating_results")


def load_rfq(conn, identifier, workspace, lock=False):
    row = conn.execute(
        "select * from procurement.rfqs where id=%s and workspace_id=%s"
        + (" for update" if lock else ""),
        (identifier, workspace),
    ).fetchone()
    if not row:
        raise HTTPException(404, "RFQ not found.")
    return row


def editable(conn, rfq, revision):
    if rfq["revision"] != revision:
        raise HTTPException(409, "This RFQ changed. Reload before saving.")
    if rfq["status"] == "approved":
        raise HTTPException(
            409, "Approved RFQs are immutable. Create a new RFQ for a new request."
        )
    active = conn.execute(
        "select id from procurement.rfq_processing_jobs where rfq_id=%s and state=any(%s)",
        (rfq["id"], list(ACTIVE_STATES)),
    ).fetchone()
    if active:
        raise HTTPException(
            409, "Wait for processing to finish or cancel the active job."
        )


def items(conn, rfq) -> list[LineItem]:
    rows = conn.execute(
        "select data from procurement.rfq_line_items where run_id=%s order by id",
        (rfq["current_run_id"],),
    ).fetchall()
    return [LineItem.model_validate(row["data"]) for row in rows]


def numeric(item: LineItem, name: str):
    field = item.fields.get(name, FieldValue())
    return (
        Decimal(field.value)
        if field.value is not None and field.status == "validated"
        else None
    )


def save_item(conn, rfq, item: LineItem):
    conn.execute(
        "insert into procurement.rfq_line_items(run_id,id,rfq_id,workspace_id,data,quantity,requested_unit_price) values(%s,%s,%s,%s,%s,%s,%s) on conflict(run_id,id) do update set data=excluded.data,quantity=excluded.quantity,requested_unit_price=excluded.requested_unit_price",
        (
            rfq["current_run_id"],
            item.id,
            rfq["id"],
            rfq["workspace_id"],
            Jsonb(item.model_dump(mode="json")),
            numeric(item, "quantity"),
            numeric(item, "requested_unit_price"),
        ),
    )


def publish(conn, job, result: Extraction):
    rfq = load_rfq(conn, job["rfq_id"], job["workspace_id"], True)
    current_job = conn.execute(
        "select state from procurement.rfq_processing_jobs where id=%s for update",
        (job["id"],),
    ).fetchone()
    if current_job["state"] == "cancelled":
        return False
    if rfq["revision"] != job["base_revision"] or rfq["status"] == "approved":
        raise RuntimeError("stale_publication")
    run_id = uuid4()
    if rfq["current_run_id"] is None:
        for name, original in rfq["header"].items():
            provided = FieldValue.model_validate(original)
            extracted = result.header.get(name, FieldValue())
            if extracted.value is None and extracted.raw is None:
                result.header[name] = provided
            elif provided.value and provided.value != extracted.value:
                extracted.status = "conflicting"
                extracted.issues.append(
                    "Source differs from customer details provided at creation; resolve before approval."
                )
    conn.execute(
        "insert into procurement.rfq_extraction_runs(id,job_id,rfq_id,workspace_id,schema_version,result,metadata) values(%s,%s,%s,%s,%s,%s,%s)",
        (
            run_id,
            job["id"],
            rfq["id"],
            rfq["workspace_id"],
            result.schema_version,
            Jsonb(result.model_dump(mode="json")),
            Jsonb(result.metadata),
        ),
    )
    rfq["current_run_id"] = run_id
    for item in result.items:
        save_item(conn, rfq, item)
    conn.execute(
        "update procurement.rfqs set current_run_id=%s,header=%s,status='awaiting_review',revision=revision+1,updated_at=now() where id=%s",
        (
            run_id,
            Jsonb({k: v.model_dump(mode="json") for k, v in result.header.items()}),
            rfq["id"],
        ),
    )
    conn.execute(
        "update procurement.rfq_processing_jobs set state='awaiting_review',finished_at=now(),retryable=false,error_category=null,error_message=null where id=%s",
        (job["id"],),
    )
    audit(
        conn,
        rfq,
        "worker",
        "extraction_published",
        {"job_id": str(job["id"]), "item_count": len(result.items)},
        run_id,
    )
    return True
