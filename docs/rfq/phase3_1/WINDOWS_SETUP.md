# Windows reproduction

Use PowerShell 7 in `G:\Project\AllFeaturedProjects\ownerpilot`. Existing Phase 1/2/3 services use separate Redis ports and document mounts. Keep their databases and workers intact. PostgreSQL validation storage is disposable; archive synthetic state before stopping that infrastructure.

```powershell
pnpm install --frozen-lockfile
python -m uv sync --project apps/api --group dev --frozen
pnpm --dir apps/web exec playwright install chromium
ollama list
# qwen3:8b and nomic-embed-text:v1.5 must already be installed.
docker compose -f infra/docker-compose.rfq-validation.yml up -d postgres
# Create ONCE. Existing names must be inspected/reused, never reset.
docker exec ownerpilot-rfq-validation-postgres-1 createdb -U postgres ownerpilot_rfq_phase3_demo_phase31_validation
docker exec ownerpilot-rfq-validation-postgres-1 createdb -U postgres ownerpilot_rfq_phase31_test
docker exec ownerpilot-rfq-validation-postgres-1 psql -U postgres -d ownerpilot_rfq_phase3_demo_phase31_validation -c 'create extension if not exists vector'
docker exec ownerpilot-rfq-validation-postgres-1 psql -U postgres -d ownerpilot_rfq_phase31_test -c 'create extension if not exists vector'
```

Privately create `.local/rfq/phase3_1/runtime-env.json`, using the same environment keys as [Phase 3 setup](../phase3/WINDOWS_SETUP.md). Set DATABASE_URL to the new demo; RFQ_REDIS_URL to `redis://127.0.0.1:6384/0`; RFQ_STORAGE_ROOT to the absolute `.local/rfq/phase3_1/documents` directory; INTERNAL_API_BASE_URL and NEXT_PUBLIC_API_BASE_URL to `http://127.0.0.1:8041`; NEXT_PUBLIC_APP_URL and CORS_ORIGINS to `http://localhost:3041`; local model URLs to `http://localhost:11434`; agent model to `qwen3:8b`; embedding model to `nomic-embed-text:v1.5`. Use private random AUTH_SECRET/RFQ_AUTH_SECRET values, at least 32 characters, with the RFQ secret shared between API and web. Never print or commit this file. The compose file contains the existing disposable validation database credentials, not production configuration.

```powershell
$runtime = Get-Content -Raw .local/rfq/phase3_1/runtime-env.json | ConvertFrom-Json
foreach ($property in $runtime.PSObject.Properties) {
  Set-Item -Path ('env:' + $property.Name) -Value $property.Value
}
$env:PYTHONPATH='apps/api/src'
pnpm --dir apps/web auth:migrate:local
pnpm db:migrate
python -m uv run --project apps/api python -m api.rfq.db
docker compose -f infra/docker-compose.procurement31-validation.yml up -d --build
```

Initialize the new **test** database's auth/business schema in a separate terminal using its DATABASE_URL, followed by the same additive RFQ migrations. Tests also verify migration checksums. Do not point integration tests at an application database.

Load the private environment in each terminal, then start the API and web:

```powershell
python -m uv run --project apps/api uvicorn api.main:app --host 127.0.0.1 --port 8041
# Separate terminal, same environment:
pnpm build
pnpm --dir apps/web exec next start --hostname 127.0.0.1 -p 3041
```

Run source preparation/evaluation sequentially, with no other model workload. These commands resume existing artifacts without overwriting them; use a new experiment name for any changed code/model. Frozen generators refuse overwrite. Keep private state files paired with their original database.

```powershell
python -m uv run --project apps/api python scripts/procurement31-evaluate.py --split development --experiment dev-contract6
python -m uv run --project apps/api python scripts/procurement31-evaluate.py --split validation --experiment dev-contract6
python -m uv run --project apps/api python scripts/procurement31-evaluate.py --split held_out --experiment dev-contract6
# Clone populated old Phase 3 database into a uniquely named new database:
python -m uv run --project apps/api python scripts/procurement31-migration-check.py
# Requires the old ten-case private state and retained populated clone:
python -m uv run --project apps/api python scripts/procurement31-historical-compare.py
python -m uv run --project apps/api python scripts/procurement31-report.py
python -m uv run --project apps/api python scripts/procurement31-preservation.py
# Deliberate kill of ONLY the isolated Phase 3.1 worker, after evaluation:
python -m uv run --project apps/api python scripts/procurement31-recovery.py
```

The historical comparison depends on the previously populated Phase 3 synthetic demo/private state. Fresh users without it can reproduce the independent v2 corpus and retain historical published results as recorded observations. Do not rerun old scripts that overwrite `docs/rfq/phase3` outputs or kill its worker.

```powershell
$env:RFQ_TEST_DATABASE_URL=$env:DATABASE_URL.Replace('ownerpilot_rfq_phase3_demo_phase31_validation','ownerpilot_rfq_phase31_test')
python -m uv run --project apps/api --group dev pytest -c apps/api/pyproject.toml apps/api/tests -q --junitxml=.local/rfq/phase3_1/repeated-tests.xml
python -m uv run --project apps/api --group dev ruff check apps/api scripts/procurement31*.py
python -m uv run --project apps/api python -m compileall -q apps/api/src
python -m uv lock --project apps/api --check
pnpm lint
pnpm typecheck
pnpm test
pnpm build
# Restart the web server after its production build, then:
$env:RFQ_WEB_URL='http://localhost:3041'
$env:RFQ_SCREENSHOT_DIR='../../.local/rfq/phase3_1/repeated-screenshots'
pnpm --dir apps/web exec playwright test
```

The new native-history browser cases require completed `dev-02` results and the Phase 3.1 demo database. Their screenshots have Phase 3.1 paths; original tests receive RFQ_SCREENSHOT_DIR so historical images cannot be overwritten. Actual measured artifacts live in `results/`; keep fresh repetition output under `.local` or a new named experiment. No command downloads model weights or changes a production deployment.
