"""Read-only retrieval against real learned vectors with an unreachable embedding endpoint."""

import json
import os
from pathlib import Path

from api.catalog.service import retrieve
from api.rfq.db import connection

ROOT = Path(__file__).resolve().parents[1]
if "ownerpilot_rfq_phase3_demo" not in os.environ["DATABASE_URL"]:
    raise SystemExit("Requires isolated Phase 3 demo environment")
state = json.loads((ROOT / ".local/rfq/phase3/evaluation-state.json").read_text())
with connection() as conn:
    source = conn.execute(
        "select query from procurement.catalog_match_runs where workspace_id=%s and rfq_id=%s order by created_at desc limit 1",
        (state["workspace"], state["cases"]["current_attested_offer"]["rfq_id"]),
    ).fetchone()["query"]
os.environ["CATALOG_EMBED_URL"] = "http://127.0.0.1:9"
results = []
for method in ["exact", "bm25", "sql", "exact_bm25"]:
    result = retrieve(state["workspace"], [state["version"]], source, method)
    results.append(
        {
            "method": method,
            "executed_channels": result["executed_channels"],
            "execution_status": result["execution_status"],
            "embedding_provider_invoked": result["model"]["invoked"],
            "candidate_count": len(result["candidates"]),
            "passed": result["execution_status"] == "complete"
            and result["model"]["invoked"] is False,
        }
    )
try:
    retrieve(state["workspace"], [state["version"]], source, "reranked")
    hybrid = {"blocked": False}
except RuntimeError as exc:
    hybrid = {
        "blocked": True,
        "reason": str(exc),
        "fallback_masqueraded_as_full_hybrid": False,
    }
record = {
    "real_database_and_previously_learned_index": True,
    "embedding_endpoint": "http://127.0.0.1:9",
    "actual_unreachable_endpoint": True,
    "read_only": True,
    "lexical": results,
    "hybrid": hybrid,
    "passed": all(result["passed"] for result in results) and hybrid["blocked"],
}
(ROOT / "docs/rfq/phase3/results/retrieval-outage.json").write_text(
    json.dumps(record, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps(record, indent=2))
raise SystemExit(not record["passed"])
