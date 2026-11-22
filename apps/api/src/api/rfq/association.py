"""Source occurrence and structural association are separate, observable checks."""

from __future__ import annotations

import re

from .contracts import (
    Evidence,
    FieldValue,
    ParsedDocument,
    Proposal,
    Extraction,
    LineItem,
    ITEM_FIELDS,
    HEADER_FIELDS,
)
from .extraction import (
    ALIASES,
    HEADER_ALIASES,
    alias,
    cells_for,
    deterministic,
    evidence,
)
from .validation import normalize, stable_item

ASSOCIATION_VERSION = "source-association/2.0"
UNTRUSTED = re.compile(
    r"(?:UNTRUSTED|SYSTEM:|ignore.{0,40}(?:schema|instructions)|reveal.{0,30}(?:secret|credential)|not (?:a |an )?(?:order|requested item)|fake tool)",
    re.I,
)


def layout(doc: ParsedDocument):
    columns = {}
    context = None
    records = {}
    headers = {}
    for block in doc.blocks:
        new_context = (block.location.page, block.location.sheet)
        if new_context != context:
            columns = {}
            context = new_context
        cells = cells_for(block)
        candidate = {
            i: ALIASES[alias(value)]
            for i, value in enumerate(cells)
            if alias(value) in ALIASES
        }
        is_header = (
            "description" in candidate.values() and "quantity" in candidate.values()
        )
        if is_header:
            columns = candidate
            headers[context] = block.id
        records[block.id] = {
            "block": block,
            "cells": cells,
            "columns": dict(columns),
            "header": is_header,
            "header_id": headers.get(context),
            "eligible": not bool(UNTRUSTED.search(block.text)),
        }
    return records


def enrich(
    e: Evidence, record, field_name: str, raw: str, anchor: str | None, *, header=False
):
    block = record["block"]
    e.source_occurrence = e.verified
    e.source_eligible = record["eligible"]
    same_row = anchor == block.id and record["eligible"] and not record["header"]
    e.row_association = "verified" if same_row else "unverified"
    e.association_reason = (
        "same source row/block"
        if same_row
        else "different row, header row or ineligible instruction/example"
    )
    if header:
        key = block.text.strip().split(":", 1)[0]
        known = HEADER_ALIASES.get(alias(key))
        e.row_association = (
            "verified" if known == field_name and record["eligible"] else "unknown"
        )
        e.association_reason = (
            "explicit matching header label"
            if known == field_name
            else "header-label association unresolved"
        )
    matching = [i for i, name in record["columns"].items() if name == field_name]
    if matching and not header:
        index = matching[0]
        expected = record["cells"][index] if index < len(record["cells"]) else ""
        exact = raw.strip() == expected.strip()
        e.column_association = "verified" if exact else "unverified"
        if block.cell_locations and index < len(block.cell_locations):
            e.location = block.cell_locations[index].model_copy(deep=True)
        meta = block.metadata.get("cells", [])
        if index < len(meta):
            e.raw_ocr = meta[index].get("raw")
            e.alternatives = meta[index].get("alternatives", [])
            e.ocr_confidence = meta[index].get("confidence")
    elif not header:
        # Row association does not justify confusing a price with a quantity or a SKU with MPN.
        labels = {
            "requested_unit_price": r"(?:unit price|price per unit)\s*[:=]?\s*"
            + re.escape(raw),
            "customer_part_number": r"customer (?:part number|pn)\s*[:=]?\s*"
            + re.escape(raw),
            "quantity": r"(?:request|quantity|qty)\s*[:=]?\s*"
            + re.escape(raw)
            + r"(?:\s|$)",
            "mpn": r"(?:\bmpn|manufacturer part number)\s*[:=]?\s*" + re.escape(raw),
            "manufacturer": r"manufacturer\s*[:=]?\s*" + re.escape(raw),
            "requested_sku": r"\bsku\s*[:=]?\s*" + re.escape(raw),
        }
        if field_name in labels and not re.search(labels[field_name], block.text, re.I):
            e.row_association = "unknown"
            e.association_reason = "field label/type association unresolved"
    return e


def require_association(field: FieldValue):
    if field.value is None:
        return
    if any(
        not e.source_eligible
        or e.row_association != "verified"
        or e.column_association == "unverified"
        for e in field.evidence
    ):
        if field.status == "validated":
            field.status = "requires_review"
        field.issues.append(
            "Source occurrence is not sufficient: resolve field-to-row/column association."
        )
    if any(e.alternatives for e in field.evidence):
        field.status = "ambiguous"
        field.issues.append(
            "OCR passes disagree; inspect the original identifier before confirming."
        )
    if any(
        e.ocr_confidence is not None and e.ocr_confidence < 45 for e in field.evidence
    ):
        if field.status == "validated":
            field.status = "requires_review"
        field.issues.append("Low raw OCR word confidence (uncalibrated heuristic).")


def deterministic_v2(doc: ParsedDocument) -> Extraction:
    result = deterministic(doc)
    records = layout(doc)
    kept = []
    for item in result.items:
        anchor = next((e.block_id for e in item.fields["description"].evidence), None)
        if anchor and (
            not records[anchor]["eligible"]
            or records[anchor]["block"]
            .text.strip()
            .lower()
            .startswith(("delivery |", "instructions |", "notes |"))
        ):
            continue
        for name, field in item.fields.items():
            for e in field.evidence:
                enrich(
                    e, records[e.block_id], name, field.raw or field.value or "", anchor
                )
            require_association(field)
        kept.append(item)
    result.items = kept
    for name, field in result.header.items():
        for e in field.evidence:
            enrich(
                e, records[e.block_id], name, field.raw or "", e.block_id, header=True
            )
        require_association(field)
    return result


def verify_v2(
    doc: ParsedDocument, blocks, proposal: Proposal, identity: str
) -> Extraction:
    records = layout(doc)
    index = {b.id: b for b in blocks}
    result = Extraction()

    def value(name, proposed, anchor, header=False):
        if proposed is None or proposed.value is None:
            return FieldValue()
        block = index.get(proposed.block_id)
        excerpt = proposed.excerpt or ""
        if (
            not block
            or excerpt not in block.text
            or not excerpt.strip()
            or proposed.value not in excerpt
        ):
            return FieldValue(
                raw=proposed.value,
                status="unverified",
                issues=["Proposed value/excerpt/source block cannot be verified."],
            )
        e = evidence(doc, block, excerpt, "llm", identity)
        enrich(e, records[block.id], name, proposed.value, anchor, header=header)
        field = normalize(name, proposed.value, [e])
        require_association(field)
        return field

    for name in HEADER_FIELDS:
        result.header[name] = value(name, getattr(proposal.header, name), None, True)
    anchors = {}
    for proposed in proposal.items:
        anchor = next(
            (
                getattr(proposed, name).block_id
                for name in ("description", "mpn", "requested_sku", "line_number")
                if getattr(proposed, name) and getattr(proposed, name).value
            ),
            None,
        )
        if anchor in records and not records[anchor]["eligible"]:
            result.warnings.append(
                "Rejected model item anchored in instructions or a quoted example."
            )
            continue
        fields = {
            name: value(name, getattr(proposed, name), anchor) for name in ITEM_FIELDS
        }
        ordinal = anchors.get(anchor, 0)
        anchors[anchor] = ordinal + 1
        row = LineItem(
            id=stable_item(doc.document_id, anchor or "unsupported", ordinal),
            fields=fields,
            extraction_method="llm",
        )
        if ordinal:
            row.warnings.append(
                "Multiple proposals use one source block; source-row identity requires review."
            )
        result.items.append(row)
    return result
