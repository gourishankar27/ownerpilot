# Windows validation setup

Use the existing Python/uv environment, pnpm workspace, Docker Desktop Linux containers, PostgreSQL/pgvector and local Ollama. This phase downloads no weights. qwen3:8b and nomic-embed-text:v1.5 were already authorized and installed in earlier phases.

The new validation database is `ownerpilot_rfq_phase3_demo_phase31_validation_phase32`, with disposable integration database `ownerpilot_rfq_phase32_test`. The dedicated compose project uses Redis 6385 and the existing PostgreSQL host port 55433. The API listens on 8042 and web on 3042. Existing older stacks are left intact. The long demo database name retains the historical browser suite's validation guard.

Private runtime configuration is in `.local/rfq/phase3_2/runtime-env.json`; never commit or print its credentials. Load it in PowerShell:

```powershell
$runtime = Get-Content .local/rfq/phase3_2/runtime-env.json | ConvertFrom-Json
$runtime.PSObject.Properties | ForEach-Object {
  Set-Item -Path ('env:' + $_.Name) -Value $_.Value
}
```

`scripts/procurement32-setup.py` creates new clones of prior validation databases, compares old columns across the migration and retains both databases. It refuses to reset an existing Phase 3.2 runtime. `scripts/procurement32-migration-check.py` creates a uniquely named empty test database, applies all eight migrations twice and completes isolated historical blob copies without overwriting mismatched data. Both scripts retain their targets for inspection.

```powershell
.venv/Scripts/python.exe scripts/procurement32-setup.py
docker compose -f infra/docker-compose.procurement32-validation.yml up -d --build
.venv/Scripts/python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8042
# In another configured terminal:
pnpm --filter @ownerpilot/web build
pnpm --filter @ownerpilot/web exec next start --port 3042
```

Use separate terminals for long-lived API/web processes. Background launch helpers on Windows must hide service windows. Do not stop the shared PostgreSQL container to simulate an outage. Recovery probes operate only on the dedicated Phase 3.2 worker and Redis containers.

The existing frozen dataset and prepared sources should be reused. The freezer refuses overwrite. Source preparation uses real signed requests and local embeddings. Run only one model experiment/recovery/browser inference workload at a time; the evaluator pauses its dedicated worker while owning inline execution. Do not rebuild/restart that paused worker during an experiment.

```powershell
.venv/Scripts/python.exe scripts/procurement32-evaluate.py --split held_out --experiment final-plan7
.venv/Scripts/python.exe scripts/procurement32-report.py --experiment final-plan7
```

The evaluator skips finished trials with matching hashes and refuses an unfinished admitted trial or changed configuration. Inspect and resume the durable original run; do not delete evidence or silently create a replacement. The released held-out result is the first frozen run, never a selectively retried score.
