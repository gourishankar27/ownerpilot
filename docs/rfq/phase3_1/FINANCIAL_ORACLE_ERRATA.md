# Additive financial oracle correction

The frozen v1 batch `batch-09` expected JPY 929. Its generator floored a tax result. The independently audited result is JPY 845 subtotal plus JPY 85 rounded tax, totaling **JPY 930**. The production Decimal engine was already correct. No production financial calculation was changed.

`data/evaluation/procurement-finance-v2` is a new version with its own manifest, generator and source-v1 hash. The corrected case is `v2-batch-09`. The old dataset, historical reports and strict expected-failure test remain untouched.

`scripts/procurement31-finance-freeze.py` uses exact `Fraction` arithmetic and integer minor-unit half-up rounding; it imports no production financial engine. It preserves the established order of unit/line, discount, shipping and tax rounding. Twenty corrected batch scenarios and nine manually audited boundary scenarios are independently calculated; 34 standalone cases are retained separately. Tests compare production outcomes with the frozen independent expectations, including pack/MOQ, unit-to-line rounding, JPY half-unit boundaries and USD tax/shipping.

The new finance suite passes **64 tests**: 29 rationally generated cases, 34 standalone cases and one manifest/historical-hash integrity check. The original known strict expected failure remains in the complete regression suite. Historical 19/20 batch-label agreement remains a historical observation, not a newly corrected old score.
