"""Reproduce legacy constraint drift on a disposable copy containing approved RFQs.

Only the named synthetic clone is mutated. A temporary CHECK(TRUE) deliberately
forces rename failure to prove transaction rollback; it is removed afterwards.
"""

import importlib.util
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


def main():
    url = os.environ["DATABASE_URL"]
    if urlparse(url).path != "/ownerpilot_rfq_phase11_populated":
        raise SystemExit("Requires the disposable populated synthetic clone.")
    spec = importlib.util.spec_from_file_location(
        "reconciliation", "scripts/rfq-reconcile-constraints.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    reference = os.environ["RFQ_SCHEMA_REFERENCE_DATABASE_URL"]
    renamed = json.loads(
        Path("docs/rfq/phase1_1/results/migrations/reconciled.json").read_text()
    )["renames"]
    if not renamed:
        renamed = json.loads(
            Path("docs/rfq/phase1_1/results/migrations/applied.json").read_text()
        )["renames"]
    with psycopg.connect(url, row_factory=dict_row) as conn:
        before = module.snapshot(conn)
        tables = conn.execute(
            "select schemaname,tablename from pg_tables where schemaname in ('public','procurement') order by 1,2"
        ).fetchall()
        counts = {}
        for t in tables:
            counts[t["schemaname"] + "." + t["tablename"]] = conn.execute(
                sql.SQL("select count(*) as n from {}.{}").format(
                    sql.Identifier(t["schemaname"]), sql.Identifier(t["tablename"])
                )
            ).fetchone()["n"]
        approved = conn.execute(
            "select count(*) as n from procurement.rfqs where status='approved'"
        ).fetchone()["n"]
        assert (
            approved > 0
            and counts.get("public.user", 0) > 0
            and counts["procurement.rfq_extraction_runs"] > 0
        )
        for r in renamed:
            conn.execute(
                sql.SQL("alter table public.{} rename constraint {} to {}").format(
                    sql.Identifier(r["table"]),
                    sql.Identifier(r["new"]),
                    sql.Identifier(r["old"]),
                )
            )
    # A missing structurally identical reference must block all renames.
    blocked = module.reconcile(url, reference, False)
    assert not blocked["blocked"] and len(blocked["renames"]) == len(renamed)
    collision = blocked["renames"][-1]
    with psycopg.connect(url, row_factory=dict_row) as conn:
        conn.execute(
            sql.SQL("alter table public.{} add constraint {} check (true)").format(
                sql.Identifier(collision["table"]), sql.Identifier(collision["new"])
            )
        )
        constraints_before_failure = conn.execute(
            "select conrelid::regclass::text as table_name,conname from pg_constraint where connamespace='public'::regnamespace order by 1,2"
        ).fetchall()
    try:
        module.reconcile(url, reference, True)
    except psycopg.errors.DuplicateObject:
        rolled_back = True
    else:
        raise AssertionError("Expected deliberate constraint name collision.")
    with psycopg.connect(url, row_factory=dict_row) as conn:
        assert module.snapshot(conn) == before
        assert (
            conn.execute(
                "select conrelid::regclass::text as table_name,conname from pg_constraint where connamespace='public'::regnamespace order by 1,2"
            ).fetchall()
            == constraints_before_failure
        )
        conn.execute(
            sql.SQL("alter table public.{} drop constraint {}").format(
                sql.Identifier(collision["table"]), sql.Identifier(collision["new"])
            )
        )
    applied = module.reconcile(url, reference, True)
    repeated = module.reconcile(url, reference, True)
    assert (
        applied["rows_preserved"]
        and repeated["rows_preserved"]
        and not repeated["renames"]
    )
    with psycopg.connect(url, row_factory=dict_row) as conn:
        assert module.snapshot(conn) == before
    report = dict(
        database="ownerpilot_rfq_phase11_populated",
        synthetic_only=True,
        table_rows=counts,
        approved_rfqs=approved,
        successful_renames=len(applied["renames"]),
        repeated_renames=len(repeated["renames"]),
        rollback_on_name_collision=rolled_back,
        constraints_rolled_back=True,
        before_sha256=before,
        after_sha256=applied["after_sha256"],
        rows_preserved=True,
    )
    Path("docs/rfq/phase1_1/results/migrations/populated-preservation.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in ("table_rows", "before_sha256", "after_sha256")
            }
        )
    )


if __name__ == "__main__":
    main()
