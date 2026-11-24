"""Explicit protocol fixtures, not native-model successes."""

import copy
from uuid import uuid4

import pytest

from api.procurement_agent.evidence import EvidenceError
from api.procurement_agent.evidence_v3 import EvidenceResolver
from api.procurement_agent.planning import (
    capacity,
    remaining,
    mandatory_plan,
    partitions,
)
from api.procurement_agent.service import digest
from api.procurement_agent.tools_v3 import Batch, VERSION, execute, canonical_arguments
from test_procurement_evidence_v2 import evidence_fixture, references


def fixture(count=4, offers=1):
    run, old = evidence_fixture(line_count=count, offers=offers)
    run["metadata"].update(tool_schema=VERSION, batch_size=4)
    run.update(planning_calls=0, planning_state={})
    first = {**old[0], "schema_version": VERSION}
    args = {"line_ids": [line["line_id"] for line in run["snapshot"]["lines"]]}
    receipt = {
        "id": str(uuid4()),
        "run_id": run["id"],
        "ordinal": 2,
        "tool": "get_line_research_batch",
        "schema_version": VERSION,
        "arguments": args,
        "status": "succeeded",
        "result": copy.deepcopy(execute("get_line_research_batch", args, run)),
    }
    return run, [first, receipt]


@pytest.mark.parametrize("count", [1, 2, 4])
def test_parent_receipt_materializes_exact_per_line_offer_facts(count):
    run, receipts = fixture(count)
    resolver = EvidenceResolver(run, receipts)
    result = resolver.resolve(references(resolver))
    assert result["complete"] and len(result["claims"]) == 5 * count
    assert all(fact["receipt_id"] == receipts[1]["id"] for fact in result["claims"])
    assert {fact["line_id"] for fact in result["claims"]} == {
        line["line_id"] for line in run["snapshot"]["lines"]
    }
    for index, line in enumerate(run["snapshot"]["lines"]):
        price = next(
            fact
            for fact in result["claims"]
            if fact["line_id"] == line["line_id"] and fact["field_type"] == "price"
        )
        assert (
            price["value"] == "12.50"
            and price["offer_id"] == line["offers"]["attestations"][0]["id"]
        )
        assert price["pointer"] == f"/data/lines/{index}/offers/attestations/0/price"


@pytest.mark.parametrize(
    "invalid", [[], ["bad"], [str(uuid4())] * 2, [str(uuid4()) for _ in range(5)]]
)
def test_closed_batch_rejects_invalid_size_uuid_and_duplicates(invalid):
    with pytest.raises(ValueError):
        Batch.model_validate({"line_ids": invalid})


@pytest.mark.parametrize(
    "extra", ["workspace_id", "rfq_id", "actor", "url", "price", "include_all"]
)
def test_batch_never_accepts_identity_or_business_overrides(extra):
    with pytest.raises(ValueError):
        Batch.model_validate({"line_ids": [str(uuid4())], extra: "forged"})


def test_batch_authorization_rejects_whole_request_before_any_source_read(monkeypatch):
    run, receipts = fixture(2)
    invoked = []
    monkeypatch.setattr(
        "api.procurement_agent.tools_v3.legacy.execute",
        lambda *args: invoked.append(args),
    )
    with pytest.raises(EvidenceError, match="batch_line_unauthorized"):
        execute(
            "get_line_research_batch",
            {"line_ids": [run["snapshot"]["lines"][0]["line_id"], str(uuid4())]},
            run,
        )
    assert not invoked


