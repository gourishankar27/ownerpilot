"""Durable citation-only execution; model actions and repair remain separately bounded."""

import json
import time
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from api.rfq.auth import Identity
from api.rfq.db import connection
from .evidence import (
    EvidenceResolver,
    EvidenceError,
    sanitize_request,
    PROTOCOL,
    VERIFIER,
)
from .provider_v2 import LocalModel, PROMPT_VERSION
from .service import digest, snapshot, stable_source, audit, owned
from .tools import definitions, execute, VERSION

ACTIVE = {"queued", "planning", "executing_tools", "verifying"}


def load(run_id):
    with connection() as conn:
        return conn.execute(
            "select * from procurement.procurement_agent_runs where id=%s", (run_id,)
        ).fetchone()


def calls(run_id):
    with connection() as conn:
        return conn.execute(
            "select * from procurement.procurement_agent_tool_calls where run_id=%s order by ordinal",
            (run_id,),
        ).fetchall()


def signature(source):
    return digest(
        {
            "source": stable_source(source),
            "validity": [
                (offer["id"], offer["freshness"])
                for line in source["lines"]
                for offer in line["offers"]["attestations"]
            ],
        }
    )


def validate(conn, run):
    current = conn.execute(
        "select state from procurement.procurement_agent_runs where id=%s for update",
        (run["id"],),
    ).fetchone()
    if current["state"] == "cancelled":
        raise EvidenceError("cancelled")
    if (datetime.now(timezone.utc) - run["created_at"]).total_seconds() > 240:
        raise EvidenceError("budget_exhausted")
    member = conn.execute(
        "select role from workspace_members where workspace_id=%s and user_id=%s for share",
        (run["workspace_id"], run["actor"]),
    ).fetchone()
    if not member or member["role"] not in {"owner", "admin", "reviewer", "editor"}:
        raise EvidenceError("permission_revoked")
    identity = Identity(run["actor"], str(run["workspace_id"]), member["role"])
    # Serialize publication with selection/review/offer mutations without holding a lock during inference.
    conn.execute(
        "select id from procurement.rfqs where id=%s and workspace_id=%s for update",
        (run["rfq_id"], run["workspace_id"]),
    )
    current_source = snapshot(conn, run["rfq_id"], identity)
    if signature(current_source) != signature(run["snapshot"]):
        raise EvidenceError("source_changed")
    if run["snapshot"].get("quote_id") and "quote_revision" in run["snapshot"]:
        quote = owned(conn, "quote_drafts", run["snapshot"]["quote_id"], identity)
        if quote["revision"] != run["snapshot"]["quote_revision"]:
            raise EvidenceError("source_changed")
    return identity


def checkpoint(run_id, stage):
    """Observable safe checkpoint; tests may interrupt this function, never model input."""
    with connection() as conn:
        conn.execute(
            "update procurement.procurement_agent_runs set diagnostics=diagnostics||%s,updated_at=now() where id=%s and state=any(%s)",
            (Jsonb({"stage": stage}), run_id, list(ACTIVE)),
        )


def update(run_id, **fields):
    allowed = {"state", "result", "error", "finalization", "diagnostics"}
    if not fields or set(fields) - allowed:
        raise ValueError("Closed state mutation")
    with connection() as conn:
        conn.execute(
            "update procurement.procurement_agent_runs set "
            + ",".join(key + "=%s" for key in fields)
            + ",updated_at=now() where id=%s and state=any(%s)",
            tuple(
                Jsonb(value)
                if key in {"result", "finalization", "diagnostics"}
                and value is not None
                else value
                for key, value in fields.items()
            )
            + (run_id, list(ACTIVE)),
        )


def model_context(receipts):
    messages = [
        {
            "role": "user",
            "content": "Research every approved line with native read-only tools. Start with get_approved_rfq if it has not already succeeded. Reuse these durable receipts; do not repeat completed reads.",
        }
    ]
    for receipt in receipts:
        value = receipt["result"]
        if receipt["tool"] == "get_reviewed_product_selection" and value:
            resolution = value.get("resolution")
            value = {
                "line_id": value["line_id"],
                "state": value["state"],
                "resolution": {
                    "id": resolution["id"],
                    "product_id": resolution["data"].get("product_id"),
                    "version_id": resolution["data"].get("version_id"),
                }
                if resolution
                else None,
            }
        tool_id = "call_" + str(receipt["id"]).replace("-", "")[:12]
        messages.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": tool_id,
                        "function": {
                            "name": receipt["tool"],
                            "arguments": receipt["arguments"],
                        },
                    }
                ],
            }
        )
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_id,
                "tool_name": receipt["tool"],
                "content": json.dumps(
                    {
                        "receipt_id": str(receipt["id"]),
                        "status": receipt["status"],
                        "data": value,
                    },
                    separators=(",", ":"),
                ),
            }
        )
    return messages


