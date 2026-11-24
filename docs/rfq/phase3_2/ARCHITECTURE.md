# Coverage-aware research architecture

Signed API admission captures the approved RFQ revision, reviewed selections, catalog versions, supplier attestations, human quote choices and quote revision. Membership, source freshness and revision checks run again before each tool receipt and publication. Research tools remain read-only.

`provider_v3.py` makes actual local Ollama native tool calls. `runner_v3.py` owns finite state, durable call admission and finalization. `planning.py` derives missing source reads from validated persisted receipts. `tools_v3.py` adds one closed batch RPC. `evidence_v3.py` extends the frozen citation-only semantic verifier to physical paths in batch parent receipts.

The backend owns the mandatory source definition; the model cannot redefine it. Receipt observations are compacted before planning: approved RFQ data, read names, line IDs, result status and receipt IDs. Commercial source notes and raw batch bodies are excluded from model context. Finalization receives a bounded reference inventory with no commercial scalar values. Backend materialization retrieves exact typed values and associations from verified receipts.

Four independent states are exposed: source inspection, required citation verification, published research completion and quote input readiness. Missing prices, unresolved products and unknown availability may be correctly researched while quote inputs still require human action. Research never approves a quote, attests an offer or sends supplier communications.

Migration 0008 adds counters/caches and receipt origin/details. Receipts remain immutable under the existing trigger. Coverage JSON is a display cache; persisted receipts and the captured snapshot are authoritative. A crash between parent receipts can leave the cache behind the ledger until recovery recomputes it. The cache never invents source completion.
