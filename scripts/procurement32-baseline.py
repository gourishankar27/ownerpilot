"""Offline deterministic source pipeline; never an agent/model accuracy score."""

import importlib.util
import json
import time
from pathlib import Path
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from api.procurement_agent.evidence_v3 import EvidenceResolver
from api.procurement_agent.planning import remaining, mandatory_plan
from api.procurement_agent.tools_v3 import execute, VERSION
from procurement32_oracle import audit, fingerprint

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs/rfq/phase3_2/results"


def main():
    if not (RESULTS / "selection.json").exists():
        raise SystemExit(
            "Freeze native strategy selection before baseline held-out scoring"
        )
    state = json.loads((ROOT / ".local/rfq/phase3_2/evaluation-state.json").read_text())
    data = json.loads(
        (ROOT / "data/evaluation/procurement-v3/scenarios.json").read_text()
    )
    spec = importlib.util.spec_from_file_location(
        "source_adapter32", ROOT / "scripts/procurement32-prepare.py"
    )
    prepared = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prepared)
    module = prepared.adapter()
    records = []
    for case in data["native_scenarios"]:
        item = state["cases"][case["id"]]
        from api.rfq.db import connection
        from api.rfq.auth import Identity

        with connection() as conn:
            source = module.snapshot(
                conn,
                item["rfq_id"],
                Identity(state["user"], state["workspace"], "owner"),
            )
            quote = conn.execute(
                "select * from procurement.quote_drafts where id=%s and workspace_id=%s",
                (item["quote_id"], state["workspace"]),
            ).fetchone()
        source.update(
            quote_id=str(quote["id"]),
            quote_revision=quote["revision"],
            quote_policy=quote["policy"],
            quote_choices=quote["offer_choices"],
            catalog_versions=[state["version"]],
        )
        run = {
            "id": str(uuid4()),
            "workspace_id": state["workspace"],
            "snapshot": jsonable_encoder(source),
            "metadata": {"tool_schema": VERSION, "batch_size": 4},
            "planning_state": {},
        }
        receipts = []
        run["metadata"]["source_fingerprint"] = fingerprint(run["snapshot"])
        started = time.perf_counter()
        work = remaining(run, receipts, EvidenceResolver(run, receipts))
        for call in mandatory_plan(work, 4):
            function = call["function"]
            receipts.append(
                {
                    "id": str(uuid4()),
                    "run_id": run["id"],
                    "workspace_id": state["workspace"],
                    "ordinal": len(receipts) + 1,
                    "tool": function["name"],
                    "arguments": function["arguments"],
                    "schema_version": VERSION,
                    "status": "succeeded",
                    "error": None,
                    "execution_origin": "backend_scheduled",
                    "result": execute(function["name"], function["arguments"], run),
                }
            )
        resolver = EvidenceResolver(run, receipts)
        request = {
            "claims": [
                {key: group[key] for key in ["source_key", "receipt_id", "pointers"]}
                for group in resolver.inventory()
            ]
        }
        result = resolver.resolve(request)
        # The inherited fact flag describes reference selection, not read origin.
        # Here references are selected by this deterministic pipeline, not a model.
        result["reference_selection_origin"] = "deterministic_pipeline"
        for fact in result["claims"]:
            fact["model_selected"] = False
        elapsed = (time.perf_counter() - started) * 1000
        checked = audit(case, item, run, result, receipts)
        passed = (
            result["complete"]
            and checked["required_source_coverage"]
            and checked["required_fact_coverage"]
            and checked["unknowns_correct"]
            and checked["quote_readiness_correct"]
            and not checked["invalid_facts"]
        )
        records.append(
            {
                "scenario": case["id"],
                "split": case["split"],
                "line_count": len(case["lines"]),
                "passed": passed,
                "audit": checked,
                "latency_ms": elapsed,
                "tool_receipts": receipts,
                "result": result,
            }
        )
    output = {
        "label": "Deterministic offline pipeline; zero model calls; no durable agent publication",
        "native_model_evidence": False,
        "model_calls": 0,
        "records": records,
    }
    (RESULTS / "deterministic-baseline.json").write_text(
        json.dumps(jsonable_encoder(output), indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "cases": len(records),
                "passed": sum(row["passed"] for row in records),
                "model_calls": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
