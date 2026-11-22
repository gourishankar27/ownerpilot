# Windows setup and reproduction

PowerShell7 in G:\Project\AllFeaturedProjects\ownerpilot. Use synthetic disposable DBs, never reset/truncate application data. Existing Phase 1.1 ports3011/8011 remain separate. Validation PostgreSQL uses tmpfs; archive needed disposable state before stopping it.

```powershell
pnpm install --frozen-lockfile
pnpm --filter @ownerpilot/web exec playwright install chromium
python -m uv sync --project apps/api --group dev --frozen
ollama list
# Only when absent and authorized; this user approved274MB:
ollama pull nomic-embed-text:v1.5
docker compose -f infra/docker-compose.rfq-validation.yml up -d postgres
# Create each named database once; do not reset if it already exists.
docker exec ownerpilot-rfq-validation-postgres-1 createdb -U postgres ownerpilot_rfq_phase2_demo
docker exec ownerpilot-rfq-validation-postgres-1 createdb -U postgres ownerpilot_rfq_phase2_test
$env:DATABASE_URL='postgresql://postgres:rfq-validation-local@127.0.0.1:55433/ownerpilot_rfq_phase2_demo'
docker exec ownerpilot-rfq-validation-postgres-1 psql -U postgres -d ownerpilot_rfq_phase2_demo -c 'create extension if not exists vector'
pnpm --filter @ownerpilot/web auth:migrate:local
pnpm db:migrate
pnpm rfq:migrate
docker compose -f infra/docker-compose.catalog-validation.yml up -d --build
$env:PYTHONPATH='apps/api/src'
$env:CATALOG_EMBED_MODEL='nomic-embed-text:v1.5'
$env:CATALOG_EMBED_URL='http://localhost:11434'
```

Populated migration validation used a synthetic pg_dump restored into a new empty database. Do not restore over application state. Auth, Drizzle and procurement migration ownership remains separate.

The ignored .local/rfq/phase2/runtime-env.json contains local private settings. On fresh installation generate independent AUTH_SECRET and RFQ_AUTH_SECRET of at least32 random characters; store privately alongside DATABASE_URL, RFQ_REDIS_URL=redis://127.0.0.1:6382/0, RFQ_STORAGE_ROOT=.local/rfq/phase2/documents, RFQ_OLLAMA_MODEL=qwen3:4b, INTERNAL_API_BASE_URL/NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8022, NEXT_PUBLIC_APP_URL/CORS_ORIGINS=http://localhost:3022. Same RFQ_AUTH_SECRET on API/web. Do not print/commit secrets.

```powershell
# Load shared private settings in each API/web terminal:
$runtime=Get-Content -Raw .local/rfq/phase2/runtime-env.json | ConvertFrom-Json
foreach($property in $runtime.PSObject.Properties){[Environment]::SetEnvironmentVariable($property.Name,[string]$property.Value,'Process')}
# Terminal1
python -m uv run --project apps/api uvicorn api.main:app --host 127.0.0.1 --port 8022
# Terminal2, same environment
pnpm build
pnpm --filter @ownerpilot/web exec next start --hostname 127.0.0.1 -p 3022
```

Import frozen data/evaluation/product-catalog/catalog.json through Catalog Intelligence preview/confirmation. The real worker builds embeddings/pgvector; BM25 reconstructs reproducibly from the published PG snapshot. The generator refuses overwrite; never regenerate committed held-out data in place.

```powershell
# Only for an absent fixture directory:
python -m uv run --project apps/api python scripts/catalog-generate.py
# Offline evaluation is explicitly separate from approval-bound application endpoints:
$env:DATABASE_URL='postgresql://postgres:rfq-validation-local@127.0.0.1:55433/ownerpilot_rfq_phase2_test'
$env:CATALOG_EVAL_OUT='docs/rfq/phase2/results/final-hardened'
python -m uv run --project apps/api python scripts/catalog-evaluate.py
```

Resume requires identical source/model/manifest. Changed code needs a new output folder. The state file .local/rfq/phase2-evaluation-state.json points to that test DB's index; after disposable DB loss archive stale state and use new outputs, never edit old metrics. The evaluator creates the source index and executes exact/hybrid ground-truth queries; no public free-query bypass exists.

```powershell
$env:RFQ_TEST_DATABASE_URL='postgresql://postgres:rfq-validation-local@127.0.0.1:55433/ownerpilot_rfq_phase2_test'
$env:RFQ_OLLAMA_MODEL='qwen3:4b'
python -m uv run --project apps/api --group dev pytest -c apps/api/pyproject.toml apps/api/tests -q
pnpm lint
pnpm typecheck
pnpm test
pnpm build
python -m uv run --project apps/api --group dev ruff check apps/api scripts/catalog-*.py --exclude legacy_v1
python -m uv run --project apps/api python -m compileall -q apps/api/src
python -m uv lock --project apps/api --check
$env:RFQ_WEB_URL='http://localhost:3022'
$env:RFQ_SCREENSHOT_DIR='../../.local/rfq/phase2/screenshots'
pnpm rfq:e2e
# Reload demo environment before this deliberate isolated worker termination:
python -m uv run --project apps/api python scripts/catalog-recovery.py
```

Recovery accepts only phase2_demo and kills only ownerpilot-catalog-validation-worker-1. Archive named experiment outputs before repeating. Better Auth signup retry respects the real limit. See security/reliability limitations before public hosting; no deployment was performed.
