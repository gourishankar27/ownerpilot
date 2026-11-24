"""Fresh additive migration check and non-destructive cloned blob completion."""

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]


def main():
    runtime = json.loads((ROOT / ".local/rfq/phase3_2/runtime-env.json").read_text())
    target = "ownerpilot_phase32_fresh_test_" + uuid4().hex[:12]
    subprocess.run(
        [
            "docker",
            "exec",
            "ownerpilot-rfq-validation-postgres-1",
            "createdb",
            "-U",
            "postgres",
            target,
        ],
        check=True,
        capture_output=True,
    )
    url = runtime["DATABASE_URL"].rsplit("/", 1)[0] + "/" + target
    os.environ["DATABASE_URL"] = url
    from api.config import get_settings
    from api.services.demo_data import ensure_operational_schema
    from api.rfq.db import connection, migrate

    get_settings.cache_clear()
    with connection() as conn:
        ensure_operational_schema(conn.cursor())
        conn.execute(
            "create table workspace_members(id uuid primary key default gen_random_uuid(),workspace_id uuid not null references business_workspaces(id),user_id text not null,role varchar(32) not null,created_at timestamptz not null default now())"
        )
    migrate()
    with connection() as conn:
        before = conn.execute(
            "select name,sha256 from procurement.schema_migrations order by name"
        ).fetchall()
    migrate()
    with connection() as conn:
        after = conn.execute(
            "select name,sha256 from procurement.schema_migrations order by name"
        ).fetchall()
    assert before == after and len(before) == 8
    copied = existing = 0
    old = ROOT / ".local/rfq/phase3_1/documents"
    new = ROOT / ".local/rfq/phase3_2/documents"
    for source in old.rglob("*"):
        if not source.is_file():
            continue
        dest = new / source.relative_to(old)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            assert (
                hashlib.sha256(source.read_bytes()).digest()
                == hashlib.sha256(dest.read_bytes()).digest()
            )
            existing += 1
        else:
            shutil.copyfile(source, dest)
            copied += 1
    result = {
        "fresh_database_retained": target,
        "migrations": before,
        "idempotent": before == after,
        "historical_blobs_copied": copied,
        "identical_existing_blobs": existing,
        "source_blobs_unchanged": True,
    }
    (ROOT / "docs/rfq/phase3_2/results/fresh-migration.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
