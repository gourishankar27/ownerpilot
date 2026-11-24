"""Aggregate immutable actual-native traces without changing labels or trials."""

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs/rfq/phase3_2/results"


def distribution(values):
    return {
        "n": len(values),
        "median": statistics.median(values) if values else None,
        "p95_nearest_rank": sorted(values)[math.ceil(0.95 * len(values)) - 1]
        if values
        else None,
    }


def summarize(rows):
    audits = [row["audit"] for row in rows]
    completed = [row for row in rows if row["verified_complete"]]
    receipts = [receipt for row in rows for receipt in row["tool_receipts"]]
    batches = [
        receipt for receipt in receipts if receipt["tool"] == "get_line_research_batch"
    ]
    samples = [
        row["resources"][phase].get("gpu_device_used_mib")
        for row in rows
        for phase in ["before", "after"]
    ]
    samples = [sample for sample in samples if sample is not None]

    def count(key):
        return sum(audit[key] for audit in audits)

    return {
        "n": len(rows),
        "complete": sum(row["verified_complete"] for row in rows),
        "source_complete_cases": count("required_source_coverage"),
        "lines": sum(row["line_count"] for row in rows),
        "covered_lines": count("covered_lines"),
        "source_pairs_required": count("source_pairs_required"),
        "source_pairs_inspected": count("source_pairs_inspected"),
        "required_facts": count("required_facts"),
        "supported_required_facts": count("supported_required_facts"),
        "invalid_facts": sum(len(audit["invalid_facts"]) for audit in audits),
        "source_errors": sum(len(audit["source_errors"]) for audit in audits),
        "unauthorized_successful_tools": count("unauthorized_successful_tools"),
        "model_selected_tools": count("model_selected_tools"),
        "backend_scheduled_tools": count("backend_scheduled_tools"),
        "model_source_pairs": count("model_source_pairs"),
        "backend_source_pairs": count("backend_source_pairs"),
        "useful_model_tool_decisions": count("useful_model_tool_decisions"),
        "duplicate_source_reads": count("duplicate_source_reads"),
        "optional_calls": count("optional_calls"),
        "model_tool_successes": sum(
            receipt["execution_origin"] in {"model_selected", "legacy_model"}
            and receipt["status"] == "succeeded"
            for receipt in receipts
        ),
        "early_finalization_attempts": None
        if rows[0]["variant"] == "phase31"
        else sum(
            event["stage"] == "early_finalization_refused"
            for row in rows
            for event in row.get("planning_state", {}).get("timeline", [])
        ),
        "source_covered_lines_per_all_tool_rpc": count("covered_lines") / len(receipts)
        if receipts
        else None,
        "batch_lines_per_successful_parent": distribution(
            [
                len(receipt["result"]["lines"])
                for receipt in batches
                if receipt["status"] == "succeeded"
            ]
        ),
        "batch_output_bytes": distribution(
            [
                receipt.get("call_details", {}).get("result_bytes", 0)
                for receipt in batches
            ]
        ),
        "batch_line_utilization": {
            "requested_lines": sum(
                len(receipt["arguments"].get("line_ids", [])) for receipt in batches
            ),
            "capacity": sum(
                row["model"].get("batch_size", 4)
                for row in rows
                for receipt in row["tool_receipts"]
                if receipt["tool"] == "get_line_research_batch"
            ),
        },
        "per_completed_run": {
            "denominator": len(completed),
            "model_calls": distribution([len(row["model_calls"]) for row in completed]),
            "model_output_tokens": distribution(
                [
                    sum(
                        call["metrics"].get("eval_count", 0)
                        for call in row["model_calls"]
                    )
                    for row in completed
                ]
            ),
            "model_input_tokens": distribution(
                [
                    sum(
                        call["metrics"].get("prompt_eval_count", 0)
                        for call in row["model_calls"]
                    )
                    for row in completed
                ]
            ),
            "tool_calls": distribution(
                [len(row["tool_receipts"]) for row in completed]
            ),
        },
        "gpu_before_after_mib": {
            "samples": len(samples),
            "minimum": min(samples) if samples else None,
            "maximum": max(samples) if samples else None,
            "scope": "Device-wide before/after samples; not peaks or isolated model memory",
        },
        "inference_warm_before": sum(
            row["resources"]["model_loaded_before"] for row in rows
        ),
        "timing_scope": "Inline execution; no broker queue. Admission-to-runner preparation and terminal execution are timed. Independent grading excluded. Queue/recovery measured separately.",
        "batch_line_counts": dict(
            Counter(
                str(size) for audit in audits for size in audit["batch_line_counts"]
            )
        ),
        "unused_tool_capacity": sum(
            max(0, 8 - len(row["tool_receipts"])) for row in rows
        ),
        "planning_calls": sum(row["planning_calls"] for row in rows),
        "finalization_calls": sum(row["finalization_calls"] for row in rows),
        "repair_calls": sum(row["repair_attempts"] for row in rows),
        "chat_request_attempts": sum(row["chat_requests"] for row in rows),
        "acknowledged_model_responses": sum(
            row.get("acknowledged_model_responses", 0) for row in rows
        ),
        "tokens": {
            key: sum(
                call["metrics"].get(key, 0)
                for row in rows
                for call in row["model_calls"]
            )
            for key in ["prompt_eval_count", "eval_count"]
        },
        "actual_inference_cases": sum(row["actual_local_inference"] for row in rows),
        "latency_ms_all": distribution([row["latency_ms"] for row in rows]),
        "latency_ms_complete": distribution(
            [row["latency_ms"] for row in rows if row["verified_complete"]]
        ),
        "errors": dict(Counter(row["error"] or "none" for row in rows)),
        "rejected_citation_codes": dict(
            Counter(
                error["code"]
                for row in rows
                for attempt in row["finalization_attempts"]
                for error in (attempt.get("resolution") or {}).get(
                    "invalid_citations", []
                )
            )
        ),
        "unknowns_correct_cases": count("unknowns_correct"),
        "quote_readiness_correct_cases": sum(
            audit["quote_readiness_correct"] is True for audit in audits
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--output", default="summary.json")
    args = parser.parse_args()
    folder = RESULTS / "evaluation" / args.experiment
    rows = [
        json.loads(path.read_text())
        for path in sorted(folder.glob("v3-*.json"))
        if not path.name.endswith(".admitted.json")
    ]
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["split"], row["variant"])].append(row)
    report = {
        "experiment": args.experiment,
        "denominators": "One actual execution per case/variant/split. Corrections are not independent trials.",
        "groups": {},
    }
    for (split, variant), values in grouped.items():
        summary = summarize(values)
        summary["by_line_count"] = {
            str(size): summarize([row for row in values if row["line_count"] == size])
            for size in sorted({row["line_count"] for row in values})
        }
        report["groups"][split + "/" + variant] = summary
    for split in sorted({row["split"] for row in rows}):
        variants = sorted({row["variant"] for row in rows if row["split"] == split})
        sets = [
            {
                row["scenario"]
                for row in grouped[(split, variant)]
                if row["verified_complete"]
            }
            for variant in variants
        ]
        common = set.intersection(*sets) if sets else set()
        report.setdefault("matched_successful_cases", {})[split] = {
            "cases": sorted(common),
            "latency_ms": {
                variant: distribution(
                    [
                        row["latency_ms"]
                        for row in grouped[(split, variant)]
                        if row["scenario"] in common
                    ]
                )
                for variant in variants
            },
        }
    (folder / args.output).write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                key: {
                    name: value[name]
                    for name in [
                        "n",
                        "complete",
                        "covered_lines",
                        "lines",
                        "invalid_facts",
                        "model_selected_tools",
                        "backend_scheduled_tools",
                    ]
                }
                for key, value in report["groups"].items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
