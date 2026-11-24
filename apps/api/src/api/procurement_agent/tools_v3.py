"""Versioned bounded local source batches. The released registry remains unchanged."""

import json
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from . import tools as legacy
from .evidence import EvidenceError
from .finance import Closed

VERSION = "procurement-tools/3"
MAX_BATCH = 4
MAX_RESULT_BYTES = 32768
KINDS = {
    "reviewed_product_selection": ("get_reviewed_product_selection", "selection"),
    "supplier_offers": ("get_supplier_offers", "offers"),
}


class Batch(Closed):
    line_ids: list[UUID] = Field(min_length=1, max_length=MAX_BATCH)
    include: list[Literal["reviewed_product_selection", "supplier_offers"]] = Field(
        default_factory=lambda: list(KINDS), min_length=1, max_length=2
    )

    @model_validator(mode="after")
    def distinct(self):
        if len(set(self.line_ids)) != len(self.line_ids) or len(
            set(self.include)
        ) != len(self.include):
            raise ValueError("Duplicate batch member")
        return self


REGISTRY = {
    **legacy.REGISTRY,
    "get_line_research_batch": (
        Batch,
        "Inspect 1 to 4 approved line IDs in ONE read-only request. Returns reviewed product selections AND supplier offers, including no-match, missing prices and unknowns. Prefer this tool for required source coverage; use include to request only missing source types. Never omit an approved line. One batch is one tool decision, not one decision per line.",
    ),
}


def definitions():
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": schema.model_json_schema(),
            },
        }
        for name, (schema, description) in REGISTRY.items()
    ]


def validate_batch(args, run):
    parsed = Batch.model_validate(args)
    authorized = {line["line_id"] for line in run["snapshot"]["lines"]}
    ids = [str(value) for value in parsed.line_ids]
    if set(ids) - authorized:
        raise EvidenceError("batch_line_unauthorized")
    if len(ids) > run["metadata"].get("batch_size", MAX_BATCH):
        raise EvidenceError("batch_size_limit")
    return parsed


def execute(name, args, run):
    if name not in REGISTRY:
        raise EvidenceError("tool_unauthorized")
    if name != "get_line_research_batch":
        result = legacy.execute(name, args, run)
    else:
        parsed = validate_batch(args, run)
        lines = []
        for line_id in parsed.line_ids:
            entry = {"line_id": str(line_id), "source_status": "inspected"}
            for kind in parsed.include:
                tool, key = KINDS[kind]
                entry[key] = legacy.execute(tool, {"line_id": str(line_id)}, run)
            lines.append(entry)
        result = {
            "lines": lines,
            "complete": True,
            "requested_line_ids": [str(value) for value in parsed.line_ids],
        }
    if (
        len(json.dumps(result, ensure_ascii=False, default=str).encode())
        > MAX_RESULT_BYTES
    ):
        raise EvidenceError("tool_result_size_limit")
    return result


def canonical_arguments(name, args):
    """Equivalent reordered/case-varied UUID batches share the repeat budget."""
    result = REGISTRY[name][0].model_validate(args).model_dump(mode="json")
    if name == "get_line_research_batch":
        result = {
            "line_ids": sorted(result["line_ids"]),
            "include": sorted(result["include"]),
        }
    return result
