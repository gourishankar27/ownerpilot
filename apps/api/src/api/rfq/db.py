from contextlib import contextmanager
import hashlib
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from api.config import get_settings


@contextmanager
def connection():
    with psycopg.connect(
        get_settings().database_url,
        row_factory=dict_row,
        connect_timeout=5,
        options="-c statement_timeout=10000 -c lock_timeout=5000",
    ) as conn:
        yield conn


def migrate() -> None:
    with connection() as conn:
        conn.execute("select pg_advisory_xact_lock(184255702)")
        if not conn.execute(
            "select to_regclass('public.business_workspaces') as workspaces, to_regclass('public.workspace_members') as members"
        ).fetchone()["members"]:
            raise RuntimeError(
                "Apply the existing OwnerPilot workspace schema first; RFQ migrations do not own it."
            )
        conn.execute("create schema if not exists procurement")
        conn.execute(
            "create table if not exists procurement.schema_migrations(name text primary key, sha256 text not null, applied_at timestamptz not null default now())"
        )
        for path in sorted((Path(__file__).parent / "migrations").glob("*.sql")):
            sql = path.read_text(encoding="utf-8")
            digest = hashlib.sha256(sql.encode()).hexdigest()
            previous = conn.execute(
                "select sha256 from procurement.schema_migrations where name=%s",
                (path.name,),
            ).fetchone()
            if previous:
                if previous["sha256"] != digest:
                    raise RuntimeError(
                        "Applied RFQ migration checksum differs; never edit released migrations."
                    )
                continue
            conn.execute(sql)
            conn.execute(
                "insert into procurement.schema_migrations(name,sha256) values(%s,%s)",
                (path.name, digest),
            )


def audit(conn, rfq, actor: str, event: str, details: dict | None = None, run_id=None):
    conn.execute(
        "insert into procurement.rfq_audit_events(rfq_id,workspace_id,actor,event,details,run_id) values(%s,%s,%s,%s,%s,%s)",
        (rfq["id"], rfq["workspace_id"], actor, event, Jsonb(details or {}), run_id),
    )


if __name__ == "__main__":
    migrate()
    print("RFQ additive migrations applied.")