def invoke(run, provider, phase, resolver=None):
    with connection() as conn:
        live = conn.execute(
            "select * from procurement.procurement_agent_runs where id=%s for update",
            (run["id"],),
        ).fetchone()
        validate(conn, live)
        if phase == "repair":
            if live["repair_attempts"] >= min(
                1, run["metadata"].get("max_repair_calls", 1)
            ):
                raise EvidenceError("repair_budget_exhausted")
            conn.execute(
                "update procurement.procurement_agent_runs set repair_attempts=repair_attempts+1 where id=%s",
                (run["id"],),
            )
            ordinal = live["turns"] + live["repair_attempts"] + 1
        else:
            if live["turns"] >= 4:
                raise EvidenceError("budget_exhausted")
            conn.execute(
                "update procurement.procurement_agent_runs set turns=turns+1 where id=%s",
                (run["id"],),
            )
            ordinal = live["turns"] + 1
        conn.execute(
            "insert into procurement.procurement_agent_model_calls(run_id,ordinal,phase,state) values(%s,%s,%s,'in_flight')",
            (run["id"], ordinal, phase),
        )
        conn.execute(
            "update procurement.procurement_agent_runs set updated_at=now() where id=%s",
            (run["id"],),
        )
    checkpoint(run["id"], "citation_repair" if phase == "repair" else phase)
    try:
        kwargs = {}
        if phase in {"finalization", "repair"}:
            kwargs = {"finalize": True, "facts": resolver.inventory()}
            if phase == "repair":
                kwargs["repair"] = {
                    "invalid_citations": run["result"].get("invalid_citations", []),
                    "missing_citations": [
                        item
                        for line in run["result"]["coverage"]["lines"]
                        for item in line["missing_citations"]
                    ],
                }
        message, summary = provider.chat(
            model_context(calls(run["id"])) if phase == "planning" else [],
            definitions(),
            run["metadata"]["digest"],
            **kwargs,
        )
        with connection() as conn:
            validate(conn, load(run["id"]))
            conn.execute(
                "update procurement.procurement_agent_model_calls set state='succeeded',metrics=%s,finished_at=now() where run_id=%s and ordinal=%s",
                (Jsonb(getattr(provider, "last_stats", {})), run["id"], ordinal),
            )
        return message, summary
    except Exception:
        with connection() as conn:
            conn.execute(
                "update procurement.procurement_agent_model_calls set state='failed',metrics=%s,finished_at=now() where run_id=%s and ordinal=%s",
                (Jsonb(getattr(provider, "last_stats", {})), run["id"], ordinal),
            )
        raise


