# Reliability validation

Actual dedicated worker `ownerpilot-procurement32-validation-worker-1` received SIGKILL after a successful batch receipt. At the post-signal observation it had 2 durable receipts. Restart and outbox redelivery reached `needs_attention` in 121.22 seconds, with 4 receipts afterwards. All prior receipt rows remained equal, consumed budgets and original creation time were preserved, and duplicate terminal delivery changed no receipts. Publications: 0.

This is **safe recovery, incomplete research**. It is an actual Docker process death/restart, not a Python exception fixture. Pre-signal observation and post-signal ledger are both retained because receipts can commit while the kill command is in transit. The independently reconstructed before/after source coverage is in `results/real-recovery.json`.

The independent oracle found 4/12 covered lines before recovery and 12/12 afterwards. Remaining source reads completed without repeating the preserved work. The terminal error was `citation_correction_exhausted`; source completion did not bypass the citation gate. Counters after recovery: 2 planning, 1 initial finalization, 1 correction, 2 delivery attempts.

Actual Redis container `ownerpilot-procurement32-validation-redis-1` was stopped while signed API admission retained a queued database outbox row. After Redis restart, beat/worker delivery reached `complete`. Queue to first model admission: 11.00 seconds; broker restoration to terminal: 11.58 seconds. Publications: 1.

Actual cancellation was issued after a durable model call entered `in_flight`; request-start telemetry was observed afterwards. State remained cancelled with zero research publications. This proves cancellation against admitted actual inference; it does not claim a packet-level timestamp for exactly when Ollama began generation.

A genuinely refused local TCP endpoint produced `model_unavailable` attention and zero source tool calls. Ollama itself was left running. Shared PostgreSQL was also left running: the PostgreSQL interruption check is an explicitly controlled `psycopg.OperationalError` connection fixture between committed batch receipts, followed by restored connectivity and exact receipt reuse. It is not claimed as a real PostgreSQL server restart.

Controlled tests separately cover six interruption checkpoints (request admission, receipt persistence, coverage update, finalization receipt, materialization and pre-publication), source change between successful batches, duplicate/repeated calls, revocation, transport timeout, original deadline expiry and cancellation before receipt commit. Fixture results are excluded from native accuracy denominators.

Quote versions/approvals remained equal before and after all research/recovery operations. Read the actual counters and retained receipt IDs in `results/real-recovery.json`; native split-level quote-preservation files provide a separate check. Recovery stays within the original 240-second publication deadline and finite call limits; in-flight HTTP may finish later up to its transport timeout and cannot publish late.
