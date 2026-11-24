# Implementation and validation plan

1. Freeze historical bytes and rerun baseline checks.
2. Add a versioned closed batch tool, exact parent-receipt evidence verification and an additive migration.
3. Implement authoritative source coverage, bounded remaining-work feedback and four explicitly attributed strategies.
4. Independently author and freeze 96 procurement-v3 cases (16 development, 20 validation, 60 held-out), then prepare their actual approved sources before selecting a strategy.
5. Run real local native tool calls on development and validation; preserve experiments and exact source hashes. Select the primary strategy before opening held-out results.
6. Run every held-out case for the preserved Phase 3.1 runner and the three new native comparison variants. Execute an explicitly separate deterministic source baseline.
7. Verify signed access, malicious inputs, typed evidence associations, finite budgets, crash recovery, cancellations, dependency outages, compatibility and browser behavior.
8. Publish exact metrics and limitations, update the runbook and stop before Phase 4. No deployment or push is authorized by this phase.

Source coverage, citation coverage, research completion and quote readiness are separate gates. Mandatory backend reads are always attributed to the backend, including in hybrid runs. Fixture-based reliability tests never enter native model accuracy denominators.