@pytest.mark.parametrize(
    "change",
    [
        "omit_line",
        "duplicate_line",
        "partial",
        "wrong_line",
        "wrong_product",
        "wrong_fingerprint",
        "wrong_offer",
        "wrong_revision",
        "wrong_workspace",
        "wrong_run",
    ],
)
def test_partial_and_rebound_batch_receipts_cannot_supply_coverage(change):
    run, receipts = fixture(2)
    receipt = receipts[1]
    entries = receipt["result"]["lines"]
    if change == "omit_line":
        entries.pop()
    if change == "duplicate_line":
        entries[1] = copy.deepcopy(entries[0])
    if change == "partial":
        receipt["result"]["complete"] = False
    if change == "wrong_line":
        entries[1]["line_id"] = str(uuid4())
    if change == "wrong_product":
        entries[1]["offers"]["attestations"][0]["product_id"] = "forged"
    if change == "wrong_fingerprint":
        entries[1]["offers"]["attestations"][0]["source_fingerprint"] = "f" * 64
    if change == "wrong_offer":
        entries[1]["offers"]["attestations"][0]["id"] = str(uuid4())
    if change == "wrong_revision":
        entries[1]["selection"]["resolution"]["revision"] = 999
    if change == "wrong_workspace":
        receipt["workspace_id"] = str(uuid4())
    if change == "wrong_run":
        receipt["run_id"] = str(uuid4())
    resolver = EvidenceResolver(run, receipts)
    assert resolver.receipt_errors
    assert not resolver.coverage()["source_coverage_complete"]
    assert not resolver.sources or not any(
        source.receipt["id"] == receipt["id"] for source in resolver.sources.values()
    )


@pytest.mark.parametrize(
    "path",
    [
        "/data/lines/1/offers/attestations/0/price",
        "/data/lines/0/offers/attestations/1/currency",
    ],
)
def test_equal_values_from_another_line_or_offer_are_rejected(path):
    run, receipts = fixture(2, offers=2)
    resolver = EvidenceResolver(run, receipts)
    source = next(
        source
        for source in resolver.sources.values()
        if "/data/lines/0/offers/attestations/0/price" in source.fields
    )
    result = resolver.resolve(
        {
            "claims": [
                {
                    "receipt_id": receipts[1]["id"],
                    "source_key": source.key,
                    "pointers": [path],
                }
            ]
        }
    )
    assert (
        not result["claims"]
        and result["invalid_citations"][0]["code"] == "incorrect_claim_association"
    )


def test_failed_receipt_is_not_citable_but_later_success_can_complete_sources():
    run, receipts = fixture(2)
    failed = {
        **receipts[1],
        "id": str(uuid4()),
        "ordinal": 2,
        "status": "failed",
        "result": None,
        "error": "tool_timeout",
    }
    receipts[1]["ordinal"] = 3
    resolver = EvidenceResolver(run, [receipts[0], failed, receipts[1]])
    result = resolver.resolve(references(resolver))
    assert result["complete"] and result["tool_failures"]
    group = references(resolver)["claims"][0]
    group["receipt_id"] = failed["id"]
    assert not resolver.resolve({"claims": [group]})["complete"]


@pytest.mark.parametrize(
    "field,value", [("price", None), ("price", "0"), ("availability", "unknown")]
)
def test_batch_unknowns_zero_and_source_types_remain_exact(field, value):
    run, _ = evidence_fixture()
    run["metadata"].update(tool_schema=VERSION, batch_size=4)
    run["snapshot"]["lines"][0]["offers"]["attestations"][0]["data"]["commercial"][
        field
    ] = value
    run["metadata"]["source_fingerprint"] = digest(run["snapshot"])
    args = {"line_ids": [run["snapshot"]["lines"][0]["line_id"]]}
    body = execute("get_line_research_batch", args, run)
    assert body["lines"][0]["offers"]["attestations"][0][field] == value


@pytest.mark.parametrize("count", [1, 2, 4, 8, 12, 13, 100])
def test_preflight_capacity_has_explicit_line_and_call_limits(count):
    run, _ = evidence_fixture(line_count=count)
    report = capacity(run["snapshot"], 4)
    assert report["supported"] is (count <= 12)
    assert report["minimum_tool_calls"] == 1 + (count + 3) // 4
    assert not report["continuation_available"]


