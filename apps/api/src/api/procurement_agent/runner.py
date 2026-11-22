"""Durable bounded native-tool state machine. Receipts survive worker termination."""

import json
import time
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from api.rfq.auth import Identity
from api.rfq.db import connection

from .provider import LocalModel
from .service import digest, audit, snapshot, stable_source
from .tools import VERSION, definitions, execute, verify, fact_inventory

ACTIVE = ["queued", "planning", "executing_tools", "verifying"]


def state(run_id, new, error=None, result=None):
    with connection() as conn:
        conn.execute(
            "update procurement.procurement_agent_runs set state=%s,error=%s,result=%s,updated_at=now() where id=%s and state<>'cancelled'",
            (new, error, Jsonb(result) if result else None, run_id),
        )


def current(run_id):
    with connection() as conn:
        row = conn.execute(
            "select * from procurement.procurement_agent_runs where id=%s", (run_id,)
        ).fetchone()
    if not row or row["state"] == "cancelled":
        raise ValueError("Research cancelled")
    if (datetime.now(timezone.utc) - row["created_at"]).total_seconds() > 240:
        raise ValueError("Research wall-time budget exceeded")
    return row


def receipts(run_id):
    with connection() as conn:
        return conn.execute(
            "select * from procurement.procurement_agent_tool_calls where run_id=%s order by ordinal",
            (run_id,),
        ).fetchall()


