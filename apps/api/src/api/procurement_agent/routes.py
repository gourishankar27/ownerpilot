"""Signed-proxy authenticated research, local commercial evidence and quote APIs."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from api.rfq.auth import Identity, authenticate
from api.rfq.db import connection
from api.rfq.repository import load_rfq

from . import contracts as c, service as s
from .provider_v3 import LocalModel
from .runner import ACTIVE

router = APIRouter(prefix="/api", tags=["Procurement research and internal quotes"])


@router.get("/agent-health")
def health(identity: Identity = Depends(authenticate)):
    try:
        return {"available": True, **LocalModel().health()}
    except Exception:
        return {"available": False, "reason": "Local native-tool model unavailable"}


@router.get("/rfqs/{rfq_id}/selections")
def selections(rfq_id: UUID, identity: Identity = Depends(authenticate)):
    with connection() as conn:
        return s.snapshot(conn, rfq_id, identity)


@router.post(
    "/rfqs/{rfq_id}/line-items/{line_id}/selection-resolution", status_code=201
)
def resolution(
    rfq_id: UUID,
    line_id: UUID,
    payload: c.ResolutionInput,
    identity: Identity = Depends(authenticate),
):
    with connection() as conn:
        return s.resolve(conn, rfq_id, line_id, payload, identity)


@router.post("/supplier-offers/attestations", status_code=201)
def attest(payload: c.AttestationInput, identity: Identity = Depends(authenticate)):
    try:
        with connection() as conn:
            return s.attest(conn, payload, identity)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("/supplier-offers/attestations/{offer_id}")
def offer(offer_id: UUID, identity: Identity = Depends(authenticate)):
    with connection() as conn:
        return s.owned(conn, "supplier_offer_attestations", offer_id, identity)


@router.get("/supplier-offers/resolutions/{resolution_id}/comparison")
def compare(resolution_id: UUID, identity: Identity = Depends(authenticate)):
    from .tools import execute

    with connection() as conn:
        resolution = s.owned(
            conn, "product_selection_resolutions", resolution_id, identity
        )
        source = s.snapshot(conn, resolution["rfq_id"], identity)
    return execute(
        "compare_supplier_offers",
        {"line_id": str(resolution["line_id"])},
        {"snapshot": source},
    )


@router.get("/rfqs/{rfq_id}/research")
def research_list(rfq_id: UUID, identity: Identity = Depends(authenticate)):
    with connection() as conn:
        load_rfq(conn, rfq_id, identity.workspace_id)
        return conn.execute(
            "select id,state,turns,attempts,error,metadata,created_at,updated_at from procurement.procurement_agent_runs where workspace_id=%s and rfq_id=%s order by created_at desc limit 50",
            (identity.workspace_id, rfq_id),
        ).fetchall()


@router.post("/rfqs/{rfq_id}/research", status_code=202)
def start_research(
    rfq_id: UUID, payload: c.ResearchInput, identity: Identity = Depends(authenticate)
):
    identity.require_write()
    from .worker import research

    with connection() as conn:
        conn.execute(
            "select pg_advisory_xact_lock(hashtextextended(%s,12))",
            (identity.workspace_id,),
        )
        rfq = load_rfq(conn, rfq_id, identity.workspace_id, True)
        existing = conn.execute(
            "select * from procurement.procurement_agent_runs where workspace_id=%s and idempotency_key=%s",
            (identity.workspace_id, payload.idempotency_key),
        ).fetchone()
        if existing:
            if (
                existing["rfq_id"] != rfq_id
                or existing["snapshot"]["revision"] != payload.revision
                or existing["snapshot"].get("quote_id")
                != (str(payload.quote_id) if payload.quote_id else None)
            ):
                raise HTTPException(409, "Idempotency key used for different inputs")
            return {
                k: v for k, v in existing.items() if k not in {"messages", "snapshot"}
            }
        if rfq["revision"] != payload.revision:
            raise HTTPException(409, "RFQ revision changed")
        active = conn.execute(
            "select count(*) as n from procurement.procurement_agent_runs where workspace_id=%s and state=any(%s)",
            (identity.workspace_id, ACTIVE),
        ).fetchone()["n"]
        if active >= 2:
            raise HTTPException(429, "Workspace research concurrency limit")
        source = s.snapshot(conn, rfq_id, identity)
        source["quote_id"] = str(payload.quote_id) if payload.quote_id else None
        if payload.quote_id:
            quote = s.owned(conn, "quote_drafts", payload.quote_id, identity)
            if quote["rfq_id"] != rfq_id or s.stable_source(
                quote["snapshot"]
            ) != s.stable_source(source):
                raise HTTPException(
                    409, "Quote sources differ from current approved RFQ"
                )
            source.update(
                quote_policy=quote["policy"],
                quote_choices=quote["offer_choices"],
                quote_revision=quote["revision"],
            )
        source["catalog_versions"] = [
            str(r["id"])
            for r in conn.execute(
                "select id from procurement.catalog_versions where workspace_id=%s and state='published' order by id limit 10",
                (identity.workspace_id,),
            ).fetchall()
        ]
        try:
            metadata = LocalModel().health()
            if metadata.get("claim_schema"):
                metadata["source_fingerprint"] = s.digest(source)
        except Exception:
            raise HTTPException(
                503, "Local native tool-calling model unavailable"
            ) from None
        try:
            row = conn.execute(
                "insert into procurement.procurement_agent_runs(workspace_id,rfq_id,idempotency_key,snapshot,messages,metadata,actor) values(%s,%s,%s,%s,%s,%s,%s) returning id,state,metadata,created_at",
                (
                    identity.workspace_id,
                    rfq_id,
                    payload.idempotency_key,
                    Jsonb(source),
                    Jsonb(
                        [
                            {
                                "role": "user",
                                "content": "Research this approved RFQ with native tools. Start with get_approved_rfq. Workspace and RFQ are provided by trusted job context.",
                            }
                        ]
                    ),
                    Jsonb(metadata),
                    identity.user_id,
                ),
            ).fetchone()
        except UniqueViolation:
            raise HTTPException(409, "Research already active for this RFQ") from None
        s.audit(
            conn,
            identity,
            row["id"],
            "research_requested",
            {"revision": payload.revision},
        )
    try:
        research.apply_async(args=[str(row["id"])], retry=False)
    except Exception:
        pass  # Database outbox remains queued; beat recovers broker outages.
    return row


@router.get("/agent-runs/{run_id}")
def run_detail(run_id: UUID, identity: Identity = Depends(authenticate)):
    with connection() as conn:
        run = s.owned(conn, "procurement_agent_runs", run_id, identity)
        return {k: v for k, v in run.items() if k != "messages"}


@router.get("/agent-runs/{run_id}/tools")
@router.get("/agent-runs/{run_id}/evidence")
def run_tools(run_id: UUID, identity: Identity = Depends(authenticate)):
    with connection() as conn:
        s.owned(conn, "procurement_agent_runs", run_id, identity)
        return conn.execute(
            "select * from procurement.procurement_agent_tool_calls where run_id=%s order by ordinal",
            (run_id,),
        ).fetchall()


@router.post("/agent-runs/{run_id}/cancel")
def cancel(run_id: UUID, identity: Identity = Depends(authenticate)):
    identity.require_write()
    with connection() as conn:
        run = s.owned(conn, "procurement_agent_runs", run_id, identity, True)
        if run["state"] in ACTIVE:
            conn.execute(
                "update procurement.procurement_agent_runs set state='cancelled',updated_at=now() where id=%s",
                (run_id,),
            )
        s.audit(conn, identity, run_id, "research_cancel_requested")
        return {
            "id": run_id,
            "state": "cancelled" if run["state"] in ACTIVE else run["state"],
        }


@router.get("/rfqs/{rfq_id}/quotes")
def quotes(rfq_id: UUID, identity: Identity = Depends(authenticate)):
    with connection() as conn:
        load_rfq(conn, rfq_id, identity.workspace_id)
        return conn.execute(
            "select id,revision,state,calculation,approved_by,approved_at,created_at from procurement.quote_drafts where rfq_id=%s and workspace_id=%s order by created_at desc limit 100",
            (rfq_id, identity.workspace_id),
        ).fetchall()


@router.post("/rfqs/{rfq_id}/quotes", status_code=201)
def create_quote(
    rfq_id: UUID, payload: c.QuoteInput, identity: Identity = Depends(authenticate)
):
    try:
        with connection() as conn:
            return s.create_quote(conn, rfq_id, payload, identity)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("/quotes/{quote_id}")
def quote(quote_id: UUID, identity: Identity = Depends(authenticate)):
    with connection() as conn:
        return s.owned(conn, "quote_drafts", quote_id, identity)


@router.patch("/quotes/{quote_id}")
def edit_quote(
    quote_id: UUID, payload: c.QuoteEdit, identity: Identity = Depends(authenticate)
):
    try:
        with connection() as conn:
            return s.quote_change(conn, quote_id, payload, identity, "edit")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.post("/quotes/{quote_id}/calculate")
def preview_quote(quote_id: UUID, identity: Identity = Depends(authenticate)):
    with connection() as conn:
        row = s.owned(conn, "quote_drafts", quote_id, identity)
        return s.quote_calculation(
            row["snapshot"],
            row["offer_choices"],
            c.QuotePolicy.model_validate(row["policy"]),
        )


@router.post("/quotes/{quote_id}/new-version", status_code=201)
def new_version(
    quote_id: UUID, payload: c.QuoteInput, identity: Identity = Depends(authenticate)
):
    with connection() as conn:
        original = s.owned(conn, "quote_drafts", quote_id, identity)
        row = s.create_quote(conn, original["rfq_id"], payload, identity)
        s.audit(
            conn,
            identity,
            row["id"],
            "quote_derived",
            {"previous_quote_id": str(quote_id), "reason": payload.reason},
        )
        return row


@router.post("/quotes/{quote_id}/{action}")
def decide(
    quote_id: UUID,
    action: str,
    payload: c.QuoteDecision,
    identity: Identity = Depends(authenticate),
):
    if action not in {"submit", "approve", "reject", "request-changes", "supersede"}:
        raise HTTPException(404, "Unknown quote action")
    try:
        with connection() as conn:
            return s.quote_change(conn, quote_id, payload, identity, action)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("/quotes/{quote_id}/history")
def quote_history(quote_id: UUID, identity: Identity = Depends(authenticate)):
    with connection() as conn:
        s.owned(conn, "quote_drafts", quote_id, identity)
        return conn.execute(
            "select * from procurement.quote_versions where quote_id=%s order by revision",
            (quote_id,),
        ).fetchall()


@router.get("/quotes/{quote_id}/audit")
def quote_audit(quote_id: UUID, identity: Identity = Depends(authenticate)):
    with connection() as conn:
        s.owned(conn, "quote_drafts", quote_id, identity)
        return conn.execute(
            "select * from procurement.quote_audit_events where workspace_id=%s and subject=%s order by id",
            (identity.workspace_id, quote_id),
        ).fetchall()
