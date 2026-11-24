"""Backend-defined remaining work and finite research capacity, never source claims."""

import json

from .tools_v3 import KINDS, MAX_BATCH, MAX_RESULT_BYTES

POLICY = "procurement-planning/2"
COVERAGE = "research-coverage/2"
STRATEGIES = {"native_batch", "coverage_native", "hybrid", "mandatory_scheduler"}
MAX_LINES = 12
MAX_PLANNING = 4
MAX_TOOLS = 8
MAX_FINALIZATIONS = 1
MAX_REPAIRS = 1
MAX_SECONDS = 240
LIMITS = {
    "max_planning_calls": 4,
    "max_finalization_calls": 1,
    "max_repair_calls": 1,
    "max_total_model_calls": 6,
    "max_calls": 8,
    "max_repeats": 2,
    "max_seconds": 240,
    "provider_timeout_seconds": 60,
    "context": 8192,
    "temperature": 0,
    "max_response_bytes": 65536,
    "finalization_output_tokens": 4096,
    "planning_output_tokens": 1600,
    "max_lines": 12,
    "max_turns": 5,
}


def partitions(ids, batch_size, sizes):
    chunk, size = [], 0
    for identifier in ids:
        estimate = sizes.get(identifier, 2048)
        if chunk and (len(chunk) >= batch_size or size + estimate > MAX_RESULT_BYTES):
            yield chunk
            chunk, size = [], 0
        chunk.append(identifier)
        size += estimate
    if chunk:
        yield chunk


def capacity(snapshot, batch_size=4):
    lines = snapshot["lines"]
    required_groups = len(lines) + sum(
        len(line["offers"]["attestations"]) for line in lines
    )
    # These are estimates only, not executed business reads or evidence receipts.
    estimated_line_bytes = [
        len(
            json.dumps(
                {
                    "selection": {
                        k: v
                        for k, v in line["selection"].items()
                        if k not in {"candidates", "reviews"}
                    },
                    "offers": line["offers"],
                },
                default=str,
            ).encode()
        )
        + 2048
        for line in lines
    ]
    sizes = dict(zip([line["line_id"] for line in lines], estimated_line_bytes))
    minimum_tools = 1 + len(
        list(partitions(list(sizes), batch_size if batch_size in {2, 4} else 4, sizes))
    )
    problems = []
    if not lines or len(lines) > MAX_LINES:
        problems.append("capacity_line_limit")
    if batch_size not in {2, MAX_BATCH}:
        problems.append("unsupported_batch_size")
    if required_groups > 32:
        problems.append("capacity_citation_groups")
    if minimum_tools > MAX_TOOLS:
        problems.append("capacity_tool_budget")
    if any(size > MAX_RESULT_BYTES for size in estimated_line_bytes):
        problems.append("capacity_source_size")
    return {
        "supported": not problems,
        "line_count": len(lines),
        "maximum_lines": MAX_LINES,
        "batch_size": batch_size,
        "minimum_tool_calls": minimum_tools,
        "required_reference_groups": required_groups,
        "estimated_line_bytes": estimated_line_bytes,
        "estimated_bytes_by_line": sizes,
        "blockers": problems,
        "continuation_available": False,
        "continuation_guidance": "Create a separately reviewed scoped RFQ if this approved scope exceeds the envelope"
        if problems
        else None,
    }


def remaining(run, receipts, resolver):
    coverage = resolver.coverage()
    pending = run.get("planning_state", {}).get("pending", [])
    recorded = {receipt["ordinal"] for receipt in receipts}
    result = []

    def mentions(receipt, line_id):
        args = receipt["arguments"]
        ids = args.get("line_ids")
        return (
            str(args.get("line_id", "")) == line_id
            or isinstance(ids, list)
            and line_id in ids
        )

    for line in coverage["lines"]:
        wanted = {name for name in line["missing_tools"]}
        result.append(
            {
                "line_id": line["line_id"],
                "selection_inspected": "get_reviewed_product_selection" not in wanted,
                "offers_inspected": "get_supplier_offers" not in wanted,
                "missing_tools": sorted(wanted),
                "receipt_ids": [
                    str(receipt["id"])
                    for receipt in receipts
                    if receipt["status"] == "succeeded"
                    and (mentions(receipt, line["line_id"]))
                ],
                "failed_receipts": [
                    str(receipt["id"])
                    for receipt in receipts
                    if receipt["status"] != "succeeded"
                    and (mentions(receipt, line["line_id"]))
                ],
                "source_covered": line["source_coverage_complete"],
            }
        )
    return {
        "policy": POLICY,
        "coverage_version": COVERAGE,
        "research_stage": "source_collection",
        "approved_rfq_read": coverage["approved_rfq_read"],
        "source_coverage_complete": coverage["source_coverage_complete"],
        "lines": result,
        "remaining_lines": [entry for entry in result if not entry["source_covered"]],
        "covered_lines": sum(entry["source_covered"] for entry in result),
        "total_lines": len(result),
        "pending_calls": sum(call["ordinal"] not in recorded for call in pending),
        "remaining_tool_calls": max(0, MAX_TOOLS - len(receipts)),
        "remaining_planning_turns": max(0, MAX_PLANNING - run.get("planning_calls", 0)),
        "required_action": "select_citations"
        if coverage["source_coverage_complete"]
        else "inspect_missing_sources",
        "capacity": capacity(run["snapshot"], run["metadata"].get("batch_size", 4)),
    }


def mandatory_plan(work, batch_size):
    result = []
    if not work["approved_rfq_read"]:
        result.append({"function": {"name": "get_approved_rfq", "arguments": {}}})
    buckets = {}
    for line in work["remaining_lines"]:
        include = tuple(
            kind for kind, (tool, _) in KINDS.items() if tool in line["missing_tools"]
        )
        if include:
            buckets.setdefault(include, []).append(line["line_id"])
    for include, ids in buckets.items():
        for chunk in partitions(
            ids, batch_size, work["capacity"].get("estimated_bytes_by_line", {})
        ):
            result.append(
                {
                    "function": {
                        "name": "get_line_research_batch",
                        "arguments": {
                            "line_ids": chunk,
                            "include": list(include),
                        },
                    }
                }
            )
    return result
