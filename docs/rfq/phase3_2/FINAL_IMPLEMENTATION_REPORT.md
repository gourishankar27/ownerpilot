# Phase 3.2 final implementation report

**Functionally validated — research-quality target unmet.** Coverage-aware hybrid research completed 52/60 independent held-out RFQs with 324/324 line source coverage. The source-read bottleneck is addressed by bounded batches and explicitly attributed mandatory completion. Native citation reliability remains separately measured and can still require human attention.

Implemented a closed four-line batch source RPC, authoritative remaining-work planner, separately admitted citation-only finalization, durable pending calls/counters, exact physical-parent evidence associations, bounded recovery and capacity attention above twelve lines. The UI shows source versus citation coverage, per-line progress, actual native/backend origins and persisted activity. No automatic scope continuation or quote approval is added.

| Variant | Development | Validation | Held-out | Held-out source-covered lines | Native / backend RPCs (held-out) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Frozen Phase 3.1 | 2/16 | 4/20 | 4/60 (6.7%) | 51/324 | 183 / 0 |
| A: native batching | 14/16 | 17/20 | 51/60 (85.0%) | 323/324 | 156 / 0 |
| B: coverage-aware native | 14/16 | 19/20 | 56/60 (93.3%) | 324/324 | 156 / 0 |
| D: bounded hybrid | 16/16 | 19/20 | 52/60 (86.7%) | 324/324 | 120 / 36 |

The independent corpus has 96 cases / 514 lines, frozen before strategy selection. D/four was selected from 16 development and 20 validation cases; final evaluation used 60 held-out cases and four separate real local executions per case. C was a development-only native experiment. The deterministic baseline passed 96/96 with zero model calls. For mandatory source reporting alone, it was more reliable and requires no model; this does not evaluate optional agent research utility. Backend scheduling success is not reported as native planning ability. Held-out rankings do not retroactively change the predeclared default.

Across 240 held-out executions, the independent oracle inspected 5274 materialized facts and 651 tool receipts: 0 unsupported/misbound accepted facts and 0 unauthorized successful tools. These are observed finite-sample results, not guarantees of universal safety.

Validation passed 473 backend tests with the existing strict xfail, and 21 browsers. New actual worker recovery was safe but incomplete, with all receipts preserved and at most one publication. Actual Redis interruption, cancellation and refused endpoint passed; PostgreSQL outage behavior is explicitly a controlled fixture. Populated and fresh migration checks passed. All 724 protected historical files and original assertions remain unchanged.

Remaining limitations: single small local model and fictional corpus; model reference copying can fail despite complete sources; no held-out retuning; larger/more-offer scopes can exceed reference/byte capacity; no automatic continuation; 240 seconds is a publication deadline rather than forced cancellation of remote computation; coverage display caches can lag committed parent receipts until recovery recomputes the ledger; device memory samples are not peaks; regression inference overlapped some original timing trials (separate window-excluded and serialized development timings are reported); historical JPY fractional-quantity strict xfail remains. These limits bound the claims made here.

## Resume-ready evidence

- Built a versioned procurement agent controller with closed four-line source batches, exact parent-receipt citations, separate planning/finalization budgets and explicit native versus backend execution attribution across approved RFQs up to twelve lines.
- Evaluated qwen3:8b on an independently frozen 96-case / 514-line corpus; the selected hybrid achieved 52/60 held-out verified completions and 100.0% source coverage, with zero independently detected unsupported accepted facts across the four-variant held-out comparison. The 95% completion target was not met.
- Validated 473 backend and 21 browser tests, actual isolated SIGKILL/Redis recovery and additive migration preservation of 9,669 existing rows, while retaining 724 historical files and human quote approval controls.

See evaluation results for failure counts/IDs, performance and contribution attribution; reliability validation for exact observations; and the demo/Windows runbooks for reproduction. Work stops before Phase 4. Nothing was pushed or deployed.
