# Demonstration

Start the isolated stack using [Windows setup](WINDOWS_SETUP.md). Open `http://localhost:3041/procurement`, use real Better Auth signup/sign-in and select an authorized workspace. The frozen evaluator creates a fictional research workspace using explicit fixture administration; access to it must be granted to the signed-in synthetic reviewer, as the browser test does. It is not public or authentication-free.

1. Open an approved RFQ. Inspect its reviewed exact product identity or explicit no-match decision. Compare local imported metadata with typed, dated human supplier attestations.
2. Start local research. Watch actual native selected tools and durable receipt IDs. Expand a receipt to inspect its original arguments, result and read-only policy.
3. In native `dev-02` history, inspect the backend-materialized null price and complete source coverage. Expand its line to see unknown price, stock and lead time. Research can be complete while quote inputs still require follow-up.
4. Expand a fact's source associations. Inspect RFQ line, product, offer, catalog version, content fingerprint and receipt pointer. The displayed price comes from the stored tool field; the model supplies no scalar value.
5. Inspect a failed coverage case such as `dev-04`: the missing supplier-offer read prevents research completion. The system does not manufacture a supplier result or use correction to execute another tool.
6. Inspect a native repair example listed in [evaluation results](EVALUATION_RESULTS.md). The correction count and finalization records are distinct from initial planning turns. Existing valid evidence survives; the correction cannot approve a quote.
7. Create a human quote draft with explicit offer choices, shipping, tax, expiry and pricing policy. Verify an incomplete quote is blocked. For a complete quote, review inputs, submit, request changes if appropriate and approve internally as owner/admin/reviewer. Reload its immutable history; a new version is required for later changes.
8. Open legacy history and confirm it is labelled original exact-value verification. No historical price or result has been upgraded to the new protocol.

Run the complete Playwright suite for a reproducible real extraction/catalog/offer/quote/native-research flow. The additional citation browser tests include one real native-history case and three **explicit UI fixtures** for staged/partial/legacy presentation. Their fixture images demonstrate display behavior, not additional native-model successes.

For interruption behavior, run the real recovery script only when evaluation/browser workloads have finished. It kills and starts `ownerpilot-procurement31-validation-worker-1`, waits for durable dispatch, tests late duplicate delivery, cancels an actual inference-stage run and probes a refused local provider endpoint. Read [recovery validation](RECOVERY_VALIDATION.md) before interpreting safe attention as research success.

No supplier messaging, quotation delivery, ordering, payment or Phase 4 action is present.
