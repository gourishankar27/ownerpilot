# Durable execution and publication

An advisory lock serializes local research per database. Each run persists source/protocol/model pins, initial-turn and repair counters, native pending calls with ordinals, tool receipts, finalization references and resolutions. Before HTTP inference, the admitted model call and consumed counter are committed. A restart records unfinished calls as interrupted and retains the consumed budget.

Pending tools resume from their durable ordinal. Existing receipts are reused; equivalent request limits count all stored receipts. Each tool remains independently authorized through the original closed registry. Model context is reconstructed from durable receipts; successful reads are not replayed merely because the worker restarted. Product-selection planning context is compacted while original receipts remain unchanged.

Publication rechecks current workspace membership, source/review/offer identity, commercial freshness, quote revision when supplied, cancellation and the original admission deadline. RFQ row locking serializes the final check with source mutations. The membership row is held for share during protected operations. No locks are held through inference. Completion and one audit event commit atomically; late duplicate deliveries to a terminal run return without new publication.

| Interruption | Resume behavior |
|---|---|
| Planning/model request | Preserve consumed turn; interrupted call remains visible |
| Tool receipt committed | Reuse receipt ID, value and ordinal |
| Final references received | Resolve saved references without another model request |
| Evidence materialized | Re-resolve saved references and publish only after rechecks |
| Before publication | Recheck source, permission, cancellation and deadline |
| Correction in flight | Preserve consumed correction budget; safe attention if exhausted |

Errors are machine codes, including `source_changed`, `permission_revoked`, `model_unavailable`, `research_coverage_incomplete`, `repair_budget_exhausted`, `citation_repair_tool_request`, `budget_exhausted` and `unsupported_pinned_protocol`. Generic provider ValueErrors are conservatively grouped as `model_or_protocol_mismatch`; this can include input/response size rejection and is a diagnostic limitation. Raw exception bodies and model reasoning are not persisted by the new runner.

Recovery has an attempt cap of three and retains the original 240-second deadline. Queue dispatch considers stale active runs after 75 seconds. A crash therefore reduces the remaining inference window. Safe `needs_attention` is an acceptable recovery outcome; it is not counted as successful research completion.
