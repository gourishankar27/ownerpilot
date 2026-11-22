"""Versioned selective routing and source-anchor merging, without confidence scores."""

from __future__ import annotations

import time
import re

from .association import deterministic_v2, layout, verify_v2, ASSOCIATION_VERSION
from .config import settings
from .contracts import Extraction, FieldValue, HEADER_FIELDS
from .extraction import chunks, merge_header
from .provider import OllamaProvider, ProviderError
from .validation import mark_duplicates

POLICY = "selective-v2"


def anchor(item):
    return next(
        (
            e.block_id
            for name in ("description", "mpn", "requested_sku", "line_number")
            for e in item.fields.get(name, FieldValue()).evidence
        ),
        None,
    )


def route(doc, baseline):
    records = layout(doc)
    consumed = {anchor(i): i for i in baseline.items}
    tasks = []
    candidates = 0
    for block_id, record in records.items():
        if record["header"] or not record["eligible"]:
            continue
        block = record["block"]
        item = consumed.get(block_id)
        table = bool(record["columns"])
        values = {
            name: record["cells"][i]
            for i, name in record["columns"].items()
            if i < len(record["cells"])
        }
        candidate = table and (
            values.get("line_number", "").strip().isdigit()
            or bool(
                values.get("description", "").strip()
                and (
                    values.get("mpn", "").strip() or values.get("quantity", "").strip()
                )
            )
        )
        if candidate:
            candidates += 1
        reasons = []
        if item:
            if any(
                item.fields[n].status != "validated"
                for n in ("description", "quantity", "unit")
            ):
                reasons.append("missing_or_uncertain_required_field")
            if item.fields["mpn"].status not in {"validated", "missing"}:
                reasons.append("unresolved_identifier")
            if any(
                f.status
                in {"ambiguous", "conflicting", "requires_review", "unverified"}
                and f.raw is not None
                for f in item.fields.values()
            ):
                reasons.append("field_association_or_ocr_uncertainty")
        elif candidate:
            reasons.append("unconsumed_table_row_or_column_mismatch")
        elif any(
            word in block.text.lower()
            for word in ("request ", "please supply", "item ", "qty:", "quantity:")
        ) and not block.text.strip().lower().startswith(
            ("rfq", "delivery requirements", "instructions:")
        ):
            reasons.append("unstructured_procurement_request")
        if reasons:
            context = (
                [records[record["header_id"]]["block"]] if record["header_id"] else []
            )
            tasks.append(
                {
                    "source": block_id,
                    "reasons": reasons,
                    "blocks": context + [block],
                    "model_eligible": True,
                }
            )
            if item:
                unresolved = [
                    (name, field)
                    for name, field in item.fields.items()
                    if field.status not in {"validated", "missing"}
                    or (
                        name in {"description", "quantity", "unit"}
                        and field.value is None
                    )
                ]
                if unresolved and all(
                    (
                        name == "quantity"
                        and field.raw is not None
                        and re.fullmatch(r"\s*\d+\s*[-–]\s*\d+\s*", field.raw)
                    )
                    or (
                        field.value is not None
                        and any(e.method == "tesseract" for e in field.evidence)
                        and all(
                            e.row_association == "verified"
                            and e.column_association != "unverified"
                            for e in field.evidence
                        )
                    )
                    for name, field in unresolved
                ):
                    tasks[-1]["model_eligible"] = False
                    tasks[-1]["reasons"].append(
                        "literal_or_ocr_ambiguity_requires_visual_human_review"
                    )
    return tasks, {
        "candidate_rows": candidates
        if any(r["columns"] for r in records.values())
        else None,
        "deterministic_rows": len(baseline.items),
        "consumed_blocks": sorted(k for k in consumed if k),
        "unresolved_blocks": [t["source"] for t in tasks],
        "coverage": "heuristic table candidates; unknown denominator for prose",
    }


def merge(baseline, proposed, counts, decisions):
    by_anchor = {anchor(item): item for item in baseline.items if anchor(item)}
    for row in proposed.items:
        source = anchor(row)
        if source and source in by_anchor:
            original = by_anchor[source]
            repaired = False
            for name, incoming in row.fields.items():
                prior = original.fields[name]
                if incoming.value is None:
                    if incoming.raw is not None:
                        counts["rejected_unsupported_proposals"] += 1
                    continue
                trusted = prior.status == "validated" and prior.value is not None
                incoming_valid = incoming.status == "validated"
                if trusted:
                    if incoming_valid and incoming.value != prior.value:
                        prior.status = "conflicting"
                        prior.issues.append(
                            "Selective model conflicts with deterministic source value; original retained."
                        )
                        prior.evidence.extend(incoming.evidence)
                        counts["conflicting_fields"] += 1
                    continue
                if incoming_valid and prior.status not in {"conflicting", "ambiguous"}:
                    original.fields[name] = incoming
                    repaired = True
                elif incoming.value != prior.value and prior.raw is not None:
                    prior.status = "conflicting"
                    prior.evidence.extend(incoming.evidence)
                    counts["conflicting_fields"] += 1
                elif prior.value is None and incoming.value is not None:
                    original.fields[name] = incoming
            if repaired:
                original.extraction_method = "hybrid"
                counts["repaired_rows"] += 1
            else:
                counts["duplicate_proposals"] += 1
            decisions.append(
                {
                    "source": source,
                    "action": "repaired" if repaired else "retained_deterministic",
                }
            )
        else:
            # Exact source identity only; equal product IDs from distinct rows remain separate.
            if source and any(
                anchor(i) == source
                and {k: f.value for k, f in i.fields.items()}
                == {k: f.value for k, f in row.fields.items()}
                for i in baseline.items
            ):
                counts["duplicate_proposals"] += 1
                continue
            baseline.items.append(row)
            if source:
                by_anchor[source] = row
            counts["added_model_rows"] += 1
            decisions.append({"source": source, "action": "added_model_row"})
    for name, value in proposed.header.items():
        if value.raw is not None:
            merge_header(baseline, name, value)


