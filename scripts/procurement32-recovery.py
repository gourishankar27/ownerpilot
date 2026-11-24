"""Actual isolated worker/broker/network faults; never native accuracy trials."""

import importlib.util
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from api.procurement_agent.evidence_v3 import EvidenceResolver
from api.procurement_agent.provider_v3 import LocalModel
from api.procurement_agent.runner import run_agent
from api.procurement_agent.runner_v2 import load, calls
from api.procurement_agent.worker import research
from api.rfq.db import connection
from procurement32_oracle import audit

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/rfq/phase3_2/results/real-recovery.json"
WORKER = "ownerpilot-procurement32-validation-worker-1"
REDIS = "ownerpilot-procurement32-validation-redis-1"
TERMINAL = {"complete", "needs_attention", "cancelled", "failed"}


def docker(*args):
    return subprocess.run(["docker", *args], check=True, capture_output=True)


def wait_for(work, predicate, seconds=180, interval=0.1):
    started = time.monotonic()
    while time.monotonic() - started < seconds:
        value = work()
        if predicate(value):
            return value
        time.sleep(interval)
    raise RuntimeError("Actual recovery observation timed out")


def publications(identifier):
    with connection() as conn:
        return conn.execute(
            "select count(*) as n from procurement.quote_audit_events where subject=%s and event='research_complete'",
            (identifier,),
        ).fetchone()["n"]


def counters(row):
    return {
        key: row[key]
        for key in [
            "state",
            "planning_calls",
            "finalization_calls",
            "repair_attempts",
            "attempts",
            "created_at",
            "diagnostics",
            "error",
        ]
    }


