# Windows reproduction and demonstration

Run PowerShell7 in `G:\Project\AllFeaturedProjects\ownerpilot`. Docker Desktop must use Linux containers; Ollama stays on the Windows host. The commands below target synthetic disposable state. Existing Phase1 services on3000/8000/6380 stay separate. The validation PostgreSQL service uses tmpfs: stopping/removing it loses its disposable data. Do not run demo:reset, truncate prompts or destructive Drizzle flags against application databases.

## Dependencies and installed models

```powershell
pnpm install --frozen-lockfile
python -m uv sync --project apps/api --group dev --frozen
ollama list
ollama ps
nvidia-smi
```

For this execution the user authorized both new weight downloads; installed tags/digests are recorded in results/final/environment.json. Only run these pulls when authorized and the tags are absent: qwen3:4b is about2.5GB and qwen3:8b about5.2GB. Runtime memory exceeds checkpoint size. No14B checkpoint was installed or needed for this experiment.

```powershell
ollama pull qwen3:4b
ollama pull qwen3:8b
```

## Isolated database and services

Start only the disposable PostgreSQL service if it is not already running. Create each named database once; if it already exists, use it without resetting it.

```powershell
docker compose -f infra/docker-compose.rfq-validation.yml up -d postgres
docker exec ownerpilot-rfq-validation-postgres-1 createdb -U postgres ownerpilot_rfq_phase11_demo
docker exec ownerpilot-rfq-validation-postgres-1 createdb -U postgres ownerpilot_rfq_phase11_test
docker exec ownerpilot-rfq-validation-postgres-1 createdb -U postgres ownerpilot_rfq_phase11_reference
$env:DATABASE_URL='postgresql://postgres:rfq-validation-local@127.0.0.1:55433/ownerpilot_rfq_phase11_demo'
docker exec ownerpilot-rfq-validation-postgres-1 psql -U postgres -d ownerpilot_rfq_phase11_demo -c 'create extension if not exists vector'
pnpm --filter @ownerpilot/web auth:migrate:local
pnpm db:migrate
pnpm rfq:migrate
docker compose -f infra/docker-compose.rfq-phase11.yml up -d --build
```

Fresh schema setup should require no truncate operation. Existing legacy databases need the separate compatibility review below. The isolated compose file binds only Redis6381, reuses disposable PostgreSQL55433, binds a private document directory, limits worker memory2GiB and concurrency1, and selects qwen3:4b full schema. Do not start its worker against an application DB by substituting credentials casually.

Create a private shared environment once. Do not print, commit or change its secrets while API/web are running. If the file already exists, reuse it.

```powershell
$configPath = Join-Path $PWD '.local/rfq/phase1_1/runtime-env.json'
if (-not (Test-Path -LiteralPath $configPath)) {
  New-Item -ItemType Directory -Path (Split-Path $configPath) -Force | Out-Null
  $runtime = @{
    DATABASE_URL='postgresql://postgres:rfq-validation-local@127.0.0.1:55433/ownerpilot_rfq_phase11_demo'
    AUTH_SECRET=[Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
    RFQ_AUTH_SECRET=[Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
    RFQ_STORAGE_ROOT=(Join-Path $PWD '.local/rfq/phase1_1/documents')
    RFQ_REDIS_URL='redis://127.0.0.1:6381/0'
    RFQ_OLLAMA_MODEL='qwen3:4b'
    RFQ_MODEL_CONTEXT='8192'
    RFQ_MODEL_OUTPUT_TOKENS='4096'
    INTERNAL_API_BASE_URL='http://127.0.0.1:8011'
    NEXT_PUBLIC_API_BASE_URL='http://127.0.0.1:8011'
    NEXT_PUBLIC_APP_URL='http://localhost:3011'
    CORS_ORIGINS='http://localhost:3011'
  }
  $runtime | ConvertTo-Json | Set-Content -LiteralPath $configPath
}
$runtime = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
foreach ($property in $runtime.PSObject.Properties) {
  [Environment]::SetEnvironmentVariable($property.Name, [string]$property.Value, 'Process')
}
$env:PYTHONPATH='apps/api/src'
$env:RFQ_WEB_URL='http://localhost:3011'
$env:RFQ_MODEL_SCHEMA_PROFILE='full'
$env:RFQ_OCR_STRATEGY='enhanced-v2'
```

In two separate terminals, load the same private environment block above first:

```powershell
python -m uv run --project apps/api uvicorn api.main:app --host 127.0.0.1 --port 8011
```

```powershell
pnpm build
pnpm --filter @ownerpilot/web exec next start --hostname 127.0.0.1 -p 3011
```

