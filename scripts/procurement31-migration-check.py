"""Clone the populated historic demo into a NEW database; check old row projections.

Never migrates or changes the historical demo database. No reset/drop/truncate.
"""

import hashlib
import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = "ownerpilot-rfq-validation-postgres-1"
SOURCE = "ownerpilot_rfq_phase3_demo"
TARGET = "ownerpilot_phase31_migration_" + uuid4().hex[:10]


def command(*args):
    return subprocess.run(
        ["docker", "exec", CONTAINER, *args], check=True, capture_output=True
    )


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def projections(conn, columns):
    result = {}
    for (schema, table), names in columns.items():
        query = sql.SQL("select {} from {}.{}").format(
            sql.SQL(",").join(map(sql.Identifier, names)),
            sql.Identifier(schema),
            sql.Identifier(table),
        )
        rows = [dict(row) for row in conn.execute(query)]
        result[schema + "." + table] = {
            "rows": len(rows),
            "sha256": digest(sorted(rows, key=digest)),
        }
    return result


def main():
    if (
        "ownerpilot_rfq_phase3_demo_phase31_validation"
        not in os.environ["DATABASE_URL"]
    ):
        raise SystemExit("Requires isolated Phase 3.1 validation environment")
    command(
        "pg_dump",
        "-U",
        "postgres",
        "-Fc",
        "-f",
        "/tmp/phase31-preservation.dump",
        SOURCE,
    )
    command("createdb", "-U", "postgres", TARGET)
    command(
        "pg_restore", "-U", "postgres", "-d", TARGET, "/tmp/phase31-preservation.dump"
    )
    url = os.environ["DATABASE_URL"].replace(
        "ownerpilot_rfq_phase3_demo_phase31_validation", TARGET
    )
    with psycopg.connect(url, row_factory=dict_row) as conn:
        columns = {}
        for row in conn.execute(
            "select table_schema,table_name,column_name from information_schema.columns where table_schema in ('public','procurement') and table_name!='schema_migrations' order by table_schema,table_name,ordinal_position"
        ):
            columns.setdefault((row["table_schema"], row["table_name"]), []).append(
                row["column_name"]
            )
        before = projections(conn, columns)
    os.environ["DATABASE_URL"] = url
    from api.config import get_settings
    from api.rfq.db import migrate

    get_settings.cache_clear()
    migrate()
    with psycopg.connect(url, row_factory=dict_row) as conn:
        after = projections(conn, columns)
        migrations = conn.execute(
            "select name,sha256 from procurement.schema_migrations order by name"
        ).fetchall()
    result = {
        "source_untouched": SOURCE,
        "new_clone_retained": TARGET,
        "old_columns_only": True,
        "tables": before,
        "migrations": migrations,
        "identical_after_additive_migration": before == after,
        "source_operation": "read-only pg_dump",
        "rows_checked": sum(row["rows"] for row in before.values()),
    }
    path = ROOT / "docs/rfq/phase3_1/results/migration-preservation.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "tables": len(before),
                "rows": result["rows_checked"],
                "preserved": before == after,
                "clone": TARGET,
            }
        )
    )
    assert before == after


if __name__ == "__main__":
    main()
