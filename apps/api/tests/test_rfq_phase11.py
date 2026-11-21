"""Explicit fixture providers test orchestration, never model quality."""

import asyncio
import json
import httpx
from PIL import Image
import pytest
from api.rfq.association import deterministic_v2, verify_v2
from api.rfq.config import settings
from api.rfq.contracts import Proposal
from api.rfq.evaluation.matching_v2 import maximum_assignment, match_items
from api.rfq.evaluation.quality_run import aggregate, score
from api.rfq.extraction import extract
from api.rfq.ocr import original_box, deskew_angle, read_tsv, ocr_page
from api.rfq.parsers import parse_document, cache_identity
from api.rfq.provider import OllamaProvider, ProviderError

TABLE = b"Line,Manufacturer,MPN,Description,Qty,UOM\n1,Northvale,00-X,Laptop alpha,12,EA\n2,Axion,01-X,Server beta,50,EA\n"


class FixtureProvider:
    def __init__(self, proposal=None, error=None):
        self.calls = []
        self.proposal = proposal or {"header": {}, "items": []}
        self.error = error

    async def extract(self, blocks):
        self.calls.append([b.id for b in blocks])
        if self.error:
            raise self.error
        return Proposal.model_validate(self.proposal), {
            "model": "explicit-test-fixture",
            "attempt": 1,
        }


def proposed(**values):
    return {
        name: {"value": value, "block_id": block, "excerpt": excerpt}
        for name, (value, block, excerpt) in values.items()
    }


def test_clean_deterministic_input_never_calls_model():
    doc = parse_document("x.csv", TABLE, "source")
    provider = FixtureProvider(error=AssertionError("Must not infer clean input"))
    result = asyncio.run(extract([doc], "hybrid", provider))
    assert (
        not provider.calls
        and len(result.items) == 2
        and result.metadata["model_call_count"] == 0
    )


def test_partial_table_selects_missing_row_and_header():
    doc = parse_document("x.csv", TABLE.replace(b"50,EA", b",EA"), "source")
    provider = FixtureProvider()
    result = asyncio.run(extract([doc], "hybrid", provider))
    assert provider.calls == [["row:1", "row:3"]]
    assert result.metadata["routing"][0]["tasks"][0]["source"] == "row:3"
    assert len(result.items) == 2 and result.items[0].fields["quantity"].value == "12"


def test_prose_and_failure_are_visible():
    doc = parse_document(
        "x.txt",
        b"Please supply 2 EA of Laptop alpha. Manufacturer Northvale; MPN 00-X.",
        "source",
    )
    provider = FixtureProvider(error=ProviderError("model_timeout", True))
    with pytest.raises(ProviderError, match="model_timeout"):
        asyncio.run(extract([doc], "hybrid", provider))
    assert provider.calls


@pytest.mark.parametrize(
    "name,value,source",
    [
        ("quantity", "50", "row:3"),
        ("manufacturer", "Axion", "row:3"),
        ("mpn", "01-X", "row:3"),
        ("quantity", "00-X", "row:2"),
        ("requested_unit_price", "12", "row:2"),
    ],
)
def test_occurrence_does_not_validate_wrong_row_column_or_type(name, value, source):
    doc = parse_document("x.csv", TABLE, "source")
    payload = proposed(
        description=("Laptop alpha", "row:2", doc.blocks[1].text),
        **{name: (value, source, next(b.text for b in doc.blocks if b.id == source))},
    )
    item = verify_v2(
        doc,
        doc.blocks,
        Proposal.model_validate({"header": {}, "items": [payload]}),
        "fixture",
    ).items[0]
    assert item.fields[name].status != "validated"


def test_wrong_column_price_requires_verification():
    doc = parse_document(
        "x.csv", b"Description,Qty,MPN,UOM,Unit price\nLaptop,12,00-X,EA,99\n", "source"
    )
    proposal = Proposal.model_validate(
        {
            "header": {},
            "items": [
                proposed(
                    description=("Laptop", "row:2", doc.blocks[1].text),
                    quantity=("99", "row:2", doc.blocks[1].text),
                )
            ],
        }
    )
    field = verify_v2(doc, doc.blocks, proposal, "fixture").items[0].fields["quantity"]
    assert (
        field.evidence[0].verified
        and field.evidence[0].column_association == "unverified"
        and field.status == "requires_review"
    )


def test_unsupported_and_cross_document_source_are_not_accepted():
    doc = parse_document("x.csv", TABLE, "source")
    proposal = Proposal.model_validate(
        {
            "header": {},
            "items": [proposed(mpn=("FAKE-X", "other-document:row:2", "FAKE-X"))],
        }
    )
    field = verify_v2(doc, doc.blocks, proposal, "fixture").items[0].fields["mpn"]
    assert field.value is None and field.status == "unverified"


def test_shipping_and_billing_labels_must_match():
    doc = parse_document("x.txt", b"Billing address: 120 Fictional Road", "source")
    proposal = Proposal.model_validate(
        {
            "header": {
                "shipping_address": {
                    "value": "120 Fictional Road",
                    "block_id": "row:1",
                    "excerpt": doc.blocks[0].text,
                }
            },
            "items": [],
        }
    )
    assert (
        verify_v2(doc, doc.blocks, proposal, "fixture")
        .header["shipping_address"]
        .status
        == "requires_review"
    )