Use http://localhost:3011/procurement, sign up with a fictional example.test account, and create a synthetic workspace. API8011 and worker share the same private storage files and disposable DB; the browser uses Better Auth and the signed proxy. Do not point Playwright at the older3000 stack when validating Phase1.1.

## Dataset generation and preservation

The committed v1/v2 datasets are frozen. Do not regenerate in place. The generator refuses to overwrite an existing manifest. To inspect reproducibility in a new diagnostic directory:

```powershell
python -m uv run --project apps/api --group dev python -c "from pathlib import Path; from api.rfq.evaluation.generate_v2 import generate; generate(Path('data/evaluation/rfq-v2-reproduction'))"
python -m uv run --project apps/api python scripts/rfq-preservation.py verify
```

Rendering and ZIP library versions can affect regenerated byte hashes. The committed frozen bytes, rather than a later regeneration, define final evaluation. The generator module's default command is `python -m api.rfq.evaluation.generate_v2`; it deliberately exits when the frozen default manifest exists.

## OCR development experiments

Use a new output directory for repeats; selected enhanced-v2 and optional targeted-v2/combined-v2 run inside Linux with Tesseract. The source bind mount ensures current code; no model calls are made.

```powershell
foreach ($strategy in @('enhanced-v2','targeted-v2','combined-v2')) {
  docker compose -f infra/docker-compose.rfq-validation.yml run --rm --no-deps -v "${PWD}:/workspace" -w /workspace -e PYTHONPATH=/workspace/apps/api/src worker python -m api.rfq.evaluation.quality_run --dataset data/evaluation/rfq-v2 --split dev --mode deterministic --ocr $strategy --output "docs/rfq/phase1_1/results/ocr/reproduction-$strategy.json"
  if ($LASTEXITCODE -ne 0) { throw "OCR experiment failed: $strategy" }
}
```

The original phase1 parser can be selected with `--policy phase1`; it uses legacy OCR regardless of the selected-v2 strategy. Initial failed grid experiments are historical new artifacts and must not be overwritten by later parser code.

## Controlled model benchmarks

Close other inference workloads. The script unloads resident models for a cold first document, then evaluates a different warm document and samples actual GPU/system RAM. It never downloads weights. Use unique output folders; reusing old names with different source fingerprints is rejected by the evaluator.

```powershell
$env:RFQ_MODEL_BENCH_DIR='docs/rfq/phase1_1/results/models/reproduction-full'
$env:RFQ_BENCH_MODELS='qwen3:4b,qwen3:8b,qwen3.8:27b'
$env:RFQ_BENCH_PROFILE='full'
$env:RFQ_BENCH_INCLUDE_FULL='0'
$env:RFQ_BENCH_FULL_WARM='1'
python -m uv run --project apps/api python scripts/rfq-model-bench.py
```

Compact experiments use RFQ_BENCH_PROFILE=compact, RFQ_COMPACT_PROMPT_VERSION=extract_v2 or extract_v3, and a separate RFQ_MODEL_BENCH_DIR for each. Full uses output4096; compact uses2048. Do not pool compact/full timing or compare cold/warm as equivalent.

## Full evaluation and resume

These are the exact selected configuration flags. Use existing output names only to resume the same frozen source/configuration; a changed tree requires a new output prefix. On the completed source snapshot, repeats simply reconstruct reports from saved journals. An incomplete JSONL tail must be preserved and repaired explicitly; no silent truncation occurs.

```powershell
foreach ($dataset in @('rfq','rfq-v2')) {
  $split = if ($dataset -eq 'rfq') { 'heldout' } else { 'evaluation' }
  foreach ($mode in @('deterministic','llm','hybrid')) {
    docker compose -f infra/docker-compose.rfq-validation.yml run --rm --no-deps -v "${PWD}:/workspace" -w /workspace -e PYTHONPATH=/workspace/apps/api/src worker python -m api.rfq.evaluation.quality_run --dataset "data/evaluation/$dataset" --split $split --mode $mode --profile full --model qwen3:4b --context 8192 --output-tokens 4096 --output "docs/rfq/phase1_1/results/final/$dataset-$mode.json"
    if ($LASTEXITCODE -ne 0) { throw "Evaluation failed: $dataset $mode" }
  }
}
python -m uv run --project apps/api python scripts/rfq-phase11-report.py
```

For fresh comparisons replace the output filenames; keep manifest/sample IDs/config fixed. `--stratified` selects one document per layout for a new eight-document run, while the published new matched-eight table is a subset of its homogeneous32-document execution. `--policy phase1` explicitly reproduces old extraction. Historical results directories must never be output targets.

## Regression checks and real workflows

