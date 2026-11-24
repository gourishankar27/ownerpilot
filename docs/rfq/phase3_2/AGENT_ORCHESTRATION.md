# Agent orchestration

| Strategy | Native planning | Required-source fallback | Attribution |
| --- | --- | --- | --- |
| A: native_batch | Improved native batch prompt and tools, without remaining-work feedback | None | Every requested RPC is model-selected |
| B: coverage_native | Native tools plus bounded missing-work feedback | None | Every requested RPC is model-selected |
| C: mandatory_scheduler | Backend required reads, then one optional native planning turn | Backend first | All mandatory coverage is backend-scheduled |
| D: hybrid | Up to two native planning turns, then minimum missing mandatory reads | Bounded by the same eight-RPC cap | Actual native and backend receipts counted separately |

The selected default is D with batch size four. Selection was frozen from 16 development and 20 validation cases before held-out trials; see `results/selection.json`. C was measured as a development experiment, not included in the four-variant final held-out denominator. The offline deterministic baseline makes zero model calls and is separately labelled.

Each planning response may enqueue several batch calls. The controller persists the full pending list with stable ordinals and assigned origins before execution. Recovery reuses committed ordinals and executes only missing entries. It does not reset consumed model calls or deadlines.

Lifecycle events include source coverage updates, planning request admission, tool/batch requests and validation, receipt persistence, citation finalization, optional citation correction, evidence materialization and guarded publication. Early planning summaries cannot publish. Finalization has no tools and accepts only reference groups. There is at most one correction; partial valid evidence survives it, while any remaining invalid/omitted citation blocks completion.

The `model_selected` flag on inherited materialized fact records means the model selected a citation. It does **not** identify who chose the source read. Agent-contribution accounting always joins the actual parent receipt's `execution_origin`.

These strategies improve operational completion through batching, finite orchestration and source guarantees. Hybrid backend coverage is not evidence of stronger native model planning. The unchanged eight-RPC legacy limit also makes four-plus-line complete source inspection intrinsically infeasible with two scalar RPCs per line; line-count stratification is required when interpreting improvements.
