# Phase 3 validation record

Branch `feature/rfq-intelligence-phase-3`, base `dd3bd99c6fede176d987aab41b1478ea3ba41ca6`. Local validation on November 21, 2026, America/Phoenix. No push/deployment or Phase 4 action.

| Command / check | Measured result | Artifact |
|---|---|---|
| Original backend baseline after checkout repair | 145 passed | baseline-tests-checkout-fixed.xml |
| Original seven browser baseline after repair | 7 passed | baseline-browser-checkout-fixed.json |
| Full Python suite, disposable phase3_test | 260 passed, 1 strict expected failure | all-tests.xml |
| Final Playwright suite, real services | See browser-final.json; original seven plus four new cases | browser-final.json |
| Frozen native benchmark | 6/10 verified complete; 30/30 authorized successful tools; 0/80 accepted unsupported claims | agent/summary.json, agent/*.json |
| 34 standalone financial cases | 34 matched expected outcomes | all-tests.xml / frozen scenarios.json |
| 200 batch financial line amounts | All matched; 19/20 total labels matched; one retained oracle defect | quote-batches.json, known-oracle-defect.json |
| Real SIGKILL recovery | Safe receipt preservation/abstention; attempt 2, 89.35 s; final needs_attention | worker-recovery.json |
| Real model capability/outage HTTP probes | 3/3 blocked research; deterministic USD 24.00 preserved | runtime-validation.json |
| Real embedding endpoint outage | 4/4 non-vector methods completed; hybrid explicitly unavailable | retrieval-outage.json |
| Real in-flight cancellation | Cancelled; no new receipts/summary | runtime-validation.json |
| Populated Phase 2 -> Phase 3 migrations | 27 original tables unchanged, seven new tables; repeat passed | migration-preservation.json |
| Historical preservation | 434 protected, 362 byte-identical + 72 verified checkout repairs, no unexpected changes | preservation-final.json |
| Ruff, compileall, dependency lock | Passed | validation-commands.json |
| Frontend lint/typecheck/test/build | Passed | validation-commands.json |

Exact main test commands:

```powershell
$env:PYTHONPATH='apps/api/src'
$env:RFQ_TEST_DATABASE_URL=$env:DATABASE_URL.Replace('ownerpilot_rfq_phase3_demo','ownerpilot_rfq_phase3_test')
.venv/Scripts/python.exe -m pytest -c apps/api/pyproject.toml apps/api/tests -q --junitxml=docs/rfq/phase3/results/all-tests.xml
.venv/Scripts/ruff.exe check apps/api scripts/procurement-*.py --exclude legacy_v1
.venv/Scripts/python.exe -m compileall -q apps/api/src
python -m uv lock --project apps/api --check
pnpm lint
pnpm typecheck
pnpm test
pnpm build
$env:RFQ_WEB_URL='http://localhost:3033'
$env:RFQ_SCREENSHOT_DIR='../../docs/rfq/phase3/screenshots'
pnpm --dir apps/web exec playwright test
.venv/Scripts/python.exe scripts/procurement-preservation.py
```

These use the existing private environment file; no secrets are included here. `pnpm test` is the repository's type-level package check, not an additional unit-test count. Pytest has existing AnyIO/deprecated datetime warnings. The one xfail is the retained batch-09 expected-label defect, not an unreported skipped security test. Its independently audited correct tax/total also has a passing test.

Initial failures are preserved: checkout-corrupted baseline, intermediate checkout attempt, development model experiments, interrupted browser debugging notes and the diagnosed mobile overflow. None are counted as final passes. Actual native tool calls are distinct from deterministic protocol fixtures and simulated UI outages.

The aspirational 95% research-completion target remains unmet. Recovery preserved correctness but did not produce a completed summary. Large independent native validation and live supplier verification remain outside demonstrated capability. Final status therefore distinguishes implemented functionality from full quality acceptance.
