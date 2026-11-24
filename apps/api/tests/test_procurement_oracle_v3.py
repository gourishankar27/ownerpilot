"""The independent evaluator catches corruption independently of production verification."""

import copy
import importlib.util
from pathlib import Path

import pytest

from api.procurement_agent.evidence_v3 import EvidenceResolver
from test_procurement_batches_v3 import fixture
from test_procurement_evidence_v2 import references

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "independent_v3_oracle", ROOT / "scripts/procurement32_oracle.py"
)
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)


def inputs():
    run, receipts = fixture(2)
    lines = []
    item = {
        "rfq_id": run["snapshot"]["rfq_id"],
        "revision": run["snapshot"]["revision"],
        "lines": {},
    }
    for index, line in enumerate(run["snapshot"]["lines"]):
        key = f"line-{index}"
        offer = line["offers"]["attestations"][0]
        selection = line["selection"]["resolution"]
        lines.append(
            {
                "key": key,
                "selection": "resolved",
                "offers": [
                    {
                        "key": "offer-a",
                        "commercial": copy.deepcopy(offer["data"]["commercial"]),
                        "expected_freshness": "current_according_to_attested_validity",
                        "expected_review_state": "active_attestation",
                    }
                ],
            }
        )
        item["lines"][key] = {
            "line_id": line["line_id"],
            "resolution_id": selection["id"],
            "product_id": selection["data"]["product_id"],
            "version_id": selection["data"]["version_id"],
            "fingerprint": "a" * 64,
            "offers": {"offer-a": offer["id"]},
        }
    case = {
        "lines": lines,
        "expected": {
            "quote_ready": False,
            "allowed_tools": ["get_approved_rfq", "get_line_research_batch"],
        },
    }
    resolver = EvidenceResolver(run, receipts)
    result = resolver.resolve(references(resolver))
    return case, item, run, result, receipts


def test_independent_grader_accepts_original_facts_source_keys_and_unknowns():
    case, item, run, result, receipts = inputs()
    audit = oracle.audit(case, item, run, result, receipts)
    assert not audit["invalid_facts"] and not audit["source_errors"]
    assert audit["required_source_coverage"] and audit["required_fact_coverage"]
    assert audit["unknowns_correct"] and audit["quote_readiness_correct"]


@pytest.mark.parametrize(
    "corruption", ["line", "offer", "price", "type", "key", "unknown", "partial_source"]
)
def test_independent_grader_rejects_corrupted_published_data(corruption):
    case, item, run, result, receipts = inputs()
    price = next(fact for fact in result["claims"] if fact["field_type"] == "price")
    if corruption == "line":
        price["line_id"] = run["snapshot"]["lines"][1]["line_id"]
    if corruption == "offer":
        price["offer_id"] = run["snapshot"]["lines"][1]["offers"]["attestations"][0][
            "id"
        ]
    if corruption == "price":
        price["value"] = "12.500"
    if corruption == "type":
        price["value"] = 12.5
    if corruption == "key":
        price["source_key"] = "s" + "0" * 12
    if corruption == "unknown":
        result["coverage"]["lines"][0]["unknowns"] = []
    if corruption == "partial_source":
        receipts[1]["result"]["lines"].pop()
    audit = oracle.audit(case, item, run, result, receipts)
    assert (
        audit["invalid_facts"]
        or audit["source_errors"]
        or not audit["unknowns_correct"]
    )
