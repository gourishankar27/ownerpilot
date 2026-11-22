# Recovery validation

Actual observations are retained in [real-recovery.json](results/real-recovery.json). Controlled protocol fixtures are separate.

The isolated Celery worker was actually killed with `docker kill --signal KILL ownerpilot-procurement31-validation-worker-1` during planning, after turn two was admitted and one receipt committed. After restart and durable dispatch, delivery two ended safely `needs_attention` with `research_coverage_incomplete`, after approximately **92.61 seconds**. Initial turns advanced from two to four and repair attempts stayed zero. The original receipt UUID/result survived, a new receipt was added, and terminal duplicate delivery changed nothing. There were **zero completion publications** for this run. This proves safe recovery, not successful recovered research.

Cancellation was submitted while the durable first planning call was marked `in_flight`. That call actually executed locally, recording 906 prompt tokens and 18 generated tokens, but post-inference state checks prevented publication. Final state remained `cancelled`, with no completion event. The probe observes the model-call lifecycle rather than instrumenting exact HTTP start time. Its row is marked failed because the response was refused after cancellation, despite successful inference.

A genuine refused local TCP endpoint produced `needs_attention`, `model_unavailable` and zero executed tools. Installed Ollama stayed available; the probe used a deliberately unavailable local endpoint after normal health-based admission. This is actual network failure, separate from the UI outage fixture.

The synthetic workspace retained exactly 60 quote versions and zero approvals before and after these probes. No quote mutation or human approval was caused by recovery/cancellation/outage. Unrelated workers and databases were left intact.

Controlled PostgreSQL/protocol fixtures interrupt planning admission, receipt commit, saved final references, evidence materialization, pre-publication and an admitted correction. They verify counters and original receipt IDs remain durable. A lost correction consumes its budget and safely requires attention. Other fixtures verify one successful correction, idempotent terminal replay with one audit event, cancellation during correction, source mutation, revoked membership and correction-time tool rejection. They are model test doubles, not additional native successes or actual process kills.

The original 240-second deadline, four initial turns, eight business tools and two equivalent requests remain; one additional correction is explicitly versioned and separately counted. An interrupted request can consume a turn without usable output, and stale dispatch waits 75 seconds. Recovery therefore reduces the remaining planning window. Prompt/schema pins are never silently upgraded.
