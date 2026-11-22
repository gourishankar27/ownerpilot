"""Real SIGKILL, duplicate delivery, cancellation and network outage on Phase 3.1 only."""

import importlib.util
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from uuid import uuid4

from fastapi.encoders import jsonable_encoder

from api.procurement_agent.provider_v2 import LocalModel
from api.procurement_agent.runner import run_agent
from api.procurement_agent.runner_v2 import load, calls
from api.procurement_agent.worker import research
from api.rfq.db import connection

ROOT = Path(__file__).resolve().parents[1]
WORKER = "ownerpilot-procurement31-validation-worker-1"
TERMINAL = {"complete", "needs_attention", "failed", "cancelled"}


def wait_for(work, predicate, seconds=120):
    start = time.monotonic()
    while time.monotonic() - start < seconds:
        value = work()
        if predicate(value):
            return value
        time.sleep(0.1)
    raise RuntimeError("Real recovery observation timed out")


def publications(identifier):
    with connection() as conn:
        return conn.execute(
            "select count(*) as n from procurement.quote_audit_events where subject=%s and event='research_complete'",
            (identifier,),
        ).fetchone()["n"]


def main():
    if (
        "ownerpilot_rfq_phase3_demo_phase31_validation"
        not in os.environ["DATABASE_URL"]
    ):
        raise SystemExit("Requires isolated Phase 3.1 validation database")
    spec = importlib.util.spec_from_file_location(
        "phase31_eval", ROOT / "scripts/procurement31-evaluate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    state = json.loads(module.PRIVATE.read_text())
    item = state["cases"]["dev-01"]

    def quote_counts():
        with connection() as conn:
            return conn.execute(
                "select (select count(*) from procurement.quote_versions v join procurement.quote_drafts q on q.id=v.quote_id where q.workspace_id=%s) as quote_versions,(select count(*) from procurement.quote_audit_events where workspace_id=%s and event='quote_approved_internal') as approvals",
                (state["workspace"], state["workspace"]),
            ).fetchone()

    counts_before = quote_counts()

    def start():
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

    identifier = start()

    def kill_window(_):
        row = load(identifier)
        return (
            row["state"] not in TERMINAL
            and row["turns"] >= 2
            and bool(calls(identifier))
        )

    wait_for(lambda: None, kill_window, 90)
    before = load(identifier)
    prior = calls(identifier)
    subprocess.run(
        ["docker", "kill", "--signal", "KILL", WORKER], check=True, capture_output=True
    )
    killed_at = time.monotonic()
    print(
        json.dumps(
            {
                "event": "real_SIGKILL",
                "run_id": identifier,
                "turns": before["turns"],
                "receipts": len(prior),
            }
        ),
        flush=True,
    )
    subprocess.run(["docker", "start", WORKER], check=True, capture_output=True)
    final = wait_for(
        lambda: load(identifier), lambda row: row["state"] in TERMINAL, 180
    )
    after = calls(identifier)
    research.apply_async(args=[identifier], retry=False)
    time.sleep(2)
    duplicate = calls(identifier)
    preserved = all(
        any(old["id"] == new["id"] and old["result"] == new["result"] for new in after)
        for old in prior
    )
    recovery = {
        "run_id": identifier,
        "worker": WORKER,
        "signal": "SIGKILL",
        "before": {
            key: before[key]
            for key in ["state", "turns", "repair_attempts", "attempts", "diagnostics"]
        },
        "after": {
            key: final[key]
            for key in [
                "state",
                "turns",
                "repair_attempts",
                "attempts",
                "diagnostics",
                "error",
            ]
        },
        "recovery_seconds": time.monotonic() - killed_at,
        "receipt_ids_before": [str(row["id"]) for row in prior],
        "receipt_ids_after": [str(row["id"]) for row in after],
        "receipts_preserved": preserved,
        "duplicate_delivery_unchanged": after == duplicate,
        "publications": publications(identifier),
    }
    recovery["passed"] = (
        preserved
        and after == duplicate
        and final["attempts"] >= 2
        and final["turns"] >= before["turns"]
        and final["turns"] <= 4
        and final["repair_attempts"] <= 1
        and recovery["publications"] <= 1
    )
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

    cancelled_id = start()

    def inference_in_progress(row):
        if row["state"] in TERMINAL:
            raise RuntimeError("No real model cancellation window observed")
        with connection() as conn:
            return bool(
                conn.execute(
                    "select 1 from procurement.procurement_agent_model_calls where run_id=%s and state='in_flight'",
                    (cancelled_id,),
                ).fetchone()
            )

    cancel_before = wait_for(lambda: load(cancelled_id), inference_in_progress, 60)
    module.request("POST", f"agent-runs/{cancelled_id}/cancel", state)
    time.sleep(15)
    cancel_after = load(cancelled_id)
    cancellation = {
        "run_id": cancelled_id,
        "cancelled_during": cancel_before["diagnostics"],
        "state": cancel_after["state"],
        "publications": publications(cancelled_id),
        "passed": cancel_after["state"] == "cancelled"
        and publications(cancelled_id) == 0,
    }
    with connection() as conn:
        cancellation["model_calls"] = conn.execute(
            "select ordinal,phase,state,metrics from procurement.procurement_agent_model_calls where run_id=%s order by ordinal",
            (cancelled_id,),
        ).fetchall()
    cancellation["actual_chat_started"] = any(
        call["metrics"].get("request_started") for call in cancellation["model_calls"]
    )
    cancellation["passed"] = (
        cancellation["passed"] and cancellation["actual_chat_started"]
    )

    # Genuine refused local TCP endpoint. The installed Ollama service is left running.
    provider = LocalModel()
    subprocess.run(["docker", "pause", WORKER], check=True, capture_output=True)
    try:
        unavailable = module.create_run(item, state, provider)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        provider.url = f"http://127.0.0.1:{port}"
        outcome = run_agent(str(unavailable["id"]), provider)
        row = load(unavailable["id"])
        outage = {
            "run_id": str(row["id"]),
            "actual_refused_local_endpoint": True,
            "state": outcome,
            "error": row["error"],
            "tools_executed": len(calls(row["id"])),
            "passed": outcome == "needs_attention"
            and row["error"] == "model_unavailable"
            and not calls(row["id"]),
        }
    finally:
        subprocess.run(["docker", "unpause", WORKER], check=True, capture_output=True)
    result = {
        "actual_worker_kill": recovery,
        "actual_cancellation": cancellation,
        "actual_network_unavailability": outage,
    }
    counts_after = quote_counts()
    result["quote_preservation"] = {
        "before": counts_before,
        "after": counts_after,
        "passed": counts_before == counts_after,
    }
    (ROOT / "docs/rfq/phase3_1/results/real-recovery.json").write_text(
        json.dumps(jsonable_encoder(result), indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(jsonable_encoder(result)), flush=True)
    assert all(value["passed"] for value in result.values())


if __name__ == "__main__":
    main()
