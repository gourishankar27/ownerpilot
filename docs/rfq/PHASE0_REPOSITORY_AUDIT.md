# Phase 0 audit — 2026-11-19

The initial tree was clean on `main`; work is on `feature/rfq-intelligence-phase-1`.
No existing database was modified or reset. Validation uses a new PostgreSQL container,
database `ownerpilot_rfq_validation`, port 55433, and a tmpfs data directory.

## Verified existing implementation

- Next.js 16.2.6 / React 19 / Better Auth / pg / Drizzle in apps/web; FastAPI,
  psycopg, Polars, DuckDB, openpyxl in apps/api. pnpm monorepo, uv workspace.
- Existing backend routes are `/api/...`. `demo_data.py` owns most services, creates
  operational tables at runtime and selects a global demo workspace. It has no
  authenticated user/workspace boundary. New RFQ code must not reuse that identity.
- Existing web session is genuine Better Auth, with `workspace_members` linking
  users to `business_workspaces`. The app shell permits anonymous demo viewing.
- Existing document ingestion stores summaries/text; it is not a PDF/OCR pipeline.
  Existing imports preview/confirm CSV/XLSX into business ledgers; reuse dependencies,
  not the global demo-data service or its import semantics.
- `embedding_for_text` hashes tokens into 24 dimensions. Investigations compose
  deterministic responses and provider metadata. Existing architecture/docs imply
  Ollama routing more broadly than the executable code demonstrates. These are not
  learned embeddings or verified LLM calls. Phase 1 introduces actual HTTP inference.
- Database ownership is already split between Drizzle push and runtime DDL, with no
  released migration files. RFQ tables use a separate `procurement` schema and a
  checksum-verified additive SQL migrator. Public schema remains existing ownership.
- No behavioral backend/frontend tests or checked-in CI workflow existed. `pnpm test`
  invokes typechecks. Existing safeJson can substitute demo fallback data; RFQ UI uses
  a separate API client with explicit errors and no fabricated success fallback.

## Environment and baseline

Git 2.52.0.windows.1; Python 3.14.0; Node 24.12.0; pnpm 10.33.0;
Docker CLI/engine 29.8.2; Compose v5.5.1; Ollama 0.40.16.
RTX 4090 Laptop, 16376 MiB VRAM, NVIDIA driver 610.88.
uv was absent; installed uv 0.13.9 through `python -m pip install uv`.
Docker Desktop was installed but stopped; started its existing executable.
Ports 5432 and 11434 were occupied; 3000, 8000, 55433 and 6380 were available.
Installed models: `qwen3.8:27b` and `qwen3.8-27b-uncensored:latest`, approximately
17 GB each. No checkpoint downloaded. Real `qwen3.8:27b` smoke call produced
`{"ok":true}`, prompt tokens 22, output tokens 6, total duration 74.297 seconds
(includes initial loading). It may exceed VRAM and offload; no utilization claimed.

Before RFQ implementation: `pnpm install --frozen-lockfile` succeeded;
`pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm build` all exit 0 (three package
tasks each). Backend `uv sync` failed because package discovery expected
`src/ownerpilot_api` while the actual module is `src/api`. Fixed module-name config.
Existing Dockerfile used Python 3.12 despite requires-python >=3.14; corrected.
The installed Next guides use `.md` extensions, not `.mdx`; read the route handler
and server/client component guides in `dist/docs` and checked actual installed types.

Final database, OCR, worker, browser, model-quality and regression evidence is in
[PHASE1_VALIDATION.md](PHASE1_VALIDATION.md). Environment errors and code failures
are reported separately there.
