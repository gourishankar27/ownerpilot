"""Resumable, synthetic-only quality evaluation with per-sample durable records."""

import argparse
import asyncio
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import platform
import statistics
import time

from ..config import settings, activate, deactivate
from ..contracts import FieldValue
from ..extraction import extract
from ..parsers import parse_document, PARSER_VERSION
from ..provider import OllamaProvider
from .matching_v2 import match_items, VERSION
from .run import match_items as historical_match


def source_hash():
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")) + sorted((root / "prompts").glob("*.txt")):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def score(truth, result):
    expected = truth["items"]
    predicted = result.items
    pairs = match_items(expected, predicted)
    counts = {
        "truth_items": len(expected),
        "predicted_items": len(predicted),
        "matches": len(pairs),
        "ambiguous_assignments": sum(p["ambiguous"] for p in pairs),
        "missed_rows": len(expected) - len(pairs),
        "unexpected_rows": len(predicted) - len(pairs),
    }
    for name in ("mpn", "manufacturer", "quantity", "unit", "description"):
        counts[name + "_correct"] = sum(
            not pair["ambiguous"]
            and expected[pair["truth"]].get(name)
            == predicted[pair["prediction"]].fields.get(name, FieldValue()).value
            for pair in pairs
        )
    counts["header_total"] = len(truth.get("header", {}))
    counts["header_correct"] = sum(
        result.header.get(name, FieldValue()).value == value
        for name, value in truth.get("header", {}).items()
    )
    fields = [f for item in predicted for f in item.fields.values()] + list(
        result.header.values()
    )
    populated = [f for f in fields if f.value is not None or f.raw is not None]
    evidence = [e for f in populated for e in f.evidence]
    counts.update(
        {
            "populated_fields": len(populated),
            "unsupported_proposals": sum(
                not f.evidence or not all(e.verified for e in f.evidence)
                for f in populated
            ),
            "accepted_fields": sum(
                f.status == "validated" and f.value is not None for f in populated
            ),
            "unsupported_accepted": sum(
                f.status == "validated"
                and f.value is not None
                and (not f.evidence or not all(e.verified for e in f.evidence))
                for f in populated
            ),
            "evidence_total": len(evidence),
            "evidence_occurrence": sum(e.verified for e in evidence),
            "association_observed": sum(
                e.row_association != "unknown" for e in evidence
            ),
            "association_verified": sum(
                e.row_association == "verified" for e in evidence
            ),
            "column_observed": sum(e.column_association != "unknown" for e in evidence),
            "column_verified": sum(
                e.column_association == "verified" for e in evidence
            ),
            "unresolved_items": sum(
                any(
                    item.fields.get(name, FieldValue()).status != "validated"
                    for name in ("description", "quantity", "unit", "mpn")
                )
                for item in predicted
            ),
            "required_populated": sum(
                item.fields.get(name, FieldValue()).value is not None
                for item in predicted
                for name in ("description", "quantity", "unit")
            ),
            "duplicate_warnings": sum(bool(item.warnings) for item in predicted),
        }
    )
    mapped = {pair["prediction"]: pair for pair in pairs}
    erroneous = 0
    item_populated = 0
    row_correct = 0
    row_total = 0
    column_correct = 0
    column_total = 0
    for j, item in enumerate(predicted):
        pair = mapped.get(j)
        for name, field in item.fields.items():
            if field.value is not None:
                item_populated += 1
                if (
                    not pair
                    or pair["ambiguous"]
                    or expected[pair["truth"]].get(name) != field.value
                ):
                    erroneous += 1
            if pair:
                label = expected[pair["truth"]].get("source", {})
                for e in field.evidence:
                    if label.get("row") and not label.get("bbox"):
                        row_total += 1
                        row_correct += e.location.row == label["row"] and (
                            not label.get("sheet") or label["sheet"] == e.location.sheet
                        )
                    if name in label.get("columns", {}):
                        column_total += 1
                        column_correct += e.location.column == label["columns"][name]
    counts.update(
        {
            "erroneous_item_fields": erroneous,
            "populated_item_fields": item_populated,
            "field_row_total": row_total,
            "field_row_correct": row_correct,
            "field_column_total": column_total,
            "field_column_correct": column_correct,
        }
    )
    legacy = historical_match(expected, predicted)
    counts["historical_compatible"] = {
        "matches": len(legacy),
        **{
            name + "_correct": sum(
                expected[i].get(name)
                == predicted[j].fields.get(name, FieldValue()).value
                for i, j in legacy
            )
            for name in ("mpn", "quantity", "manufacturer")
        },
    }
    return counts