def run_agent(run_id, provider=None):
    # One local model execution globally plus one lock per run; both released by PostgreSQL on death.
    with connection() as lock:
        acquired = lock.execute(
            "select pg_try_advisory_lock(hashtextextended('procurement-agent-local',0)) as ok"
        ).fetchone()["ok"]
        lock.commit()
        if not acquired:
            return "capacity_busy"
        try:
            with connection() as conn:
                run = conn.execute(
                    "select * from procurement.procurement_agent_runs where id=%s for update",
                    (run_id,),
                ).fetchone()
                if not run or run["state"] not in ACTIVE:
                    return "terminal"
                if run["attempts"] >= 3:
                    conn.execute(
                        "update procurement.procurement_agent_runs set state='failed',error='Recovery attempt limit',updated_at=now() where id=%s",
                        (run_id,),
                    )
                    return "failed"
                conn.execute(
                    "update procurement.procurement_agent_runs set attempts=attempts+1,updated_at=now() where id=%s",
                    (run_id,),
                )
            try:
                provider = provider or LocalModel()
                # Frozen metadata/model identity from request time. A retry cannot silently change models.
                health = provider.health()
                if health["digest"] != run["metadata"]["digest"]:
                    raise ValueError("Agent model digest changed")
                if health.get("prompt_version") != run["metadata"].get(
                    "prompt_version"
                ):
                    raise ValueError(
                        "Agent prompt version changed; start a new research run"
                    )
                if health.get("tool_schema") != run["metadata"].get("tool_schema"):
                    raise ValueError(
                        "Agent tool schema changed; start a new research run"
                    )
                while True:
                    run = current(run_id)
                    membership = None
                    with connection() as conn:
                        membership = conn.execute(
                            "select role from workspace_members where workspace_id=%s and user_id=%s",
                            (run["workspace_id"], run["actor"]),
                        ).fetchone()
                        if not membership or membership["role"] not in {
                            "owner",
                            "admin",
                            "reviewer",
                            "editor",
                        }:
                            raise ValueError("Research permission revoked")
                        identity = Identity(
                            run["actor"], str(run["workspace_id"]), membership["role"]
                        )
                        if stable_source(
                            snapshot(conn, run["rfq_id"], identity)
                        ) != stable_source(run["snapshot"]):
                            raise ValueError(
                                "Research sources changed; start a new run"
                            )
                    messages = run["messages"]
                    stored = receipts(run_id)
                    last = messages[-1] if messages else {}
                    if last.get("role") == "assistant" and last.get("tool_calls"):
                        pending = last["tool_calls"]
                        for call in pending:
                            current(run_id)
                            index = call["receipt_ordinal"]
                            existing = next(
                                (r for r in stored if r["ordinal"] == index), None
                            )
                            if existing:
                                continue
                            function = call.get("function", {})
                            name = function.get("name", "")
                            args = function.get("arguments", {})
                            if isinstance(args, str):
                                try:
                                    args = json.loads(args)
                                except ValueError:
                                    args = {"invalid_arguments": True}
                            if not isinstance(args, dict):
                                args = {"invalid_arguments": True}
                            if len(json.dumps(args)) > 4000:
                                args = {"oversized_arguments": True}
                            key = digest({"name": name, "args": args})
                            policy = "allowed_read_only"
                            status = "succeeded"
                            error = None
                            value = None
                            start = time.perf_counter()
                            try:
                                if index > 8:
                                    raise ValueError("Tool-call budget exceeded")
                                if sum(r["argument_hash"] == key for r in stored) >= 2:
                                    raise ValueError(
                                        "Repeated equivalent tool-call limit"
                                    )
                                value = execute(name, args, run)
                                if not isinstance(value, dict):
                                    raise RuntimeError(
                                        "Tool returned no structured result"
                                    )
                                current(run_id)
                                if time.perf_counter() - start > 125:
                                    raise ValueError(
                                        "Tool execution time budget exceeded"
                                    )
                            except (ValueError, HTTPException, RuntimeError) as exc:
                                status = "rejected"
                                policy = "policy_or_data_error"
                                error = (
                                    type(exc).__name__
                                    + ": "
                                    + (
                                        "Closed tool argument schema rejected"
                                        if isinstance(exc, ValidationError)
                                        else str(exc.detail)
                                        if isinstance(exc, HTTPException)
                                        else str(exc)
                                    )[:300]
                                )
                            except Exception as exc:
                                status = "failed"
                                policy = "allowed_read_only"
                                error = (
                                    "Tool service unavailable or timed out: "
                                    + type(exc).__name__
                                )
                            identifier = str(uuid4())
                            with connection() as conn:
                                # A cancelled job never publishes additional receipts.
                                if (
                                    conn.execute(
                                        "select state from procurement.procurement_agent_runs where id=%s for update",
                                        (run_id,),
                                    ).fetchone()["state"]
                                    == "cancelled"
                                ):
                                    raise ValueError("Research cancelled")
                                conn.execute(
                                    "insert into procurement.procurement_agent_tool_calls(id,run_id,ordinal,tool,schema_version,arguments,argument_hash,status,policy,result,error,duration_ms,finished_at) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())",
                                    (
                                        identifier,
                                        run_id,
                                        index,
                                        name[:100],
                                        VERSION,
                                        Jsonb(args),
                                        key,
                                        status,
                                        policy,
                                        Jsonb(value) if value is not None else None,
                                        error,
                                        round((time.perf_counter() - start) * 1000, 3),
                                    ),
                                )
                                conn.execute(
                                    "update procurement.procurement_agent_runs set updated_at=now() where id=%s",
                                    (run_id,),
                                )
                            stored = receipts(run_id)
                        messages = messages + [
                            {
                                "role": "tool",
                                "tool_name": call["function"]["name"],
                                "content": json.dumps(
                                    {
                                        "receipt_id": str(
                                            next(
                                                r
                                                for r in stored
                                                if r["ordinal"]
                                                == call["receipt_ordinal"]
                                            )["id"]
                                        ),
                                        "status": next(
                                            r
                                            for r in stored
                                            if r["ordinal"] == call["receipt_ordinal"]
                                        )["status"],
                                        "data": next(
                                            r
                                            for r in stored
                                            if r["ordinal"] == call["receipt_ordinal"]
                                        )["result"],
                                    },
                                    default=str,
                                ),
                            }
                            for call in pending
                        ]
                        with connection() as conn:
                            conn.execute(
                                "update procurement.procurement_agent_runs set messages=%s,state='planning',updated_at=now() where id=%s and state<>'cancelled'",
                                (Jsonb(messages), run_id),
                            )
                        if any(r["status"] != "succeeded" for r in stored):
                            raise ValueError(
                                "Tool request rejected; human attention required"
                            )
                        continue
                    if run["turns"] >= 4:
                        raise ValueError("Planning turn budget exhausted")
                    state(run_id, "planning")
                    # Count the turn before calling Ollama; crashes cannot evade planning budgets.
                    with connection() as conn:
                        conn.execute(
                            "update procurement.procurement_agent_runs set turns=turns+1 where id=%s and state<>'cancelled'",
                            (run_id,),
                        )
                    safe_messages = [
                        {k: v for k, v in m.items() if k != "receipt_ordinal"}
                        for m in messages
                    ]
                    for m in safe_messages:
                        if "tool_calls" in m:
                            m["tool_calls"] = [
                                {
                                    k: v
                                    for k, v in call.items()
                                    if k != "receipt_ordinal"
                                }
                                for call in m["tool_calls"]
                            ]
                    covered = {
                        str(r["arguments"].get("line_id"))
                        for r in stored
                        if r["tool"] == "get_supplier_offers"
                        and r["status"] == "succeeded"
                    }
                    selected = {
                        str(r["arguments"].get("line_id"))
                        for r in stored
                        if r["tool"] == "get_reviewed_product_selection"
                        and r["status"] == "succeeded"
                    }
                    all_lines = {entry["line_id"] for entry in run["snapshot"]["lines"]}
                    finalize = (
                        run["turns"] >= 3
                        or len(stored) >= 8
                        or bool(stored and all_lines.issubset(covered & selected))
                    )
                    if finalize:
                        message, summary = provider.chat(
                            safe_messages,
                            definitions(),
                            run["metadata"]["digest"],
                            finalize=True,
                            facts=fact_inventory(stored),
                        )
                    else:
                        message, summary = provider.chat(
                            safe_messages, definitions(), run["metadata"]["digest"]
                        )
                    current(run_id)
                    if message.get("tool_calls"):
                        calls = message["tool_calls"]
                        if (
                            not isinstance(calls, list)
                            or not 1 <= len(calls) <= 8
                            or len(stored) + len(calls) > 8
                        ):
                            raise ValueError("Tool-call budget exceeded")
                        for offset, call in enumerate(calls):
                            call["receipt_ordinal"] = len(stored) + offset + 1
                        with connection() as conn:
                            conn.execute(
                                "update procurement.procurement_agent_runs set messages=%s,state='executing_tools',updated_at=now() where id=%s and state<>'cancelled'",
                                (Jsonb(messages + [message]), run_id),
                            )
                    else:
                        state(run_id, "verifying")
                        result = verify(summary or "", stored)
                        researched = {
                            str(r["arguments"].get("line_id"))
                            for r in stored
                            if r["tool"] == "get_supplier_offers"
                            and r["status"] == "succeeded"
                        }
                        if not {
                            entry["line_id"] for entry in run["snapshot"]["lines"]
                        }.issubset(researched):
                            raise ValueError(
                                "Research coverage incomplete: supplier offers not inspected for every line"
                            )
                        with connection() as conn:
                            final = conn.execute(
                                "select state from procurement.procurement_agent_runs where id=%s for update",
                                (run_id,),
                            ).fetchone()
                            if final["state"] == "cancelled":
                                return "cancelled"
                            if stable_source(
                                snapshot(conn, run["rfq_id"], identity)
                            ) != stable_source(run["snapshot"]):
                                raise ValueError(
                                    "Research source version changed before publication"
                                )
                            conn.execute(
                                "update procurement.procurement_agent_runs set state='complete',result=%s,updated_at=now() where id=%s",
                                (Jsonb(result), run_id),
                            )
                            audit(
                                conn,
                                identity,
                                run_id,
                                "research_complete",
                                {
                                    "tool_calls": len(stored),
                                    "claims": len(result["claims"]),
                                },
                            )
                        return "complete"
            except Exception as exc:
                # Never persist raw model output, request bodies, source text or transport traces.
                category = type(exc).__name__
                safe = (
                    str(exc)[:300]
                    if isinstance(exc, ValueError)
                    and not isinstance(exc, ValidationError)
                    else "Local research execution failed; see receipt status and service health"
                )
                state(run_id, "needs_attention", category + ": " + safe)
                return "needs_attention"
        finally:
            lock.execute(
                "select pg_advisory_unlock(hashtextextended('procurement-agent-local',0))"
            )
