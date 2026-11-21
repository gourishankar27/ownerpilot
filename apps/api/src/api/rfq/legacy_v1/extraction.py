from __future__ import annotations

import re
import time

from openpyxl.utils import get_column_letter

from .config import settings
from .contracts import (
    Block,
    Evidence,
    Extraction,
    FieldValue,
    HEADER_FIELDS,
    ITEM_FIELDS,
    LineItem,
    ParsedDocument,
    Proposal,
)
from .provider import OllamaProvider, PROMPT_VERSION, ProviderError
from .validation import mark_duplicates, normalize, stable_item

ALIASES = {
    "line": "line_number",
    "line no": "line_number",
    "line number": "line_number",
    "manufacturer": "manufacturer",
    "brand": "manufacturer",
    "make": "manufacturer",
    "mpn": "mpn",
    "manufacturer part number": "mpn",
    "mfr part number": "mpn",
    "part number": "mpn",
    "customer part number": "customer_part_number",
    "customer pn": "customer_part_number",
    "sku": "requested_sku",
    "requested sku": "requested_sku",
    "description": "description",
    "product description": "description",
    "product": "description",
    "item description": "description",
    "qty": "quantity",
    "quantity": "quantity",
    "requested quantity": "quantity",
    "uom": "unit",
    "unit": "unit",
    "unit of measure": "unit",
    "delivery date": "required_delivery_date",
    "required delivery date": "required_delivery_date",
    "unit price": "requested_unit_price",
    "requested unit price": "requested_unit_price",
    "currency": "currency",
    "alternatives allowed": "alternatives_allowed",
    "specifications": "specifications",
    "special requirements": "special_requirements",
}
HEADER_ALIASES = {name.replace("_", " "): name for name in HEADER_FIELDS} | {
    "rfq": "external_rfq_number",
    "rfq number": "external_rfq_number",
    "customer": "customer_name",
    "quote deadline": "submission_deadline",
    "ship to": "shipping_address",
    "bill to": "billing_address",
    "email": "contact_email",
}


def alias(value: str) -> str:
    return re.sub(r"[\s_#.-]+", " ", value.strip().lower()).strip()


def evidence(
    doc: ParsedDocument,
    block: Block,
    excerpt: str,
    method: str,
    identity: str,
    column: int | None = None,
) -> Evidence:
    location = block.location.model_copy(deep=True)
    if column is not None:
        location.column = get_column_letter(column + 1)
    return Evidence(
        document_id=doc.document_id,
        fingerprint=doc.fingerprint,
        block_id=block.id,
        location=location,
        excerpt=excerpt,
        method=method,
        identity=identity,
        verified=bool(excerpt.strip()) and excerpt in block.text,
    )


def merge_header(result: Extraction, name: str, field: FieldValue) -> None:
    previous = result.header.get(name)
    if previous and previous.value is not None:
        if previous.value != field.value:
            previous.status = "conflicting"
            previous.issues.append("Conflicting source values; reviewer must resolve.")
        previous.evidence.extend(field.evidence)
    else:
        result.header[name] = field


def cells_for(block: Block) -> list[str]:
    if block.cells is not None:
        return block.cells
    if "|" in block.text:
        return [c.strip() for c in block.text.strip().strip("|").split("|")]
    return [c.strip() for c in re.split(r"\s{2,}", block.text.strip())]


def deterministic(doc: ParsedDocument) -> Extraction:
    result = Extraction(warnings=list(doc.warnings))
    columns: dict[int, str] = {}
    ambiguous_columns: set[int] = set()
    context = None
    for block in doc.blocks:
        new_context = (block.location.sheet, block.location.page)
        if new_context != context:
            columns = {}
            ambiguous_columns = set()
            context = new_context
        cells = cells_for(block)
        proposed = {
            i: ALIASES[alias(c)] for i, c in enumerate(cells) if alias(c) in ALIASES
        }
        if "description" in proposed.values() and "quantity" in proposed.values():
            columns = proposed
            ambiguous_columns = {
                i for i, c in enumerate(cells) if alias(c) == "part number"
            }
            continue
        # Exact key-value headers only; no guessing customer, SKU or dates.
        if ":" in block.text:
            key, raw = block.text.strip().split(":", 1)
            name = HEADER_ALIASES.get(alias(key))
            if name and raw.strip():
                field = normalize(
                    name,
                    raw.strip(),
                    [evidence(doc, block, raw.strip(), "deterministic", doc.parser)],
                )
                merge_header(result, name, field)
                continue
        if columns and len(cells) >= max(columns) + 1:
            fields = {name: FieldValue() for name in ITEM_FIELDS}
            for index, name in columns.items():
                raw = cells[index].strip() or None
                fields[name] = normalize(
                    name,
                    raw,
                    [evidence(doc, block, raw, "deterministic", doc.parser, index)]
                    if raw
                    else [],
                )
                if index in ambiguous_columns and raw:
                    fields[name].status = "ambiguous"
                    fields[name].issues.append(
                        "Unqualified part number column: confirm whether this is an MPN, customer part number or SKU."
                    )
            if fields["description"].value:
                result.items.append(
                    LineItem(
                        id=stable_item(doc.document_id, block.id),
                        fields=fields,
                        extraction_method="deterministic",
                    )
                )
    if not result.items:
        result.warnings.append(
            "No supported procurement table detected; model extraction or manual entry is needed."
        )
    return result


