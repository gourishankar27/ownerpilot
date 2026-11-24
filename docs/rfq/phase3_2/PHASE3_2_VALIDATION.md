# Phase 3.2 validation

**Functionally validated — research-quality target unmet.**

| Gate | Evidence/result |
| --- | --- |
| Backend regressions | 473 passed; 1 retained strict xfail; zero failures/errors (`results/final-backend-tests.xml`) |
| Browser regressions | 21 passed: original 15 unchanged plus 6 coverage scenarios (`results/final-browser.json`) |
| Python checks | Ruff lint/format on new code, compileall and uv lock check passed |
| Frontend checks | Root lint, typecheck, test and production build passed (`results/frontend-build.log`) |
| Native held-out | 52/60 selected-strategy verified completions; target 57 |
| Required line sources | 324/324; target 99% |
| Independent safety | 0 invalid accepted facts and 0 unauthorized successes across 240 held-out executions |
| Deterministic source pipeline | 96/96, zero model calls; separate baseline |
| Actual recovery | SIGKILL restart, duplicate terminal delivery, cancellation, Redis outage and refused endpoint passed |
| PostgreSQL interruption | Explicit controlled connection fixture passed; shared server not stopped |
| Migration upgrade | Original columns across 39 tables / 3,149 demo and 6,520 test rows preserved |
| Fresh migrations | All eight migrations applied twice idempotently in retained new database |
| Historical bytes | 724 protected files and 22 original test files unchanged |
| Model/score freeze | Selected execution/grading hashes and selection-summary hash unchanged |
| Native visible-description security probe | Actual local inference, no successful unauthorized action or fabricated accepted price; outside benchmark |
| Timing discipline correction | Original timings retained; regression-window exclusion plus twenty separately serialized development timing trials |

The prior strict xfail retains the historical JPY fractional-quantity policy limitation. It was not relabelled or fixed in this phase. Existing finance-v2 independent evaluation tests remain in the full regression suite. No download, cloud model, supplier communication, approval automation, push, deployment or Phase 4 work was performed.