async def extract_selective(documents, mode="hybrid", provider=None, cancel_check=None):
    started = time.perf_counter()
    result = Extraction(header={n: FieldValue() for n in HEADER_FIELDS})
    runs = []
    routing = []
    decisions = []
    calls = 0
    model_ms = 0
    deterministic_ms = 0
    counts = {
        k: 0
        for k in (
            "original_deterministic_rows",
            "accepted_deterministic_rows",
            "repaired_rows",
            "added_model_rows",
            "rejected_unsupported_proposals",
            "conflicting_fields",
            "duplicate_proposals",
            "remaining_unresolved_fields",
        )
    }
    provider = provider or OllamaProvider(
        compact=settings().model_schema_profile == "compact"
    )
    for doc in documents:
        before = time.perf_counter()
        baseline = deterministic_v2(doc)
        deterministic_ms += (time.perf_counter() - before) * 1000
        counts["original_deterministic_rows"] += len(baseline.items)
        tasks, coverage = route(doc, baseline)
        if mode == "llm":
            batches = chunks(doc)
            baseline = Extraction(warnings=list(doc.warnings))
        elif mode == "hybrid":
            # Batch unresolved rows with their actual headers; deduplicate overlap before calls.
            selected = {
                b.id: b
                for task in tasks
                if task["model_eligible"]
                for b in task["blocks"]
            }
            if len(selected) > settings().max_routing_blocks:
                raise ProviderError("routing_block_limit")
            subset = doc.model_copy(update={"blocks": list(selected.values())})
            batches = chunks(subset) if selected else []
        else:
            batches = []
        routing.append(
            {
                "document_id": doc.document_id,
                "coverage": coverage,
                "tasks": [
                    {
                        "source": t["source"],
                        "reasons": t["reasons"],
                        "model_eligible": t["model_eligible"],
                    }
                    for t in tasks
                ],
                "selected_blocks": [b.id for batch in batches for b in batch],
            }
        )
        document_calls = 0
        for batch in batches:
            if cancel_check:
                cancel_check()
            if document_calls >= settings().max_model_calls:
                raise ProviderError("model_call_budget_exceeded")
            before = time.perf_counter()
            proposal, metadata = await provider.extract(batch)
            model_ms += (time.perf_counter() - before) * 1000
            calls += 1
            document_calls += 1
            runs.append(metadata)
            proposed = verify_v2(
                doc, batch, proposal, metadata.get("model", "explicit-test-provider")
            )
            counts["rejected_unsupported_proposals"] += sum(
                f.raw is not None and f.value is None
                for item in proposed.items
                for f in item.fields.values()
            )
            merge(baseline, proposed, counts, decisions)
            for name in metadata.get("header_conflicts", []):
                baseline.header[name].status = "conflicting"
                baseline.header[name].issues.append(
                    "Model proposed conflicting header readings."
                )
        counts["accepted_deterministic_rows"] += sum(
            i.extraction_method == "deterministic" for i in baseline.items
        )
        result.items.extend(baseline.items)
        result.warnings.extend(baseline.warnings)
        if len(result.items) > 2000:
            raise ProviderError("line_item_limit")
        for name, value in baseline.header.items():
            if value.raw is not None:
                merge_header(result, name, value)
    mark_duplicates(result.items)
    counts["remaining_unresolved_fields"] = sum(
        f.status != "validated"
        for i in result.items
        for name, f in i.fields.items()
        if f.raw is not None or name in {"description", "quantity", "unit"}
    )
    result.metadata = {
        "mode": mode,
        "policy": POLICY,
        "policy_version": "2.0",
        "association_version": ASSOCIATION_VERSION,
        "model_runs": runs,
        "model_call_count": calls,
        "model_escalation_count": 0,
        "routing": routing,
        "merge": counts,
        "merge_decisions": decisions,
        "deterministic_ms": deterministic_ms,
        "model_ms": model_ms,
        "ocr_ms": sum(d.ocr_ms for d in documents),
        "parser_ms": sum(d.duration_ms for d in documents),
        "extraction_ms": (time.perf_counter() - started) * 1000,
        "ocr_strategy": settings().ocr_strategy,
        "prompt_version": getattr(provider, "prompt_version", "explicit-test-fixture"),
    }
    return result
