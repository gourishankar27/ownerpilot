# Coverage planner

Every approved line requires `get_reviewed_product_selection` and `get_supplier_offers`, including explicit no-match and absent offers. A successful `get_approved_rfq` is also required globally. Snapshot availability alone does not count as an executed source read.

`remaining()` rebuilds inspection flags from an EvidenceResolver constructed over actual receipts. It reports each line's missing tool types, successful receipt IDs, unsuccessful attempts and pending calls, plus remaining tool/planning budgets and preflight capacity. Citation coverage is calculated separately by the resolver after model reference selection.

After the first development experiment, the prompt feedback was corrected to name the missing global RFQ read explicitly, withhold actionable line IDs until that read succeeds and omit already-inspected lines from remaining work. The original experiment and its exact source files are retained under `results/evaluation/dev-plan7-v1`. This was development feedback; no held-out results were used.

`mandatory_plan()` groups only missing read types and partitions within the configured line and byte limits. A line missing only offers does not cause a repeat selection read. Successful duplicates are allowed within the repeat cap but receive no additional coverage credit. Failed or rejected calls remain visible and cannot supply citable fields; subsequent valid reads may close the missing work under verifier version 3.

Global RFQ inspection and both line reads are necessary before citation finalization is admitted. Prose asserting completion during planning is ignored and recorded. Exhausted planning/tool budgets produce explicit attention with the actual ledger retained.
