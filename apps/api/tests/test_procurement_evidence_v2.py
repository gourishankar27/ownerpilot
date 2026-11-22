"""Independent reference/association assertions; protocol fixtures are not native-model runs."""

import copy
import json
from uuid import uuid4

import pytest

from api.procurement_agent.contracts import CitationGroup
from api.procurement_agent.evidence import (
    EvidenceResolver,
    EvidenceError,
    pointer_value,
    check_type,
    sanitize_request,
    PROTOCOL,
    VERIFIER,
)
from api.procurement_agent.service import digest
from api.procurement_agent.tools import execute


def evidence_fixture(line_count=1, offers=1, price="12.50"):
    run_id = str(uuid4())
    workspace = str(uuid4())
    lines = []
    for index in range(line_count):
        line_id = str(uuid4())
        resolution_id = str(uuid4())
        version = str(uuid4())
        product = f"fictional-product-{index}"
        selected = {
            "id": resolution_id,
            "data": {
                "decision": "select",
                "product_id": product,
                "version_id": version,
                "content_hash": "a" * 64,
                "product": {
                    "manufacturer": "Fictional",
                    "mpn": f"SYN-{index}",
                    "name": "Fictional device",
                },
            },
        }
        attestations = []
        for offer_index in range(offers):
            commercial = {
                "supplier": f"Fictional supplier {offer_index}",
                "supplier_sku": f"SKU-{index}",
                "price": price,
                "currency": "USD",
                "price_basis": "each",
                "pack_size": 1,
                "minimum_units": "1",
                "breaks": [],
                "availability": "available",
                "observed_on": "2026-11-21",
                "valid_until": "2026-12-31",
                "source_reference": "Fictional description containing price 999; not an authoritative price field",
            }
            attestations.append(
                {
                    "id": str(uuid4()),
                    "resolution_id": resolution_id,
                    "actor": "synthetic-reviewer",
                    "reason": "Source independently reviewed",
                    "freshness": "current_according_to_attested_validity",
                    "data": {
                        "commercial": commercial,
                        "product_id": product,
                        "version_id": version,
                        "source_fingerprint": "a" * 64,
                    },
                }
            )
        lines.append(
            {
                "line_id": line_id,
                "quantity": "2",
                "unit": "EA",
                "fields": {"description": {"value": "Fictional device"}},
                "selection": {
                    "state": "resolved",
                    "line_id": line_id,
                    "resolution": selected,
                    "candidates": [],
                    "reviews": [],
                },
                "offers": {"attestations": attestations, "imported": []},
            }
        )
    source = {
        "rfq_id": str(uuid4()),
        "revision": 7,
        "source_run": str(uuid4()),
        "lines": lines,
    }
    run = {
        "id": run_id,
        "workspace_id": workspace,
        "snapshot": source,
        "metadata": {
            "claim_schema": PROTOCOL,
            "verifier_version": VERIFIER,
            "tool_schema": "procurement-tools/2",
            "source_fingerprint": digest(source),
        },
    }
    receipts = []

    def add(name, args):
        receipts.append(
            {
                "id": str(uuid4()),
                "run_id": run_id,
                "ordinal": len(receipts) + 1,
                "tool": name,
                "arguments": args,
                "schema_version": "procurement-tools/2",
                "status": "succeeded",
                "result": execute(name, args, run),
            }
        )

    add("get_approved_rfq", {})
    for line in lines:
        add("get_reviewed_product_selection", {"line_id": line["line_id"]})
        add("get_supplier_offers", {"line_id": line["line_id"]})
    return run, receipts


def references(resolver):
    return {
        "claims": [
            {key: item[key] for key in ["source_key", "receipt_id", "pointers"]}
            for item in resolver.inventory()
        ]
    }


def test_materializes_exact_price_and_complete_research_separate_from_quote():
    run, receipts = evidence_fixture()
    resolver = EvidenceResolver(run, receipts)
    result = resolver.resolve(references(resolver))
    assert result["complete"] is True and result["quote_ready"] is False
    price = next(fact for fact in result["claims"] if fact["field_type"] == "price")
    assert (
        price["value"] == "12.50"
        and price["rfq_revision"] == 7
        and price["offer_id"]
        == run["snapshot"]["lines"][0]["offers"]["attestations"][0]["id"]
    )
    assert (
        price["product_id"] == "fictional-product-0"
        and price["workspace_id"] == run["workspace_id"]
    )


