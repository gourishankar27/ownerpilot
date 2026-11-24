"""Read-only clone of prior synthetic DBs, additive upgrade and private runtime setup."""

import importlib.util
import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / ".local/rfq/phase3_2/runtime-env.json"
CONTAINER = "ownerpilot-rfq-validation-postgres-1"
DEMO = "ownerpilot_rfq_phase3_demo_phase31_validation_phase32"
TEST = "ownerpilot_rfq_phase32_test"


def command(*args):
    return subprocess.run(
        ["docker", "exec", CONTAINER, *args], check=True, capture_output=True
    )


def main():
    if PRIVATE.exists():
        print(
            "Phase 3.2 runtime already exists; retaining it without resetting databases"
        )
        return
    prior = json.loads((ROOT / ".local/rfq/phase3_1/runtime-env.json").read_text())
    spec = importlib.util.spec_from_file_location(
        "migration_projection", ROOT / "scripts/procurement31-migration-check.py"
    )
    projection = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(projection)
    reports = []
    for source, target in [
        ("ownerpilot_rfq_phase3_demo_phase31_validation", DEMO),
        ("ownerpilot_rfq_phase31_test", TEST),
    ]:
        dump = "/tmp/phase32-" + uuid4().hex + ".dump"
        command("pg_dump", "-U", "postgres", "-Fc", "-f", dump, source)
        command("createdb", "-U", "postgres", target)
        command("pg_restore", "-U", "postgres", "-d", target, dump)
        url = prior["DATABASE_URL"].replace(
            "ownerpilot_rfq_phase3_demo_phase31_validation", target
        )
        with psycopg.connect(url, row_factory=dict_row) as conn:
            columns = {}
            for row in conn.execute(
                "select table_schema,table_name,column_name from information_schema.columns where table_schema in ('public','procurement') and table_name!='schema_migrations' order by table_schema,table_name,ordinal_position"
            ):
                columns.setdefault((row["table_schema"], row["table_name"]), []).append(
                    row["column_name"]
                )
            before = projection.projections(conn, columns)
        os.environ["DATABASE_URL"] = url
        from api.config import get_settings
        from api.rfq.db import migrate

        get_settings.cache_clear()
        migrate()
        with psycopg.connect(url, row_factory=dict_row) as conn:
            after = projection.projections(conn, columns)
            migrations = conn.execute(
                "select name,sha256 from procurement.schema_migrations order by name"
            ).fetchall()
        assert before == after
        reports.append(
            {
                "source_read_only": source,
                "new_target_retained": target,
                "tables": before,
                "rows_checked": sum(row["rows"] for row in before.values()),
                "identical_old_columns": True,
                "migrations": migrations,
            }
        )
    runtime = {
        name: value.replace("ownerpilot_rfq_phase3_demo_phase31_validation", DEMO)
        .replace("6384", "6385")
        .replace("8041", "8042")
        .replace("3041", "3042")
        .replace("phase3_1/documents", "phase3_2/documents")
        .replace("phase3_1\\documents", "phase3_2\\documents")
        if isinstance(value, str)
        else value
        for name, value in prior.items()
    }
    PRIVATE.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE.write_text(json.dumps(runtime, indent=2) + "\n", encoding="utf-8")
    (ROOT / ".local/rfq/phase3_2/documents").mkdir(exist_ok=True)
    (ROOT / "docs/rfq/phase3_2/results/migration-preservation.json").write_text(
        json.dumps(reports, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            [
                {
                    key: report[key]
                    for key in [
                        "new_target_retained",
                        "rows_checked",
                        "identical_old_columns",
                    ]
                }
                for report in reports
            ]
        )
    )


if __name__ == "__main__":
    main()
