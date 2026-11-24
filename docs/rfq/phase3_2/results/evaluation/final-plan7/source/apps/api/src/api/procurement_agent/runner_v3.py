"""Coverage-aware durable controller, with explicit model/scheduler attribution."""

import json
import time
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from api.rfq.db import connection
from .evidence import EvidenceError, PROTOCOL, sanitize_request
from .evidence_v3 import EvidenceResolver, VERIFIER
from .planning import (
    POLICY,
    COVERAGE,
    MAX_PLANNING,
    MAX_TOOLS,
    remaining,
    mandatory_plan,
    capacity,
    LIMITS,
)
from .provider_v3 import LocalModel, PROMPT_VERSION
from .runner_v2 import load, calls, validate, publish as publish_evidence
from .service import digest
from .tools_v3 import (
    VERSION,
    REGISTRY,
    KINDS,
    canonical_arguments,
    validate_batch,
    definitions,
    execute,
)

ACTIVE = {"queued", "planning", "executing_tools", "verifying"}


def mutate(run_id, **fields):
    allowed = {
        "state",
        "result",
        "error",
        "planning_state",
        "coverage_state",
        "finalization",
        "diagnostics",
    }
    if not fields or set(fields) - allowed:
        raise ValueError("Closed planning mutation")
    with connection() as conn:
        conn.execute(
            "update procurement.procurement_agent_runs set "
            + ",".join(key + "=%s" for key in fields)
            + ",updated_at=now() where id=%s and state=any(%s)",
            tuple(
                Jsonb(value)
                if key in allowed - {"state", "error"} and value is not None
                else value
                for key, value in fields.items()
            )
            + (run_id, list(ACTIVE)),
        )


def checkpoint(run_id, stage, **details):
    with connection() as conn:
        event = {
            "stage": stage,
            "at": datetime.now(timezone.utc).isoformat(),
            **details,
        }
        conn.execute(
            "update procurement.procurement_agent_runs set planning_state=jsonb_set(planning_state,'{timeline}',coalesce(planning_state->'timeline','[]'::jsonb)||%s),diagnostics=diagnostics||%s,updated_at=now() where id=%s and state=any(%s) and jsonb_array_length(coalesce(planning_state->'timeline','[]'::jsonb))<128",
            (Jsonb([event]), Jsonb({"stage": stage}), run_id, list(ACTIVE)),
        )


def observations(rows):
    messages = [
        {
            "role": "user",
            "content": "Inspect all approved sources using real native read-only tools. Batch approved line IDs within the configured limit. Final citations are requested separately.",
        }
    ]
    for receipt in rows:
        tool_id = "call_" + str(receipt["id"]).replace("-", "")[:12]
        if receipt["tool"] == "get_approved_rfq":
            value = receipt["result"]
        else:
            value = {
                "receipt_id": str(receipt["id"]),
                "status": receipt["status"],
                "source_lines": receipt.get("call_details", {}).get("line_ids", []),
                "source_reads": receipt.get("call_details", {}).get("source_reads", []),
                "error": receipt["error"],
            }
        messages.extend(
            [
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
                },
                {
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "tool_name": receipt["tool"],
                    "content": json.dumps(value, separators=(",", ":")),
                },
            ]
        )
    return messages


