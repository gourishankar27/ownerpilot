# Migration compatibility

The original issue reproduces on a disposable legacy-runtime schema: Drizzle interprets equivalent legacy PK/unique/FK names as schema changes, and missing suppliers definitions contribute to a truncate prompt. No truncate response, force push, application reset or released migration edit was accepted.

The safe procedure has two parts. `infra/migrations/20261119_public_suppliers_compat.sql` creates only the missing Drizzle-owned suppliers table, if absent, with its expected workspace FK. `scripts/rfq-reconcile-constraints.py` compares a fresh Drizzle reference catalog and renames only structurally identical primary/unique/foreign-key constraints. It does not infer semantic FK changes. Missing structural matches block all renames. Identifiers are quoted and the operation runs in a repeatable-read transaction with lock/statement timeouts, an advisory lock and all-public/procurement content hashes before/after.

The script is read-only unless --apply is explicit. Automatic apply is restricted to database names containing validation/test/phase11. This is a guardrail, not authentication or a production rollout authorization. Application-data use would require separately reviewed SQL and normal backup/maintenance ownership; no existing application database was reconciled in this milestone.

| Experiment | Actual result |
|---|---|
| Fresh auth + vector + Drizzle + RFQ0001/2/3 | Pass on phase11_reference and phase11_demo |
| Legacy populated demo DDL |16 equivalent rename candidates;2 missing suppliers-related structural matches; safely blocked |
| Add missing suppliers, apply names |16 renames, all row hashes unchanged |
| Repeat reconciliation |0 renames, content unchanged |
| Populated synthetic copy with auth/history/approvals |3 approved RFQs plus auth/business/extraction rows preserved across16 renames |
| Deliberate target-name collision on disposable copy |Error rolled back all partial constraint renames; schema and data snapshots identical |
| Drizzle after reconciliation |Exit0, no changes detected, no truncate prompt |
| Repeat RFQ migration |Exit0; existing approved records and history retained |

Raw evidence is in results/migrations, including initial blocked reports and populated-preservation.json with every table hash and row count. The latter database is a pg_dump/pg_restore copy of only synthetic Phase1.1 demo state. It has no running dispatcher. The forced CHECK(TRUE) name-collision constraint is test-only and removed afterwards. The empty fresh reference and representative populated experiments are distinct.

RFQ migration0003 adds a configuration JSONB object column with phase1/legacy-v1 defaults for already stored jobs. New API requests explicitly persist trusted selected processing configuration.0001/0002 remain byte-for-byte preserved. Better Auth remains owned by its installed migrator, public business tables by Drizzle, and procurement by the RFQ migration runner. Exact commands are in WINDOWS_SETUP.md; never accept a truncate prompt to bypass a mismatch.
