"""Batch adapter around the unchanged citation-only semantic resolver.

Temporary child views are validation inputs only. Every emitted fact and pointer
belongs to the original immutable parent receipt; no child receipt is persisted.
"""

from copy import deepcopy

from .evidence import (
    EvidenceResolver as PreviousResolver,
    EvidenceError,
    exact,
    pointer_value,
)
from .tools_v3 import VERSION, KINDS, validate_batch

VERIFIER = "research-verifier/3"


class EvidenceResolver(PreviousResolver):
    def __init__(self, run, receipts):
        self.tool_failures = []
        super().__init__(run, receipts)

    def resolve(self, summary):
        result = super().resolve(summary)
        result["verification"] = VERIFIER
        result["tool_failures"] = self.tool_failures
        return result

    def _receipt(self, receipt):
        # Unsuccessful attempts remain visible, never supply source coverage or
        # citeable fields. A later successful read can close the missing work.
        if str(receipt.get("run_id")) != str(self.run["id"]) or (
            receipt.get("workspace_id") is not None
            and str(receipt["workspace_id"]) != str(self.run["workspace_id"])
        ):
            raise EvidenceError("receipt_ownership")
        if receipt["schema_version"] != self.run["metadata"]["tool_schema"]:
            raise EvidenceError("receipt_schema_mismatch")
        if receipt["status"] != "succeeded":
            self.tool_failures.append(
                {
                    "receipt_id": str(receipt["id"]),
                    "code": receipt.get("error") or "unsuccessful_receipt",
                }
            )
            return
        if receipt["tool"] != "get_line_research_batch":
            return super()._receipt(receipt)
        if str(receipt.get("run_id")) != str(self.run["id"]) or (
            receipt.get("workspace_id") is not None
            and str(receipt["workspace_id"]) != str(self.run["workspace_id"])
        ):
            raise EvidenceError("receipt_ownership")
        if receipt["status"] != "succeeded":
            raise EvidenceError("unsuccessful_receipt")
        if (
            receipt["schema_version"] != VERSION
            or self.run["metadata"]["tool_schema"] != VERSION
        ):
            raise EvidenceError("receipt_schema_mismatch")
        try:
            args = validate_batch(receipt["arguments"], self.run)
        except ValueError:
            raise EvidenceError("batch_schema_or_scope_rejected") from None
        expected_ids = [str(value) for value in args.line_ids]
        result = receipt["result"]
        if (
            type(result) is not dict
            or set(result) != {"lines", "complete", "requested_line_ids"}
            or result["complete"] is not True
            or result["requested_line_ids"] != expected_ids
            or type(result["lines"]) is not list
            or len(result["lines"]) != len(expected_ids)
        ):
            raise EvidenceError("incomplete_batch_receipt")
        previous_sources = dict(self.sources)
        previous_inspected = deepcopy(self.inspected)
        try:
            for index, (line_id, entry) in enumerate(
                zip(expected_ids, result["lines"])
            ):
                wanted_keys = {"line_id", "source_status"} | {
                    KINDS[kind][1] for kind in args.include
                }
                if (
                    type(entry) is not dict
                    or set(entry) != wanted_keys
                    or entry["line_id"] != line_id
                    or entry["source_status"] != "inspected"
                ):
                    raise EvidenceError("incomplete_batch_receipt")
                for kind in args.include:
                    tool, key = KINDS[kind]
                    before = set(self.sources)
                    child = {
                        **receipt,
                        "tool": tool,
                        "arguments": {"line_id": line_id},
                        "result": entry[key],
                    }
                    super()._receipt(child)
                    for source_key in set(self.sources) - before:
                        source = self.sources[source_key]
                        prefix = f"/data/lines/{index}/{key}"
                        fields = {
                            prefix + path[5:]: value
                            for path, value in source.fields.items()
                        }
                        required = {prefix + path[5:] for path in source.required}
                        for path, (_, value) in fields.items():
                            if not exact(pointer_value({"data": result}, path), value):
                                raise EvidenceError("incorrect_claim_association")
                        source.receipt = receipt
                        source.fields = fields
                        source.required = required
        except (ValueError, KeyError, TypeError, IndexError):
            self.sources = previous_sources
            self.inspected = previous_inspected
            raise EvidenceError("batch_binding_rejected") from None
