# Windows local setup

Use PowerShell from the repository root. Python 3.14+, Node 24+, pnpm 10+, Docker
Desktop Linux engine and Ollama are required. No WSL migration is needed.

```powershell
git switch feature/rfq-intelligence-phase-1
python --version
node --version
pnpm --version
docker info
docker compose version
ollama list
nvidia-smi
python -m pip install uv
pnpm install --frozen-lockfile
python -m uv sync --project apps/api --group dev
```

For a new local installation, create an ignored `.env` from `.env.example`; preserve
any existing file. Generate independent random AUTH_SECRET and RFQ_AUTH_SECRET values:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
[Convert]::ToHexString([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
```

Store the generated values privately in `.env` and `apps/web/.env.local`. The web/API
RFQ_AUTH_SECRET values must match and be at least 32 characters. Choose an exact
installed RFQ_OLLAMA_MODEL from `ollama list`. The tested tag was `qwen3.8:27b`, 17 GB;
it is optional configuration, not a default or automatic download.

For the following commands, load the ignored `.env` into **each PowerShell terminal**
without evaluating it as PowerShell code or printing values:

```powershell
Get-Content .env | ForEach-Object {
  if ($_ -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
    [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim('"'), 'Process')
  }
}
```

Start existing PostgreSQL only if this is your intended development database:

```powershell
docker compose -f infra/docker-compose.yml up -d postgres
pnpm --filter @ownerpilot/web auth:migrate:local
pnpm db:migrate
pnpm rfq:migrate
```

`auth:migrate:local` uses the installed Better Auth library, avoiding the existing
floating `npx auth@latest` CLI. Drizzle now filters its explicit business table names
and public schema; it does not own Better Auth tables or procurement schema. Review
any existing Drizzle push prompts; do not accept unrelated destructive changes.
RFQ migrations are explicit additive SQL and never run a demo reset.

For native web/API plus Linux worker, use the same ignored storage directory:

```powershell
$env:RFQ_OLLAMA_URL='http://host.docker.internal:11434'
docker compose -f infra/docker-compose.yml -f infra/docker-compose.rfq.yml up -d --build redis rfq-worker rfq-dispatcher
```

The production overlay uses a named document volume shared by container API and
worker. Therefore run the API in its container for that overlay, or use the disposable
validation stack below for the verified native API/shared-bind-volume workflow.
Full container API path:

```powershell
docker compose -f infra/docker-compose.yml -f infra/docker-compose.rfq.yml up -d --build api web redis rfq-worker rfq-dispatcher
```

The original Compose Ollama service publishes port 11434. If native Ollama already
uses that port, avoid starting the base Ollama container: launch API/web with `--no-deps`
after PostgreSQL/Redis/worker are up, or stop the unused local service deliberately.
Do not expose native Ollama publicly to solve this. The worker host address was
verified with Docker Desktop's existing forwarding, without changing Ollama binding.

## Verified disposable development path

This path uses separate database port 55433, Redis 6380 and a tmpfs PostgreSQL
directory. Its data disappears when that container is removed. It never mounts an
existing application's database volume. Do not use it for durable business records.

```powershell
docker compose -f infra/docker-compose.rfq-validation.yml up -d postgres redis
$env:DATABASE_URL='postgresql://postgres:rfq-validation-local@127.0.0.1:55433/ownerpilot_rfq_validation'
$env:RFQ_TEST_DATABASE_URL=$env:DATABASE_URL
pnpm --filter @ownerpilot/web auth:migrate:local
# Initialize public schema and vector extension on this fresh DB:
docker compose -f infra/docker-compose.rfq-validation.yml exec postgres psql -U postgres -d ownerpilot_rfq_validation -c 'create extension if not exists vector;'
pnpm db:migrate
pnpm rfq:migrate
docker compose -f infra/docker-compose.rfq-validation.yml up -d --build worker
```

Then start these commands in separate terminals with matching environment values:

```powershell
python -m uv run --project apps/api uvicorn api.main:app --host 127.0.0.1 --port 8000
pnpm web:dev
```

Use localhost:3000/procurement. Create a real account and workspace from Overview.
The worker container and native API share `.local/rfq/documents`; Tesseract is built
into the container. No native Windows Celery multiprocessing is required.

## Checks and benchmarks

```powershell
pnpm lint
pnpm typecheck
pnpm test
pnpm build
python -m uv run --project apps/api python -m compileall -q apps/api/src
pnpm rfq:test
pnpm --filter @ownerpilot/web exec playwright install chromium
pnpm rfq:e2e
python -m uv run --project apps/api --group dev python scripts/rfq-runtime-check.py
# Generate only into a new dataset directory/version; the checked-in dataset is frozen.
pnpm rfq:generate
```

The generator intentionally refuses to overwrite the checked-in manifest. For a new
version call `generate(Path('data/evaluation/rfq-v2'))` from its module.
For repeatable in-process integration tests, use a separate disposable test database
or stop the validation worker while `pnpm rfq:test` runs; its independent dispatcher
can otherwise race jobs that a test intends to process explicitly. Restart the worker
before browser tests and the runtime recovery check.
Run evaluation sequentially (see EVALUATION); model calls can take ~100 seconds each
on this machine. Worker commands are in the Compose files. Production uses separate
worker and dispatcher processes; `-B` is only a convenience in the disposable stack.

Troubleshooting: `python -m uv` avoids Windows user-Scripts PATH issues. Use 127.0.0.1
for disposable PostgreSQL: localhost resolved slowly in this session. Start Docker
Desktop's Linux engine when the named-pipe error appears. Check `docker compose ... logs
worker`, `/health` and signed `/api/rfq-health`. Missing model and OCR are distinct
from parser errors. Stop test services with the validation Compose `down` command;
do not run existing database reset scripts. No migration or model download is implicit.
