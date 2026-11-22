# Reliability validation

PostgreSQL version rows are the durable outbox; beat redispatches queued/stale-building jobs. Session advisory lock serializes each build; max3 attempts. Vectors stage in bounded memory; products/state/active-pointer/audit publish in one transaction. Newer confirmed versions prevent older work winning. Failed embedding batches publish no products. Repeated confirmation/delivery is idempotent.

Real Linux SIGKILL during actual neural indexing recovered on attempt2:zero partial vectors visible,1020 vectors published once after3 repeated deliveries. Raw evidence:results/worker-recovery.json. Fixture tests separately cover embedding failure, stale index, unauthorized/duplicate reviews; no fixture counts as quality. Populated migration preserved26 legacy table contents with6 additive tables; repeat identical. Broad concurrent-import/load, Redis outage and DB outage drills were not separately executed; no blanket claim that they passed.
