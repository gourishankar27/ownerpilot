"""Reproducible supplemental source baseline, independent audits and measured summaries."""

import importlib.util
import json
import math
import statistics
import time
from collections import Counter
from pathlib import Path
from uuid import uuid4

from api.procurement_agent.evidence import EvidenceResolver
from api.procurement_agent.service import digest
from api.procurement_agent.tools import execute, verify

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs/rfq/phase3_1/results"
OUT = RESULTS / "evaluation/dev-contract6"


def quantile(values, percentile):
    return (
        sorted(values)[max(0, math.ceil(len(values) * percentile) - 1)]
        if values
        else None
    )


def aggregate(records, initial=False, legacy=False):
    def complete(row):
        return row["initial_verified_complete"] if initial else row["verified_complete"]

    # Initial checkpoint timestamps include DB admission; runner totals do not.
    # Use observed runner totals for unrepaired traces, and do not fabricate a
    # no-repair counterfactual total for the trace that actually used correction.
    timed = [row for row in records if not initial or not row["repair_attempts"]]
    latencies = [row["latency_ms"] for row in timed]
    stats = [
        stat
        for row in records
        for stat in row["model_stats"]
        if not initial or stat.get("phase") != "repair"
    ]
    facts = sum(
        row["initial_audit" if initial else "audit"]["facts_inspected"]
        for row in records
    )
    unsupported = sum(
        len(row["initial_audit" if initial else "audit"]["invalid_claims"])
        for row in records
    )
    tools = [tool for row in records for tool in row["tool_receipts"]]
    result = {
        "runs": len(records),
        "verified_complete": sum(complete(row) for row in records),
        "by_split": {
            split: {
                "runs": sum(row["split"] == split for row in records),
                "complete": sum(
                    complete(row) for row in records if row["split"] == split
                ),
            }
            for split in sorted({row["split"] for row in records})
        },
        "materialized_facts": facts,
        "independent_invalid_facts": unsupported,
        "tool_calls": len(tools),
        "successful_tools": sum(tool["status"] == "succeeded" for tool in tools),
        "unauthorized_execution": sum(
            tool["status"] == "succeeded" and tool["policy"] != "allowed_read_only"
            for tool in tools
        ),
        "authorized_tool_arguments": all(
            row["audit"]["tool_arguments_authorized"] for row in records
        ),
        "source_coverage_complete": sum(
            row["audit"]["source_tool_coverage"] for row in records
        ),
        "median_ms": statistics.median(latencies) if latencies else None,
        "latency_samples": len(timed),
        "latency_scope": "Observed runner totals; initial-only excludes repaired traces whose counterfactual total was not executed",
        "p95_ms": quantile(latencies, 0.95),
        "successful_median_ms": statistics.median(
            [latency for row, latency in zip(timed, latencies) if complete(row)]
        )
        if any(complete(row) for row in timed)
        else None,
        "repairs": 0
        if initial or legacy
        else sum(row["repair_attempts"] for row in records),
        "actual_chat_requests": sum(
            row["actual_chat_requests"] - (row["repair_attempts"] if initial else 0)
            for row in records
        ),
        "prompt_tokens": sum(stat.get("prompt_eval_count", 0) for stat in stats),
        "generated_tokens": sum(stat.get("eval_count", 0) for stat in stats),
        "load_ms": sum(stat.get("load_duration", 0) for stat in stats) / 1e6,
        "model_ms": sum(stat.get("total_duration", 0) for stat in stats) / 1e6,
        "repair_ms": sum(
            stat.get("wall_ms", 0)
            for row in records
            for stat in row["model_stats"]
            if stat.get("phase") == "repair"
        )
        if not initial
        else 0,
        "tool_ms": sum(float(tool["duration_ms"]) for tool in tools),
        "loaded_before_runs": sum(
            row["resources"]["model_loaded_before"] for row in records
        ),
        "readiness_label_disagreements": [
            row["scenario"]
            for row in records
            if not row["quote_ready_matches_authored"]
        ],
        "failures": dict(
            Counter(
                (
                    "initial_citation_or_coverage_failure"
                    if initial
                    else row["error"] or "independent_coverage_failure"
                )
                for row in records
                if not complete(row)
            )
        ),
    }
    if legacy:
        accepted = rejected = 0
        for row in records:
            for claim in (row.get("legacy_candidate") or {}).get("claims", []):
                try:
                    verify(json.dumps({"claims": [claim]}), row["tool_receipts"])
                    accepted += 1
                except ValueError:
                    rejected += 1
        result.update(
            valid_candidate_citations=accepted,
            rejected_candidate_citations=rejected,
            legacy_backend_complete=sum(row["state"] == "complete" for row in records),
        )
    else:
        selected = [
            row["initial_result"] if initial else row["result"] for row in records
        ]
        result["rejected_reference_diagnostics"] = sum(
            len(value.get("invalid_citations", [])) for value in selected
        )
        result["resolved_scalar_references"] = sum(
            len(value.get("claims", [])) for value in selected
        )
    return result