def verify_proposal(
    doc: ParsedDocument, blocks: list[Block], proposal: Proposal, identity: str
) -> Extraction:
    result = Extraction()
    index = {b.id: b for b in blocks}

    def field_value(name: str, proposed) -> FieldValue:
        if proposed is None or proposed.value is None:
            return FieldValue()
        block = index.get(proposed.block_id)
        excerpt = proposed.excerpt or ""
        supported = (
            block is not None
            and bool(excerpt.strip())
            and excerpt in block.text
            and proposed.value in excerpt
        )
        if not supported:
            # Never publish an unsupported generated value as usable data.
            return FieldValue(
                raw=proposed.value,
                status="unverified",
                issues=[
                    "Model value lacks verifiable source evidence; enter a sourced correction."
                ],
            )
        return normalize(
            name, proposed.value, [evidence(doc, block, excerpt, "llm", identity)]
        )

    for name in HEADER_FIELDS:
        result.header[name] = field_value(name, getattr(proposal.header, name))
    for ordinal, proposed in enumerate(proposal.items):
        fields = {
            name: field_value(name, getattr(proposed, name)) for name in ITEM_FIELDS
        }
        source = next(
            (f.evidence[0].block_id for f in fields.values() if f.evidence),
            f"unsupported:{ordinal}",
        )
        # Stable by source block; ordinal only needed for multiple items in a block.
        count = sum(
            1
            for item in result.items
            if any(
                e.block_id == source for f in item.fields.values() for e in f.evidence
            )
        )
        result.items.append(
            LineItem(
                id=stable_item(doc.document_id, source, count),
                fields=fields,
                extraction_method="llm",
            )
        )
    return result


def chunks(doc: ParsedDocument) -> list[list[Block]]:
    cfg = settings()
    from .provider import PROMPT

    # Allow for JSON block identifiers and escaping as well as message tokens.
    byte_budget = (
        cfg.model_context - cfg.model_output_tokens - len(PROMPT.encode("utf-8")) - 512
    )
    if byte_budget < 256:
        raise ProviderError("model_context_budget_exceeded")
    groups: list[list[Block]] = []
    current: list[Block] = []
    size = 0
    for block in doc.blocks:
        block_size = (
            len(block.text.encode("utf-8")) + len(block.id.encode("utf-8")) + 80
        )
        if len(block.text) > cfg.model_input_chars or block_size > byte_budget:
            raise ProviderError("single_block_input_limit")
        if current and size + block_size > min(cfg.model_input_chars, byte_budget):
            groups.append(current)
            current, size = [], 0
        current.append(block)
        size += block_size
    if current:
        groups.append(current)
    if len(groups) > cfg.max_chunks:
        raise ProviderError("chunk_limit")
    return groups


async def extract(
    documents: list[ParsedDocument], mode: str = "hybrid", provider=None
) -> Extraction:
    start = time.perf_counter()
    result = Extraction(header={name: FieldValue() for name in HEADER_FIELDS})
    model_runs = []
    model_ms = 0.0
    deterministic_ms = 0.0
    for doc in documents:
        before = time.perf_counter()
        baseline = deterministic(doc)
        deterministic_ms += (time.perf_counter() - before) * 1000
        use_baseline = mode == "deterministic" or (mode == "hybrid" and baseline.items)
        if use_baseline:
            extracted = baseline
        else:
            extracted = Extraction(warnings=list(doc.warnings))
            for batch in chunks(doc):
                before = time.perf_counter()
                proposal, metadata = await (provider or OllamaProvider()).extract(batch)
                model_ms += (time.perf_counter() - before) * 1000
                model_runs.append(metadata)
                part = verify_proposal(
                    doc, batch, proposal, metadata.get("model", "test-provider")
                )
                extracted.items.extend(part.items)
                for name, value in part.header.items():
                    if value.value is not None or value.raw is not None:
                        merge_header(extracted, name, value)
        result.items.extend(extracted.items)
        if len(result.items) > 2000:
            raise ProviderError("line_item_limit")
        result.warnings.extend(extracted.warnings)
        for name, value in extracted.header.items():
            if value.value is not None or value.raw is not None:
                merge_header(result, name, value)
    mark_duplicates(result.items)
    result.metadata = {
        "mode": mode,
        "prompt_version": PROMPT_VERSION,
        "model_runs": model_runs,
        "model_ms": model_ms,
        "deterministic_ms": deterministic_ms,
        "ocr_ms": sum(d.ocr_ms for d in documents),
        "parser_ms": sum(d.duration_ms for d in documents),
        "extraction_ms": (time.perf_counter() - start) * 1000,
    }
    return result