def save(result):
    OUT.write_text(
        json.dumps(jsonable_encoder(result), indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main():
    if "phase31_validation_phase32" not in os.environ["DATABASE_URL"]:
        raise SystemExit("Requires isolated Phase 3.2 database")
    if OUT.exists():
        raise SystemExit(
            "Retain existing recovery evidence; inspect before any new probe"
        )
    if json.loads(
        docker("inspect", "--format", "{{json .State.Paused}}", WORKER).stdout
    ):
        raise SystemExit("An evaluator owns the paused worker; wait for it to finish")
    spec = importlib.util.spec_from_file_location(
        "recovery_sources32", ROOT / "scripts/procurement32-prepare.py"
    )
    prepared = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prepared)
    module = prepared.adapter()
    state = json.loads(prepared.PRIVATE.read_text())
    frozen, _ = prepared.frozen_data()
    recovery_case = next(
        case for case in frozen["native_scenarios"] if case["id"] == "v3-dev-05"
    )
    result = {
        "scope": "Actual dedicated Phase 3.2 containers; shared PostgreSQL and Ollama left running"
    }
    with connection() as conn:
        counts_before = conn.execute(
            "select (select count(*) from procurement.quote_versions v join procurement.quote_drafts q on q.id=v.quote_id where q.workspace_id=%s) as versions,(select count(*) from procurement.quote_audit_events where workspace_id=%s and event='quote_approved_internal') as approvals",
            (state["workspace"], state["workspace"]),
        ).fetchone()

    def start(case_id):
        item = state["cases"][case_id]
        return module.request(
            "POST",
            f"rfqs/{item['rfq_id']}/research",
            state,
            json={
                "revision": item["revision"],
                "quote_id": item["quote_id"],
                "idempotency_key": str(uuid4()),
            },
        )["id"]

    identifier = start("v3-dev-05")
    result["kill_admitted_run"] = identifier
    save(result)

    def batch_window(row):
        if row["state"] in TERMINAL:
            raise RuntimeError("Completed before actual batch kill window")
        return row["finalization_calls"] == 0 and any(
            receipt["tool"] == "get_line_research_batch"
            and receipt["status"] == "succeeded"
            for receipt in calls(identifier)
        )

    observed = wait_for(lambda: load(identifier), batch_window, 90, interval=0.025)
    docker("kill", "--signal", "KILL", WORKER)
    killed_at = time.monotonic()
    killed = load(identifier)
    prior = calls(identifier)
    coverage_before = EvidenceResolver(killed, prior).coverage()
    checked_before = audit(
        recovery_case,
        state["cases"]["v3-dev-05"],
        killed,
        killed["result"] or {},
        prior,
    )
    result["kill_observation"] = {
        "pre_signal": counters(observed),
        "post_signal": counters(killed),
        "receipts": prior,
        "coverage": coverage_before,
    }
    save(result)
    print(
        json.dumps(
            {
                "event": "actual_SIGKILL",
                "run_id": identifier,
                "receipts_after_signal": len(prior),
            }
        ),
        flush=True,
    )
    docker("start", WORKER)
    final = wait_for(lambda: load(identifier), lambda row: row["state"] in TERMINAL)
    elapsed = time.monotonic() - killed_at
    after = calls(identifier)
    research.apply_async(args=[identifier], retry=False)
    time.sleep(2)
    duplicate = calls(identifier)
    coverage_after = EvidenceResolver(final, after).coverage()
    checked_after = audit(
        recovery_case, state["cases"]["v3-dev-05"], final, final["result"] or {}, after
    )
    preserved = all(any(old == new for new in after) for old in prior)
    recovery = {
        "run_id": identifier,
        "signal": "SIGKILL",
        "worker": WORKER,
        "before": counters(killed),
        "after": counters(final),
        "recovery_seconds": elapsed,
        "coverage_before": coverage_before,
        "coverage_after": coverage_after,
        "independent_audit_before": checked_before,
        "independent_audit_after": checked_after,
        "receipt_ids_before": [str(row["id"]) for row in prior],
        "receipt_ids_after": [str(row["id"]) for row in after],
        "receipts_preserved": preserved,
        "duplicate_delivery_unchanged": after == duplicate,
        "publications": publications(identifier),
        "completed_recovery": final["state"] == "complete",
    }
    recovery["passed"] = (
        preserved
        and after == duplicate
        and final["attempts"] >= 2
        and checked_after["source_pairs_inspected"]
        >= checked_before["source_pairs_inspected"]
        and not checked_after["invalid_facts"]
        and not checked_after["unauthorized_successful_tools"]
        and final["created_at"] == killed["created_at"]
        and final["planning_calls"] >= killed["planning_calls"]
        and final["planning_calls"] <= 4
        and final["finalization_calls"] <= 1
        and final["repair_attempts"] <= 1
        and recovery["publications"] <= 1
    )
    result["actual_worker_kill"] = recovery
    save(result)
    print(
        json.dumps(
            {
                "event": "recovered",
                "state": final["state"],
                "passed": recovery["passed"],
            }
        ),
        flush=True,
    )

    cancel_id = start("v3-dev-05")

    def admitted(row):
        if row["state"] in TERMINAL:
            raise RuntimeError("No finalization cancellation window observed")
        with connection() as conn:
            return bool(
                conn.execute(
                    "select 1 from procurement.procurement_agent_model_calls where run_id=%s and phase='finalization' and state='in_flight'",
                    (cancel_id,),
                ).fetchone()
            )

    cancel_before = wait_for(lambda: load(cancel_id), admitted, 90)
    time.sleep(0.75)
    module.request("POST", f"agent-runs/{cancel_id}/cancel", state)

    def call_rows():
        with connection() as conn:
            return conn.execute(
                "select * from procurement.procurement_agent_model_calls where run_id=%s order by ordinal",
                (cancel_id,),
            ).fetchall()

    model_calls = wait_for(
        call_rows,
        lambda rows: rows and all(call["state"] != "in_flight" for call in rows),
        75,
    )
    cancelled = load(cancel_id)
    result["actual_cancellation"] = {
        "run_id": cancel_id,
        "observation": "Durable finalization call in_flight before cancellation; waited for its completion/timeout telemetry to verify actual request_start",
        "before": counters(cancel_before),
        "after": counters(cancelled),
        "model_calls": model_calls,
        "publications": publications(cancel_id),
        "passed": cancelled["state"] == "cancelled"
        and publications(cancel_id) == 0
        and any(
            call["phase"] == "finalization" and call["metrics"].get("request_started")
            for call in model_calls
        ),
    }
    save(result)

    docker("stop", REDIS)
    try:
        queued_id = start("v3-dev-01")
        queued = load(queued_id)
        assert queued["state"] == "queued" and not calls(queued_id)
        time.sleep(3)
    finally:
        docker("start", REDIS)
    restored_at = time.monotonic()
    resumed = wait_for(
        lambda: load(queued_id), lambda row: row["state"] in TERMINAL, 150
    )
    with connection() as conn:
        first = conn.execute(
            "select min(created_at) as started from procurement.procurement_agent_model_calls where run_id=%s",
            (queued_id,),
        ).fetchone()["started"]
    result["actual_redis_outage"] = {
        "run_id": queued_id,
        "container": REDIS,
        "queued_during_outage": counters(queued),
        "after": counters(resumed),
        "broker_restoration_to_terminal_seconds": time.monotonic() - restored_at,
        "queue_to_first_model_admission_seconds": (
            first - queued["created_at"]
        ).total_seconds()
        if first
        else None,
        "publications": publications(queued_id),
        "passed": queued["state"] == "queued"
        and resumed["state"] == "complete"
        and publications(queued_id) == 1,
    }
    save(result)

    provider = LocalModel()
    docker("pause", WORKER)
    try:
        unavailable = module.create_run(state["cases"]["v3-dev-01"], state, provider)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        provider.url = f"http://127.0.0.1:{port}"
        outcome = run_agent(str(unavailable["id"]), provider)
        row = load(unavailable["id"])
        result["actual_refused_endpoint"] = {
            "run_id": str(row["id"]),
            "state": outcome,
            "error": row["error"],
            "tools": len(calls(row["id"])),
            "passed": outcome == "needs_attention"
            and row["error"] == "model_unavailable"
            and not calls(row["id"]),
        }
    finally:
        docker("unpause", WORKER)
    with connection() as conn:
        counts_after = conn.execute(
            "select (select count(*) from procurement.quote_versions v join procurement.quote_drafts q on q.id=v.quote_id where q.workspace_id=%s) as versions,(select count(*) from procurement.quote_audit_events where workspace_id=%s and event='quote_approved_internal') as approvals",
            (state["workspace"], state["workspace"]),
        ).fetchone()
    result["quote_preservation"] = {
        "before": counts_before,
        "after": counts_after,
        "passed": counts_before == counts_after,
    }
    save(result)
    assert all(
        result[key]["passed"]
        for key in [
            "actual_worker_kill",
            "actual_cancellation",
            "actual_redis_outage",
            "actual_refused_endpoint",
            "quote_preservation",
        ]
    )
    print("All actual isolated recovery checks passed", flush=True)


if __name__ == "__main__":
    main()