def aggregate(samples):
    def total(key):
        return sum(s.get("counts", {}).get(key, 0) for s in samples)

    def ratio(a, b):
        return total(a) / total(b) if total(b) else None

    completed = [s for s in samples if s["success"]]
    matched = total("matches")
    truth = total("truth_items")
    pred = total("predicted_items")
    precision = matched / pred if pred else 0
    recall = matched / truth if truth else 0
    result = {
        "attempted_documents": len(samples),
        "successful_documents": len(completed),
        "failed_documents": len(samples) - len(completed),
        "raw_counts": {
            key: total(key)
            for key in sorted(
                {
                    k
                    for s in samples
                    for k, v in s.get("counts", {}).items()
                    if isinstance(v, (int, float))
                }
            )
        },
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall)
        if precision + recall
        else 0,
        "success_rate": len(completed) / len(samples) if samples else None,
        "structured_output_validity": len(completed) / len(samples)
        if samples
        else None,
    }
    for name in ("mpn", "manufacturer", "quantity", "unit", "description"):
        result[name + "_accuracy"] = ratio(name + "_correct", "truth_items")
    for label, a, b in [
        ("header_accuracy", "header_correct", "header_total"),
        ("source_occurrence", "evidence_occurrence", "evidence_total"),
        ("structural_association_rate", "association_verified", "association_observed"),
        ("field_row_accuracy", "field_row_correct", "field_row_total"),
        ("field_column_accuracy", "field_column_correct", "field_column_total"),
        ("unsupported_proposed_rate", "unsupported_proposals", "populated_fields"),
        ("unsupported_accepted_rate", "unsupported_accepted", "accepted_fields"),
        (
            "erroneous_item_fields_rate",
            "erroneous_item_fields",
            "populated_item_fields",
        ),
        ("unresolved_item_rate", "unresolved_items", "predicted_items"),
    ]:
        result[label] = ratio(a, b)
    result["required_completeness"] = (
        total("required_populated") / (truth * 3) if truth else None
    )
    for key in ("latency_ms", "ocr_ms", "parser_ms", "model_ms", "deterministic_ms"):
        values = sorted(s.get("timings", {}).get(key, 0) for s in completed)
        result[key] = {
            "median": statistics.median(values) if values else None,
            "p95": values[max(0, math.ceil(len(values) * 0.95) - 1)]
            if values
            else None,
            "successful_denominator": len(values),
            "failed_attempt_ms": sum(
                s.get("timings", {}).get(key, 0) for s in samples if not s["success"]
            ),
        }
    calls = sum(
        s.get("metadata", {}).get(
            "model_call_count", len(s.get("metadata", {}).get("model_runs", []))
        )
        for s in completed
    )
    result["model_calls"] = calls
    result["average_model_calls"] = calls / len(samples) if samples else None
    result["deterministic_only_rate"] = (
        sum(not s.get("metadata", {}).get("model_runs") for s in completed)
        / len(completed)
        if completed
        else None
    )
    result["retry_attempts"] = sum(
        max(0, run.get("attempt", 1) - 1)
        for s in completed
        for run in s.get("metadata", {}).get("model_runs", [])
    )
    return result


