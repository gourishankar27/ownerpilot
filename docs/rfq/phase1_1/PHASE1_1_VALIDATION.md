# Phase 1.1 validation record

Status: implementation and mandatory local functional checks complete, with unmet extraction performance targets. This validates local mechanics on synthetic data; model repair and OCR recognition remain materially weaker than required for unattended use. Phase2 is not implemented.

Starting commit c752ae855bbbe639b2c37ee5774b9a7fd484108e; dedicated branch feature/rfq-intelligence-phase-1-1. The supplied main merge commit was not in local history, so no unsupported merge-history claim is made. Final extraction source fingerprint ae593462a75cf0a2c86e849c53e515b9e456df7080e7b9dc8abb13cfce59c9f3 is identical across all six final configs. Frontend/tests/docs changes after selection do not change that extraction fingerprint.

| Check | Exact command or artifact | Result |
|---|---|---|
| Baseline backend | pytest apps/api/tests -m 'not ollama' on separate test DB |57 passed,1 real-model test deselected; baseline genuine hybrid inference separately executed |
| Original baseline browser | pnpm rfq:e2e before feature tests |4 passed |
| Final Python suite | python -m uv run --project apps/api --group dev pytest -c apps/api/pyproject.toml apps/api/tests -q --junitxml=.local/rfq/phase1_1/final-tests.xml |103 passed,0 failed,0 skipped, including real Ollama and original legacy API regressions |
| Final browser | RFQ_WEB_URL=http://localhost:3011 pnpm rfq:e2e |6 passed,0 failed/skipped/flaky; latest browser-ocr-label-final.json, previous browser-checks.json and browser-resumed.json retained |
| Frontend lint | pnpm lint |Exit0 |
| Types | pnpm typecheck |Exit0 |
| Repository test script | pnpm test |Exit0; this script performs type-level checks, not a separate frontend unit count |
| Production bundle | pnpm build |Exit0 on Next16.2.6,17 routes |
| Python lint | python -m uv run --project apps/api --group dev ruff check apps/api --exclude legacy_v1 |Exit0; new experiment scripts also checked |
| Python compilation | python -m uv run --project apps/api python -m compileall -q apps/api/src apps/api/tests scripts |Exit0 |
| Lock consistency | python -m uv lock --project apps/api --check |Exit0,57 packages |
| Fresh migration | Auth installed migrator, vector, pnpm db:migrate, pnpm rfq:migrate |Exit0 on fresh disposable DB |
| Populated migration | scripts/rfq-phase11-migration-check.py; pnpm db:migrate; pnpm rfq:migrate |225 rows across27 tables,3 approvals preserved;16 equivalent renames; repeat0; forced rollback pass |
| Artifact preservation | python -m uv run --project apps/api python scripts/rfq-preservation.py verify |128 protected files, changed[] |
| Frozen v1/v2 hashes | test_frozen_v1_and_v2_payload_hashes |All96 source and96 truth files match manifests |
| Full evaluation | final/*-{deterministic,llm,hybrid}.json |192 actual attempts/192 planned;0 failed jobs;0 skipped samples |
| Real integration | real-workflows.json |Actual HTTP/DB/Redis/Linux Tesseract/Ollama, review/approval and cross-workspace denial |
| Crash/delivery | worker-restart.json |Actual SIGKILL, recovery attempt2,3 repeated deliveries,1 run |

There are45 added backend cases beyond the original58:27 selective/evidence/provider/matcher cases,4 job integration cases,6 resource cases and8 additional evaluator/hash cases. The final suite includes the originally gated real-model test. Four existing warnings remain: one AnyIO/pytest deprecation and three uses of datetime.utcnow in unchanged legacy business code.

Browser scenarios preserve the four existing flows and add an explicitly mocked quality-filter/evidence fixture plus actual Linux OCR geometry/confidence. The original unavailable-model browser scenario is explicitly simulated. Only the real OCR case and real integration/model benchmarks establish OCR/inference execution; fixtures never enter quality metrics. Signup helper honors Better Auth X-Retry-After once on429, with a bounded wait; auth configuration and assertions are unchanged.

Previous failures are retained in local logs and described honestly: an early regression removed an import used by an existing monkeypatch, then was fixed; initial OCR grid variants found no items and remain in results/ocr; workflow script initially referenced a nonexistent digital fixture, corrected to an existing native PDF; one browser attempt used the old3000 backend; another expected the wrong UI text ('Raw OCR:' versus 'Raw OCR reading:'); repeated signup runs hit real429 limits. The final test helper respects those limits rather than disabling them. These earlier attempts are not counted as passing final executions.

No complete hostile-file corpus, public penetration test, concurrent multi-worker load experiment, real procurement corpus, in-flight GPU cancellation proof or SIGKILL-during-inference experiment was performed. None is represented as passed. Actual OCR recovery plus atomic cancellation/duplicate tests establish the bounded local reliability gate; broader production hardening remains open.

On resuming November21, Docker services had stopped and the disposable PostgreSQL
tmpfs data was gone. The isolated demo database was recreated only after verifying
it did not exist, and restored from the saved synthetic pg_dump, including its3
approved RFQs. Existing application databases were not restored over or reset.
The Phase1.1 API8011/web3011/Redis6381/worker were restarted, then all six browser
scenarios passed again in23.9seconds. The original final benchmark/test artifacts
remain intact; browser-resumed.json records the new execution separately. The
source/configuration fingerprint and128-file preservation check still match.

Visual QA also caught an OCR source-label bug: deterministic extraction from OCR
retains method=deterministic, so checking method=tesseract alone mislabeled those
rows as native. The UI now also uses retained raw OCR/confidence metadata to show
OCR-derived. The real browser scenario asserts that label. This presentation fix
does not alter extraction code, saved predictions or final evaluation results.
After that fix, web lint/typecheck/build exited0 and the full production browser
suite passed6/6 again in23.7seconds. Updated actual OCR screenshots show the corrected
source label. The original103-case backend execution remains the final extraction
suite because extraction behavior did not change during the presentation fix.

Performance: v1 hybrid98/160 MPN,86/160 quantity,F1=78.87%; v2 hybrid78/160 MPN,97/160 quantity,F1=71.68%. The v2 scanned subset has0/40 exact MPNs and18/40 quantities. Matched-eight latency drops to2.987s P95 from fresh117.643s, but quality regresses; it is not an equivalent-quality improvement. All exact counts, subset definitions and failed target rows are in [EVALUATION_RESULTS.md](EVALUATION_RESULTS.md) and performance-gates.json.
