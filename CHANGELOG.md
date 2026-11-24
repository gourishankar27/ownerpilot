# Changelog

All notable changes to OwnerPilot are documented in this file.

## Unreleased

### Added

- Phase 3.2 coverage-aware planning, a closed four-line batch source tool, exact
  parent-receipt citation verification, separate planning/finalization budgets,
  durable pending work and explicit native/backend execution origins. Added
  independent procurement-v3 scenarios (96 RFQs, 514 lines), native strategy and
  batch-size experiments, source/citation coverage UI, additive migration 0008,
  preserved-source checks and isolated recovery/browser validation tooling.
  Validation: 473 backend passes plus the historical strict xfail, 21 browser
  passes, and actual isolated worker/Redis recovery. Selected hybrid: 52/60 held-out
  completions and 324/324 source-covered lines; coverage-native: 56/60. The 57/60
  quality target remains unmet. Zero unsupported accepted facts/unauthorized
  successes across 240 held-out executions. Timing interference is disclosed,
  with regression-window exclusions and a separate serialized development study.
- Phase 3.1 versioned citation-only research, backend scalar materialization and
  entity provenance, independent line coverage, safe partial evidence, one durable
  correction, immutable receipts/finalizations and recovery diagnostics. Added frozen
  60-case research and rational finance-v2 corpora, evidence UI, native comparisons,
  worker/network probes and additive migration checks. Final validation: 386 backend
  passes plus the retained strict oracle xfail; fifteen browser scenarios passed.
  New benchmark: 36/60 complete, 20/36 held-out; zero accepted unsupported facts.
  Separate original scenarios: 10/10. Research quality remains unmet, including a
  source-tool coverage regression. Historical artifacts and financial semantics
  remain preserved; only the new financial dataset corrects the JPY label to 930.
- Phase 3 restricted native Ollama procurement research, durable tool receipts,
  explicit product resolutions, append-only supplier attestations/supersession,
  deterministic Decimal quote preparation and immutable internal review/approval.
  Added signed APIs, responsive review UI, synthetic evaluation and real worker
  recovery/cancellation probes. Final native benchmark: 6/10 verified completions,
  30/30 authorized successful tool calls, zero accepted unsupported claims. Research
  quality target remains unmet; one frozen financial oracle defect is retained.
- Phase 2 Catalog Intelligence: versioned catalog preview/confirmation, durable
  neural indexing, genuine BM25, pgvector cosine retrieval, RRF, deterministic
  compatibility and approved-RFQ product decision history. Synthetic corpus has
  1,224 offers/1,020 products;816 final query/method comparisons,145 backend tests
  and seven browser scenarios at that milestone.
- Phase 1.1 versioned selective RFQ routing, bounded geometry-aware OCR, explicit
  source occurrence/row/column associations, processing telemetry and review filters.
- Local 4B/8B/27B inference experiments, independent frozen v2 synthetic layouts,
  maximum-weight evaluation matching and 192 final document/configuration attempts.
- Safe equivalent-constraint reconciliation on disposable populated schemas,
  preservation/rollback evidence, 45 additional backend cases and two browser cases.
  Final validation: 103 backend and six browser tests pass. OCR/model extraction
  quality targets remain unmet; see docs/rfq/phase1_1/FINAL_IMPLEMENTATION_REPORT.md.
- Workspace-authenticated Procurement UI and isolated RFQ APIs, additive procurement
  schema migrations, durable Redis/Celery jobs, bounded PDF/OCR/CSV/XLSX/TXT parsers,
  real local Ollama structured extraction, verified source evidence and explicit
  versioned human correction/approval workflows.
- Frozen synthetic RFQ dataset (48 documents, 240 items), reproducible extraction
  metrics, PostgreSQL/security/recovery tests, Playwright flows and Windows runbooks.

### Fixed

- Exact/BM25/SQL catalog retrieval no longer requires the embedding provider;
  vector/hybrid failures are explicit and channel metadata is recorded. Preserved
  ranking semantics. Constrained long catalog line selectors on mobile screens.
- Windows fixture checkout attributes preserve original frozen payload hashes;
  verified binary/text repairs changed no historical labels or Git payload objects.
- API uv package discovery (`api` module), Python version and locked container installs.
- Drizzle ownership filters protect auth and RFQ schemas from business schema push.
- Added an installed-library auth migration command without a floating CLI download.

### Changed

- Aligned workspace and API version metadata to `1.0.0` to match the public `v1.0.0-showcase` release baseline.
- Replaced placeholder test scripts with smoke-check commands (`pnpm test` now executes type-level checks in active workspace packages).

## v1.0.0-showcase - 2026-05-09

### Added

- Hosted + self-hosted deployment documentation for `Vercel + Render + Supabase` and Docker Compose local mode.
- Full-stack self-hosted runtime packaging:
  - `apps/web/Dockerfile`
  - `apps/api/Dockerfile`
  - `infra/docker-compose.yml` (web + api + postgres + ollama)
- Showcase assets/docs:
  - architecture overview with system flow
  - scripted 90-second and 2-minute demo paths
  - contributor roadmap and good-first-issue list
- Demo data privacy guardrails and anonymization script:
  - `data/demo/README.md`
  - `data/demo/anonymize_fixtures.py`

## v0.5.0-milestone-d - 2026-05-09

### Added

- Forecasting and scenario planning APIs with explainable, deterministic baselines.
- Scheduler execution endpoint for morning brief + anomaly + due-reminder runs.
- Forecast Lab UI with:
  - metric forecast
  - scenario planner templates
  - manual scheduler trigger panel
- Action Center status lifecycle support:
  - `open`
  - `watching`
  - `snoozed`
  - `resolved`

## v0.4.0-milestone-c - 2026-05-09

### Added

- Model provider runtime settings API and persistence:
  - `local-open`
  - `byo-cloud`
  - `hybrid`
- Investigation response metadata:
  - provider
  - mode
  - latency
  - estimated cost
- Retrieval chunk storage with pgvector-backed similarity lookup and evidence citations.
- Guarded investigation flow with safe prompt checks and SQL insight helper.
- Model settings UI and expanded investigation workspace for recruiter-facing demo clarity.

## v0.3.0-milestone-b-final - 2026-05-09

### Added

- Postgres-backed import jobs and import-row persistence for preview/confirm flows.
- Postgres-backed recurring obligations, business documents, and ledger transaction storage.
- Quick-add API + dashboard UX for `sale`, `purchase`, and `expense` daily owner entries.
- Demo workspace data utilities:
  - `pnpm demo:seed` (idempotent seed)
  - `pnpm demo:reset` (deterministic reset + reload)

### Changed

- Dashboard stats and action queue now compute from live Postgres data.
- API persistence moved off runtime JSON files for owner-critical flows.
- Drizzle schema expanded to include operational tables used by the API layer.

## v0.2.0-milestone-b-preview - 2026-05-09

### Added

- Recurring obligation CRUD flows with owner-facing status transitions (`due`, `scheduled`, `paid`).
- Persisted document upload workspace and retrieval-ready document history view.
- Import preview + confirm/apply workflow for CSV and Excel historical records.
- Runtime-backed import ledger cards and import history timeline.
- Action Center queue surface powered by persisted owner context.

### Changed

- Dashboard recurring obligations section now includes interactive management instead of static rows.
- Actions and imports pages now render from runtime API data contracts.
- Shared contracts expanded for import confirmation, action center snapshots, and recurring obligation inputs.

### Quality

- Lint, typecheck, build, tests, and API compile sanity verified on this checkpoint.