def baseline(records, data, state, module):
    cases = {case["id"]: case for case in data["native_scenarios"]}
    reports = []
    for row in records:
        identifier = str(uuid4())
        run = {
            "id": identifier,
            "workspace_id": state["workspace"],
            "snapshot": row["source_snapshot"],
            "metadata": {
                **row["model"],
                "source_fingerprint": digest(row["source_snapshot"]),
            },
        }
        # Workspace binding comes from the real source result when available; the
        # deterministic report is offline and is never inserted into the database.
        run["workspace_id"] = state["workspace"]
        started = time.perf_counter()
        receipts = []
        requests = [("get_approved_rfq", {})] + [
            (name, {"line_id": line["line_id"]})
            for line in run["snapshot"]["lines"]
            for name in ["get_reviewed_product_selection", "get_supplier_offers"]
        ]
        for name, arguments in requests:
            receipts.append(
                {
                    "id": str(uuid4()),
                    "run_id": identifier,
                    "ordinal": len(receipts) + 1,
                    "tool": name,
                    "schema_version": "procurement-tools/2",
                    "arguments": arguments,
                    "status": "succeeded",
                    "result": execute(name, arguments, run),
                }
            )
        resolver = EvidenceResolver(run, receipts)
        resolved = resolver.resolve(
            {
                "claims": [
                    {
                        key: group[key]
                        for key in ["receipt_id", "source_key", "pointers"]
                    }
                    for group in resolver.inventory()
                ]
            }
        )
        audit = module.authored_audit(
            cases[row["scenario"]],
            state["cases"][row["scenario"]],
            resolved["claims"],
            receipts,
        )
        reports.append(
            {
                "scenario": row["scenario"],
                "latency_ms": (time.perf_counter() - started) * 1000,
                "complete": resolved["complete"]
                and audit["required_fact_coverage"]
                and not audit["invalid_claims"],
                "audit": audit,
                "result": resolved,
                "model_calls": 0,
                "deterministic_not_agent": True,
            }
        )
    return reports


def main():
    spec = importlib.util.spec_from_file_location(
        "phase31_eval", ROOT / "scripts/procurement31-evaluate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    records = [
        json.loads(path.read_text()) for path in OUT.glob("*-citation_repair.json")
    ]
    legacy = [json.loads(path.read_text()) for path in OUT.glob("*-legacy.json")]
    if len(records) != 60 or len(legacy) != 60:
        raise SystemExit("Refuses to publish a partial corpus as a final benchmark")
    data = json.loads(
        (ROOT / "data/evaluation/procurement-v2/scenarios.json").read_text()
    )
    state = json.loads((ROOT / ".local/rfq/phase3_1/evaluation-state.json").read_text())
    baseline_path = RESULTS / "deterministic-source-baseline.json"
    if baseline_path.exists():
        reports = json.loads(baseline_path.read_text())
    else:
        reports = baseline(records, data, state, module)
        baseline_path.write_text(json.dumps(reports, indent=2) + "\n", encoding="utf-8")
    summary = {
        "native_attempts": 120,
        "dataset_version": "procurement-v2",
        "configuration": "evaluation/dev-contract6/configuration.json",
        "legacy": aggregate(legacy, legacy=True),
        "citation_only": aggregate(records, initial=True),
        "citation_repair": aggregate(records),
        "deterministic": {
            "runs": len(reports),
            "complete": sum(row["complete"] for row in reports),
            "invalid_facts": sum(
                len(row["audit"]["invalid_claims"]) for row in reports
            ),
            "median_ms": statistics.median(row["latency_ms"] for row in reports),
            "p95_ms": quantile([row["latency_ms"] for row in reports], 0.95),
            "model_calls": 0,
        },
        "failure_cases": [
            {
                "scenario": row["scenario"],
                "pattern": row["pattern"],
                "error": row["error"],
                "coverage": row["result"].get("coverage"),
                "invalid_citations": row["result"].get("invalid_citations"),
            }
            for row in records
            if not row["verified_complete"]
        ],
    }
    for variant, rows, initial in [
        ("citation_only", records, True),
        ("citation_repair", records, False),
    ]:
        summary[variant]["by_split_held_out"] = aggregate(
            [row for row in rows if row["split"] == "held_out"], initial=initial
        )
    historic = [
        json.loads(path.read_text())
        for path in (RESULTS / "historical-comparison").glob("*-citation_repair.json")
    ]
    if len(historic) == 10:
        summary["historical_ten_case"] = {
            "citation_only": aggregate(historic, initial=True),
            "citation_repair": aggregate(historic),
            "original": json.loads(
                (ROOT / "docs/rfq/phase3/results/agent/summary.json").read_text()
            ),
        }
    (RESULTS / "evaluation-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                key: value
                for key, value in summary.items()
                if key not in {"failure_cases", "historical_ten_case"}
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
