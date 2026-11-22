"""Deliberate SIGKILL of the isolated Phase 3 worker only; no application DB resets."""

import importlib.util
import json
import os
import subprocess
import time
from pathlib import Path
from uuid import uuid4

from api.rfq.db import connection
from api.procurement_agent.worker import research

ROOT = Path(__file__).resolve().parents[1]
if "ownerpilot_rfq_phase3_demo" not in os.environ["DATABASE_URL"]:
    raise SystemExit("Requires isolated Phase 3 demo database")
spec = importlib.util.spec_from_file_location(
    "phase3_eval", ROOT / "scripts/procurement-evaluate.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
state = json.loads((ROOT / ".local/rfq/phase3/evaluation-state.json").read_text())
workspace, user = state["workspace"], state["user"]
case = state["cases"]["current_attested_offer"]
worker = "ownerpilot-procurement-validation-worker-1"


def get(path):
    return module.request("GET", path, workspace, user)


def post(path, data=None):
    return module.request("POST", path, workspace, user, json=data or {})


def counts():
    with connection() as conn:
        return conn.execute(
            "select (select count(*) from procurement.quote_versions v join procurement.quote_drafts q on q.id=v.quote_id where q.workspace_id=%s) as quote_versions,(select count(*) from procurement.quote_audit_events where workspace_id=%s and event='quote_approved_internal') as approvals",
            (workspace, workspace),
        ).fetchone()


before = counts()
run = post(
    f"rfqs/{case['rfq_id']}/research",
    {"revision": case["revision"], "idempotency_key": str(uuid4())},
)
identifier = run["id"]
start = time.perf_counter()
prior = []
while time.perf_counter() - start < 90:
    row = get(f"agent-runs/{identifier}")
    prior = get(f"agent-runs/{identifier}/tools")
    if prior and row["state"] in {"planning", "executing_tools"} and row["turns"] >= 2:
        break
    if row["state"] in {"complete", "needs_attention", "failed"}:
        raise RuntimeError("Job finished before SIGKILL; no crash success claimed")
    time.sleep(0.15)
else:
    raise RuntimeError("No observable model/tool processing window")
killed_state = row["state"]
killed_turns = row["turns"]
subprocess.run(
    ["docker", "kill", "--signal", "KILL", worker], check=True, capture_output=True
)
killed_at = time.time()
print(
    json.dumps(
        {
            "event": "SIGKILL",
            "run_id": identifier,
            "persisted_receipts": len(prior),
            "turns": row["turns"],
        }
    ),
    flush=True,
)
subprocess.run(["docker", "start", worker], check=True, capture_output=True)
# The database outbox dispatcher recovers planning after a 75-second stale heartbeat.
start = time.perf_counter()
while time.perf_counter() - start < 180:
    row = get(f"agent-runs/{identifier}")
    if row["state"] in {"complete", "needs_attention", "failed", "cancelled"}:
        break
    time.sleep(1)
final = get(f"agent-runs/{identifier}/tools")
after = counts()
research.apply_async(args=[identifier], retry=False)
time.sleep(2)
replayed = get(f"agent-runs/{identifier}/tools")
with connection() as conn:
    completions = conn.execute(
        "select count(*) as n from procurement.quote_audit_events where subject=%s and event='research_complete'",
        (identifier,),
    ).fetchone()["n"]
result = {
    "run_id": identifier,
    "worker": worker,
    "signal": "SIGKILL",
    "killed_during": {
        "state": killed_state,
        "turns": killed_turns,
        "prior_receipts": len(prior),
    },
    "recovery_seconds": time.time() - killed_at,
    "attempts": row["attempts"],
    "final_state": row["state"],
    "error": row["error"],
    "persisted_receipts_preserved": all(
        any(old["id"] == new["id"] and old["result"] == new["result"] for new in final)
        for old in prior
    ),
    "receipt_ordinals_unique": len({r["ordinal"] for r in final}) == len(final),
    "redelivery_receipts_unchanged": final == replayed,
    "quote_counts_before": before,
    "quote_counts_after": after,
    "research_completion_events": completions,
    "safe_recovery_passed": row["attempts"] >= 2
    and row["state"] in {"complete", "needs_attention"}
    and before == after
    and completions <= 1
    and final == replayed,
}
result["safe_recovery_passed"] = (
    result["safe_recovery_passed"]
    and result["persisted_receipts_preserved"]
    and result["receipt_ordinals_unique"]
)
(ROOT / "docs/rfq/phase3/results/worker-recovery.json").write_text(
    json.dumps(result, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps(result, indent=2), flush=True)
raise SystemExit(not result["safe_recovery_passed"])
