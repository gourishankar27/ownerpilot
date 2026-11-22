# Bounded citation correction

The initial finalization request is durably sanitized before resolution. The runner stores a separate immutable initial resolution, including valid partial facts and error codes. If sources were fully inspected but references are incomplete/invalid, it admits at most one correction using the same pinned model, inventory and receipts. The correction receives only machine-generated error and missing-reference information.

No business tools are provided during correction. A model response requesting tools is rejected without execution. There is no provider/model fallback, new supplier source, alternate price or wall-clock extension. Missing tool coverage goes directly to `needs_attention`; citation correction cannot repair research the model never performed.

| Budget | Original | Citation-only |
|---|---:|---:|
| Initial model turns, including finalization | 4 | 4 |
| Business tool calls | 8 | 8 |
| Equivalent tool requests | 2 | 2 |
| Admission-to-completion seconds | 240 | 240 |
| Provider timeout seconds | 60 | 60 |
| Additional citation corrections | 0 | 1 |
| Maximum total model calls | 4 | 5 |

The one extra call is an explicit versioned budget change. `repair_attempts`, model-call phase, duration and immutable finalization rows record it separately. Delivery retry never resets it. If a worker dies during an admitted correction, that correction remains consumed; the system may safely need attention rather than making an unrecorded extra request.

After a correction, valid prior facts and current valid references are re-resolved. Any remaining current error or missing required fact prevents completion. Prior errors remain auditable rather than being silently discarded. Tests distinguish successful correction, zero allowed corrections, exhausted correction, cancellation and a prohibited repair-time tool request. Native correction outcomes are in the evaluation artifacts, separate from deterministic protocol fixtures.
