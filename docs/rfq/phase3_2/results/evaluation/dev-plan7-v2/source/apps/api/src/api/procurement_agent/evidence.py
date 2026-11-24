"""One backend authority for citation ownership, semantics, associations and coverage."""

import json
import re
from dataclasses import dataclass, field
from datetime import date

from .contracts import CitationGroup
from .finance import QuotePolicy, number
from .service import digest, commercial_review_state, quote_calculation

PROTOCOL = "research-citation-only/2"
VERIFIER = "research-verifier/2"


def reference_document(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate reference member")
            result[key] = value
        return result

    def constant(_):
        raise ValueError("Non-JSON constant")

    return (
        json.loads(raw, object_pairs_hook=unique, parse_constant=constant)
        if isinstance(raw, str)
        else raw
    )


def sanitize_request(summary):
    """Persist only validated references or opaque rejection markers, never model values/prose."""
    try:
        data = reference_document(summary)
        if (
            type(data) is not dict
            or set(data) != {"claims"}
            or type(data["claims"]) is not list
            or not 1 <= len(data["claims"]) <= 32
        ):
            return {"invalid_document": True}
    except (ValueError, TypeError):
        return {"invalid_document": True}
    groups = []
    for raw in data["claims"]:
        try:
            groups.append(CitationGroup.model_validate(raw).model_dump(mode="json"))
        except ValueError:
            groups.append({"rejected_reference": True})
    return {"claims": groups}


class EvidenceError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def pointer_value(document, pointer):
    """RFC 6901 JSON pointer, including strict array-index and escape semantics."""
    if (
        not isinstance(pointer, str)
        or len(pointer) > 300
        or (pointer and not pointer.startswith("/"))
    ):
        raise EvidenceError("invalid_citation_pointer")
    value = document
    if pointer == "":
        return value
    for raw in pointer[1:].split("/"):
        if re.search(r"~(?![01])", raw):
            raise EvidenceError("invalid_pointer_escape")
        token = re.sub(r"~[01]", lambda match: "/" if match[0] == "~1" else "~", raw)
        if isinstance(value, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", token):
                raise EvidenceError("invalid_list_index")
            index = int(token)
            if index >= len(value):
                raise EvidenceError("missing_pointer_value")
            value = value[index]
        elif isinstance(value, dict):
            if token not in value:
                raise EvidenceError("missing_pointer_value")
            value = value[token]
        else:
            raise EvidenceError("scalar_pointer_traversal")
    return value


def exact(left, right):
    return type(left) is type(right) and digest(left) == digest(right)


def check_type(kind, value):
    if value is None:
        return
    if kind in {"price", "quantity", "minimum_units", "stock_units"}:
        if type(value) is not str:
            raise EvidenceError("commercial_field_type")
        try:
            number(value, positive=kind == "quantity")
        except ValueError:
            raise EvidenceError("commercial_field_type") from None
    elif kind in {"revision", "pack_size", "lead_time_days"}:
        if type(value) is not int or value < 0:
            raise EvidenceError("commercial_field_type")
    elif kind == "boolean":
        if type(value) is not bool:
            raise EvidenceError("commercial_field_type")
    elif type(value) is not str:
        raise EvidenceError("commercial_field_type")
    if kind == "currency" and not re.fullmatch("[A-Z]{3}", value):
        raise EvidenceError("commercial_field_type")
    if kind == "availability" and value not in {"available", "unavailable", "unknown"}:
        raise EvidenceError("commercial_field_type")
    if kind == "date":
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise EvidenceError("commercial_field_type")
        try:
            date.fromisoformat(value)
        except ValueError:
            raise EvidenceError("commercial_field_type") from None


@dataclass
class Source:
    key: str
    receipt: dict
    binding: dict
    fields: dict = field(default_factory=dict)
    required: set = field(default_factory=set)


class EvidenceResolver:
    def __init__(self, run, receipts):
        self.run = run
        self.snapshot = run["snapshot"]
        self.sources = {}
        self.receipt_errors = []
        self.inspected = {}
        self.approved_read = False
        if run.get("metadata", {}).get("source_fingerprint") != digest(self.snapshot):
            raise EvidenceError("source_snapshot_mismatch")
        for receipt in sorted(receipts, key=lambda row: row["ordinal"]):
            try:
                self._receipt(receipt)
            except EvidenceError as exc:
                self.receipt_errors.append(
                    {"receipt_id": str(receipt["id"]), "code": exc.code}
                )

    def _source(self, receipt, line=None, offer=None, data_class="approved_rfq"):
        selection = (line or {}).get("selection", {}).get("resolution") or {}
        product = selection.get("data", {})
        binding = {
            "run_id": str(self.run["id"]),
            "workspace_id": str(self.run["workspace_id"]),
            "rfq_id": self.snapshot["rfq_id"],
            "rfq_revision": self.snapshot["revision"],
            "line_id": line["line_id"] if line else None,
            "selection_id": selection.get("id"),
            "product_id": product.get("product_id"),
            "catalog_version": product.get("version_id"),
            "offer_id": offer["id"] if offer else None,
            "source_fingerprint": offer["data"]["source_fingerprint"]
            if offer
            else product.get("content_hash")
            or digest(
                {
                    "rfq": self.snapshot["rfq_id"],
                    "revision": self.snapshot["revision"],
                    "source_run": self.snapshot["source_run"],
                }
            ),
            "data_class": data_class,
        }
        key = "s" + digest({"receipt": str(receipt["id"]), "binding": binding})[:12]
        source = Source(key, receipt, binding)
        self.sources[key] = source
        return source

    def _field(self, source, path, kind, expected, required=False):
        actual = pointer_value({"data": source.receipt["result"]}, path)
        if type(actual) in {dict, list}:
            raise EvidenceError("scalar_reference_required")
        if not exact(actual, expected):
            raise EvidenceError("incorrect_claim_association")
        check_type(kind, actual)
        source.fields[path] = (kind, actual)
        if required:
            source.required.add(path)

    def _receipt(self, receipt):
        if str(receipt.get("run_id")) != str(self.run["id"]):
            raise EvidenceError("receipt_ownership")
        if receipt.get("workspace_id") is not None and str(
            receipt["workspace_id"]
        ) != str(self.run["workspace_id"]):
            raise EvidenceError("receipt_ownership")
        if receipt["status"] != "succeeded":
            raise EvidenceError("unsuccessful_receipt")
        if receipt["schema_version"] != self.run["metadata"]["tool_schema"]:
            raise EvidenceError("receipt_schema_mismatch")
        from .tools import REGISTRY

        name = receipt["tool"]
        if name not in REGISTRY:
            raise EvidenceError("tool_unauthorized")
        try:
            args = REGISTRY[name][0].model_validate(receipt["arguments"])
        except ValueError:
            raise EvidenceError("tool_schema_rejected") from None
        data = receipt["result"]
        if type(data) is not dict:
            raise EvidenceError("missing_tool_response")
        lines = {line["line_id"]: line for line in self.snapshot["lines"]}
        line = lines.get(str(getattr(args, "line_id", "")))
        if hasattr(args, "line_id") and line is None:
            raise EvidenceError("incorrect_claim_association")
        checkpoint = set(self.sources)
        try:
            if name == "get_approved_rfq":
                if (
                    data.get("rfq_id") != self.snapshot["rfq_id"]
                    or data.get("revision") != self.snapshot["revision"]
                ):
                    raise EvidenceError("incorrect_claim_association")
                source = self._source(receipt)
                self._field(source, "/data/rfq_id", "identity", self.snapshot["rfq_id"])
                self._field(
                    source, "/data/revision", "revision", self.snapshot["revision"]
                )
                if len(data.get("lines", [])) != len(lines):
                    raise EvidenceError("incorrect_claim_association")
                seen = set()
                for index, raw in enumerate(data["lines"]):
                    item = lines.get(raw.get("line_id"))
                    if item is None or item["line_id"] in seen:
                        raise EvidenceError("incorrect_claim_association")
                    seen.add(item["line_id"])
                    entry = self._source(receipt, item)
                    for key, kind in [
                        ("line_id", "identity"),
                        ("quantity", "quantity"),
                        ("unit", "unit"),
                    ]:
                        self._field(
                            entry, f"/data/lines/{index}/{key}", kind, item[key]
                        )
                self.approved_read = True
            elif name == "get_reviewed_product_selection":
                expected = {
                    key: value
                    for key, value in line["selection"].items()
                    if key not in {"candidates", "reviews"}
                }
                if not exact(data, expected):
                    raise EvidenceError("incorrect_claim_association")
                source = self._source(
                    receipt, line, data_class="human_reviewed_selection"
                )
                self._field(
                    source,
                    "/data/state",
                    "selection_state",
                    line["selection"]["state"],
                    True,
                )
                self._field(source, "/data/line_id", "identity", line["line_id"])
                resolution = line["selection"].get("resolution")
                if resolution:
                    self._field(
                        source, "/data/resolution/id", "identity", resolution["id"]
                    )
                    for key in ["product_id", "version_id"]:
                        if key in resolution["data"]:
                            self._field(
                                source,
                                "/data/resolution/data/" + key,
                                "identity",
                                resolution["data"][key],
                            )
                self.inspected.setdefault(line["line_id"], set()).add(name)
            elif name == "get_supplier_offers":
                if (
                    data.get("line_id") != line["line_id"]
                    or data.get("selection_state") != line["selection"]["state"]
                ):
                    raise EvidenceError("incorrect_claim_association")
                expected = {
                    offer["id"]: offer for offer in line["offers"]["attestations"]
                }
                raw_offers = data.get("attestations")
                if (
                    type(raw_offers) is not list
                    or len(raw_offers) != len(expected)
                    or {offer.get("id") for offer in raw_offers} != set(expected)
                ):
                    raise EvidenceError("incorrect_claim_association")
                if not exact(data.get("imported"), line["offers"]["imported"]):
                    raise EvidenceError("incorrect_claim_association")
                source = self._source(
                    receipt, line, data_class="local_supplier_research"
                )
                self._field(
                    source,
                    "/data/selection_state",
                    "selection_state",
                    line["selection"]["state"],
                )
                for index, raw in enumerate(raw_offers):
                    offer = expected[raw["id"]]
                    resolution = line["selection"]["resolution"]["data"]
                    if (
                        str(offer["resolution_id"])
                        != line["selection"]["resolution"]["id"]
                        or offer["data"]["product_id"] != resolution["product_id"]
                        or offer["data"]["version_id"] != resolution["version_id"]
                        or offer["data"]["source_fingerprint"]
                        != resolution["content_hash"]
                    ):
                        raise EvidenceError("incorrect_claim_association")
                    for key, wanted in {
                        "product_id": resolution["product_id"],
                        "version_id": resolution["version_id"],
                        "resolution_id": line["selection"]["resolution"]["id"],
                        "source_fingerprint": resolution["content_hash"],
                        "data_class": "user_attested",
                    }.items():
                        if not exact(raw.get(key), wanted):
                            raise EvidenceError("incorrect_claim_association")
                    source = self._source(receipt, line, offer, "user_attested")
                    prefix = f"/data/attestations/{index}/"
                    commercial = offer["data"]["commercial"]
                    for key, kind in [
                        ("price", "price"),
                        ("currency", "currency"),
                        ("availability", "availability"),
                        ("supplier", "supplier"),
                        ("pack_size", "pack_size"),
                        ("minimum_units", "minimum_units"),
                        ("price_basis", "price_basis"),
                        ("lead_time_days", "lead_time_days"),
                        ("stock_units", "stock_units"),
                        ("observed_on", "date"),
                        ("valid_until", "date"),
                    ]:
                        if key in raw or key in {"price", "currency", "availability"}:
                            self._field(
                                source,
                                prefix + key,
                                kind,
                                commercial.get(key),
                                key in {"price", "currency", "availability"},
                            )
                    self._field(
                        source,
                        prefix + "freshness",
                        "freshness",
                        offer["freshness"],
                        True,
                    )
                    review_state = commercial_review_state(
                        offer, line["offers"]["attestations"]
                    )
                    if review_state != "active_attestation":
                        self._field(
                            source,
                            prefix + "commercial_review_state",
                            "review_state",
                            review_state,
                            True,
                        )
                self.inspected.setdefault(line["line_id"], set()).add(name)
            elif (
                name == "get_product_details"
                and line["selection"]["state"] == "resolved"
            ):
                expected = line["selection"]["resolution"]["data"]
                if not exact(data.get("product"), expected):
                    raise EvidenceError("incorrect_claim_association")
                source = self._source(receipt, line, data_class="reviewed_catalog")
                for key in ["product_id", "version_id"]:
                    self._field(
                        source, "/data/product/" + key, "identity", expected[key]
                    )
                for key in ["manufacturer", "mpn", "name"]:
                    self._field(
                        source,
                        "/data/product/product/" + key,
                        "product_identity",
                        expected["product"][key],
                    )
            # Other allowlisted tools remain observable evidence. Their arbitrary text is never
            # promoted into an authoritative commercial scalar by guessing a semantic type.
        except (EvidenceError, KeyError, TypeError, ValueError) as exc:
            for key in set(self.sources) - checkpoint:
                self.sources.pop(key)
            if isinstance(exc, EvidenceError):
                raise
            raise EvidenceError("receipt_binding_rejected") from None

    def inventory(self):
        result = []
        seen = set()
        for source in self.sources.values():
            if not source.required:
                continue
            pointers = []
            for pointer in sorted(source.required):
                key = self.semantic_key(source, pointer)
                if key not in seen:
                    seen.add(key)
                    pointers.append(pointer)
            if pointers:
                result.append(
                    {
                        "source_key": source.key,
                        "receipt_id": str(source.receipt["id"]),
                        "line_id": source.binding["line_id"],
                        "offer_id": source.binding["offer_id"],
                        "pointers": pointers,
                        "required": True,
                    }
                )
        return result

    def semantic_key(self, source, pointer):
        kind = source.fields[pointer][0]
        role = (
            pointer.rsplit("/", 1)[-1]
            if kind in {"identity", "date", "product_identity"}
            else kind
        )
        return (source.binding["line_id"], source.binding["offer_id"], kind, role)

    def resolve(self, summary):
        errors = list(self.receipt_errors)
        groups = []
        facts = []
        seen = set()
        dedup = {}
        duplicates = 0
        try:
            payload = reference_document(summary)
            if (
                type(payload) is not dict
                or set(payload) != {"claims"}
                or type(payload["claims"]) is not list
                or not 1 <= len(payload["claims"]) <= 32
            ):
                raise ValueError
        except (ValueError, TypeError):
            payload = {"claims": []}
            errors.append({"code": "claim_schema_rejected"})
        for index, raw in enumerate(payload["claims"]):
            try:
                group = CitationGroup.model_validate(raw)
            except ValueError:
                errors.append({"group": index, "code": "claim_schema_rejected"})
                continue
            groups.append(group.model_dump(mode="json"))
            source = self.sources.get(group.source_key)
            if source is None or str(source.receipt["id"]) != str(group.receipt_id):
                errors.append({"group": index, "code": "incorrect_claim_association"})
                continue
            for pointer in group.pointers:
                try:
                    pointed = pointer_value({"data": source.receipt["result"]}, pointer)
                    if type(pointed) in {dict, list}:
                        raise EvidenceError("scalar_reference_required")
                    if pointer not in source.fields:
                        if any(
                            other.receipt["id"] == source.receipt["id"]
                            and pointer in other.fields
                            for other in self.sources.values()
                        ):
                            raise EvidenceError("incorrect_claim_association")
                        raise EvidenceError("unregistered_semantic_field")
                    kind, value = source.fields[pointer]
                    pair = (source.key, pointer)
                    if pair in seen:
                        duplicates += 1
                        continue
                    seen.add(pair)
                    semantic = self.semantic_key(source, pointer)
                    if semantic in dedup:
                        if not exact(dedup[semantic], value):
                            raise EvidenceError("conflicting_source_claim")
                        duplicates += 1
                        continue
                    dedup[semantic] = value
                    facts.append(
                        {
                            "receipt_id": str(group.receipt_id),
                            "source_key": source.key,
                            "pointer": pointer,
                            "field_type": kind,
                            "value": value,
                            "known": value is not None and value != "unknown",
                            "observation_class": "derived_classification"
                            if kind in {"freshness", "review_state"}
                            else "unresolved"
                            if value is None or value == "unknown"
                            else source.binding["data_class"],
                            "model_selected": True,
                            **source.binding,
                        }
                    )
                except EvidenceError as exc:
                    errors.append(
                        {"group": index, "pointer": pointer, "code": exc.code}
                    )
        coverage = self.coverage(seen)
        complete = not errors and bool(facts) and coverage["complete"]
        return {
            "protocol": PROTOCOL,
            "verification": VERIFIER,
            "claims": facts,
            "invalid_citations": errors,
            "duplicates_removed": duplicates,
            "references": groups,
            "coverage": coverage,
            "complete": complete,
            "partial": not complete and bool(facts),
            "quote_ready": coverage["quote_ready"],
            "needs_human_follow_up": not complete or not coverage["quote_ready"],
            "backend_summary": {
                "lines_inspected": sum(
                    line["source_coverage_complete"] for line in coverage["lines"]
                ),
                "lines_total": len(coverage["lines"]),
                "verified_facts": len(facts),
                "unknown_fields": sum(
                    len(line["unknowns"]) for line in coverage["lines"]
                ),
            },
            "limitations": [
                "Local imported and user-attested facts only",
                "Research completion does not authorize quote approval",
                "No live supplier availability or delivery commitment",
            ],
        }

    def coverage(self, seen=None):
        seen = seen or set()
        lines = []
        selected = {
            self.semantic_key(self.sources[key], pointer) for key, pointer in seen
        }
        for line in self.snapshot["lines"]:
            inspected = self.inspected.get(line["line_id"], set())
            missing_tools = sorted(
                {"get_reviewed_product_selection", "get_supplier_offers"} - inspected
            )
            missing_refs = [
                {
                    "source_key": source.key,
                    "receipt_id": str(source.receipt["id"]),
                    "pointer": pointer,
                }
                for source in self.sources.values()
                if source.binding["line_id"] == line["line_id"]
                for pointer in sorted(source.required)
                if self.semantic_key(source, pointer) not in selected
            ]
            unknowns = []
            conflicts = []
            if line["selection"]["state"] != "resolved":
                unknowns.append(
                    {"field": "product_selection", "state": line["selection"]["state"]}
                )
            if not line["offers"]["attestations"]:
                unknowns.append(
                    {"field": "attested_supplier_offer", "state": "missing"}
                )
            for offer in line["offers"]["attestations"]:
                for key in [
                    "price",
                    "currency",
                    "availability",
                    "lead_time_days",
                    "stock_units",
                    "observed_on",
                    "valid_until",
                ]:
                    if offer["data"]["commercial"].get(key) in {None, "unknown"}:
                        unknowns.append(
                            {"offer_id": offer["id"], "field": key, "state": "unknown"}
                        )
                review = commercial_review_state(offer, line["offers"]["attestations"])
                if review != "active_attestation":
                    conflicts.append({"offer_id": offer["id"], "state": review})
            source_complete = self.approved_read and not missing_tools
            lines.append(
                {
                    "line_id": line["line_id"],
                    "selection_state": line["selection"]["state"],
                    "inspected_tools": sorted(inspected),
                    "missing_tools": missing_tools,
                    "missing_citations": missing_refs,
                    "source_coverage_complete": source_complete,
                    "complete": source_complete and not missing_refs,
                    "unknowns": unknowns,
                    "commercial_review": conflicts,
                }
            )
        ready = False
        quote_issues = ["quote_policy_not_supplied"]
        if self.snapshot.get("quote_policy"):
            try:
                calculation = quote_calculation(
                    self.snapshot,
                    self.snapshot["quote_choices"],
                    QuotePolicy.model_validate(self.snapshot["quote_policy"]),
                )
                ready = calculation["complete"]
                quote_issues = calculation["issues"]
            except Exception:
                # No source text or financial guesses in status. The quote API remains authoritative.
                quote_issues = ["quote_inputs_require_review"]
                ready = False
        return {
            "approved_rfq_read": self.approved_read,
            "source_coverage_complete": self.approved_read
            and all(line["source_coverage_complete"] for line in lines)
            and bool(lines),
            "complete": self.approved_read
            and all(line["complete"] for line in lines)
            and bool(lines),
            "lines": lines,
            "quote_ready": ready,
            "quote_issues": quote_issues,
        }

    def merge_partial(self, previous, current):
        groups = {}
        for fact in [*previous.get("claims", []), *current.get("claims", [])]:
            key = (fact["source_key"], fact["receipt_id"])
            groups.setdefault(key, []).append(fact["pointer"])
        payload = {
            "claims": [
                {
                    "source_key": key[0],
                    "receipt_id": key[1],
                    "pointers": sorted(set(paths)),
                }
                for key, paths in groups.items()
            ]
        }
        merged = self.resolve(payload)
        merged["invalid_citations"] = current["invalid_citations"]
        merged["prior_invalid_citations"] = previous.get("invalid_citations", [])
        merged["complete"] = (
            bool(merged["claims"])
            and merged["coverage"]["complete"]
            and not merged["invalid_citations"]
        )
        merged["partial"] = bool(merged["claims"]) and not merged["complete"]
        merged["repaired"] = merged["complete"] and bool(
            previous.get("invalid_citations")
        )
        merged["needs_human_follow_up"] = (
            not merged["complete"] or not merged["quote_ready"]
        )
        return merged
