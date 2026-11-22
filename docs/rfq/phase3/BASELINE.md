# Phase 3 baseline

Validated locally on November 21, 2026 (America/Phoenix). Historical Phase 2 metrics remain historical.

The initial local `main` pointed to `56d6f6d`, while the supplied Phase 2 merge existed at `origin/main`, `dd3bd99c6fede176d987aab41b1478ea3ba41ca6`. Created `feature/rfq-intelligence-phase-3` from that merge. Preserved ignored runtime files and existing branches; no reset, force checkout, push or deployment.

## Repeated baseline checks

| Check | Result | Evidence |
|---|---|---|
| Original backend suite, initial checkout | 144 passed, 1 failed | `results/baseline-tests.xml` |
| Original backend suite, verified checkout | 145 passed | `results/baseline-tests-checkout-fixed.xml` |
| Original seven browser scenarios, initial checkout | 6 passed, 1 failed (OCR PDF) | `results/baseline-browser-checkout-failed.json` |
| Original seven browser scenarios, verified checkout | 7 passed | `results/baseline-browser-checkout-fixed.json` |
| Frontend lint, typecheck, test, build | Passed before implementation | Session command results; repeated final checks in PHASE3_VALIDATION |
| Ruff excluding frozen `legacy_v1`; uv lock check | Passed before implementation | Repeated final checks |
| Native Ollama smoke, installed qwen3:4b | Real `get_approved_rfq` tool request, 4,792 ms | `results/tool-smoke.json` |

Commands: `.venv/Scripts/python.exe -m pytest -c apps/api/pyproject.toml apps/api/tests -q`; `pnpm lint`; `pnpm typecheck`; `pnpm test`; `pnpm build`; `pnpm --dir apps/web exec playwright test` with Phase 2 runtime environment, `RFQ_WEB_URL=http://localhost:3022`, screenshots redirected to ignored Phase 3 baseline storage. Backend database was newly created `ownerpilot_rfq_phase3_test`, not an existing application database.

## Checkout defect and preservation

Windows `core.autocrlf=true` changed 72 ASCII PDF/TXT source payloads during checkout. The unchanged frozen manifests detected this; OCR also failed on a mangled PDF. A first overly broad checkout repair did not preserve mixed historical LF/CRLF expectations and the intermediate baseline failed again (`baseline-tests-repaired.xml`). The final repair chose only Git-blob or original line-ending candidates whose SHA-256 matched each existing manifest. Ground-truth labels were never edited.

`.gitattributes` now marks binary files appropriately and specifies each historical text fixture's original LF/CRLF checkout convention. `results/checkout-repair.json` records all 72 repairs. The original checkout bytes are backed up privately in `.local/rfq/phase3/checkout-before.zip`.

`results/preservation.json` captured 434 protected files. Final verification records 362 byte-identical files plus 72 manifest-verified checkout repairs normalizing to identical original Git objects. No historical report, label, released migration or approved application record was rewritten. Exact hashes are in the JSON manifests and `artifact-hashes.json`.

## Runtime

Windows, PowerShell 7, Python 3.14, PostgreSQL 17/pgvector, Redis, Celery, Next.js 16.2.6, pnpm 10.33.0. Intel i9-14900HX; RTX 4090 Laptop GPU, 16,376 MiB VRAM, driver 610.88. Existing qwen3:4b, qwen3:8b and nomic-embed-text:v1.5 were available; no model weights or drivers were downloaded or changed. Final research defaults to the installed 8B model after documented development failures with 4B.

Phase 1.1 extraction/OCR limitations are unchanged. The Phase 2 1,020-product, 816-pair benchmark and its ranking metrics were not rerun or represented as Phase 3 measurements.
