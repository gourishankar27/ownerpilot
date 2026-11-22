"""New isolated populated Phase 2 schema -> additive Phase 3 migrations, never a reset."""

import hashlib
import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

from api.config import get_settings
from api.rfq.db import connection, migrate
from api.services.demo_data import ensure_operational_schema

ROOT = Path(__file__).resolve().parents[1]
database = "ownerpilot_rfq_phase3_migration_test_" + uuid4().hex[:8]
subprocess.run(
    [
        "docker",
        "exec",
        "ownerpilot-rfq-validation-postgres-1",
        "createdb",
        "-U",
        "postgres",
        database,
    ],
    check=True,
)
url = os.environ["DATABASE_URL"]
if "ownerpilot_rfq_phase3_demo" not in url:
    raise SystemExit("Load isolated Phase 3 demo environment")
os.environ["DATABASE_URL"] = url.replace("ownerpilot_rfq_phase3_demo", database)
get_settings.cache_clear()

with connection() as conn:
    conn.execute("create extension vector")
    ensure_operational_schema(conn.cursor())
    conn.execute(
        "create table workspace_members(id uuid primary key default gen_random_uuid(),workspace_id uuid not null references business_workspaces(id),user_id text not null,role text not null,created_at timestamptz not null default now())"
    )
    conn.execute("create schema procurement")
    conn.execute(
        "create table procurement.schema_migrations(name text primary key,sha256 text not null,applied_at timestamptz not null default now())"
    )
    for path in sorted(
        (ROOT / "apps/api/src/api/rfq/migrations").glob("000[1-4]*.sql")
    ):
        sql = path.read_text(encoding="utf-8")
        conn.execute(sql)
        conn.execute(
            "insert into procurement.schema_migrations(name,sha256) values(%s,%s)",
            (path.name, hashlib.sha256(sql.encode()).hexdigest()),
        )
    workspace = uuid4()
    rfq = uuid4()
    conn.execute(
        "insert into business_workspaces(id,name,slug) values(%s,'Synthetic preservation sentinel',%s)",
        (workspace, str(workspace)),
    )
    conn.execute(
        "insert into workspace_members(workspace_id,user_id,role) values(%s,'synthetic-preservation','owner')",
        (workspace,),
    )
    # Phase 2 approved sentinel has no processing artifacts; migration is schema-only and must preserve it verbatim.
    conn.execute(
        "insert into procurement.rfqs(id,workspace_id,title,created_by,status,approved_by,approved_at) values(%s,%s,'Synthetic approved sentinel','synthetic-preservation','approved','synthetic-preservation',now())",
        (rfq, workspace),
    )


def fingerprint():
    with connection() as conn:
        tables = conn.execute(
            "select table_schema,table_name from information_schema.tables where table_type='BASE TABLE' and table_schema in ('public','procurement') order by table_schema,table_name"
        ).fetchall()
        result = {}
        for table in tables:
            schema, name = table["table_schema"], table["table_name"]
            if name == "schema_migrations" or name.startswith("pg_"):
                continue
            from psycopg import sql

            rows = conn.execute(
                sql.SQL(
                    "select to_jsonb(t)::text as data from {}.{} t order by to_jsonb(t)::text"
                ).format(sql.Identifier(schema), sql.Identifier(name))
            ).fetchall()
            result[f"{schema}.{name}"] = {
                "rows": len(rows),
                "sha256": hashlib.sha256(
                    json.dumps(rows, sort_keys=True).encode()
                ).hexdigest(),
            }
        return result


before = fingerprint()
migrate()
migrate()
after = fingerprint()
changed = [table for table in before if before[table] != after.get(table)]
record = {
    "isolated_database": database,
    "pre_phase3_tables": before,
    "post_phase3_tables": after,
    "changed_original_tables": changed,
    "repeat_migration_passed": True,
    "approved_rfq_sentinel": str(rfq),
    "passed": not changed,
}
(ROOT / "docs/rfq/phase3/results/migration-preservation.json").write_text(
    json.dumps(record, indent=2) + "\n", encoding="utf-8"
)
print(
    json.dumps(
        {
            "tables_preserved": len(before),
            "new_tables": len(after) - len(before),
            "changed_original_tables": changed,
        }
    )
)
raise SystemExit(bool(changed))