def invoke(run, provider, phase, resolver, work):
    field = {
        "planning": "planning_calls",
        "finalization": "finalization_calls",
        "repair": "repair_attempts",
    }[phase]
    limit = 4 if phase == "planning" else 1
    with connection() as conn:
        live = conn.execute(
            "select * from procurement.procurement_agent_runs where id=%s for update",
            (run["id"],),
        ).fetchone()
        validate(conn, live)
        if phase != "planning" and not work["source_coverage_complete"]:
            raise EvidenceError("finalization_source_coverage_missing")
        if live[field] >= limit:
            raise EvidenceError(phase + "_budget_exhausted")
        ordinal = (
            live["planning_calls"]
            + live["finalization_calls"]
            + live["repair_attempts"]
            + 1
        )
        conn.execute(
            f"update procurement.procurement_agent_runs set {field}={field}+1,turns=turns+%s,updated_at=now() where id=%s",
            (0 if phase == "repair" else 1, run["id"]),
        )
        conn.execute(
            "insert into procurement.procurement_agent_model_calls(run_id,ordinal,phase,state) values(%s,%s,%s,'in_flight')",
            (run["id"], ordinal, phase),
        )
    checkpoint(
        run["id"],
        "citation_correction"
        if phase == "repair"
        else "citation_finalization"
        if phase == "finalization"
        else "planning_request",
        ordinal=ordinal,
    )
    try:
        messages = observations(calls(run["id"])) if phase == "planning" else []
        if phase == "planning":
            if run["metadata"]["orchestration_strategy"] != "native_batch":
                messages.append(
                    {
                        "role": "user",
                        "content": "Authoritative remaining-work controller state (not source evidence): "
                        + json.dumps(
                            {
                                "approved_rfq_read": work["approved_rfq_read"],
                                "required_global_tools": []
                                if work["approved_rfq_read"]
                                else ["get_approved_rfq"],
                                "remaining_lines": [
                                    {
                                        "line_id": line["line_id"],
                                        "missing_tools": line["missing_tools"],
                                    }
                                    for line in work["remaining_lines"]
                                    if work["approved_rfq_read"]
                                    and line["missing_tools"]
                                ],
                                "remaining_tool_calls": work["remaining_tool_calls"],
                                "remaining_planning_turns": work[
                                    "remaining_planning_turns"
                                ]
                                - 1,
                                "required_action": work["required_action"]
                                if work["approved_rfq_read"]
                                else "inspect_approved_rfq_first",
                                "batch_size": run["metadata"]["batch_size"],
                            },
                            separators=(",", ":"),
                        ),
                    }
                )
            else:
                messages.append(
                    {
                        "role": "user",
                        "content": f"Configured batch size: {run['metadata']['batch_size']}. Use one batch per group of approved lines, with several native calls in one response if necessary.",
                    }
                )
        kwargs = {}
        if phase != "planning":
            kwargs = {"finalize": True, "facts": resolver.inventory()}
            if phase == "repair":
                kwargs["repair"] = {
                    "invalid_citations": run["result"]["invalid_citations"],
                    "missing_citations": [
                        citation
                        for line in run["result"]["coverage"]["lines"]
                        for citation in line["missing_citations"]
                    ],
                }
        with connection() as conn:
            validate(conn, load(run["id"]))
        message, summary = provider.chat(
            messages, definitions(), run["metadata"]["digest"], **kwargs
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


def enqueue(run, requested, origin):
    if type(requested) is not list or not 1 <= len(requested) <= 8:
        raise EvidenceError("tool_schema_rejected")
    stored = calls(run["id"])
    if len(stored) + len(requested) > MAX_TOOLS:
        raise EvidenceError("tool_budget_exhausted")
    pending = []
    for index, call in enumerate(requested):
        if type(call) is not dict or type(call.get("function")) is not dict:
            raise EvidenceError("tool_schema_rejected")
        pending.append(
            {
                "ordinal": len(stored) + index + 1,
                "function": call["function"],
                "origin": origin,
            }
        )
    with connection() as conn:
        validate(conn, load(run["id"]))
        conn.execute(
            "update procurement.procurement_agent_runs set planning_state=jsonb_set(planning_state,'{pending}',%s),state='executing_tools',updated_at=now() where id=%s",
            (Jsonb(pending), run["id"]),
        )
    checkpoint(
        run["id"],
        "batch_requested"
        if any(
            item["function"].get("name") == "get_line_research_batch"
            for item in pending
        )
        else "tools_requested",
        origin=origin,
        calls=len(pending),
    )


def execute_pending(run):
    for item in run["planning_state"].get("pending", []):
        rows = calls(run["id"])
        if any(receipt["ordinal"] == item["ordinal"] for receipt in rows):
            continue
        with connection() as conn:
            validate(conn, load(run["id"]))
        function = item["function"]
        name = function.get("name", "")
        raw = function.get("arguments", {})
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                raw = {"invalid_arguments": True}
        if type(raw) is not dict or len(json.dumps(raw)) > 4000:
            raw = {"invalid_arguments": True}
        args = raw
        status, policy, error, result = "succeeded", "allowed_read_only", None, None
        before = EvidenceResolver(run, rows).coverage()
        started = time.perf_counter()
        argument_hash = digest({"name": name, "args": args})
        source_reads, line_ids = [], []
        try:
            if type(name) is not str or name not in REGISTRY:
                raise EvidenceError("tool_unauthorized")
            parsed = REGISTRY[name][0].model_validate(raw)
            args = parsed.model_dump(mode="json")
            argument_hash = digest(
                {"name": name, "args": canonical_arguments(name, args)}
            )
            if sum(row["argument_hash"] == argument_hash for row in rows) >= 2:
                raise EvidenceError("tool_repeat_limit")
            if name == "get_line_research_batch":
                validate_batch(args, run)
                line_ids = args["line_ids"]
                source_reads = [KINDS[kind][0] for kind in args["include"]]
            elif "line_id" in args:
                line_ids = [args["line_id"]]
                source_reads = [name]
            elif name == "get_approved_rfq":
                source_reads = [name]
                line_ids = [line["line_id"] for line in run["snapshot"]["lines"]]
            checkpoint(
                run["id"],
                "batch_validated"
                if name == "get_line_research_batch"
                else "tool_validated",
                origin=item["origin"],
                line_count=len(line_ids),
            )
            result = execute(name, args, run)
        except ValidationError:
            status, policy, error = (
                "rejected",
                "policy_or_data_error",
                "tool_schema_rejected",
            )
        except EvidenceError as exc:
            status, policy, error = "rejected", "policy_or_data_error", exc.code
        except ValueError:
            status, policy, error = (
                "rejected",
                "policy_or_data_error",
                "tool_unauthorized_or_invalid",
            )
        except Exception:
            status, error = "failed", "tool_service_failure"
        receipt = {
            "id": str(uuid4()),
            "run_id": run["id"],
            "ordinal": item["ordinal"],
            "tool": str(name)[:100],
            "schema_version": VERSION,
            "arguments": args,
            "argument_hash": argument_hash,
            "status": status,
            "policy": policy,
            "result": result,
            "error": error,
        }
        checked = EvidenceResolver(run, [*rows, receipt])
        if status == "succeeded" and checked.receipt_errors:
            status, error = "failed", "tool_response_binding_rejected"
            receipt.update(status=status, error=error)
            checked = EvidenceResolver(run, [*rows, receipt])
        after = checked.coverage()
        details = {
            "line_ids": line_ids,
            "source_reads": source_reads,
            "source_version": run["metadata"]["source_fingerprint"],
            "reason": "required_remaining_sources"
            if item["origin"] == "backend_scheduled"
            else "native_model_choice",
            "result_bytes": len(
                json.dumps(result, ensure_ascii=False, default=str).encode()
            )
            if result is not None
            else 0,
            "contributed_to_coverage": before["approved_rfq_read"]
            != after["approved_rfq_read"]
            or any(
                left["inspected_tools"] != right["inspected_tools"]
                for left, right in zip(before["lines"], after["lines"])
            ),
            "source_covered_before": sum(
                line["source_coverage_complete"] for line in before["lines"]
            ),
            "source_covered_after": sum(
                line["source_coverage_complete"] for line in after["lines"]
            ),
            "batch_line_count": len(line_ids)
            if name == "get_line_research_batch"
            else 0,
        }
        duration = round((time.perf_counter() - started) * 1000, 3)
        with connection() as conn:
            validate(conn, load(run["id"]))
            conn.execute(
                "insert into procurement.procurement_agent_tool_calls(id,run_id,ordinal,tool,schema_version,arguments,argument_hash,status,policy,result,error,duration_ms,finished_at,execution_origin,call_details) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),%s,%s)",
                (
                    receipt["id"],
                    run["id"],
                    item["ordinal"],
                    receipt["tool"],
                    VERSION,
                    Jsonb(args),
                    argument_hash,
                    status,
                    policy,
                    Jsonb(result) if result is not None else None,
                    error,
                    duration,
                    item["origin"],
                    Jsonb(details),
                ),
            )
        checkpoint(
            run["id"],
            "receipt_persisted",
            receipt_id=receipt["id"],
            origin=item["origin"],
            lines=len(line_ids),
            status=status,
        )
    with connection() as conn:
        validate(conn, load(run["id"]))
        conn.execute(
            "update procurement.procurement_agent_runs set planning_state=jsonb_set(planning_state,'{pending}','[]'::jsonb),state='planning',updated_at=now() where id=%s",
            (run["id"],),
        )


def accept_finalization(run, resolver):
    final = run["finalization"]
    result = resolver.resolve(final["request"])
    with connection() as conn:
        validate(conn, load(run["id"]))
        conn.execute(
            "insert into procurement.procurement_agent_finalizations(run_id,phase,reference_request,resolution) values(%s,%s,%s,%s) on conflict(run_id,phase) do nothing",
            (run["id"], final["phase"], Jsonb(final["request"]), Jsonb(result)),
        )
    if final["phase"] == "repair":
        result = resolver.merge_partial(run.get("result") or {}, result)
    mutate(run["id"], result=result)
    checkpoint(run["id"], "evidence_materialized", verified_facts=len(result["claims"]))
    if result["complete"]:
        result["orchestration"] = {
            "planning_policy": POLICY,
            "strategy": run["metadata"]["orchestration_strategy"],
            "model_selected_tools": sum(
                row["execution_origin"] == "model_selected" for row in calls(run["id"])
            ),
            "backend_scheduled_tools": sum(
                row["execution_origin"] == "backend_scheduled"
                for row in calls(run["id"])
            ),
        }
        checkpoint(run["id"], "before_publication")
        return publish_evidence(run, result)
    if final["phase"] == "initial" and run["repair_attempts"] == 0:
        mutate(run["id"], finalization={"stage": "repair_pending", "phase": "repair"})
        return None
    raise EvidenceError("citation_correction_exhausted")


def run_research(run_id, provider=None):
    with connection() as lock:
        if not lock.execute(
            "select pg_try_advisory_lock(hashtextextended('procurement-agent-local',0)) as ok"
        ).fetchone()["ok"]:
            return "capacity_busy"
        lock.commit()
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
            preflight = capacity(run["snapshot"], run["metadata"]["batch_size"])
            if not preflight["supported"]:
                mutate(
                    run_id,
                    coverage_state={
                        "capacity": preflight,
                        "total_lines": preflight["line_count"],
                        "covered_lines": 0,
                    },
                    diagnostics={"stage": "capacity_blocked"},
                )
                raise EvidenceError(preflight["blockers"][0])
            provider = provider or LocalModel(
                strategy=run["metadata"]["orchestration_strategy"],
                batch_size=run["metadata"]["batch_size"],
            )
            health = provider.health()
            for key, value in {
                "model": run["metadata"].get("model"),
                "digest": run["metadata"]["digest"],
                "prompt_version": PROMPT_VERSION,
                "planning_policy": POLICY,
                "coverage_version": COVERAGE,
                "claim_schema": PROTOCOL,
                "verifier_version": VERIFIER,
                "tool_schema": VERSION,
                "orchestration_strategy": run["metadata"]["orchestration_strategy"],
                "batch_size": run["metadata"]["batch_size"],
                **LIMITS,
            }.items():
                if health.get(key) != value or run["metadata"].get(key) != value:
                    raise EvidenceError("model_or_policy_mismatch")
            while True:
                run = load(run_id)
                with connection() as conn:
                    validate(conn, run)
                rows = calls(run_id)
                resolver = EvidenceResolver(run, rows)
                work = remaining(run, rows, resolver)
                mutate(run_id, coverage_state=work)
                if run["planning_state"].get("pending"):
                    execute_pending(run)
                    continue
                checkpoint(
                    run_id,
                    "coverage_updated",
                    covered_lines=work["covered_lines"],
                    total_lines=work["total_lines"],
                )
                if run["finalization"].get("stage") == "received":
                    if not work["source_coverage_complete"]:
                        raise EvidenceError("finalization_source_coverage_missing")
                    outcome = accept_finalization(run, resolver)
                    if outcome:
                        return outcome
                    continue
                if run["finalization"].get("stage") == "repair_pending":
                    phase = "repair"
                elif work["source_coverage_complete"] and not (
                    run["metadata"]["orchestration_strategy"] == "mandatory_scheduler"
                    and run["planning_calls"] == 0
                ):
                    phase = "finalization"
                else:
                    strategy = run["metadata"]["orchestration_strategy"]
                    scheduled = (
                        strategy == "mandatory_scheduler"
                        and not work["source_coverage_complete"]
                        or strategy == "hybrid"
                        and not work["source_coverage_complete"]
                        and run["planning_calls"] >= 2
                    )
                    if scheduled:
                        planned = mandatory_plan(work, run["metadata"]["batch_size"])
                        if not planned or len(planned) > work["remaining_tool_calls"]:
                            raise EvidenceError("coverage_capacity_exhausted")
                        enqueue(run, planned, "backend_scheduled")
                        continue
                    if (
                        run["planning_calls"] >= MAX_PLANNING
                        or not work["remaining_tool_calls"]
                    ):
                        raise EvidenceError(
                            "planning_budget_exhausted"
                            if run["planning_calls"] >= MAX_PLANNING
                            else "tool_budget_exhausted"
                        )
                    phase = "planning"
                mutate(run_id, state="planning" if phase == "planning" else "verifying")
                message, summary = invoke(run, provider, phase, resolver, work)
                if phase == "planning":
                    if message.get("tool_calls"):
                        enqueue(run, message["tool_calls"], "model_selected")
                    else:
                        checkpoint(
                            run_id,
                            "early_finalization_refused",
                            reason="planning_output_cannot_complete_research",
                        )
                    continue
                if message.get("tool_calls"):
                    raise EvidenceError("citation_stage_tool_request")
                mutate(
                    run_id,
                    finalization={
                        "stage": "received",
                        "phase": "repair" if phase == "repair" else "initial",
                        "request": sanitize_request(summary or ""),
                    },
                )
                checkpoint(run_id, "finalization_received")
        except Exception as exc:
            row = load(run_id)
            if row and row["state"] == "cancelled":
                return "cancelled"
            code = (
                exc.code
                if isinstance(exc, EvidenceError)
                else "model_unavailable"
                if isinstance(exc, httpx.HTTPError)
                else "model_output_invalid"
                if isinstance(exc, ValueError)
                else "internal_service_error"
            )
            if row:
                try:
                    partial = EvidenceResolver(row, calls(run_id)).resolve(
                        {"claims": []}
                    )
                    partial["partial"] = bool((row.get("result") or {}).get("claims"))
                    if row.get("result"):
                        partial = row["result"]
                    mutate(
                        run_id,
                        result=partial,
                        state="needs_attention",
                        error=code,
                        diagnostics={
                            **row["diagnostics"],
                            "stage": "needs_attention",
                            "error_code": code,
                        },
                    )
                except Exception:
                    mutate(run_id, state="needs_attention", error=code)
            return "needs_attention"
        finally:
            lock.execute(
                "select pg_advisory_unlock(hashtextextended('procurement-agent-local',0))"
            )
