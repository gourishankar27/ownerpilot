"""Frozen paired local-model benchmark. No-verifier comparison is offline, never an API mode.

Creates only clearly named synthetic workspace/RFQs in the isolated Phase 3 demo DB.
Actual native model calls run through the production runner and local tools.
"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import statistics
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import httpx

from api.procurement_agent.contracts import ResearchSummary
from api.procurement_agent.provider import LocalModel
from api.procurement_agent.runner import run_agent
from api.procurement_agent.service import snapshot
from api.procurement_agent.tools import execute
from api.rfq.auth import Identity
from api.rfq.db import connection

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "data/evaluation/procurement-v1"
OUT = ROOT / "docs/rfq/phase3/results/agent"
STATE = ROOT / ".local/rfq/phase3/evaluation-state.json"
client = httpx.Client(
    base_url=os.getenv("PROCUREMENT_API_URL", "http://127.0.0.1:8033"),
    timeout=30,
    trust_env=False,
)


def request(method, path, workspace, user, **kwargs):
    now = int(time.time())
    claims = {
        "sub": user,
        "workspace": workspace,
        "iat": now,
        "exp": now + 60,
        "method": method,
        "path": "/api/" + path,
    }
    raw = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    signature = hmac.new(
        os.environ["RFQ_AUTH_SECRET"].encode(), raw.encode(), hashlib.sha256
    ).hexdigest()
    response = client.request(
        method,
        "/api/" + path,
        headers={"Authorization": f"Bearer {raw}.{signature}"},
        **kwargs,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"HTTP {response.status_code} for {method} {path}; no private body logged"
        )
    return response.json()


def wait_job(path, workspace, user, field, terminal):
    start = time.perf_counter()
    while time.perf_counter() - start < 180:
        row = request("GET", path, workspace, user)
        if row[field] in terminal:
            return row
        time.sleep(1)
    raise RuntimeError("Synthetic job timeout")


def setup():
    if "ownerpilot_rfq_phase3_demo" not in os.environ["DATABASE_URL"]:
        raise SystemExit("Requires isolated Phase 3 demo database")
    if STATE.exists():
        return json.loads(STATE.read_text())
    workspace = str(uuid4())
    user = "synthetic-evaluation-" + str(uuid4())
    with connection() as conn:
        conn.execute(
            "insert into business_workspaces(id,name,slug) values(%s,'Phase 3 fictional procurement benchmark',%s)",
            (workspace, workspace),
        )
        conn.execute(
            "insert into workspace_members(workspace_id,user_id,role) values(%s,%s,'owner')",
            (workspace, user),
        )
    catalog = request(
        "POST",
        "catalogs",
        workspace,
        user,
        json={"name": "Phase 3 fictional benchmark", "license": "CC0 synthetic"},
    )
    preview = request(
        "POST",
        f"catalogs/{catalog['id']}/imports/preview",
        workspace,
        user,
        files={
            "file": (
                "synthetic.json",
                json.dumps(
                    [
                        {
                            "source_id": "SYN-P3-001",
                            "manufacturer": "Northvale",
                            "mpn": "000-P3.1",
                            "name": "Fictional device",
                            "category": "memory",
                            "specs": {"capacity": 32},
                            "supplier": "Fictional Supply",
                        }
                    ]
                ).encode(),
                "application/json",
            )
        },
    )
    request(
        "POST",
        f"catalogs/{catalog['id']}/imports/confirm",
        workspace,
        user,
        json={"version_id": preview["id"], "fingerprint": preview["fingerprint"]},
    )
    result = wait_job(
        f"catalog-import-jobs/{preview['id']}",
        workspace,
        user,
        "state",
        {"published", "failed"},
    )
    if result["state"] != "published":
        raise RuntimeError("Real neural catalog indexing failed")
    state = {
        "workspace": workspace,
        "user": user,
        "version": preview["id"],
        "catalog": catalog["id"],
        "cases": {},
    }
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


def prepare(case, state):
    if case["id"] in state["cases"]:
        return state["cases"][case["id"]]
    workspace, user = state["workspace"], state["user"]
    rfq = request(
        "POST",
        "rfqs",
        workspace,
        user,
        json={"title": "Synthetic Phase 3: " + case["id"]},
    )
    path = f"rfqs/{rfq['id']}"
    request(
        "POST",
        path + "/documents",
        workspace,
        user,
        data={"revision": "0"},
        files={
            "file": (
                "synthetic.csv",
                (
                    "Manufacturer,MPN,Description,Qty,UOM\nNorthvale,000-P3.1,Fictional device "
                    + case["id"]
                    + ",2,EA\n"
                ).encode(),
                "text/csv",
            )
        },
    )
    job = request(
        "POST",
        path + "/process",
        workspace,
        user,
        json={"revision": 1, "mode": "deterministic"},
    )
    wait_job(
        f"rfq-jobs/{job['id']}", workspace, user, "state", {"awaiting_review", "failed"}
    )
    detail = request("GET", path, workspace, user)
    line = detail["items"][0]["id"]
    saved = request(
        "PATCH",
        path + f"/line-items/{line}",
        workspace,
        user,
        json={
            "revision": detail["revision"],
            "fields": {},
            "review_status": "reviewed",
            "reason": "Synthetic source independently reviewed",
        },
    )
    request(
        "POST", path + "/approve", workspace, user, json={"revision": saved["revision"]}
    )
    detail = request("GET", path, workspace, user)
    match = request(
        "POST",
        path + f"/line-items/{line}/matches",
        workspace,
        user,
        json={"revision": detail["revision"], "versions": [state["version"]]},
    )
    product = match["candidates"][0]["id"]
    request(
        "POST",
        f"catalog-match-runs/{match['id']}/review",
        workspace,
        user,
        json={
            "decision": "select",
            "product_id": product,
            "note": "Reviewed synthetic exact identity",
        },
    )
    resolution = request(
        "POST",
        path + f"/line-items/{line}/selection-resolution",
        workspace,
        user,
        json={
            "expected_revision": 0,
            "run_id": match["id"],
            "decision": "select",
            "product_id": product,
            "version_id": state["version"],
            "reason": "Explicit synthetic authoritative resolution",
        },
    )
    offer = request(
        "POST",
        "supplier-offers/attestations",
        workspace,
        user,
        json={
            "resolution_id": resolution["id"],
            "commercial": case["commercial"],
            "reason": "Frozen fictional benchmark commercial evidence",
        },
    )
    item = {
        "rfq_id": rfq["id"],
        "revision": detail["revision"],
        "line_id": line,
        "resolution_id": resolution["id"],
        "offer_id": offer["id"],
    }
    state["cases"][case["id"]] = item
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return item


class ObservedLocalModel(LocalModel):
    def __init__(self):
        super().__init__()
        self.candidate = None
        self.model_calls = 0
        self.model_seconds = 0

    def chat(self, *args, **kwargs):
        start = time.perf_counter()
        self.model_calls += 1
        message, summary = super().chat(*args, **kwargs)
        self.model_seconds += time.perf_counter() - start
        if summary:
            try:
                self.candidate = ResearchSummary.model_validate_json(
                    summary
                ).model_dump(mode="json")
            except ValueError:
                self.candidate = {
                    "parse_error": True
                }  # No raw model reasoning/prose persisted.
        return message, summary


def evaluate(case, state):
    target = OUT / (case["id"] + ".json")
    if target.exists():
        return json.loads(target.read_text())
    item = prepare(case, state)
    workspace, user = state["workspace"], state["user"]
    identity = Identity(user, workspace, "owner")
    with connection() as conn:
        source = snapshot(conn, item["rfq_id"], identity)
    baseline_start = time.perf_counter()
    baseline = execute(
        "get_supplier_offers", {"line_id": item["line_id"]}, {"snapshot": source}
    )
    baseline_ms = (time.perf_counter() - baseline_start) * 1000
    # Reserve an API-created queued run. The worker is deliberately stopped for this paired evaluator.
    subprocess.run(
        ["docker", "pause", "ownerpilot-procurement-validation-worker-1"],
        check=True,
        capture_output=True,
    )
    try:
        return measure_native(case, state, item, baseline, baseline_ms, target)
    finally:
        subprocess.run(
            ["docker", "unpause", "ownerpilot-procurement-validation-worker-1"],
            check=True,
            capture_output=True,
        )


def measure_native(case, state, item, baseline, baseline_ms, target):
    workspace, user = state["workspace"], state["user"]
    run = request(
        "POST",
        f"rfqs/{item['rfq_id']}/research",
        workspace,
        user,
        json={"revision": item["revision"], "idempotency_key": str(uuid4())},
    )
    provider = ObservedLocalModel()
    start = time.perf_counter()
    outcome = run_agent(run["id"], provider)
    latency = (time.perf_counter() - start) * 1000
    detail = request("GET", f"agent-runs/{run['id']}", workspace, user)
    receipts = request("GET", f"agent-runs/{run['id']}/tools", workspace, user)
    candidate = provider.candidate
    valid_claims = 0
    unsupported = 0
    if candidate and "claims" in candidate:
        from api.procurement_agent.tools import verify

        for claim in candidate["claims"]:
            try:
                verify(json.dumps({"claims": [claim]}), receipts)
                valid_claims += 1
            except ValueError:
                unsupported += 1
    record = {
        "scenario": case["id"],
        "split": case["split"],
        "run_id": run["id"],
        "model": detail["metadata"],
        "deterministic": {
            "completion": True,
            "latency_ms": baseline_ms,
            "unsupported_claims": 0,
            "evidence_valid": True,
            "facts": baseline,
        },
        "native_without_verifier": {
            "schema_valid_completion": bool(candidate and candidate.get("claims")),
            "candidate": candidate,
            "valid_claims": valid_claims,
            "unsupported_claims": unsupported,
            "paired_trace": True,
        },
        "verified": {
            "state": outcome,
            "error": detail["error"],
            "result": detail["result"],
            "latency_ms": latency,
            "accepted_claims": len((detail["result"] or {}).get("claims", [])),
            "unsupported_accepted": 0
            if detail["state"] != "complete" or unsupported == 0
            else unsupported,
        },
        "model_calls": provider.model_calls,
        "model_seconds": provider.model_seconds,
        "tools": receipts,
        "native_trace": True,
    }
    target.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "case": case["id"],
                "outcome": outcome,
                "tools": len(receipts),
                "latency_ms": round(latency),
                "error": detail["error"],
            }
        ),
        flush=True,
    )
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--split", choices=["development", "held_out", "all"], default="development"
    )
    args = parser.parse_args()
    manifest = json.loads((FROZEN / "manifest.json").read_text())
    raw = (FROZEN / "scenarios.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == manifest["files"]["scenarios.json"]
    OUT.mkdir(parents=True, exist_ok=True)
    state = setup()
    for case in json.loads(raw)["research"]:
        if args.split == "all" or case["split"] == args.split:
            evaluate(case, state)
    records = [
        json.loads(p.read_text())
        for p in OUT.glob("*.json")
        if p.name != "summary.json"
    ]
    times = sorted(r["verified"]["latency_ms"] for r in records)
    summary = {
        "dataset_sha256": manifest["files"]["scenarios.json"],
        "native_runs": len(records),
        "development_runs": sum(r["split"] == "development" for r in records),
        "held_out_runs": sum(r["split"] == "held_out" for r in records),
        "deterministic_completed": len(records),
        "native_schema_completed": sum(
            r["native_without_verifier"]["schema_valid_completion"] for r in records
        ),
        "verified_completed": sum(
            r["verified"]["state"] == "complete" for r in records
        ),
        "total_tool_calls": sum(len(r["tools"]) for r in records),
        "successful_tool_calls": sum(
            t["status"] == "succeeded" for r in records for t in r["tools"]
        ),
        "unsupported_candidate_claims": sum(
            r["native_without_verifier"]["unsupported_claims"] for r in records
        ),
        "valid_candidate_claims": sum(
            r["native_without_verifier"]["valid_claims"] for r in records
        ),
        "accepted_claims": sum(r["verified"]["accepted_claims"] for r in records),
        "unsupported_accepted": sum(
            r["verified"]["unsupported_accepted"] for r in records
        ),
        "latency_median_ms": statistics.median(times),
        "latency_p95_ms": times[max(0, __import__("math").ceil(0.95 * len(times)) - 1)],
        "deterministic_median_ms": statistics.median(
            r["deterministic"]["latency_ms"] for r in records
        ),
        "comparison": "Native/no-verifier and verified use the same actual model trace. No-verifier is an offline schema-only acceptance counter; never deployed. Deterministic baseline is authorized local facts listing, not autonomous agent research.",
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