def test_snapshot_is_never_counted_as_executed_research_and_scheduler_is_minimal():
    run, receipts = fixture(4)
    none = EvidenceResolver(run, [])
    work = remaining(run, [], none)
    assert work["covered_lines"] == 0 and len(work["remaining_lines"]) == 4
    plan = mandatory_plan(work, 2)
    assert len(plan) == 3 and plan[0]["function"]["name"] == "get_approved_rfq"
    complete = remaining(run, receipts, EvidenceResolver(run, receipts))
    assert complete["covered_lines"] == 4 and not mandatory_plan(complete, 2)


def test_only_missing_read_types_are_scheduled_and_reordered_batches_share_repeat_key():
    run, receipts = fixture(2)
    args = {
        "line_ids": [line["line_id"] for line in run["snapshot"]["lines"]],
        "include": ["reviewed_product_selection"],
    }
    receipts[1].update(
        arguments=args, result=execute("get_line_research_batch", args, run)
    )
    work = remaining(run, receipts, EvidenceResolver(run, receipts))
    planned = mandatory_plan(work, 4)
    assert len(planned) == 1 and planned[0]["function"]["arguments"]["include"] == [
        "supplier_offers"
    ]
    reversed_args = {
        "line_ids": [value.upper() for value in reversed(args["line_ids"])],
        "include": args["include"],
    }
    assert canonical_arguments("get_line_research_batch", args) == canonical_arguments(
        "get_line_research_batch", reversed_args
    )


def test_byte_aware_partition_never_silently_omits_a_line():
    chunks = list(
        partitions(["a", "b", "c", "d"], 4, dict.fromkeys(["a", "b", "c", "d"], 15000))
    )
    assert chunks == [["a", "b"], ["c", "d"]]


def test_source_keys_stable_and_duplicate_batch_sources_deduplicate():
    run, receipts = fixture(2)
    one = EvidenceResolver(run, receipts)
    two = EvidenceResolver(run, receipts)
    assert one.inventory() == two.inventory()
    duplicate = {**receipts[1], "id": str(uuid4()), "ordinal": 3}
    resolver = EvidenceResolver(run, [*receipts, duplicate])
    result = resolver.resolve(references(resolver))
    assert result["complete"] and len(result["claims"]) == 10


def test_large_result_is_rejected_as_a_whole_without_truncation():
    run, _ = evidence_fixture(line_count=4, offers=3)
    for line in run["snapshot"]["lines"]:
        for offer in line["offers"]["attestations"]:
            offer["reason"] = "r" * 1000
            offer["data"]["commercial"]["source_reference"] = "s" * 1000
    run["metadata"].update(tool_schema=VERSION, batch_size=4)
    with pytest.raises(EvidenceError, match="tool_result_size_limit"):
        execute(
            "get_line_research_batch",
            {"line_ids": [line["line_id"] for line in run["snapshot"]["lines"]]},
            run,
        )


def test_experimental_two_line_limit_is_enforced_before_child_reads(monkeypatch):
    from api.procurement_agent import tools_v3

    run, _ = evidence_fixture(line_count=3)
    run["metadata"].update(tool_schema=VERSION, batch_size=2)
    touched = []
    monkeypatch.setattr(tools_v3.legacy, "execute", lambda *args: touched.append(args))
    with pytest.raises(EvidenceError, match="batch_size_limit"):
        execute(
            "get_line_research_batch",
            {"line_ids": [line["line_id"] for line in run["snapshot"]["lines"]]},
            run,
        )
    assert not touched


@pytest.mark.parametrize("problem", ["citation_groups", "source_size", "tool_budget"])
def test_preflight_rejects_infeasible_reference_and_byte_envelopes(problem):
    run, _ = evidence_fixture(
        line_count=12 if problem == "citation_groups" else 8,
        offers=2 if problem == "citation_groups" else 1,
    )
    if problem != "citation_groups":
        for line in run["snapshot"]["lines"]:
            line["offers"]["attestations"][0]["data"]["commercial"]["notes"] = "x" * (
                40000 if problem == "source_size" else 17000
            )
    check = capacity(run["snapshot"])
    assert not check["supported"] and "capacity_" + problem in check["blockers"]
    assert not check["continuation_available"]
