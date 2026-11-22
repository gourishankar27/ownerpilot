# Acceptance criteria

| Boundary | Required behavior | Validation |
|---|---|---|
| Existing features | Preserve original tests, artifacts and migrations | Original 145 tests; original seven browser cases; preservation manifests |
| Retrieval | Exact/BM25/SQL have no embedding dependency; vector identity remains strict | Outage/digest regression tests; executed-channel metadata |
| Selection | No arbitrary newest-review winner; conflicts need explicit authorized resolution | Review digest, optimistic revision, source-version and compatibility tests |
| Offers | Import date cannot establish price freshness; no invented values | Separate imported/user-attested data; dates/source/actor/reason; append-only triggers |
| Agent | Actual local model native calls; no arbitrary tools or trusted model workspace | Real model traces; closed-schema, scope and allowlist tests |
| Grounding | Every accepted scalar has a valid receipt and exact typed JSON-pointer value | Independent verifier; retained unsupported candidates |
| Finance | Decimal, fixed rounding, explicit missing values and unit/currency policies | 34 standalone cases; 200 batch lines; independent manual checks |
| Approval | Roles, current revision/source snapshots, complete inputs and explicit review | HTTP integration tests and real signed-proxy browser flow |
| Immutability | Approved quote and evidence/history cannot be edited | API checks and PostgreSQL trigger tests |
| Reliability | Bounded calls/repeats/time/concurrency, durable receipts, cancel/recovery | Protocol tests, real SIGKILL experiment, repeated delivery |
| Quality | Aspirational 95% research completion/source attribution | Measured counts, never inferred from JSON validity |

The research completion aspiration is not met: 6/10 final native runs passed verification (4/8 held-out). Four unsupported candidate scalars were blocked. One frozen financial batch has a retained, independently diagnosed oracle-label defect, recorded as a strict expected failure. These are open quality limitations, not passed acceptance checks.
