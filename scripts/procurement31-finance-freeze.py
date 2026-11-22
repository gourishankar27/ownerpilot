"""Corrected versioned financial expectations using exact rational arithmetic, not production code."""

import hashlib
import json
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data/evaluation/procurement-finance-v2"


def round_money(value, scale):
    scaled = value * scale
    units = (scaled.numerator * 2 + scaled.denominator) // (2 * scaled.denominator)
    return F(units, scale)


def display(value, scale):
    units = int(value * scale)
    return str(units) if scale == 1 else f"{units // scale}.{units % scale:02d}"


def oracle(lines, policy):
    scale = 1 if policy["currency"] == "JPY" else 100
    subtotal = F(0)
    output = []
    for line in lines:
        offer = line["offer"]
        quantity = F(line["quantity"])
        pack = F(offer["pack_size"])
        minimum = F(offer["minimum_units"])
        ratio = max(quantity, minimum) / pack
        packs = (ratio.numerator + ratio.denominator - 1) // ratio.denominator
        purchased = packs * pack
        price = F(offer["price"])
        tiers = [
            (F(tier["minimum_units"]), F(tier["price"]))
            for tier in offer.get("breaks", [])
            if F(tier["minimum_units"]) <= purchased
        ]
        if tiers:
            price = max(tiers)[1]
        cost = round_money(
            price * (packs if offer["price_basis"] == "pack" else purchased), scale
        )
        billed = (
            purchased if policy["pricing"]["surplus"] == "bill_purchased" else quantity
        )
        rate = F(policy["pricing"]["rate"])
        basis = cost / billed
        unit = round_money(
            basis / (1 - rate)
            if policy["pricing"]["mode"] == "margin"
            else basis * (1 + rate),
            scale,
        )
        gross = round_money(unit * billed, scale)
        discount = round_money(gross * F(policy["pricing"]["discount"]), scale)
        amount = gross - discount
        subtotal += amount
        output.append(
            {
                "amount": display(amount, scale),
                "purchase_cost": display(cost, scale),
                "selling_unit_price": display(unit, scale),
            }
        )
    shipping = round_money(F(policy["shipping"]), scale)
    tax = round_money(
        (
            subtotal + shipping
            if policy["tax_basis"] == "subtotal_plus_shipping"
            else subtotal
        )
        * F(policy["tax_rate"]),
        scale,
    )
    return {
        "lines": output,
        "subtotal": display(subtotal, scale),
        "shipping": display(shipping, scale),
        "tax": display(tax, scale),
        "grand_total": display(subtotal + shipping + tax, scale),
    }


old_path = ROOT / "data/evaluation/procurement-v1/quote-batches.json"
old_bytes = old_path.read_bytes()
old = json.loads(old_bytes)
cases = []
for original in old["cases"]:
    item = deepcopy(original)
    item["origin_id"] = item["id"]
    item["id"] = "v2-" + item["id"]
    item["expected"] = oracle(item["lines"], item["policy"])
    cases.append(item)
base_offer = {
    "supplier": "Fictional rounding lab",
    "price": "10",
    "currency": "USD",
    "price_basis": "each",
    "pack_size": 1,
    "minimum_units": "1",
    "availability": "available",
    "observed_on": "2026-11-21",
    "valid_until": "2026-12-31",
    "source_reference": "Manually audited fictional financial example",
}
base_policy = {
    "currency": "USD",
    "shipping": "0",
    "tax_rate": "0",
    "tax_basis": "subtotal",
    "valid_until": "2026-12-01",
    "pricing": {
        "mode": "markup",
        "rate": "0",
        "discount": "0",
        "surplus": "allocate_purchase_cost",
    },
}
manual = [
    ("half_cent_unit", "3", {"price": "0.005"}, {}, {}, "0.03"),
    (
        "jpy_half_discount",
        "1",
        {"price": "5", "currency": "JPY"},
        {"currency": "JPY"},
        {"discount": "0.1"},
        "4",
    ),
    (
        "tax_shipping_fraction",
        "3",
        {"price": "19.99"},
        {
            "shipping": "4.95",
            "tax_rate": "0.0825",
            "tax_basis": "subtotal_plus_shipping",
        },
        {"rate": "0.2"},
        "83.27",
    ),
    ("markup_twenty", "2", {}, {}, {"rate": "0.2"}, "24.00"),
    ("margin_twenty", "2", {}, {}, {"mode": "margin", "rate": "0.2"}, "25.00"),
    (
        "pack_unit_then_line",
        "7",
        {"price": "24", "price_basis": "pack", "pack_size": 6},
        {},
        {},
        "48.02",
    ),
    ("moq_unit_then_line", "3", {"price": "2", "minimum_units": "10"}, {}, {}, "20.01"),
    (
        "quantity_break_half_unit",
        "12",
        {
            "price": "10",
            "pack_size": 6,
            "breaks": [{"minimum_units": "10", "price": "7.25"}],
        },
        {},
        {"rate": "0.1"},
        "95.76",
    ),
    ("explicit_zero", "2", {"price": "0"}, {}, {}, "0.00"),
]
for name, quantity, offer_changes, policy_changes, pricing_changes, expected in manual:
    offer = {**base_offer, **offer_changes}
    policy = deepcopy(base_policy)
    policy.update(policy_changes)
    policy["pricing"].update(pricing_changes)
    lines = [{"line_id": name, "quantity": quantity, "offer": offer}]
    result = oracle(lines, policy)
    assert result["grand_total"] == expected, (
        "Independent rational oracle disagrees with manual arithmetic",
        name,
        result,
    )
    cases.append(
        {
            "id": name,
            "split": "manual_audit",
            "lines": lines,
            "policy": policy,
            "expected": result,
            "manual_expected_total": expected,
        }
    )
standalone = json.loads(
    (ROOT / "data/evaluation/procurement-v1/scenarios.json").read_text()
)["finance"]
record = {
    "version": "procurement-finance-v2",
    "oracle": "exact-rational-minor-units/2",
    "as_of": "2026-11-22",
    "license": "CC0 fictional",
    "cases": cases,
    "standalone_manual_cases": standalone,
    "historical_source_sha256": hashlib.sha256(old_bytes).hexdigest(),
    "errata": [
        {
            "old_case": "batch-09",
            "old_expected": "929",
            "new_case": "v2-batch-09",
            "correct_expected": "930",
            "proof": "JPY subtotal 845; tax 84.5 rounded HALF_UP to 85; total 930",
            "old_file_unchanged": True,
        }
    ],
}
DEST.mkdir(parents=True, exist_ok=True)
target = DEST / "cases.json"
if target.exists():
    raise SystemExit("Refusing to overwrite corrected frozen finance v2")
raw = (json.dumps(record, indent=2) + "\n").encode()
target.write_bytes(raw)
(DEST / "manifest.json").write_text(
    json.dumps(
        {
            "version": "procurement-finance-v2",
            "files": {"cases.json": hashlib.sha256(raw).hexdigest()},
            "rational_scenarios": len(cases),
            "manual_standalone_scenarios": len(standalone),
            "historical_v1_sha256": hashlib.sha256(old_bytes).hexdigest(),
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
print(
    f"Frozen {len(cases)} rational scenarios and {len(standalone)} standalone manual cases; original v1 unchanged"
)