@pytest.mark.parametrize("value", [None, "0", "123456.78"])
def test_null_and_decimal_strings_are_materialized_without_model_values(value):
    run, receipts = evidence_fixture(price=value)
    resolver = EvidenceResolver(run, receipts)
    result = resolver.resolve(references(resolver))
    assert result["complete"] is True
    fact = next(fact for fact in result["claims"] if fact["field_type"] == "price")
    assert fact["value"] is value if value is None else fact["value"] == value


@pytest.mark.parametrize(
    "pointer,expected",
    [
        ("", {"a/b": {"~key": [False, 2, None]}}),
        ("/a~1b/~0key/0", False),
        ("/a~1b/~0key/1", 2),
        ("/a~1b/~0key/2", None),
    ],
)
def test_rfc6901_valid_escapes_lists_and_scalar_types(pointer, expected):
    value = pointer_value({"a/b": {"~key": [False, 2, None]}}, pointer)
    assert type(value) is type(expected) and value == expected


@pytest.mark.parametrize(
    "pointer",
    [
        "#/a",
        "a",
        "/a/~2",
        "/a/~",
        "/a/-1",
        "/a/+1",
        "/a/01",
        "/a/-",
        "/a/1_0",
        "/a/99",
        "/a/0/x",
    ],
)
def test_rfc6901_invalid_pointer_and_index(pointer):
    with pytest.raises(EvidenceError):
        pointer_value({"a": ["scalar"]}, pointer)


@pytest.mark.parametrize(
    "kind,value",
    [
        ("boolean", 1),
        ("revision", True),
        ("pack_size", False),
        ("price", 12.5),
        ("currency", "usd"),
        ("price", "NaN"),
        ("date", "2026-99-01"),
    ],
)
def test_semantic_type_checks_do_not_guess_or_coerce(kind, value):
    with pytest.raises(EvidenceError):
        check_type(kind, value)


@pytest.mark.parametrize(
    "mutation",
    ["run", "workspace", "failed", "revision", "product", "offer", "fingerprint"],
)
def test_receipt_ownership_and_source_binding(mutation):
    run, receipts = evidence_fixture()
    forged = copy.deepcopy(receipts)
    if mutation == "run":
        forged[-1]["run_id"] = str(uuid4())
    if mutation == "workspace":
        forged[-1]["workspace_id"] = str(uuid4())
    if mutation == "failed":
        forged[-1]["status"] = "failed"
    if mutation == "revision":
        forged[0]["result"]["revision"] = 999
    if mutation == "product":
        forged[-1]["result"]["attestations"][0]["product_id"] = "other-product"
    if mutation == "offer":
        forged[-1]["result"]["attestations"][0]["id"] = str(uuid4())
    if mutation == "fingerprint":
        forged[-1]["result"]["attestations"][0]["source_fingerprint"] = "b" * 64
    resolver = EvidenceResolver(run, forged)
    result = resolver.resolve(references(resolver))
    assert result["complete"] is False and result["invalid_citations"]


def test_price_pointer_cannot_move_to_other_offer_even_with_equal_prices():
    run, receipts = evidence_fixture(offers=2)
    resolver = EvidenceResolver(run, receipts)
    groups = references(resolver)
    commercial = [
        group
        for group in groups["claims"]
        if any(pointer.endswith("/price") for pointer in group["pointers"])
    ]
    commercial[0]["pointers"] = [
        pointer for pointer in commercial[1]["pointers"] if pointer.endswith("/price")
    ]
    result = resolver.resolve(groups)
    assert result["complete"] is False and any(
        error["code"] == "incorrect_claim_association"
        for error in result["invalid_citations"]
    )
    assert not any(
        fact["offer_id"]
        == run["snapshot"]["lines"][0]["offers"]["attestations"][0]["id"]
        and fact["field_type"] == "price"
        for fact in result["claims"]
    )


def test_cross_line_and_unknown_receipt_rejected():
    run, receipts = evidence_fixture(2)
    resolver = EvidenceResolver(run, receipts)
    groups = references(resolver)
    groups["claims"][0]["receipt_id"] = str(uuid4())
    result = resolver.resolve(groups)
    assert result["complete"] is False and any(
        error["code"] == "incorrect_claim_association"
        for error in result["invalid_citations"]
    )


