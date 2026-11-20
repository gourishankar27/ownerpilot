"""Actual parser/provider benchmark. Never loads ground truth into extraction."""

import argparse
import asyncio
from collections import defaultdict
from difflib import SequenceMatcher
import hashlib
import json
import math
import platform
from pathlib import Path
import statistics
import time

from ..config import settings
from ..extraction import extract
from ..parsers import PARSER_VERSION, parse_document
from ..provider import PROMPT_VERSION, ProviderError


def match_items(expected, predicted):
    edges = []
    for i, truth in enumerate(expected):
        for j, item in enumerate(predicted):
            values = {k: v.value for k, v in item.fields.items()}
            mpn = truth.get("mpn")
            score = (
                2
                if mpn and mpn == values.get("mpn")
                else SequenceMatcher(
                    None,
                    truth.get("description", "").casefold(),
                    (values.get("description") or "").casefold(),
                ).ratio()
            )
            if score >= 0.7:
                edges.append((score, i, j))
    used_expected = set()
    used_predicted = set()
    pairs = []
    for _, i, j in sorted(edges, reverse=True):
        if i not in used_expected and j not in used_predicted:
            used_expected.add(i)
            used_predicted.add(j)
            pairs.append((i, j))
    return pairs


def metrics(rows):
    truth_count = sum(r.get("truth_count", 0) for r in rows)
    pred_count = sum(r.get("pred_count", 0) for r in rows)
    matches = sum(r.get("matches", 0) for r in rows)

    def ratio(numerator, denominator):
        return numerator / denominator if denominator else None

    precision = ratio(matches, pred_count) or 0
    recall = ratio(matches, truth_count) or 0
    result = {
        "documents": len(rows),
        "processed": sum(r["success"] for r in rows),
        "failed": sum(not r["success"] for r in rows),
        "truth_items": truth_count,
        "predicted_items": pred_count,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall)
        if precision + recall
        else 0,
    }
    for name in ("mpn", "manufacturer", "quantity"):
        result[name + "_accuracy"] = ratio(
            sum(r.get(name + "_correct", 0) for r in rows), truth_count
        )
    result["required_completeness"] = ratio(
        sum(r.get("complete", 0) for r in rows), truth_count * 3
    )
    result["structured_validity"] = ratio(sum(r["success"] for r in rows), len(rows))
    result["document_success_rate"] = result["structured_validity"]
    result["unsupported_field_rate"] = ratio(
        sum(r.get("unsupported", 0) for r in rows),
        sum(r.get("populated", 0) for r in rows),
    )
    result["evidence_validity"] = ratio(
        sum(r.get("verified", 0) for r in rows), sum(r.get("evidence", 0) for r in rows)
    )
    result["duplicate_warning_rows"] = sum(r.get("duplicate_rows", 0) for r in rows)
    result["hallucinated_item_fields_rate"] = ratio(
        sum(r.get("hallucinated_item_fields", 0) for r in rows),
        sum(r.get("populated_item_fields", 0) for r in rows),
    )
    for name in ("latency_ms", "ocr_ms", "model_ms", "parser_ms", "deterministic_ms"):
        values = sorted(r.get(name, 0) for r in rows if r["success"])
        result[name] = {
            "median": statistics.median(values) if values else None,
            "p95": values[max(0, math.ceil(len(values) * 0.95) - 1)]
            if values
            else None,
            "total": sum(values),
        }
    return result


