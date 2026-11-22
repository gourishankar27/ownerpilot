"""Independently specified integer-minor-unit oracle for 200 synthetic quote lines.

No production calculator import. Exact prices are multiples of four, so the authored
25% markup/20% margin and 10% discounts/taxes have exact minor-unit arithmetic.
This corpus expands financial coverage, not the number of real-model agent runs.
"""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data/evaluation/procurement-v1"
target = DEST / "quote-batches.json"
if target.exists():
    raise SystemExit("Refusing to overwrite frozen batch cases")
cases = []
for batch in range(20):
    currency = ["USD", "EUR", "GBP", "INR", "JPY"][batch % 5]
    scale = 1 if currency == "JPY" else 100
    discounted = batch % 2 == 1
    taxed = batch % 3 == 0
    shipping = 5 if batch % 4 == 0 else 0
    total_minor = 0
    lines = []
    amounts = []
    for index in range(10):
        price = 4 * (1 + (index + batch) % 5)
        quantity = 1 + (index * 3 + batch) % 11
        sell = price * 5 // 4
        amount = sell * quantity * scale
        if discounted:
            amount = amount * 9 // 10
        total_minor += amount
        amounts.append(
            str(amount) if scale == 1 else f"{amount // 100}.{amount % 100:02d}"
        )
        lines.append(
            {
                "line_id": f"batch-{batch:02d}-line-{index:02d}",
                "quantity": str(quantity),
                "offer_id": f"fictional-offer-{batch}-{index}",
                "offer": {
                    "supplier": f"Fictional supplier {index % 3}",
                    "supplier_sku": f"SYN-{batch}-{index}",
                    "price": str(price),
                    "currency": currency,
                    "price_basis": "each",
                    "pack_size": 1,
                    "minimum_units": "1",
                    "availability": "available",
                    "observed_on": "2026-11-20",
                    "valid_until": "2026-12-20",
                    "source_reference": f"Fictional {['memory', 'storage', 'network', 'display', 'accessory'][index % 5]} quote evidence B{batch}L{index}",
                },
            }
        )
    shipping_minor = shipping * scale
    tax_minor = (total_minor + shipping_minor) // 10 if taxed else 0
    grand = total_minor + shipping_minor + tax_minor
    total = str(grand) if scale == 1 else f"{grand // 100}.{grand % 100:02d}"
    cases.append(
        {
            "id": f"batch-{batch:02d}",
            "split": "development"
            if batch < 4
            else "validation"
            if batch < 8
            else "held_out",
            "lines": lines,
            "policy": {
                "currency": currency,
                "shipping": str(shipping),
                "tax_rate": "0.1" if taxed else "0",
                "tax_basis": "subtotal_plus_shipping",
                "valid_until": "2026-12-01",
                "pricing": {
                    "mode": "markup" if batch % 2 == 0 else "margin",
                    "rate": "0.25" if batch % 2 == 0 else "0.2",
                    "discount": "0.1" if discounted else "0",
                    "surplus": "allocate_purchase_cost",
                },
            },
            "expected_line_amounts": amounts,
            "expected_grand_total": total,
        }
    )
raw = (
    json.dumps(
        {
            "version": "quote-batches/1",
            "license": "CC0 synthetic fictional",
            "cases": cases,
            "oracle": "Independently authored integer minor-unit arithmetic; production implementation not imported",
            "limitations": "20 templated multi-line scenarios; correlated arithmetic families, not 200 independent real-world procurement tasks",
        },
        indent=2,
    )
    + "\n"
).encode()
target.write_bytes(raw)
(DEST / "quote-batches-manifest.json").write_text(
    json.dumps(
        {
            "files": {"quote-batches.json": hashlib.sha256(raw).hexdigest()},
            "scenarios": 20,
            "quote_lines": 200,
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
print("Frozen 20 batch scenarios / 200 financial lines")
