# RFQ API v1

Contracts use `rfq.v1`, snake_case keys, and string decimals. Existing `/api` naming
is preserved. OpenAPI is available from `/docs`; request DTOs reject unexpected keys.
Browser clients use `/api/procurement/{path}` on Next; the proxy derives user identity
from Better Auth and checks workspace membership. `x-workspace-id` selects membership;
it is never trusted as authorization. FastAPI independently rechecks membership/role.
The server-to-server signature is short lived and bound to HTTP method and path.
Do not distribute RFQ_AUTH_SECRET to browsers or external API clients.

| Method /api route | Behavior |
|---|---|
| POST rfqs | Create `{title,customer_name?}`; 201 |
| GET rfqs | Workspace list; search/title, status, limit 1–100, offset; persisted counts |
| GET rfqs/{id} | Current header/items, documents, latest 20 jobs/runs, role and approval requirements |
| POST rfqs/{id}/documents | Multipart file+revision; 201; bounded streaming and validation |
| GET rfqs/{id}/documents | Metadata, max 50 |
| GET rfqs/{id}/documents/{doc}/download | Authenticated attachment, octet-stream/nosniff |
| POST rfqs/{id}/process | `{revision,mode,reason?}`; 202 durable job |
| POST rfqs/{id}/reprocess | Same; nonempty reason required; prior versions retained |
| GET rfqs/{id}/jobs | Paginated history, limit max 100 |
| GET rfq-jobs/{id} | Actual persisted stage, counts, attempts, error and timestamps |
| POST rfq-jobs/{id}/cancel | Persist cancellation; in-flight inference cannot publish |
| GET rfqs/{id}/line-items | Current items, limit max 500 and offset |
| POST rfqs/{id}/line-items | Manual row after extraction; revision, fields, reason, review_status |
| PATCH rfqs/{id}/line-items/{item} | Same review payload; stale revision is 409 |
| PATCH rfqs/{id}/header | Supported header fields, revision and nonempty review reason |
| GET rfqs/{id}/evidence | Current field evidence; bounded by RFQ item/file limits |
| POST rfqs/{id}/approve | Explicit `{revision,reason?}`; reviewer role and all review gates |
| GET rfqs/{id}/audit | Paginated before/after history, limit max 100 |
| GET rfq-health | Authenticated DB/broker/worker/local-model checks; no generation |

Modes are `deterministic`, `llm`, `hybrid`. Business status is draft, awaiting_review
or approved. Job states are queued, validating, parsing, extracting,
validating_results, awaiting_review, failed, cancelled. No invented percentages.

401: missing/invalid session signature. 403: membership/role/origin denial.
404: resource not visible in this workspace. 409: duplicate, stale revision, active
job or immutable approval. 413: request/file byte limit. 422: invalid document,
unsupported fields or unresolved approval requirements. 503: auth configuration or
upstream readiness. Database errors never return connection strings/document text.

GET detail is bounded to 2,000 items and configured document count; larger histories
use paginated endpoints. Evidence contains real locations only: CSV/XLSX columns,
worksheet/row, native/OCR PDF page/line and text spans. No bounding boxes are fabricated.