def test_source_dedup_and_repeated_products_stay_distinct():
    doc = parse_document("x.csv", TABLE, "source")
    payload = proposed(
        description=("Laptop alpha", "row:2", doc.blocks[1].text),
        quantity=("12", "row:2", doc.blocks[1].text),
        unit=("EA", "row:2", doc.blocks[1].text),
    )
    result = asyncio.run(
        extract(
            [doc], "llm", FixtureProvider({"header": {}, "items": [payload, payload]})
        )
    )
    assert (
        len(result.items) == 1 and result.metadata["merge"]["duplicate_proposals"] == 1
    )
    repeated = deterministic_v2(
        parse_document(
            "x.csv",
            TABLE.replace(b"Server beta", b"Laptop alpha").replace(b"01-X", b"00-X"),
            "source",
        )
    )
    assert len(repeated.items) == 2 and repeated.items[0].id != repeated.items[1].id


def test_reliable_values_retained_on_conflicting_repair():
    from api.rfq.selective import merge

    baseline = deterministic_v2(parse_document("x.csv", TABLE, "source"))
    alternative = baseline.model_copy(deep=True)
    alternative.items = alternative.items[:1]
    alternative.items[0].fields["quantity"].value = "99"
    counts = {
        k: 0
        for k in (
            "repaired_rows",
            "duplicate_proposals",
            "rejected_unsupported_proposals",
            "conflicting_fields",
            "added_model_rows",
        )
    }
    merge(baseline, alternative, counts, [])
    assert (
        baseline.items[0].fields["quantity"].value == "12"
        and baseline.items[0].fields["quantity"].status == "conflicting"
    )


def test_ocr_alternatives_flag_ambiguity_and_keep_characters():
    doc = parse_document("x.csv", TABLE, "source")
    doc.blocks[1].metadata = {
        "cells": [
            {},
            {},
            {"raw": "00-X", "alternatives": ["OO-X"], "confidence": 92},
            {},
            {},
            {},
        ]
    }
    item = deterministic_v2(doc).items[0]
    assert (
        item.fields["mpn"].value == "00-X" and item.fields["mpn"].status == "ambiguous"
    )


def test_geometry_and_dimensions():
    assert original_box([10, 20, 30, 40], (100, 100), 0, 144) == [5, 10, 15, 20]
    box = original_box([10, 20, 30, 40], (100, 100), 3, 300)
    assert box[0] < box[2] and box[1] < box[3]
    assert deskew_angle(Image.new("L", (200, 100), 255)) == 0
    with pytest.raises(Exception, match="invalid dimensions"):
        ocr_page(Image.new("L", (1, 1)), 1, "enhanced-v2", 300)


def test_invalid_tsv_and_cache_identity(monkeypatch):
    with pytest.raises(Exception):
        read_tsv(
            "level\ttext\tleft\ttop\twidth\theight\tconf\n5\tword\t-1\t2\t3\t4\t90\n"
        )
    first = cache_identity("selective-v2", "x.csv")
    monkeypatch.setenv("RFQ_OCR_DPI", "250")
    settings.cache_clear()
    assert first != cache_identity("selective-v2", "x.csv")
    assert cache_identity("phase1", "x.csv") == "ownerpilot-parser/1.0"
    settings.cache_clear()


def test_assignment_is_global_and_ignores_mpn_and_quantity():
    assert set(maximum_assignment([[9, 8, 0, 0], [8, 0, 0, 0]])) == {(0, 1), (1, 0)}
    doc = parse_document("x.csv", TABLE, "source")
    items = deterministic_v2(doc).items
    truth = [
        {
            "line_number": "1",
            "mpn": "00-X",
            "description": "Laptop alpha",
            "quantity": "12",
        },
        {
            "line_number": "2",
            "mpn": "01-X",
            "description": "Server beta",
            "quantity": "50",
        },
    ]
    items[0].fields["quantity"].value = "50"
    items[1].fields["quantity"].value = "12"
    assert [p["prediction"] for p in match_items(truth, items)] == [0, 1]
    result = deterministic_v2(doc)
    result.items = items
    assert score({"items": truth}, result)["quantity_correct"] == 0
    assert len(match_items(truth, items + [items[0]])) == 2
    assert len(match_items(truth, [])) == 0


def test_missing_metric_denominators_are_null():
    assert (
        aggregate([])["mpn_accuracy"] is None
        and aggregate([])["latency_ms"]["median"] is None
    )


@pytest.mark.parametrize(
    "behavior", ["valid", "wrong_model", "extra", "incomplete", "unavailable"]
)
def test_compact_provider_validation(behavior, monkeypatch):
    monkeypatch.setenv("RFQ_OLLAMA_MODEL", "fixture")
    monkeypatch.setenv("RFQ_MODEL_RETRIES", "0")
    settings.cache_clear()

    def respond(request):
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": []
                    if behavior == "unavailable"
                    else [{"name": "fixture", "digest": "test"}]
                },
            )
        payload = {"header": [], "items": []}
        if behavior == "extra":
            payload["command"] = "execute"
        return httpx.Response(
            200,
            json={
                "model": "different" if behavior == "wrong_model" else "fixture",
                "done": behavior != "incomplete",
                "message": {"content": json.dumps(payload)},
            },
        )

    provider = OllamaProvider(transport=httpx.MockTransport(respond), compact=True)
    if behavior == "valid":
        assert not asyncio.run(provider.extract([]))[0].items
    else:
        with pytest.raises(ProviderError):
            asyncio.run(provider.extract([]))
    settings.cache_clear()


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://localhost@evil.invalid",
        "http://127.0.0.1.evil.invalid",
        "file:///tmp/model",
    ],
)
def test_local_provider_allowlist(url, monkeypatch):
    monkeypatch.setenv("RFQ_OLLAMA_URL", url)
    settings.cache_clear()
    with pytest.raises(ProviderError):
        OllamaProvider(compact=True)
    settings.cache_clear()