@pytest.mark.parametrize(
    "pointer",
    [
        "/data",
        "/data/attestations",
        "/data/attestations/0/source_reference",
        "/data/attestations/0/fictional_price",
    ],
)
def test_objects_description_numbers_and_fabricated_price_paths_never_become_prices(
    pointer,
):
    run, receipts = evidence_fixture()
    resolver = EvidenceResolver(run, receipts)
    groups = references(resolver)
    offer_group = next(
        group
        for group in groups["claims"]
        if any(path.endswith("/price") for path in group["pointers"])
    )
    offer_group["pointers"] = [pointer]
    result = resolver.resolve(groups)
    assert result["complete"] is False and not any(
        fact["field_type"] == "price" for fact in result["claims"]
    )


def test_unknown_value_field_rejected_and_never_persisted_as_authoritative_data():
    run, receipts = evidence_fixture()
    resolver = EvidenceResolver(run, receipts)
    payload = references(resolver)
    payload["claims"][0]["value"] = "10},{"
    safe = sanitize_request(json.dumps(payload))
    assert "10},{" not in json.dumps(safe)
    result = resolver.resolve(safe)
    assert result["complete"] is False and result["partial"] is True
    assert any(
        error["code"] == "claim_schema_rejected"
        for error in result["invalid_citations"]
    )


def test_duplicate_claims_deduplicate_and_missing_required_reference_blocks_completion():
    run, receipts = evidence_fixture()
    resolver = EvidenceResolver(run, receipts)
    payload = references(resolver)
    payload["claims"].append(copy.deepcopy(payload["claims"][0]))
    result = resolver.resolve(payload)
    assert result["complete"] and result["duplicates_removed"] > 0
    payload["claims"] = [payload["claims"][0]]
    result = resolver.resolve(payload)
    assert (
        not result["complete"] and result["coverage"]["lines"][0]["missing_citations"]
    )


def test_partial_evidence_repaired_without_losing_valid_facts():
    run, receipts = evidence_fixture()
    resolver = EvidenceResolver(run, receipts)
    payload = references(resolver)
    payload["claims"][-1]["pointers"].append("/data/missing")
    partial = resolver.resolve(payload)
    assert partial["partial"] and not partial["complete"]
    corrected = resolver.resolve(references(resolver))
    merged = resolver.merge_partial(partial, corrected)
    assert merged["complete"] and merged["prior_invalid_citations"] and merged["claims"]


def test_stale_snapshot_cannot_be_reinterpreted():
    run, receipts = evidence_fixture()
    run["snapshot"]["revision"] = 8
    with pytest.raises(EvidenceError, match="source_snapshot_mismatch"):
        EvidenceResolver(run, receipts)


def test_citation_only_contract_forbids_business_association_overrides():
    group = {
        "receipt_id": str(uuid4()),
        "source_key": "s" + "a" * 12,
        "pointers": ["/data/price"],
    }
    for extra in ["value", "product_id", "offer_id", "workspace_id", "line_id", "role"]:
        with pytest.raises(ValueError):
            CitationGroup.model_validate({**group, extra: "forged"})


def test_duplicate_json_members_cannot_hide_a_rejected_claim():
    run, receipts = evidence_fixture()
    resolver = EvidenceResolver(run, receipts)
    good = json.dumps(references(resolver)["claims"])
    raw = '{"claims":[{"value":"fabricated"}],"claims":' + good + "}"
    result = resolver.resolve(sanitize_request(raw))
    assert not result["complete"] and result["invalid_citations"]


def test_equal_quantities_cannot_cross_line_subject_bindings():
    run, receipts = evidence_fixture(line_count=2)
    resolver = EvidenceResolver(run, receipts)
    source = next(
        source
        for source in resolver.sources.values()
        if "/data/lines/0/quantity" in source.fields
    )
    result = resolver.resolve(
        {
            "claims": [
                {
                    "source_key": source.key,
                    "receipt_id": str(source.receipt["id"]),
                    "pointers": ["/data/lines/1/quantity"],
                }
            ]
        }
    )
    assert not result["complete"] and not result["claims"]
    assert result["invalid_citations"][0]["code"] == "incorrect_claim_association"
