# Phase 3 status

**Implemented and locally validated; research quality is not fully accepted.** Work stops at Phase 3, with no external purchasing, messaging, delivery, payment, push or deployment.

Implemented: embedding-independent exact/lexical retrieval; explicit versioned product-selection resolutions; source-labeled supplier attestations and supersession; ten restricted local research tools; real Ollama native selection/execution; durable receipts, cancellation and safe worker recovery; deterministic Decimal quotes; explicit review/approval, immutable approved versions/history; authenticated UI and proxy routes.

Measured: 260 backend tests pass with one retained strict expected failure for a diagnosed frozen JPY oracle-label defect. The original 145 backend cases remain included. Final browser evidence is in `results/browser-final.json`, retaining the original seven scenarios and adding four Phase 3 scenarios. Financial coverage includes 34 standalone cases and 200 batch line amounts.

Final native benchmark: 30/30 tool requests executed successfully and authorized; 6/10 complete verified summaries, 4/8 held-out. Four malformed price strings were rejected; no unsupported claim was accepted. This misses the aspirational 95% completion target. Safe SIGKILL recovery preserved receipts and budget counters but ended needing human attention, not complete.

Open limitations: small 10-run native sample; formatting/summary reliability; retained batch-09 oracle total defect; key-based compatibility is not certification; user-attested/static supplier data is not live verified stock; API supports more optional commercial fields/tiers than the first form; limited currencies/each-unit conversion; no independent-approver assignment policy; no production HA/SLO/security certification. Phase 1.1 OCR weaknesses are unchanged.

See [final report](FINAL_IMPLEMENTATION_REPORT.md), [validation](PHASE3_VALIDATION.md), [evaluation](EVALUATION_RESULTS.md), [Windows setup](WINDOWS_SETUP.md) and [demo](DEMO_RUNBOOK.md). The repository changes are local and reviewable. No Phase 4 implementation was started.
