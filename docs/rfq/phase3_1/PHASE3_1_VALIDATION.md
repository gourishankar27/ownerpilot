# Phase 3.1 validation

**Functionally validated — research-quality target unmet.** Functional checks pass; held-out completion is 20/36 (55.6%), below 95%. Synthetic evidence does not establish production readiness.

| Check | Result | Evidence |
|---|---|---|
| Fresh backend baseline | 260 passed, one strict expected failure | [baseline XML](results/baseline-tests.xml) |
| Final complete backend suite | **386 passed, one preserved strict expected failure**, no other failures/skips | [regression XML](results/regression-tests.xml) |
| Browser baseline | Eleven passed | [baseline browser JSON](results/baseline-browser.json) |
| Final complete browser suite | **Fifteen passed**, original eleven retained plus four new | [final browser JSON](results/final-browser.json) |
| New finance suite | 64 passed | [finance XML](results/finance-v2-tests.xml) |
| Ruff / Python compilation | Passed | Commands below |
| Workspace lint/typecheck/test/build | Passed | Commands below |
| Dependency lock check | Passed, lock files unchanged | `python -m uv lock --project apps/api --check` |
| Native smoke | Real qwen3:8b request succeeded | [smoke](results/native-smoke.json) |
| Final model/index identity | Original qwen3:8b digest; 66 published real Nomic vectors | [identity](results/final-model-identity.json) |
| Independent native benchmark | 120 runs, 481 requests, 370 successful read-only tools | [summary](results/evaluation-summary.json) |
| Fresh original matched cases | Ten runs, forty requests, thirty tools, ten complete | [comparison](results/historical-comparison) |
| Real kill / duplicate / cancellation / outage | Safe behavior passed; recovered research incomplete | [recovery](results/real-recovery.json) |
| Populated additive migration | 39 tables / 1,363 original rows preserved in a new clone | [projection hashes](results/migration-preservation.json) |
| Historical bytes | 525 protected files identical; old provider identical | [preservation](results/final-preservation.json) |

Original tests were not removed or changed. New backend cases comprise 46 resolver, 16 runner and 64 finance checks. Frontend `test` scripts perform TypeScript checks; Playwright separately exercises browser behavior. Four pre-existing Python deprecation warnings remain: the pytest alias and legacy naive UTC calls. No new failed tests are suppressed.

The browser suite uses real Better Auth, signed proxy, PostgreSQL/Redis/Celery, OCR, catalog indexing, RFQ review, supplier attestation and quote submission/approval/history. Existing explicit UI fixtures stay labelled. Of four new cases, one reads actual native missing-price history; three simulate partial/staged/legacy presentation. The real quote flow again starts native research and reloads evidence. Images live under [screenshots](screenshots); old screenshot outputs were redirected into the new directory.

Commands used after loading the private isolated environment:

```powershell
$env:RFQ_TEST_DATABASE_URL=$env:DATABASE_URL.Replace('ownerpilot_rfq_phase3_demo_phase31_validation','ownerpilot_rfq_phase31_test')
.venv/Scripts/python.exe -m pytest apps/api/tests -q --junitxml=docs/rfq/phase3_1/results/regression-tests.xml
.venv/Scripts/ruff.exe check apps/api scripts/procurement31*.py
.venv/Scripts/python.exe -m compileall -q apps/api/src
python -m uv lock --project apps/api --check
pnpm lint
pnpm typecheck
pnpm test
pnpm build
# Final UI refinement: web lint/typecheck/build followed by server restart.
pnpm --dir apps/web lint
pnpm --dir apps/web typecheck
pnpm --dir apps/web build
$env:RFQ_WEB_URL='http://localhost:3041'
$env:RFQ_SCREENSHOT_DIR='../../docs/rfq/phase3_1/screenshots'
pnpm --dir apps/web exec playwright test
.venv/Scripts/python.exe scripts/procurement31-migration-check.py
.venv/Scripts/python.exe scripts/procurement31-historical-compare.py
.venv/Scripts/python.exe scripts/procurement31-report.py
.venv/Scripts/python.exe scripts/procurement31-recovery.py
.venv/Scripts/python.exe scripts/procurement31-preservation.py
git diff --check
```

The migration check dumps the historical populated synthetic demo read-only, restores to a uniquely named new database, and applies migration 0007 there. Hashes compare old columns of all original public/procurement tables, excluding the migration bookkeeping table whose new row is expected. No original database was reset, truncated or migrated by this check. Existing migrations and frozen historical artifacts match their protected hashes. All 152 current result artifacts have a separate [SHA-256 manifest](results/artifact-manifest.json); new JSON/XML files use explicit LF checkout rules.

Measured stack: PostgreSQL validation container 55433, dedicated Redis 6384 and Celery worker, FastAPI 8041, Ollama 11434, Next.js 3041. Models were already installed; no model download or cloud inference occurred. [Windows setup](WINDOWS_SETUP.md) records safe repetition and private state dependencies.