async def run(args):
    root = Path(args.dataset)
    manifest_bytes = (root / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    docs = [d for d in manifest["documents"] if d["split"] == args.split]
    if args.stratified:
        groups = {}
        for doc in docs:
            groups.setdefault(doc["layout_group"], doc)
        docs = list(groups.values())
    if args.ids:
        selected = set(args.ids.split(","))
        docs = [d for d in docs if d["id"] in selected]
    if args.limit:
        docs = docs[: args.limit]
    rows = []
    for doc in docs:
        started = time.perf_counter()
        truth_bytes = (root / doc["truth"]).read_bytes()
        truth = json.loads(truth_bytes)["items"]
        row = {
            "id": doc["id"],
            "format": doc["format"],
            "difficulty": doc["difficulty"],
            "group": doc["layout_group"],
            "truth_count": len(truth),
            "success": False,
        }
        try:
            content = (root / doc["source"]).read_bytes()
            if (
                hashlib.sha256(content).hexdigest() != doc["sha256"]
                or hashlib.sha256(truth_bytes).hexdigest() != doc["truth_sha256"]
            ):
                raise ValueError("frozen_dataset_hash_mismatch")
            parsed = parse_document(doc["source"], content, doc["id"])
            result = await extract([parsed], args.mode)
            pairs = match_items(truth, result.items)
            row.update(
                {
                    "success": True,
                    "pred_count": len(result.items),
                    "matches": len(pairs),
                    "latency_ms": (time.perf_counter() - started) * 1000,
                    **{
                        k: result.metadata[k]
                        for k in ("ocr_ms", "model_ms", "parser_ms", "deterministic_ms")
                    },
                    "metadata": result.metadata,
                }
            )
            for name in ("mpn", "manufacturer", "quantity"):
                row[name + "_correct"] = sum(
                    truth[i].get(name) == result.items[j].fields[name].value
                    for i, j in pairs
                )
            row["complete"] = sum(
                sum(
                    result.items[j].fields[n].value is not None
                    for n in ("description", "quantity", "unit")
                )
                for _, j in pairs
            )
            matched_predictions = {j: i for i, j in pairs}
            row["populated_item_fields"] = sum(
                f.value is not None
                for item in result.items
                for f in item.fields.values()
            )
            row["hallucinated_item_fields"] = sum(
                f.value is not None
                and (
                    j not in matched_predictions
                    or f.value != truth[matched_predictions[j]].get(name)
                )
                for j, item in enumerate(result.items)
                for name, f in item.fields.items()
            )
            fields = list(result.header.values()) + [
                f for item in result.items for f in item.fields.values()
            ]
            populated = [f for f in fields if f.value is not None or f.raw is not None]
            row["populated"] = len(populated)
            row["unsupported"] = sum(
                not f.evidence or not all(e.verified for e in f.evidence)
                for f in populated
            )
            evidence = [e for f in fields for e in f.evidence]
            row["evidence"] = len(evidence)
            row["verified"] = sum(e.verified for e in evidence)
            row["duplicate_rows"] = sum(bool(i.warnings) for i in result.items)
        except Exception as exc:
            row["failure"] = (
                exc.category if isinstance(exc, ProviderError) else type(exc).__name__
            )
            row["latency_ms"] = (time.perf_counter() - started) * 1000
        rows.append(row)
        print(
            json.dumps(
                {k: row[k] for k in ("id", "success", "latency_ms")}
                | ({"failure": row["failure"]} if "failure" in row else {})
            ),
            flush=True,
        )
    grouped = defaultdict(list)
    for row in rows:
        grouped["format:" + row["format"]].append(row)
        grouped["difficulty:" + row["difficulty"]].append(row)
        grouped["layout:" + row["group"]].append(row)
    report = {
        "dataset_version": manifest["version"],
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "mode": args.mode,
        "split": args.split,
        "stratified": args.stratified,
        "planned_samples": len(docs),
        "skipped_samples": 0,
        "parser_version": PARSER_VERSION,
        "prompt_version": PROMPT_VERSION,
        "model": settings().ollama_model or None,
        "hardware": platform.platform(),
        "configuration": {
            "model_input_chars": settings().model_input_chars,
            "model_context": settings().model_context,
            "model_output_tokens": settings().model_output_tokens,
            "temperature": settings().model_temperature,
            "model_timeout": settings().model_timeout,
            "model_retries": settings().model_retries,
        },
        "metrics": metrics(rows),
        "by_group": {k: metrics(v) for k, v in grouped.items()},
        "samples": rows,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["metrics"], indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="data/evaluation/rfq")
    parser.add_argument("--split", choices=["dev", "heldout"], default="heldout")
    parser.add_argument(
        "--mode", choices=["deterministic", "llm", "hybrid"], default="deterministic"
    )
    parser.add_argument("--stratified", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--ids", help="Comma-separated document IDs for explicit diagnostic subsets"
    )
    parser.add_argument("--output", required=True)
    asyncio.run(run(parser.parse_args()))