def perform_pending(run):
    pending = run["messages"][-1]["tool_calls"]
    stored = calls(run["id"])
    for call in pending:
        ordinal = call["receipt_ordinal"]
        if any(receipt["ordinal"] == ordinal for receipt in stored):
            continue
        with connection() as conn:
            validate(conn, load(run["id"]))
        function = call.get("function", {})
        name = function.get("name", "")
        args = function.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                args = {"invalid_arguments": True}
        if type(args) is not dict or len(json.dumps(args)) > 4000:
            args = {"invalid_arguments": True}
        argument_hash = digest({"name": name, "args": args})
        status = "succeeded"
        policy = "allowed_read_only"
        result = None
        error = None
        started = time.perf_counter()
        try:
            if ordinal > 8:
                raise EvidenceError("tool_budget_exhausted")
            if (
                sum(receipt["argument_hash"] == argument_hash for receipt in stored)
                >= 2
            ):
                raise EvidenceError("tool_repeat_limit")
            result = execute(name, args, run)
            if type(result) is not dict:
                raise EvidenceError("missing_tool_response")
        except EvidenceError as exc:
            status = "rejected"
            policy = "policy_or_data_error"
            error = exc.code
        except ValidationError:
            status = "rejected"
            policy = "policy_or_data_error"
            error = "tool_schema_rejected"
        except ValueError:
            status = "rejected"
            policy = "policy_or_data_error"
            error = "tool_unauthorized_or_invalid"
        except Exception:
            status = "failed"
            error = "tool_failed"
        with connection() as conn:
            validate(conn, load(run["id"]))
            conn.execute(
                "insert into procurement.procurement_agent_tool_calls(id,run_id,ordinal,tool,schema_version,arguments,argument_hash,status,policy,result,error,duration_ms,finished_at) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())",
                (
                    str(uuid4()),
                    run["id"],
                    ordinal,
                    name[:100],
                    VERSION,
                    Jsonb(args),
                    argument_hash,
                    status,
                    policy,
                    Jsonb(result) if result is not None else None,
                    error,
                    round((time.perf_counter() - started) * 1000, 3),
                ),
            )
        stored = calls(run["id"])
        checkpoint(run["id"], "receipt_persisted")
    with connection() as conn:
        validate(conn, load(run["id"]))
        conn.execute(
            "update procurement.procurement_agent_runs set messages=messages||%s,state='planning',updated_at=now() where id=%s",
            (
                Jsonb([{"role": "tool", "content": "Durable tool receipts recorded"}]),
                run["id"],
            ),
        )


def publish(run, result):
    checkpoint(run["id"], "before_publication")
    with connection() as conn:
        live = conn.execute(
            "select * from procurement.procurement_agent_runs where id=%s for update",
            (run["id"],),
        ).fetchone()
        if live["state"] == "complete":
            return "complete"
        identity = validate(conn, live)
        conn.execute(
            "update procurement.procurement_agent_runs set state='complete',result=%s,error=null,finalization=finalization||%s,updated_at=now() where id=%s",
            (Jsonb(result), Jsonb({"stage": "published"}), run["id"]),
        )
        audit(
            conn,
            identity,
            run["id"],
            "research_complete",
            {
                "protocol": PROTOCOL,
                "claims": len(result["claims"]),
                "repair_attempts": live["repair_attempts"],
            },
        )
    return "complete"