```powershell
$env:RFQ_TEST_DATABASE_URL='postgresql://postgres:rfq-validation-local@127.0.0.1:55433/ownerpilot_rfq_phase11_test'
$env:RFQ_OLLAMA_MODEL='qwen3:4b'
pnpm lint
pnpm typecheck
pnpm test
pnpm build
python -m uv run --project apps/api python -m compileall -q apps/api/src apps/api/tests
python -m uv run --project apps/api --group dev ruff check apps/api --exclude legacy_v1
python -m uv lock --project apps/api --check
python -m uv run --project apps/api --group dev pytest -c apps/api/pyproject.toml apps/api/tests -q --junitxml=.local/rfq/phase1_1/final-tests.xml
$env:RFQ_WEB_URL='http://localhost:3011'
$env:RFQ_SCREENSHOT_DIR='../../.local/rfq/phase1_1/screenshots'
pnpm rfq:e2e
python -m uv run --project apps/api python scripts/rfq-phase11-workflows.py
python -m uv run --project apps/api --group dev python scripts/rfq-phase11-runtime-check.py
python -m uv run --project apps/api python scripts/rfq-preservation.py verify
```

Real-workflow scripts append synthetic DB state and write named new reports; choose/archive report names before repeating if preserving an experiment. The runtime check deliberately kills only the named isolated Phase1.1 worker during OCR and restarts it. Do not use it on another container. Better Auth signup is rate limited; repeated browser suite runs can legitimately receive429. Preserve failed reports and allow the window to expire; do not disable production auth limits to make a test pass. The frozen legacy_v1 directory is excluded from formatting/lint rewrites because its exact bytes are preservation evidence.

## Migration compatibility reproduction

Fresh reference: select ownerpilot_rfq_phase11_reference as DATABASE_URL, create vector and run the installed auth/Drizzle/RFQ migrators as above. A representative legacy synthetic copy needs the additive suppliers SQL before structurally identical constraint renaming. These commands are for a disposable copy only:

```powershell
$env:DATABASE_URL='postgresql://postgres:rfq-validation-local@127.0.0.1:55433/ownerpilot_rfq_phase11_compat'
$env:RFQ_SCHEMA_REFERENCE_DATABASE_URL='postgresql://postgres:rfq-validation-local@127.0.0.1:55433/ownerpilot_rfq_phase11_reference'
Get-Content -Raw infra/migrations/20261119_public_suppliers_compat.sql | docker exec -i ownerpilot-rfq-validation-postgres-1 psql -U postgres -d ownerpilot_rfq_phase11_compat
python -m uv run --project apps/api python scripts/rfq-reconcile-constraints.py --output .local/rfq/phase1_1/compat-dry-run.json
python -m uv run --project apps/api python scripts/rfq-reconcile-constraints.py --apply --output .local/rfq/phase1_1/compat-applied.json
pnpm db:migrate
pnpm rfq:migrate
```

The stronger preservation check copies only synthetic demo state to another new DB, reproduces legacy names, verifies3 existing approvals/auth/history and deliberately forces transaction rollback. Create this clone once and do not restore over existing application data:

```powershell
docker exec ownerpilot-rfq-validation-postgres-1 pg_dump -U postgres -d ownerpilot_rfq_phase11_demo -Fc -f /tmp/phase11-populated.dump
docker exec ownerpilot-rfq-validation-postgres-1 createdb -U postgres ownerpilot_rfq_phase11_populated
docker exec ownerpilot-rfq-validation-postgres-1 pg_restore -U postgres -d ownerpilot_rfq_phase11_populated /tmp/phase11-populated.dump
$env:DATABASE_URL='postgresql://postgres:rfq-validation-local@127.0.0.1:55433/ownerpilot_rfq_phase11_populated'
python -m uv run --project apps/api python scripts/rfq-phase11-migration-check.py
pnpm db:migrate
pnpm rfq:migrate
```

## Demonstration steps

Open3011/procurement and create a fictional workspace. Upload `data/evaluation/rfq/sources/rfq-05-00.xlsx` for a clean table, choose hybrid, process and inspect actual calls0. For scanned geometry use v2/sources/v2-00-00.pdf, deterministic mode, inspect MPN raw OCR/box/confidence and correct it by visual source review; do not treat the OCR confidence as accuracy. For partial routing upload diagnostics/sources/partial.txt in hybrid mode; inspect history/routing and the unresolved model row rather than claiming successful recovery. The diagnostics are under `data/evaluation/rfq-phase11-diagnostics`.

Review every line, enter an explicit reason for corrections, confirm the approval checkbox and approve. Refresh to verify persistence and locked approval. Reprocess only unapproved RFQs with a reason to create a new version. The real crash check above demonstrates recovery separately. Browser screenshots in results/final/screenshots show actual evidence, reviewed approval and Linux OCR; the OCR-disagreement UI fixture is explicitly separate and is not an OCR-quality measurement.
