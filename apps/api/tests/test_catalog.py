import io
import json
import math

import httpx
import openpyxl
import pytest

from api.catalog.core import (
    BM25,
    Product,
    comparison,
    manufacturer,
    group_products,
    identity,
    compatibility,
    fuse,
    parse_catalog,
    tokens,
)
from api.catalog.embedding import Embeddings

PRODUCT = dict(
    source_id="s1",
    manufacturer="Northvale",
    mpn="00-XY/O1",
    name="Synthetic memory",
    category="memory",
    specs={"capacity": 32, "connector": "DDR5"},
)


def product(**values):
    return Product.model_validate({**PRODUCT, **values}).model_dump(mode="json")


@pytest.mark.parametrize(
    "raw,wanted", [("001-O1", "001-O1"), (" A–B ", "A-B"), ("a_B/01", "a_B/01")]
)
def test_conservative_identifiers(raw, wanted):
    assert comparison(raw) == wanted


def test_alias_is_explicit_and_not_fuzzy():
    assert manufacturer("Northvale Systems") == manufacturer("Northvale")
    assert manufacturer("Northval") != manufacturer("Northvale")


@pytest.mark.parametrize(
    "changed",
    [
        {"mpn": "00-XY/01"},
        {"mpn": "00-XY/O10"},
        {"manufacturer": "Other"},
        {"specs": {"capacity": 64}},
    ],
)
def test_variants_not_conflated(changed):
    assert identity(product()) != identity(product(**changed))


def test_supplier_offers_group_without_loss():
    rows = [
        product(),
        product(source_id="s2", supplier="Other", manufacturer="Northvale Systems"),
    ]
    grouped = group_products(rows)
    assert len(grouped) == 1 and len(grouped[0]["offers"]) == 2


def test_bm25_matches_published_equation():
    scores = BM25(["memory memory", "storage"]).scores("memory")
    expected = (
        math.log(1 + (2 - 1 + 0.5) / (1 + 0.5))
        * 2
        * 2.5
        / (2 + 1.5 * (0.25 + 0.75 * 2 / 1.5))
    )
    assert scores[0] == pytest.approx(expected) and scores[1] == 0


def test_technical_tokenization():
    assert "ssd-001/o1" in tokens("SSD-001/O1 32GB DDR5")
    assert "32gb" in tokens("SSD-001/O1 32GB DDR5")


@pytest.mark.parametrize(
    "specs,status",
    [
        ({"capacity": 32}, "compatible_alternative"),
        ({"capacity": 64}, "incompatible"),
        ({"voltage": 12}, "insufficient_information"),
    ],
)
def test_compatibility_never_infers_missing_fact(specs, status):
    assert (
        compatibility({"category": "memory", "specs": specs}, product())["status"]
        == status
    )


def test_exact_with_conflicting_requirement_is_incompatible():
    assert (
        compatibility(
            {"manufacturer": "Northvale", "mpn": "00-XY/O1", "specs": {"capacity": 64}},
            product(),
        )["status"]
        == "incompatible"
    )


@pytest.mark.parametrize("mpn", ["00-XY/O1", "DIFFERENT"])
def test_requested_manufacturer_is_a_hard_requirement(mpn):
    result = compatibility(
        {
            "manufacturer": "Other",
            "mpn": mpn,
            "category": "memory",
            "specs": {"capacity": 32},
        },
        product(),
    )
    assert result["status"] == "incompatible"
    assert any(c["attribute"] == "manufacturer" for c in result["conflicts"])


def test_exact_protected_during_fusion_and_ties_stable():
    result = fuse({"exact": [("x", 1)], "bm25": [("a", 100)], "vector": [("a", 0.99)]})
    assert result[0]["id"] == "x" and len(result) == 2


@pytest.mark.parametrize(
    "name,content",
    [
        ("x.exe", b"hi"),
        ("x.json", b"{}"),
        ("x.csv", b"manufacturer,brand\na,b\n"),
        ("x.json", json.dumps([PRODUCT, PRODUCT]).encode()),
    ],
)
def test_import_rejects_invalid_sources(name, content):
    with pytest.raises(ValueError):
        parse_catalog(name, content)


@pytest.mark.parametrize(
    "fields",
    [
        {"price": "-2"},
        {"price": "NaN"},
        {"specs": {"capacity": -1}},
        {"mpn": ""},
        {"specs": {"x": float("inf")}},
    ],
)
def test_bad_product_values(fields):
    with pytest.raises(ValueError):
        product(**fields)


def test_parse_all_formats_preserves_identifiers():
    rows, _ = parse_catalog("safe.json", json.dumps([PRODUCT]).encode())
    assert rows[0]["mpn"] == PRODUCT["mpn"]
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["source_id", "manufacturer", "mpn", "name", "category"])
    sheet.append(["s1", "Northvale", "001-XY", "Device", "memory"])
    stream = io.BytesIO()
    book.save(stream)
    assert parse_catalog("safe.xlsx", stream.getvalue())[0][0]["mpn"] == "001-XY"


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://localhost@evil.test",
        "http://localhost:11434/path",
    ],
)
def test_embedding_ssrf_rejected(monkeypatch, url):
    monkeypatch.setenv("CATALOG_EMBED_URL", url)
    with pytest.raises(ValueError):
        Embeddings()


@pytest.mark.parametrize("kind", ["dimension", "nan", "model", "zero", "count"])
def test_explicit_embedding_response_fixtures(kind):
    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"name": "nomic-embed-text:v1.5", "digest": "fixture-digest"}
                    ]
                },
            )
        vector = [1.0] * 768
        if kind == "dimension":
            vector = [1.0]
        if kind == "nan":
            vector[0] = "NaN"
        if kind == "zero":
            vector = [0.0] * 768
        return httpx.Response(
            200,
            json={
                "model": "wrong" if kind == "model" else "nomic-embed-text:v1.5",
                "embeddings": [] if kind == "count" else [vector],
            },
        )

    with pytest.raises(ValueError):
        Embeddings(httpx.MockTransport(handler)).encode(["Synthetic fixture"])