def run_research(run_id, provider=None):
    with connection() as lock:
        acquired = lock.execute(
            "select pg_try_advisory_lock(hashtextextended('procurement-agent-local',0)) as ok"
        ).fetchone()["ok"]
        lock.commit()
        if not acquired:
            return "capacity_busy"
        try:
            run = load(run_id)
            if not run or run["state"] not in ACTIVE:
                return "terminal"
            with connection() as conn:
                validate(conn, run)
                if run["attempts"] >= 3:
                    raise EvidenceError("retry_budget_exhausted")
                conn.execute(
                    "update procurement.procurement_agent_runs set attempts=attempts+1,diagnostics=diagnostics||%s,updated_at=now() where id=%s",
                    (Jsonb({"recovered": run["attempts"] > 0}), run_id),
                )
                conn.execute(
                    "update procurement.procurement_agent_model_calls set state='interrupted',finished_at=now() where run_id=%s and state='in_flight'",
                    (run_id,),
                )
            provider = provider or LocalModel()
            health = provider.health()
            for key, expected in [
                ("digest", run["metadata"]["digest"]),
                ("prompt_version", PROMPT_VERSION),
                ("claim_schema", PROTOCOL),
                ("verifier_version", VERIFIER),
                ("tool_schema", VERSION),
            ]:
                if health.get(key) != expected or run["metadata"].get(key) != expected:
                    raise EvidenceError("model_or_protocol_mismatch")
            while True:
                run = load(run_id)
                with connection() as conn:
                    validate(conn, run)
                stored = calls(run_id)
                resolver = EvidenceResolver(run, stored)
                final = run["finalization"]
                if final.get("stage") == "received":
                    result = resolver.resolve(final["request"])
                    with connection() as conn:
                        validate(conn, load(run_id))
                        conn.execute(
                            "insert into procurement.procurement_agent_finalizations(run_id,phase,reference_request,resolution) values(%s,%s,%s,%s) on conflict(run_id,phase) do nothing",
                            (
                                run_id,
                                final["phase"],
                                Jsonb(final["request"]),
                                Jsonb(result),
                            ),
                        )
                    if final["phase"] == "repair":
                        result = resolver.merge_partial(run.get("result") or {}, result)
                    update(run_id, result=result)
                    checkpoint(run_id, "evidence_materialized")
                    if result["complete"]:
                        return publish(run, result)
                    source_ok = (
                        result["coverage"]["source_coverage_complete"]
                        and not resolver.receipt_errors
                    )
                    if (
                        final["phase"] == "initial"
                        and source_ok
                        and run["repair_attempts"]
                        < min(1, run["metadata"].get("max_repair_calls", 1))
                    ):
                        update(
                            run_id,
                            state="verifying",
                            finalization={"stage": "repair_pending", "phase": "repair"},
                        )
                        continue
                    code = (
                        "research_coverage_incomplete"
                        if not source_ok
                        else "repair_budget_exhausted"
                        if final["phase"] == "repair"
                        else "invalid_citation_pointer"
                    )
                    update(
                        run_id,
                        state="needs_attention",
                        error=code,
                        diagnostics={
                            **run["diagnostics"],
                            "stage": "needs_attention",
                            "error_code": code,
                        },
                    )
                    return "needs_attention"
                if final.get("stage") == "repair_pending":
                    message, summary = invoke(run, provider, "repair", resolver)
                    if message.get("tool_calls"):
                        raise EvidenceError("citation_repair_tool_request")
                    update(
                        run_id,
                        state="verifying",
                        finalization={
                            "stage": "received",
                            "phase": "repair",
                            "request": sanitize_request(summary or ""),
                        },
                    )
                    checkpoint(run_id, "finalization_received")
                    continue
                if run["messages"][-1].get("role") == "assistant" and run["messages"][
                    -1
                ].get("tool_calls"):
                    perform_pending(run)
                    continue
                if any(receipt["status"] != "succeeded" for receipt in stored):
                    partial = resolver.resolve({"claims": []})
                    update(run_id, result=partial)
                    raise EvidenceError("tool_failed")
                if run["turns"] >= 4:
                    raise EvidenceError("budget_exhausted")
                finalize = (
                    resolver.coverage()["source_coverage_complete"]
                    or run["turns"] >= 3
                    or len(stored) >= 8
                )
                update(run_id, state="verifying" if finalize else "planning")
                message, summary = invoke(
                    run, provider, "finalization" if finalize else "planning", resolver
                )
                if message.get("tool_calls"):
                    requested = message["tool_calls"]
                    if finalize:
                        raise EvidenceError("finalization_tool_request")
                    if (
                        type(requested) is not list
                        or not 1 <= len(requested) <= 8
                        or len(stored) + len(requested) > 8
                    ):
                        raise EvidenceError("tool_budget_exhausted")
                    for index, call in enumerate(requested):
                        if (
                            type(call) is not dict
                            or type(call.get("function")) is not dict
                            or type(call["function"].get("name")) is not str
                        ):
                            raise EvidenceError("tool_schema_rejected")
                        call["receipt_ordinal"] = len(stored) + index + 1
                    with connection() as conn:
                        validate(conn, load(run_id))
                        conn.execute(
                            "update procurement.procurement_agent_runs set messages=messages||%s,state='executing_tools',updated_at=now() where id=%s",
                            (Jsonb([message]), run_id),
                        )
                else:
                    update(
                        run_id,
                        state="verifying",
                        finalization={
                            "stage": "received",
                            "phase": "initial",
                            "request": sanitize_request(summary or ""),
                        },
                    )
                    checkpoint(run_id, "finalization_received")
        except Exception as exc:
            code = (
                exc.code
                if isinstance(exc, EvidenceError)
                else "model_unavailable"
                if isinstance(exc, httpx.HTTPError)
                else "model_or_protocol_mismatch"
                if isinstance(exc, ValueError)
                else "internal_service_error"
            )
            live = load(run_id)
            if live and live["state"] == "cancelled":
                return "cancelled"
            update(
                run_id,
                state="needs_attention",
                error=code,
                diagnostics={
                    **(live or {}).get("diagnostics", {}),
                    "stage": "needs_attention",
                    "error_code": code,
                },
            )
            return "needs_attention"
        finally:
            lock.execute(
                "select pg_advisory_unlock(hashtextextended('procurement-agent-local',0))"
            )
