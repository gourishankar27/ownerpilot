"""SIGKILL the named isolated Linux catalog worker during real neural indexing."""

import json
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4
from urllib.parse import urlparse

from psycopg.types.json import Jsonb
from api.rfq.db import connection
from api.catalog.worker import index_catalog


def wait(version, states, timeout=240):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with connection() as conn:
            r = conn.execute(
                "select * from procurement.catalog_versions where id=%s", (version,)
            ).fetchone()
        if r["state"] in states:
            return r
        if r["state"] == "failed":
            raise RuntimeError(r["error"])
        time.sleep(0.1)
    raise TimeoutError("Catalog recovery deadline")


def main():
    if urlparse(os.environ["DATABASE_URL"]).path != "/ownerpilot_rfq_phase2_demo":
        raise SystemExit("Synthetic Phase2 demo only")
    rows = json.loads(Path("data/evaluation/product-catalog/catalog.json").read_text())
    workspace = str(uuid4())
    with connection() as conn:
        conn.execute(
            "insert into business_workspaces(id,name,slug) values(%s,'Synthetic catalog recovery',%s)",
            (workspace, workspace),
        )
        catalog = conn.execute(
            "insert into procurement.product_catalogs(workspace_id,name,license) values(%s,'Synthetic SIGKILL recovery','CC0') returning id",
            (workspace,),
        ).fetchone()["id"]
        version = conn.execute(
            "insert into procurement.catalog_versions(catalog_id,workspace_id,fingerprint,specification,rows,requested_by,state) values(%s,%s,%s,'{}',%s,'synthetic-recovery','queued') returning id",
            (catalog, workspace, uuid4().hex, Jsonb(rows)),
        ).fetchone()["id"]
    index_catalog.apply_async(args=[str(version)])
    wait(version, {"building"})
    container = "ownerpilot-catalog-validation-worker-1"
    subprocess.run(
        ["docker", "kill", "-s", "SIGKILL", container], check=True, capture_output=True
    )
    with connection() as conn:
        partial = conn.execute(
            "select count(*) as n from procurement.catalog_products where version_id=%s",
            (version,),
        ).fetchone()["n"]
    assert partial == 0
    subprocess.run(["docker", "start", container], check=True, capture_output=True)
    recovered = wait(version, {"published"})
    for _ in range(3):
        index_catalog.apply_async(args=[str(version)])
    time.sleep(3)
    with connection() as conn:
        count = conn.execute(
            "select count(*) as n from procurement.catalog_products where version_id=%s",
            (version,),
        ).fetchone()["n"]
        publications = conn.execute(
            "select count(*) as n from procurement.catalog_audit_events where subject=%s and event='index_published'",
            (version,),
        ).fetchone()["n"]
    assert count == 1020 and publications == 1 and recovered["attempts"] >= 2
    report = dict(
        container=container,
        version=str(version),
        partial_visible_vectors=partial,
        recovery_attempt=recovered["attempts"],
        published_vectors=count,
        publications=publications,
        repeated_deliveries=3,
        metadata=recovered["metadata"],
    )
    Path("docs/rfq/phase2/results/worker-recovery.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report))


if __name__ == "__main__":
    main()
