"""Rename only structurally identical constraints using a fresh Drizzle reference.

Read-only by default. Apply is restricted to disposable validation/test databases.
No drops, truncation, FK semantics changes, or table rewrites.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row
from psycopg import sql


def constraints(conn, tables):
    return conn.execute(
        "select c.conname as name,c.contype as type,t.relname as table_name,pg_get_constraintdef(c.oid,true) as definition from pg_constraint c join pg_class t on t.oid=c.conrelid join pg_namespace n on n.oid=t.relnamespace where n.nspname='public' and t.relname=any(%s) and c.contype in ('p','u','f') order by t.relname,c.conname",
        (tables,),
    ).fetchall()


def key(record):
    definition = re.sub(
        r"\s+", " ", record["definition"].replace('"', "").replace("public.", "")
    ).strip()
    return record["table_name"], record["type"], definition


def snapshot(conn):
    tables = conn.execute(
        "select schemaname,tablename from pg_tables where schemaname in ('public','procurement') order by 1,2"
    ).fetchall()
    hashes = {}
    for table in tables:
        query = sql.SQL(
            "select to_jsonb(t)::text as row from {}.{} t order by to_jsonb(t)::text"
        ).format(
            sql.Identifier(table["schemaname"]), sql.Identifier(table["tablename"])
        )
        digest = hashlib.sha256()
        for row in conn.execute(query):
            digest.update(row["row"].encode())
            digest.update(b"\n")
        hashes[table["schemaname"] + "." + table["tablename"]] = digest.hexdigest()
    return hashes


def reconcile(source_url, reference_url, apply=False):
    if apply and not any(
        s in urlparse(source_url).path for s in ("validation", "test", "phase11")
    ):
        raise ValueError(
            "Automatic application is restricted to disposable databases. Review SQL separately for application data."
        )
    tables = re.findall(
        r'pgTable\("([a-z_]+)"', Path("apps/web/lib/schema.ts").read_text()
    )
    with psycopg.connect(reference_url, row_factory=dict_row) as reference:
        desired = constraints(reference, tables)
    with psycopg.connect(
        source_url,
        row_factory=dict_row,
        options="-c lock_timeout=5000 -c statement_timeout=10000",
    ) as source:
        source.execute("set transaction isolation level repeatable read")
        source.execute("select pg_advisory_xact_lock(184255703)")
        actual = constraints(source, tables)
        by_key = {key(c): c for c in actual}
        renames = []
        blocked = []
        for target in desired:
            current = by_key.get(key(target))
            if current is None:
                blocked.append(
                    {
                        "table": target["table_name"],
                        "definition": target["definition"],
                        "reason": "No structurally identical constraint; no semantic change is inferred.",
                    }
                )
            elif current["name"] != target["name"]:
                renames.append(
                    {
                        "table": target["table_name"],
                        "old": current["name"],
                        "new": target["name"],
                        "definition": target["definition"],
                    }
                )
        before = snapshot(source)
        if apply and not blocked:
            for rename in renames:
                source.execute(
                    sql.SQL("alter table public.{} rename constraint {} to {}").format(
                        sql.Identifier(rename["table"]),
                        sql.Identifier(rename["old"]),
                        sql.Identifier(rename["new"]),
                    )
                )
        after = snapshot(source)
        if before != after:
            raise RuntimeError(
                "Data changed during reconciliation; transaction rolled back."
            )
        return {
            "applied": apply and not blocked,
            "renames": renames,
            "blocked": blocked,
            "before_sha256": before,
            "after_sha256": after,
            "rows_preserved": before == after,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = reconcile(
        os.environ["DATABASE_URL"],
        os.environ["RFQ_SCHEMA_REFERENCE_DATABASE_URL"],
        args.apply,
    )
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "applied": report["applied"],
                "renames": len(report["renames"]),
                "blocked": len(report["blocked"]),
                "rows_preserved": report["rows_preserved"],
            }
        )
    )
    if report["blocked"]:
        raise SystemExit(2)
