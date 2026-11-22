import hashlib
import json
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from api.procurement_agent.finance import Commercial, QuotePolicy, calculate, number
from api.procurement_agent.tools import execute, verify, definitions

ROOT = Path(__file__).resolve().parents[3]
CASES = json.loads(
    (ROOT / "data/evaluation/procurement-v1/scenarios.json").read_text()
)["finance"]
BATCHES = json.loads(
    (ROOT / "data/evaluation/procurement-v1/quote-batches.json").read_text()
)["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_frozen_independent_finance(case):
    lines = [
        {
            "line_id": "synthetic",
            "quantity": case["quantity"],
            "offer_id": "synthetic",
            "offer": case["offer"],
        }
    ]
    if case["expected_error"]:
        with pytest.raises(ValueError):
            calculate(
                lines, QuotePolicy.model_validate(case["policy"]), date(2026, 11, 21)
            )
        return
    result = calculate(
        lines, QuotePolicy.model_validate(case["policy"]), date(2026, 11, 21)
    )
    assert result["grand_total"] == case["expected_total"]
    assert result["complete"] == (case["expected_total"] is not None)
    if case["expected_issue"]:
        assert any(case["expected_issue"] in issue for issue in result["issues"])


def test_frozen_manifest():
    folder = ROOT / "data/evaluation/procurement-v1"
    manifest = json.loads((folder / "manifest.json").read_text())
    for path, expected in manifest["files"].items():
        assert hashlib.sha256((folder / path).read_bytes()).hexdigest() == expected


@pytest.mark.parametrize(
    "raw", [True, 1, 1.2, "NaN", "Infinity", "-1", "1e200", "0.0000000000001"]
)
def test_decimal_boundary(raw):
    with pytest.raises(ValueError):
        number(raw)


@pytest.mark.parametrize(
    "name", ["run_shell", "sql", "fetch_url", "send_email", "approve_quote"]
)
def test_tools_cannot_execute_outbound_or_arbitrary_actions(name):
    with pytest.raises(ValueError, match="allowlisted"):
        execute(name, {}, {"snapshot": {}})


def test_all_tool_schemas_closed_and_workspace_is_trusted():
    for definition in definitions():
        assert definition["function"]["parameters"]["additionalProperties"] is False
    with pytest.raises(ValidationError):
        execute("get_approved_rfq", {"workspace_id": str(uuid4())}, {"snapshot": {}})
    with pytest.raises(ValueError, match="outside authorized"):
        execute(
            "get_supplier_offers",
            {"line_id": str(uuid4())},
            {"snapshot": {"lines": []}},
        )


@pytest.mark.parametrize(
    "value,pointer,valid",
    [
        ("10", "/data/price", True),
        ("0", "/data/price", False),
        (10, "/data/price", False),
        ("10", "/data/absent", False),
    ],
)
def test_claim_verification_exact_scalar_not_plausible_prose(value, pointer, valid):
    receipt = str(uuid4())
    summary = json.dumps(
        {"claims": [{"receipt_id": receipt, "pointer": pointer, "value": value}]}
    )
    evidence = [{"id": receipt, "status": "succeeded", "result": {"price": "10"}}]
    if valid:
        assert len(verify(summary, evidence)["claims"]) == 1
    else:
        with pytest.raises(ValueError):
            verify(summary, evidence)


def test_missing_offer_never_becomes_free():
    result = calculate(
        [{"line_id": "x", "quantity": "1", "offer": None}],
        QuotePolicy.model_validate(CASES[0]["policy"]),
        date(2026, 11, 21),
    )
    assert result["grand_total"] is None and result["lines"][0]["amount"] is None


def test_attestation_schema_never_accepts_float_price():
    with pytest.raises(ValidationError):
        Commercial.model_validate({**CASES[0]["offer"], "price": 1.23})


def test_multiple_lines_independent_total_and_repeated_calculation():
    lines = [
        {"line_id": "a", "quantity": "2", "offer": CASES[0]["offer"]},
        {
            "line_id": "b",
            "quantity": "3",
            "offer": {**CASES[0]["offer"], "price": "7.5"},
        },
    ]
    policy = QuotePolicy.model_validate(CASES[0]["policy"])
    result = calculate(lines, policy, date(2026, 11, 21))
    assert result["grand_total"] == "51.00" and [
        row["amount"] for row in result["lines"]
    ] == ["24.00", "27.00"]
    assert calculate(lines, policy, date(2026, 11, 21)) == result


def test_large_supported_quantity_exact_decimal_total():
    line = {
        "line_id": "a",
        "quantity": "1000000",
        "offer": {**CASES[0]["offer"], "price": "0.01"},
    }
    result = calculate(
        [line], QuotePolicy.model_validate(CASES[0]["policy"]), date(2026, 11, 21)
    )
    # Unit rounding is explicit: .01 * 1.2 -> .01, then 1,000,000 units.
    assert result["grand_total"] == "10000.00"


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            case,
            marks=pytest.mark.xfail(
                strict=True,
                reason="Preserved batch-09 frozen oracle defect: JPY tax was floored; 845 + ROUND_HALF_UP(84.5) = 930, not 929",
            ),
        )
        if case["id"] == "batch-09"
        else case
        for case in BATCHES
    ],
    ids=lambda case: case["id"],
)
def test_two_hundred_frozen_batch_lines(case):
    result = calculate(
        case["lines"], QuotePolicy.model_validate(case["policy"]), date(2026, 11, 21)
    )
    assert result["complete"] is True
    assert [row["amount"] for row in result["lines"]] == case["expected_line_amounts"]
    assert result["grand_total"] == case["expected_grand_total"]


def test_independent_manual_audit_of_jpy_tax_fixture_defect():
    case = next(case for case in BATCHES if case["id"] == "batch-09")
    assert sum(int(value) for value in case["expected_line_amounts"]) == 845
    result = calculate(
        case["lines"], QuotePolicy.model_validate(case["policy"]), date(2026, 11, 21)
    )
    assert (
        result["subtotal"] == "845"
        and result["tax"] == "85"
        and result["grand_total"] == "930"
    )
    assert (
        case["expected_grand_total"] == "929"
    )  # Retain original label and report its defect.


def test_stock_quantity_limits_purchase_not_only_requested_units():
    line = {
        "line_id": "a",
        "quantity": "2",
        "offer": {**CASES[0]["offer"], "pack_size": 6, "stock_units": "4"},
    }
    result = calculate(
        [line], QuotePolicy.model_validate(CASES[0]["policy"]), date(2026, 11, 21)
    )
    assert result["grand_total"] is None
    assert (
        "attested_stock_insufficient_for_purchase_quantity"
        in result["lines"][0]["issues"]
    )


def test_extreme_legal_inputs_raise_validation_error_before_decimal_overflow():
    line = {
        "line_id": "bounded",
        "quantity": "0.000000000001",
        "offer": {**CASES[0]["offer"], "price": "1000000000000", "pack_size": 1000000},
    }
    policy = {
        **CASES[0]["policy"],
        "pricing": {
            **CASES[0]["policy"]["pricing"],
            "mode": "margin",
            "rate": "0.999999999999",
        },
    }
    with pytest.raises(ValueError, match="supported quote range"):
        calculate([line], QuotePolicy.model_validate(policy), date(2026, 11, 21))
