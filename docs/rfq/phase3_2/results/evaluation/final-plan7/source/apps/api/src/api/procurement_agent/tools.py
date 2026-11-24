"""Backend allowlist; tool arguments cannot supply workspace/RFQ/actor identity."""

import json


from api.catalog.service import retrieve

from . import contracts as c
from .finance import Commercial, freshness, number
from .service import commercial_review_state

VERSION = "procurement-tools/2"
REGISTRY = {
    "get_approved_rfq": (
        c.Empty,
        "Read approved RFQ identity, revision and approved lines.",
    ),
    "get_reviewed_product_selection": (
        c.Line,
        "Read authoritative product resolution and compatibility for one approved line.",
    ),
    "search_catalog": (
        c.Search,
        "Search snapshotted local catalog versions; retrieval is evidence only, never approval.",
    ),
    "get_product_details": (
        c.Line,
        "Read the explicitly resolved canonical product and source version.",
    ),
    "get_supplier_offers": (
        c.Line,
        "Read imported metadata and separately labeled user-attested commercial offers for one line.",
    ),
    "compare_supplier_offers": (
        c.Line,
        "Compare attested prices only within the same currency, price basis and pack size. No FX.",
    ),
    "check_offer_freshness": (
        c.Offer,
        "Read an attested offer's documented validity; ingestion is not price observation.",
    ),
    "get_quote_requirements": (
        c.Empty,
        "Read RFQ quantities, units and user-declared quote policy, if supplied.",
    ),
    "calculate_quote_preview": (
        c.Empty,
        "Run backend Decimal calculations using the user-selected quote policy and offers, if supplied.",
    ),
    "get_source_evidence": (
        c.Line,
        "Read bounded approved-field evidence and selected catalog fingerprints for one line.",
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


def execute(name, args, run):
    if name not in REGISTRY:
        raise ValueError("Tool not allowlisted")
    parsed = REGISTRY[name][0].model_validate(args)
    source = run["snapshot"]
    line = None
    if hasattr(parsed, "line_id"):
        line = next(
            (
                entry
                for entry in source["lines"]
                if entry["line_id"] == str(parsed.line_id)
            ),
            None,
        )
        if not line:
            raise ValueError("Line outside authorized approved RFQ snapshot")
    if name == "get_approved_rfq":
        result = {
            "rfq_id": source["rfq_id"],
            "revision": source["revision"],
            "source_run": source["source_run"],
            "lines": [
                {
                    "line_id": entry["line_id"],
                    "quantity": entry["quantity"],
                    "unit": entry["unit"],
                    "description": entry["fields"].get("description", {}).get("value"),
                }
                for entry in source["lines"]
            ],
        }
    elif name == "get_reviewed_product_selection":
        result = {
            k: v
            for k, v in line["selection"].items()
            if k not in {"candidates", "reviews"}
        }
    elif name == "search_catalog":
        resolution = line["selection"].get("resolution")
        versions = (
            [resolution["data"]["version_id"]]
            if line["selection"]["state"] == "resolved" and resolution
            else source["catalog_versions"]
        )
        result = retrieve(
            run["workspace_id"],
            versions,
            line["selection"]["query"],
            parsed.method,
        )
        result["candidates"] = result["candidates"][:5]
    elif name == "get_product_details":
        resolution = line["selection"].get("resolution")
        result = {
            "selection_state": line["selection"]["state"],
            "product": resolution["data"]
            if resolution and line["selection"]["state"] == "resolved"
            else None,
        }
    elif name == "get_supplier_offers":
        result = {
            "line_id": line["line_id"],
            "selection_state": line["selection"]["state"],
            "imported": line["offers"]["imported"],
            "attestations": [
                {
                    "id": offer["id"],
                    **offer["data"]["commercial"],
                    "data_class": "user_attested",
                    "freshness": offer["freshness"],
                    "actor": offer["actor"],
                    "reason": offer["reason"],
                    "resolution_id": offer["resolution_id"],
                    "product_id": offer["data"]["product_id"],
                    "version_id": offer["data"]["version_id"],
                    "source_fingerprint": offer["data"]["source_fingerprint"],
                    **(
                        {
                            "commercial_review_state": commercial_review_state(
                                offer, line["offers"]["attestations"]
                            )
                        }
                        if commercial_review_state(
                            offer, line["offers"]["attestations"]
                        )
                        != "active_attestation"
                        else {}
                    ),
                }
                for offer in line["offers"]["attestations"]
            ],
        }
    elif name == "compare_supplier_offers":
        groups = {}
        unknown = []
        excluded = []
        for offer in line["offers"]["attestations"]:
            review_state = commercial_review_state(
                offer, line["offers"]["attestations"]
            )
            if review_state != "active_attestation":
                excluded.append({"offer_id": offer["id"], "reason": review_state})
                continue
            value = offer["data"]["commercial"]
            if (
                value.get("price") is None
                or not value.get("currency")
                or not value.get("pack_size")
                or not value.get("price_basis")
            ):
                unknown.append(offer["id"])
                continue
            key = f"{value['currency']}:{value['price_basis']}:{value['pack_size']}"
            groups.setdefault(key, []).append(
                {
                    "offer_id": offer["id"],
                    "price": value["price"],
                    "freshness": offer["freshness"],
                    "availability": value["availability"],
                    "data_class": "user_attested",
                }
            )
        for group in groups.values():
            group.sort(key=lambda o: (number(o["price"]), o["offer_id"]))
        result = {
            "groups": groups,
            "unresolved": unknown,
            "excluded": excluded,
            "scope": "base prices only; pack/MOQ/quantity breaks require quote calculation; no currency conversion",
        }
    elif name == "check_offer_freshness":
        offer = next(
            (
                o
                for entry in source["lines"]
                for o in entry["offers"]["attestations"]
                if o["id"] == str(parsed.offer_id)
            ),
            None,
        )
        if not offer:
            raise ValueError("Offer outside authorized snapshot")
        result = {
            "offer_id": offer["id"],
            "freshness": freshness(
                Commercial.model_validate(offer["data"]["commercial"])
            ),
            "observed_on": offer["data"]["commercial"]["observed_on"],
            "valid_until": offer["data"]["commercial"]["valid_until"],
            "data_class": "user_attested",
        }
    elif name == "get_quote_requirements":
        result = {
            "lines": [
                {
                    "line_id": entry["line_id"],
                    "quantity": entry["quantity"],
                    "unit": entry["unit"],
                }
                for entry in source["lines"]
            ],
            "policy": source.get("quote_policy"),
            "unknowns_require_human_review": True,
        }
    elif name == "calculate_quote_preview":
        if not source.get("quote_policy"):
            result = {"status": "quote_policy_not_supplied", "grand_total": None}
        else:
            from .finance import QuotePolicy
            from .service import quote_calculation

            result = quote_calculation(
                source,
                source["quote_choices"],
                QuotePolicy.model_validate(source["quote_policy"]),
            )
    else:
        resolution = line["selection"].get("resolution")
        result = {
            "line_id": line["line_id"],
            "approved_fields": line["fields"],
            "catalog_sources": resolution["data"].get("sources", [])
            if resolution
            else [],
        }
    if len(json.dumps(result, default=str).encode()) > 20000:
        raise ValueError("Tool result exceeds bounded evidence size")
    return result


def verify(summary, receipts):
    result = c.ResearchSummary.model_validate_json(summary)
    if not result.claims:
        raise ValueError("No source-grounded claims returned")
    validated = []
    for claim in result.claims:
        receipt = next(
            (
                r
                for r in receipts
                if str(r["id"]) == str(claim.receipt_id) and r["status"] == "succeeded"
            ),
            None,
        )
        if not receipt:
            raise ValueError("Claim cites absent or unsuccessful tool receipt")
        # The canonical citation root is the same data envelope shown to the model.
        value = {"data": receipt["result"]}
        try:
            for token in claim.pointer[1:].split("/"):
                key = token.replace("~1", "/").replace("~0", "~")
                value = value[int(key)] if isinstance(value, list) else value[key]
        except (KeyError, IndexError, ValueError, TypeError):
            raise ValueError(
                "Claim pointer is not supported by cited tool evidence"
            ) from None
        if type(value) is not type(claim.value) or value != claim.value:
            raise ValueError("Claim value differs from cited evidence")
        validated.append(claim.model_dump(mode="json"))
    return {
        "claims": validated,
        "verification": "exact JSON pointer/scalar equality; no free-form commercial assertions",
        "limitations": [
            "Local imported and user-attested facts only",
            "Compatibility checks are limited; alternative suitability needs authorized review",
            "No live supplier stock or delivery commitments",
        ],
    }


def fact_inventory(receipts):
    """Bounded citation aids derived from receipts, not model-created commercial facts."""
    facts = []
    preferred = {
        "price",
        "currency",
        "availability",
        "freshness",
        "selection_state",
        "state",
        "quantity",
        "unit",
        "supplier",
        "data_class",
        "observed_on",
        "valid_until",
        "grand_total",
        "status",
    }

    def walk(value, path, receipt_id):
        if isinstance(value, dict):
            for key, child in value.items():
                pointer = path + "/" + key.replace("~", "~0").replace("/", "~1")
                if key in preferred and (
                    child is None or type(child) in {str, int, bool}
                ):
                    facts.append(
                        {
                            "receipt_id": str(receipt_id),
                            "pointer": pointer,
                            "value": child,
                        }
                    )
                elif isinstance(child, (dict, list)):
                    walk(child, pointer, receipt_id)
        elif isinstance(value, list):
            for index, child in enumerate(value[:10]):
                walk(child, path + "/" + str(index), receipt_id)

    for receipt in receipts:
        if receipt["status"] == "succeeded":
            walk(receipt["result"], "/data", receipt["id"])
    return facts[:100]
