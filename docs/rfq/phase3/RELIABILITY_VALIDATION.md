# Reliability validation

## Actual worker death and recovery

`python scripts/procurement-recovery.py` targeted only `ownerpilot-procurement-validation-worker-1`, with an explicit phase3_demo database guard. It started a real native research job, waited for one durable tool receipt and the second planning turn, sent container **SIGKILL**, then restarted the worker. PostgreSQL released the session execution lock; the database outbox dispatcher recovered the stale job.

Observed recovery: **89.35 seconds**, delivery attempt **2**, final state **needs_attention** because the remaining turn budget did not yield supplier-offer coverage for every line. This is successful safe recovery/abstention, **not** a successful completed research summary. No completion result was published.

The first receipt retained the same ID/result; receipt ordinals stayed unique. Actual terminal task redelivery left receipts unchanged. Research completion events: 0. Scoped quote versions and approvals were 0 before/after. No quote or approval can be published by these read-only tools. Exact artifact: `results/worker-recovery.json`.

The original interrupted model turn remains counted. Recovery does not reset budgets or silently run unlimited replacement turns. This is why durable recovery can correctly require human attention instead of promising completion.

## Actual outages and cancellation

`scripts/procurement-runtime-check.py` launched separate loopback FastAPI processes on 8044 with the same isolated synthetic DB and real local HTTP transport. It tested an absent chat tag, installed Nomic embedding model lacking native tools, and unreachable local endpoint on port 9. All three reported unavailable model health and rejected research with HTTP 503. The saved human-selected deterministic quote still calculated USD 24.00 in each process. No main service or model was stopped and no weights were downloaded.

The same script started actual Celery/Ollama research, observed planning turn 1, cancelled over authenticated HTTP and verified final `cancelled`, zero additional receipts and no published summary. Existing model requests can continue until their bounded timeout; cancellation gates publication. Artifact: `results/runtime-validation.json`.

`scripts/procurement-retrieval-outage.py` also exercised the real learned catalog index with embedding endpoint `http://127.0.0.1:9`. Exact, BM25, SQL and exact+BM25 all completed without invoking embeddings; full hybrid failed explicitly without fallback. SQL returned zero candidates because this synthetic product has no description text, while the other three returned the known product. This is availability evidence, not a claim that SQL matching found a product. Artifact: `results/retrieval-outage.json`. The public matching API and UI expose these explicit methods while retaining reranked hybrid as the historical default.

## Protocol and database checks

Explicit fixtures test forbidden requests, invalid schemas/JSON, response size/timeout, repeated equivalent tools, tool-service failures, retry limits, source changes, idempotent starts and terminal duplicate deliveries. These are separate from the real SIGKILL/native counts. Failures have durable states/receipts and cannot make quotes complete.

The populated migration experiment created a new uniquely named database, applied original migrations 0001–0004, populated a business/workspace/approved RFQ sentinel and hashed all 27 original tables. Migrations 0005/0006 added seven tables. All original table hashes/counts were identical afterward; repeat migration passed. `results/migration-preservation.json` contains exact hashes. The first attempt omitted required approval metadata on its synthetic sentinel and rolled back; the corrected experiment supplied valid metadata. No application database was reset.

The final browser suite uses real PostgreSQL, Redis, Celery, FastAPI, Next.js, Better Auth, local neural indexing and native chat tool calls. It covers review/change/approval/reload immutability, evidence/history, expired and unselected lines, actual signed-proxy editor rejection, plus labeled UI outage fixtures. Original cases remain unchanged. An initial mobile overflow from the pre-existing catalog line selector was fixed with width constraints; captured failures remain separate from final results.

Operational limits: local single-inference concurrency, small synthetic tests, tmpfs validation DB, no production high-availability/backup/SLO proof, no large-scale crash campaign and no guarantee that recovered model work completes within the original budgets. Redis or model availability does not authorize bypassing commercial approval checks.
