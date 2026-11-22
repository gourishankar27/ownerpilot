# Deterministic quote calculations

Version `quote-decimal/1`. Backend Decimal arithmetic only; monetary request fields are bounded decimal strings, never binary floats. NaN/infinity, negative inputs, excessive scale/magnitude and invalid policies are rejected. Price zero is valid only when explicitly attested; missing price is null and never converted to free.

Individual rounded amounts and totals are capped at 10^18 currency units; unsupported precision/range raises a validation error before Decimal quantization can overflow. This is an explicit local workflow limit, not an inferred commercial amount.

Supported currencies: USD/EUR/GBP/INR (two minor digits), JPY (zero). One quote has one currency. Other-currency offers block aggregation; no FX rate is inferred. Requested units must explicitly be each/EA/unit/PC/PCS; other conversions require review and remain blocked.

1. `purchase_packs = ceil(max(requested_units, minimum_units) / units_per_pack)`.
2. `purchased_units = purchase_packs * units_per_pack`. Validate stock against purchased units when attested.
3. Choose the highest applicable, unambiguous quantity-break threshold using purchased units. Price basis is explicit: multiply each price by purchased units, or pack price by purchase packs.
4. Round purchase cost to currency minor units. A surplus requires an explicit policy: allocate full purchase cost to requested units, or bill purchased units. No surplus policy is needed when requested and purchased quantities are equal.
5. Divide purchase cost by billable quantity. Markup: `cost_basis * (1 + rate)`; gross margin: `cost_basis / (1 - rate)` with margin < 1. Rates are fractions, e.g. 0.20. Markup is bounded at 10; discount/tax at 1.
6. Round selling unit price using ROUND_HALF_UP; multiply by billable quantity and round gross line amount. Round the explicit discount amount and subtract it.
7. Sum discounted lines. Add explicitly reviewed shipping; calculate/round explicit tax on discounted subtotal or subtotal + shipping, as declared. Round grand total.

This is unit-then-line-then-tax rounding. Example: a $0.01 purchase cost with 20% markup rounds to $0.01 per selling unit; one million units total $10,000. The API records the full rounding policy and calculation version so this behavior is visible, not silently replaced by round-once arithmetic.

For two units at $10, 20% markup gives $24; 20% gross margin gives $25. With $5 shipping and 10% tax including shipping, the markup quote totals $31.90. Six-unit packs at $10 per individual unit cost $60 even when only two units were requested; the declared surplus policy determines billing/allocation. A $10 pack price instead costs $10 per pack.

Unresolved shipping, tax basis/rate, quote validity, reviewed selection, compatible product, quantity/unit, current price/availability, purchasing units or surplus policy block a complete grand total. Quote validity cannot outlive selected offer validity. Freshness is recomputed at calculation/submission/approval time; static saved amounts cannot override expired sources.

Validation uses 34 frozen standalone cases plus 20 frozen ten-line batches. The 200 line amounts match the authored expectations. One batch total has an independently diagnosed JPY tax oracle error: frozen 929 vs correct 845 + ROUND_HALF_UP(84.5) = 930. The label is retained as a strict expected failure and separately audited. See `results/known-oracle-defect.json`; do not describe all frozen total labels as passing.
