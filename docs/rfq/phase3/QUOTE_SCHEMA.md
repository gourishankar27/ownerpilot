# Quote schema and API

`quote_drafts` holds the current internal quote aggregate: workspace/RFQ IDs, optimistic revision, state, approved RFQ/selection/offer snapshot, declared quote policy, explicit line -> attestation choices, calculation result, preparer and approval identity/time. JSON contains decimal strings; PostgreSQL numeric mirrors support exact commercial storage.

`quote_versions` appends the complete aggregate after each change, with revision, state, actor/reason/time and grand total. `quote_audit_events` separately records workflow actions and lineage. Both are append-only at the database layer. Product resolutions and offer attestations are also append-only. The approved aggregate has an update/delete protection trigger.

States: `incomplete`, `draft`, `under_review`, `changes_requested`, `approved_internal`, `rejected`, `superseded`. Editing increments revision. Submitting/deciding also increments revision. Incomplete drafts preserve all unresolved RFQ lines and null amounts. An approved/rejected/superseded aggregate is final at the API; new versions create a new draft ID linked by an explicit audit lineage event. Prior approvals remain immutable.

| Operation | Endpoint |
|---|---|
| Read approved selection/offer snapshot | GET `/api/rfqs/{id}/selections` |
| Authoritative resolution | POST `/api/rfqs/{id}/line-items/{line}/selection-resolution` |
| Add/read commercial evidence | POST `/api/supplier-offers/attestations`; GET `/api/supplier-offers/attestations/{id}` |
| Compare attested prices | GET `/api/supplier-offers/resolutions/{id}/comparison` |
| Start/list research | POST/GET `/api/rfqs/{id}/research` |
| Research details/tools/evidence/cancel | `/api/agent-runs/{id}` and `/tools`, `/evidence`, `/cancel` |
| Research model health | GET `/api/agent-health` |
| Create/list quotes | POST/GET `/api/rfqs/{id}/quotes` |
| Read/edit quote | GET/PATCH `/api/quotes/{id}` |
| Calculate saved inputs | POST `/api/quotes/{id}/calculate` (read-only preview) |
| Review state decisions | POST `/api/quotes/{id}/{submit,approve,reject,request-changes,supersede}` |
| New immutable lineage branch | POST `/api/quotes/{id}/new-version` |
| History/audit | GET `/api/quotes/{id}/history`, `/audit` |

The web routes use `/api/procurement/...`, signed by the existing proxy. No unauthenticated/free-query tool route exists. Every edit/decision carries current revision and a reason; submit/approve additionally require explicit input-review attestation. Missing choices are allowed only as incomplete drafts, never guessed automatically.

The model does not select quote offers, choose markup/margin/tax/shipping policy or create approved records. Optional `quote_id` on a research request binds the human-selected quote policy/offers for read-only calculation previews.