async def run(args):
    root = Path(args.dataset)
    if not str(root).replace("\\", "/").startswith("data/evaluation/"):
        raise SystemExit(
            "This benchmark runner permits synthetic evaluation datasets only."
        )
    manifest_bytes = (root / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    documents = [d for d in manifest["documents"] if d["split"] == args.split]
    if args.stratified:
        selected = {}
        for d in documents:
            selected.setdefault(d["layout_group"], d)
        documents = list(selected.values())
    if args.ids:
        documents = [d for d in documents if d["id"] in set(args.ids.split(","))]
    configuration = {
        "ollama_model": args.model or settings().ollama_model,
        "ocr_strategy": args.ocr or settings().ocr_strategy,
        "model_context": args.context,
        "model_output_tokens": args.output_tokens,
        "model_retries": args.retries,
    }
    token = activate(configuration)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    provider = OllamaProvider(
        model=configuration["ollama_model"], compact=args.profile == "compact"
    )
    model_health = (
        await provider.health() if args.mode != "deterministic" else {"available": None}
    )
    identity = {
        "source_sha256": source_hash(),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "dataset_version": manifest["version"],
        "policy": args.policy,
        "mode": args.mode,
        "profile": args.profile,
        "configuration": configuration,
        "model": model_health,
        "evaluator": VERSION,
        "parser": PARSER_VERSION,
        "sample_ids": [d["id"] for d in documents],
        "split": args.split,
    }
    config_file = output.with_suffix(".config.json")
    journal = output.with_suffix(".jsonl")
    if config_file.exists() and json.loads(config_file.read_text()) != identity:
        raise SystemExit("Resume configuration/source mismatch; use a new output name.")
    config_file.write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    completed = {}
    if journal.exists():
        for line in journal.read_text().splitlines():
            try:
                r = json.loads(line)
                completed[r["id"]] = r
            except json.JSONDecodeError:
                raise SystemExit(
                    "Journal has an incomplete tail; preserve and repair it explicitly before resuming."
                )
    try:
        for document in documents:
            if document["id"] in completed:
                continue
            started = time.perf_counter()
            record = {
                "id": document["id"],
                "format": document["format"],
                "difficulty": document["difficulty"],
                "layout_group": document["layout_group"],
                "success": False,
                "counts": {"truth_items": document["expected_items"]},
            }
            try:
                content = (root / document["source"]).read_bytes()
                labels = (root / document["truth"]).read_bytes()
                if (
                    hashlib.sha256(content).hexdigest() != document["sha256"]
                    or hashlib.sha256(labels).hexdigest() != document["truth_sha256"]
                ):
                    raise ValueError("frozen_dataset_hash_mismatch")
                parsed = parse_document(
                    document["source"], content, document["id"], policy=args.policy
                )
                result = await extract(
                    [parsed], args.mode, provider, policy=args.policy
                )
                record.update(
                    {
                        "success": True,
                        "counts": score(json.loads(labels), result),
                        "metadata": result.metadata,
                        "parsed_metadata": parsed.metadata,
                        "predictions": result.model_dump(mode="json"),
                        "timings": {
                            "latency_ms": (time.perf_counter() - started) * 1000,
                            **{
                                k: result.metadata.get(k, 0)
                                for k in (
                                    "ocr_ms",
                                    "parser_ms",
                                    "model_ms",
                                    "deterministic_ms",
                                )
                            },
                        },
                    }
                )
            except Exception as exc:
                record.update(
                    {
                        "failure": getattr(exc, "category", type(exc).__name__),
                        "timings": {
                            "latency_ms": (time.perf_counter() - started) * 1000
                        },
                    }
                )
            completed[document["id"]] = record
            with journal.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record) + "\n")
                stream.flush()
            print(
                json.dumps(
                    {k: record[k] for k in ("id", "success")}
                    | {"elapsed_ms": record["timings"]["latency_ms"]}
                ),
                flush=True,
            )
            write_report(output, identity, documents, completed)
    finally:
        deactivate(token)
    write_report(output, identity, documents, completed)


def write_report(output, identity, documents, completed):
    samples = [completed[d["id"]] for d in documents if d["id"] in completed]
    groups = defaultdict(list)
    for sample in samples:
        groups["layout:" + sample["layout_group"]].append(sample)
        groups["format:" + sample["format"]].append(sample)
        groups["difficulty:" + sample["difficulty"]].append(sample)
    report = {
        **identity,
        "status": "complete" if len(samples) == len(documents) else "incomplete",
        "planned_samples": len(documents),
        "actual_samples": len(samples),
        "skipped_samples": 0,
        "pending_ids": [d["id"] for d in documents if d["id"] not in completed],
        "hardware": platform.platform(),
        "metrics": aggregate(samples),
        "by_group": {key: aggregate(value) for key, value in groups.items()},
        "samples": samples,
    }
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="data/evaluation/rfq")
    parser.add_argument("--split", default="heldout")
    parser.add_argument(
        "--mode", choices=["deterministic", "llm", "hybrid"], default="hybrid"
    )
    parser.add_argument(
        "--policy", choices=["phase1", "selective-v2"], default="selective-v2"
    )
    parser.add_argument("--profile", choices=["full", "compact"], default="full")
    parser.add_argument("--model", default="")
    parser.add_argument("--ocr", default="")
    parser.add_argument("--context", type=int, default=8192)
    parser.add_argument("--output-tokens", type=int, default=2048)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--ids")
    parser.add_argument("--stratified", action="store_true")
    parser.add_argument("--output", required=True)
    asyncio.run(run(parser.parse_args()))
