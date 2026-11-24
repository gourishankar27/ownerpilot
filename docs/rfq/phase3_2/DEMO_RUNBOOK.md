# Coverage-aware research demo

Open `http://localhost:3042/procurement` using an authorized local account. Select the Phase 3.2 independent batch research workspace. The frozen synthetic sources are fictional and have explicit approved RFQ/product/offer decisions.

1. Search `Independent synthetic study v3-dev-01` for one line, `v3-dev-02` for two, `v3-dev-03` for four, `v3-dev-04` for eight and `v3-dev-05` for twelve. Select an actual completed `procurement-native/7` hybrid history row. The raw run IDs are recorded in `results/evaluation/dev-plan7-v2`.
2. Expand **Source inspection and citation verification**. Read actual source-covered/remaining lines and the global approved RFQ inspection state. Open a line to compare selection/offers inspection with required citation verification.
3. Read native model-selected and backend-scheduled RPC counts. A batch inspecting four lines is one decision. Open **Recorded research activity** to see persisted requests, receipt commits, coverage changes, citation finalization/materialization and publication; the timeline contains events, not hidden chain-of-thought.
4. Open a batch receipt and a verified observation. Its receipt ID is the parent ledger row, and its pointer includes the physical line index. Inspect selection/product/offer/catalog/revision/fingerprint associations. Values come from the backend verifier, not model prose.
5. Compare a missing-price/no-match case: research may be complete while quote inputs need human follow-up. Quote approval still requires the existing human workflow and deterministic preview.
6. Review an incomplete history row. Missing source reads and preserved receipts stay visible; an early planning summary cannot show published completion. For a scope above twelve lines, capacity attention explicitly states that automatic continuation is unavailable and calls for a separately reviewed scoped RFQ.

New Playwright coverage uses real measured one-, two- and twelve-line histories. Partial, recovery and capacity display variants are explicitly labelled UI fixtures. Six screenshots and test evidence are under this phase's folders. Fixture screenshots do not prove model completion or actual worker recovery; use the separate actual recovery JSON for that claim.

To rerun validation, set `RFQ_TEST_DATABASE_URL` to the isolated test database, run the backend suite and use `scripts/procurement32-browser.py` against the dedicated services. The wrapper preserves historical screenshots while archiving newly rendered regression images. No supplier communication, approval, deployment or Phase 4 operation is part of this demo.
