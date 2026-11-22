# Demonstration

Use http://localhost:3022/procurement with API8022/Redis6382/Linux catalog worker and disposable PG55433. Create fictional workspace/RFQ, upload CSV, process, correct identifiers, review lines and approve.

Catalog Intelligence:create source/license; upload JSON/CSV/XLSX; inspect mapping/sample/counts; confirm; wait queued→building→published. Inspect model/digest metadata and indexed records. Select approved line and published scope; Find matching products. Compare factual specs/conflicts/missing values/offers and independent channel evidence. Add note; select exact product, reject candidate or record no valid match. One decision per actor/run; run another search for another decision. Reload RFQ/line/history to verify persistence.

Superseded history remains explainable but cannot be newly selected as current. Actual screenshot:results/screenshots/catalog-match.png. Original6 browser cases are preserved; new real catalog case exercises neural indexing and review. No Phase 3 actions.
