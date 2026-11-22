# Windows setup and reproduction

Use PowerShell 7 in `G:\Project\AllFeaturedProjects\ownerpilot`. Keep Phase 1/2 services separate. PostgreSQL validation storage is disposable/tmpfs: archive synthetic state before stopping infrastructure. Never reset/truncate an application database.

```powershell
pnpm install --frozen-lockfile
python -m uv sync --project apps/api --group dev --frozen
pnpm --filter @ownerpilot/web exec playwright install chromium
ollama list
# Models must already be installed; no automatic downloads.
Invoke-RestMethod http://localhost:11434/api/show -Method Post -ContentType application/json -Body '{"model":"qwen3:8b"}' | Select-Object capabilities
docker compose -f infra/docker-compose.rfq-validation.yml up -d postgres
# Create each named database ONCE. If it exists, inspect/reuse it; never reset it.
docker exec ownerpilot-rfq-validation-postgres-1 createdb -U postgres ownerpilot_rfq_phase3_demo
docker exec ownerpilot-rfq-validation-postgres-1 createdb -U postgres ownerpilot_rfq_phase3_test
docker exec ownerpilot-rfq-validation-postgres-1 psql -U postgres -d ownerpilot_rfq_phase3_demo -c 'create extension if not exists vector'
docker exec ownerpilot-rfq-validation-postgres-1 psql -U postgres -d ownerpilot_rfq_phase3_test -c 'create extension if not exists vector'
```

Privately configure `.local/rfq/phase3/runtime-env.json`. Never commit or print its secrets. Required values: DATABASE_URL pointing at the new phase3_demo database; AUTH_SECRET and RFQ_AUTH_SECRET (at least 32 random characters, same RFQ secret in web/API); RFQ_REDIS_URL `redis://127.0.0.1:6383/0`; RFQ_STORAGE_ROOT absolute `.local/rfq/phase3/documents`; RFQ_OLLAMA_MODEL qwen3:4b; PROCUREMENT_AGENT_MODEL qwen3:8b; local Ollama endpoint; CATALOG_EMBED_MODEL nomic-embed-text:v1.5; web/API URLs below. The validation compose uses its documented disposable local PostgreSQL credentials; it is not production configuration.

```powershell
$runtime = Get-Content -Raw .local/rfq/phase3/runtime-env.json | ConvertFrom-Json
foreach ($property in $runtime.PSObject.Properties) {
  [Environment]::SetEnvironmentVariable($property.Name,[string]$property.Value,'Process')
}
$env:INTERNAL_API_BASE_URL='http://127.0.0.1:8033'
$env:NEXT_PUBLIC_API_BASE_URL='http://127.0.0.1:8033'
$env:NEXT_PUBLIC_APP_URL='http://localhost:3033'
$env:CORS_ORIGINS='http://localhost:3033'
pnpm --filter @ownerpilot/web auth:migrate:local
pnpm db:migrate
pnpm rfq:migrate
docker compose -f infra/docker-compose.procurement-validation.yml up -d --build
```

In separate terminals load the same private environment:

```powershell
# API
$env:PYTHONPATH='apps/api/src'
python -m uv run --project apps/api uvicorn api.main:app --host 127.0.0.1 --port 8033
# Web
pnpm build
pnpm --filter @ownerpilot/web exec next start --hostname 127.0.0.1 -p 3033
```

Open `http://localhost:3033/procurement`; use the real sign-in/signup UI and an authorized workspace. The worker registers RFQ, catalog and procurement tasks together. It uses host.docker.internal for PostgreSQL/Ollama and a distinct Redis on 6383. Its mounted documents directory belongs only to Phase 3.

For the repository's standard local Docker stack, the additive `infra/docker-compose.procurement.yml` overlay extends the existing base/RFQ overlays, registering all task types and model settings. Validate with `docker compose -f infra/docker-compose.yml -f infra/docker-compose.rfq.yml -f infra/docker-compose.procurement.yml config --quiet`. Apply auth/business/procurement migrations first and explicitly choose local installed model endpoints. This overlay was configuration-validated; the measured full-stack experiments used the isolated validation compose above. No deployment to the standard stack was performed.

```powershell
# Do not regenerate frozen files. These generators refuse overwrite.
python -m uv run --project apps/api python scripts/procurement-freeze.py
python -m uv run --project apps/api python scripts/procurement-freeze-batches.py
# Existing native records are resumed, not overwritten. Use a new output/version for a new experiment.
python -m uv run --project apps/api python scripts/procurement-evaluate.py --split development
python -m uv run --project apps/api python scripts/procurement-evaluate.py --split held_out
# Deliberate isolated worker kill; run only after browser/evaluation workloads finish.
python -m uv run --project apps/api python scripts/procurement-recovery.py
python -m uv run --project apps/api python scripts/procurement-migration-check.py
python -m uv run --project apps/api python scripts/procurement-preservation.py
```

Evaluator state is private `.local/rfq/phase3/evaluation-state.json` and refers to disposable DB IDs. Do not silently reuse it after database loss or change frozen outputs in place. Archive a new experiment location instead. Migration check creates a uniquely named additional test database; it does not restore over existing state. A previously failed sentinel setup left an empty isolated test database and was corrected, not reset.

```powershell
$env:RFQ_TEST_DATABASE_URL=$env:DATABASE_URL.Replace('ownerpilot_rfq_phase3_demo','ownerpilot_rfq_phase3_test')
python -m uv run --project apps/api --group dev pytest -c apps/api/pyproject.toml apps/api/tests -q --junitxml=docs/rfq/phase3/results/all-tests.xml
python -m uv run --project apps/api --group dev ruff check apps/api scripts/procurement-*.py --exclude legacy_v1
python -m uv run --project apps/api python -m compileall -q apps/api/src
python -m uv lock --project apps/api --check
pnpm lint
pnpm typecheck
pnpm test
pnpm build
$env:RFQ_WEB_URL='http://localhost:3033'
$env:RFQ_SCREENSHOT_DIR='../../docs/rfq/phase3/screenshots'
pnpm rfq:e2e
python -m uv run --project apps/api python scripts/procurement-report.py
```

Restart the local web server after rebuilding its production output. The existing Phase 2 services should not be pointed at the Phase 3 DB or stopped merely for this demo. No push, deployment, model download, supplier network access or Phase 4 action is part of these commands.
