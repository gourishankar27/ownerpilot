# Phase 1 validation — 2026-11-19 (America/Phoenix)

The original tree was clean. Work is on `feature/rfq-intelligence-phase-1`. No push,
external deployment, model download, existing application database change or demo reset
occurred. Integration/browser checks used disposable PostgreSQL at 127.0.0.1:55433.

| Check | Baseline | Final outcome |
|---|---|---|
| pnpm install --frozen-lockfile | Exit 0 | Playwright added; lock updated |
| pnpm lint | Exit 0, three tasks | Exit 0, three tasks |
| pnpm typecheck | Exit 0, three tasks | Exit 0, three tasks |
| pnpm test | Exit 0, type checks only | Exit 0; original semantics preserved |
| pnpm build | Exit 0 | Exit 0, Procurement/proxy routes included |
| uv sync --project apps/api | Failed package discovery | Correct module-name; exit 0 |
| Python compileall | Executed after setup | Exit 0 |
| Ruff RFQ modules/tests/scripts | No RFQ code | Exit 0 |
| uv lock --check | Lock inspected | Exit 0 |
| Existing behavioral tests | None | Added 13 legacy API cases |
| RFQ migrations | None | Fresh/representative schemas and repeat applies pass |
| Existing Drizzle push on populated representative schema | Not run on application data | Stopped at truncate prompt; no truncate accepted |

Legacy runtime DDL and Drizzle use differing constraint names. The populated-schema
Drizzle attempt stopped before applying changes. A separate fresh disposable database
successfully applied Better Auth, pgvector, Drizzle public schema and RFQ migrations
0001/0002, then reapplied the RFQ migrations. Preservation tests compare original
workspace rows before/after repeat RFQ migration. Existing application data was never
connected to. Explicit Drizzle filters now protect auth tables and procurement schema.

Backend tests cover secure upload limits, hashing/path safety, PDF/encryption/OCR
absence, CSV preambles, worksheets/formulas/ZIP limits, normalization, distinct
identifiers, closed structured output, evidence rejection, prompt boundaries, provider
JSON/timeouts and one-to-one matching. Real PostgreSQL/FastAPI tests exercise membership,
cross-workspace 403/404, role denial, stale revisions, duplicates, correction history,
manual/invalid rows, approval, immutable approved records, reprocessing, concurrent
delivery locks, bounded retries, transactional rollback and sanitized database loss.
Broker/provider outage fixtures are explicit tests and contribute no quality results.

The 13 legacy API smoke checks cover health, dashboard, documents, import ledger,
obligations, actions, reorder, model settings, investigation, forecast, briefing,
scenario and scheduler. They do not prove every historical business calculation.

Four Chromium scenarios cover anonymous denial; explicitly simulated unavailable-model
UI; real signup/workspace/create/upload/Celery/evidence/correction/approval/reload; and
corrupt upload plus stale-tab errors. Synthetic screenshots in `screenshots/` were
visually inspected. An initial selector failure matched Next's additional route alert;
the Procurement alert now has its own accessible name. The business E2E flow passed
before that selector correction. Final counts are in STATUS and the final report;
machine-readable pytest/Playwright artifacts remain in ignored `.local/rfq`.

[results/worker-restart.json](results/worker-restart.json) records a real SIGKILL of the
Linux worker during OCR of a 20-page synthetic PDF. Restart/outbox recovery completed
on attempt 2. Three additional deliveries left one published run, 100 source rows and
revision 1. An earlier harness missed the processing window due to slow Windows
localhost Redis resolution; it did not kill a worker and is not claimed as success.
Native Redis now uses 127.0.0.1 with bounded broker socket/connect timeouts. The harness
targets only the named disposable worker and preserves its environment on restart.

PostgreSQL/pgvector, Redis, Linux Tesseract, container-to-native Ollama HTTP and actual
qwen3.8:27b inference were exercised. No invented GPU utilization. `/health` is basic
liveness; signed RFQ health reports database, broker, worker and local-model readiness
without generation. Fresh container installs use the checked-in Python lock.

Initial evaluation exposed CSV-preamble and PDFium page-cleanup defects; both were
corrected and rechecked without changing held-out labels or tuning the prompt.
See EVALUATION for measured quality. No private-customer validation, hostile-file
penetration test, full legacy UI regression matrix or production load test is claimed.
OCR identifiers/partial tables remain weak and require review. Phase 2 is not implemented.
