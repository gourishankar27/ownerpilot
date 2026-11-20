# Database schema and ownership

The additive migration runner is `python -m api.rfq.db`. It takes a transaction-scoped
migration advisory lock and stores checksums in `procurement.schema_migrations`.
Applied migrations with changed content fail rather than being rerun. Migrations
require existing `public.business_workspaces` and `public.workspace_members`.
They never create/alter/drop existing business tables. New constraints are subsequent
migrations, not edits to migration 0001. There are no automatic down migrations.

| Table | Responsibility |
|---|---|
| rfqs | Workspace FK, title, business lifecycle, revision, current header and run, creator, approver/time |
| rfq_documents | Immutable generated storage ID, safe display name, extension, SHA-256, byte size, uploader/time, parser status |
| rfq_document_pages | Parser-versioned extracted blocks/cache, actual page/sheet/row/column spans, OCR metadata |
| rfq_processing_jobs | Durable queue, stages/counters, attempts, sanitized errors, trusted requester and workspace |
| rfq_extraction_runs | Immutable original validated extraction JSON, metadata, schema version, unique job ID |
| rfq_line_items | Editable items by run+stable source item ID; JSON fields/evidence; numeric(20,6) quantity and price |
| rfq_audit_events | Creation, upload, enqueue, publication, corrections, cancellation and approval; actor/time/version |

Field evidence and review events are stored in typed field JSON and audit-event JSON
instead of additional tables duplicating those values. A run's original result retains
the extraction before any correction. Review events retain before/after, reason and
actor. JSON data is private business data and is subject to the same authorization.

Workspace composite FKs bind documents, jobs, runs and items to their RFQ. Composite
run/RFQ FKs prevent associating an item or audit event with a different RFQ version.
Unique workspace+fingerprint rejects duplicate uploads across RFQs in that workspace.
One partial unique index allows only one active job per RFQ; unique job/run mapping
prevents double publication. Ownership/time/state indexes support listing and recovery.

A session advisory lock serializes repeated deliveries of one job across connections.
Run creation, all line inserts, current-run pointer/header update, job completion and
publication audit commit together. Exceptions roll the whole publication back.
Cancelled jobs and stale base revisions cannot publish. Approval locks the RFQ row,
checks current revision and review requirements, then commits actor/time and audit.

Cached parsed blocks avoid repeated OCR of unchanged documents with the same parser
version. Increment PARSER_VERSION when parser behavior changes. No old snapshots are
deleted by reprocessing. Back up both PostgreSQL and the document volume together.
The application does not offer a data-retention/deletion UI in this phase.
