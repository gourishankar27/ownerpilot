import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from api.procurement_agent.finance import calculate, QuotePolicy

ROOT = Path(__file__).resolve().parents[3]
DATA = json.loads(
    (ROOT / "data/evaluation/procurement-finance-v2/cases.json").read_text()
)


@pytest.mark.parametrize("case", DATA["cases"], ids=lambda case: case["id"])
def test_corrected_independent_rational_finance(case):
    result = calculate(
        case["lines"], QuotePolicy.model_validate(case["policy"]), date(2026, 11, 22)
    )
    assert result["complete"]
    for field in ["subtotal", "shipping", "tax", "grand_total"]:
        assert result[field] == case["expected"][field]
    for actual, expected in zip(result["lines"], case["expected"]["lines"]):
        for field in ["amount", "purchase_cost", "selling_unit_price"]:
            assert actual[field] == expected[field]


@pytest.mark.parametrize(
    "case", DATA["standalone_manual_cases"], ids=lambda case: case["id"]
)
def test_independently_authored_standalone_commercial_policies_v2(case):
    lines = [
        {"line_id": case["id"], "quantity": case["quantity"], "offer": case["offer"]}
    ]
    if case["expected_error"]:
        with pytest.raises(ValueError):
            calculate(
                lines, QuotePolicy.model_validate(case["policy"]), date(2026, 11, 22)
            )
    else:
        result = calculate(
            lines, QuotePolicy.model_validate(case["policy"]), date(2026, 11, 22)
        )
        assert result["grand_total"] == case["expected_total"]


def test_v1_jpy_label_and_all_new_dataset_hashes_preserved():
    original = ROOT / "data/evaluation/procurement-v1/quote-batches.json"
    assert (
        hashlib.sha256(original.read_bytes()).hexdigest()
        == DATA["historical_source_sha256"]
    )
    old = next(
        case
        for case in json.loads(original.read_text())["cases"]
        if case["id"] == "batch-09"
    )
    new = next(case for case in DATA["cases"] if case["id"] == "v2-batch-09")
    assert (
        old["expected_grand_total"] == "929" and new["expected"]["grand_total"] == "930"
    )
    for directory, manifest_name in [
        ("procurement-finance-v2", "manifest.json"),
        ("procurement-v2", "manifest.json"),
    ]:
        folder = ROOT / "data/evaluation" / directory
        for name, expected in json.loads((folder / manifest_name).read_text())[
            "files"
        ].items():
            assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == expected
