"""Actual HTTP/local-Ollama outage/capability and in-flight cancellation probes."""

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
if "ownerpilot_rfq_phase3_demo" not in os.environ["DATABASE_URL"]:
    raise SystemExit("Requires isolated Phase 3 demo environment")
spec = importlib.util.spec_from_file_location(
    "phase3_eval", ROOT / "scripts/procurement-evaluate.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
state = json.loads((ROOT / ".local/rfq/phase3/evaluation-state.json").read_text())
workspace, user = state["workspace"], state["user"]
case = state["cases"]["current_attested_offer"]
frozen = json.loads(
    (ROOT / "data/evaluation/procurement-v1/scenarios.json").read_text()
)
quote = module.request(
    "POST",
    f"rfqs/{case['rfq_id']}/quotes",
    workspace,
    user,
    json={
        "policy": frozen["finance"][0]["policy"],
        "offer_choices": {case["line_id"]: case["offer_id"]},
        "reason": "Actual outage deterministic calculation validation",
    },
)
assert quote["calculation"]["grand_total"] == "24.00"
probes = []
for name, config in [
    (
        "missing_chat_tag",
        {"PROCUREMENT_AGENT_MODEL": "ownerpilot-synthetic-absent:never-pull"},
    ),
    (
        "installed_model_without_tools",
        {"PROCUREMENT_AGENT_MODEL": "nomic-embed-text:v1.5"},
    ),
    ("unreachable_local_endpoint", {"PROCUREMENT_AGENT_URL": "http://127.0.0.1:9"}),
]:
    environment = os.environ.copy()
    environment.update(config)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8044",
        ],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        with httpx.Client(
            base_url="http://127.0.0.1:8044", timeout=20, trust_env=False
        ) as probe:
            for _ in range(100):
                try:
                    if probe.get("/openapi.json").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            module.client = probe
            health = module.request("GET", "agent-health", workspace, user)
            blocked = False
            try:
                module.request(
                    "POST",
                    f"rfqs/{case['rfq_id']}/research",
                    workspace,
                    user,
                    json={
                        "revision": case["revision"],
                        "idempotency_key": str(uuid4()),
                    },
                )
            except RuntimeError as exc:
                blocked = "HTTP 503" in str(exc)
            calculation = module.request(
                "POST", f"quotes/{quote['id']}/calculate", workspace, user
            )
            probes.append(
                {
                    "case": name,
                    "actual_http_port": 8044,
                    "health_available": health["available"],
                    "research_blocked_503": blocked,
                    "deterministic_total": calculation["grand_total"],
                    "passed": not health["available"]
                    and blocked
                    and calculation["grand_total"] == "24.00",
                }
            )
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
module.client = httpx.Client(
    base_url="http://127.0.0.1:8033", timeout=30, trust_env=False
)
run = module.request(
    "POST",
    f"rfqs/{case['rfq_id']}/research",
    workspace,
    user,
    json={"revision": case["revision"], "idempotency_key": str(uuid4())},
)
for _ in range(200):
    row = module.request("GET", f"agent-runs/{run['id']}", workspace, user)
    if row["state"] == "planning" and row["turns"] >= 1:
        break
    time.sleep(0.1)
before = module.request("GET", f"agent-runs/{run['id']}/tools", workspace, user)
cancelled = module.request("POST", f"agent-runs/{run['id']}/cancel", workspace, user)
time.sleep(5)
after = module.request("GET", f"agent-runs/{run['id']}/tools", workspace, user)
final = module.request("GET", f"agent-runs/{run['id']}", workspace, user)
cancel = {
    "run_id": run["id"],
    "cancelled_during_state": row["state"],
    "turns": row["turns"],
    "final_state": final["state"],
    "receipt_count_before": len(before),
    "receipt_count_after": len(after),
    "no_summary_published": final["result"] is None,
    "passed": row["turns"] >= 1
    and cancelled["state"] == "cancelled"
    and final["state"] == "cancelled"
    and before == after
    and final["result"] is None,
}
record = {
    "outage_probes": probes,
    "actual_inflight_cancellation": cancel,
    "passed": all(p["passed"] for p in probes) and cancel["passed"],
    "not_mocked": True,
    "note": "Separate loopback API processes used unavailable tag, installed non-tool embedding model and unreachable local URL; main Ollama/API/worker services were not stopped.",
}
(ROOT / "docs/rfq/phase3/results/runtime-validation.json").write_text(
    json.dumps(record, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps(record, indent=2))
raise SystemExit(not record["passed"])
