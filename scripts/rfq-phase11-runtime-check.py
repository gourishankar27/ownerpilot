"""Phase 1.1 real worker restart and duplicate delivery, disposable database only.

Start the validation stack first. No fixture model/provider is used.
"""

import json
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4

from pypdf import PdfReader, PdfWriter
from psycopg.types.json import Jsonb

from api.rfq.db import connection, migrate
from api.rfq.config import settings, PROCESSING_KEYS
from api.rfq.storage import LocalStorage, fingerprint
from api.rfq.worker import process


def wait_for(job_id, states, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with connection() as conn:
            row = conn.execute(
                "select * from procurement.rfq_processing_jobs where id=%s", (job_id,)
            ).fetchone()
        if row["state"] in states:
            return row
        if row["state"] == "failed":
            raise RuntimeError(row["error_category"])
        time.sleep(0.1)
    raise TimeoutError("Worker did not reach the required persisted stage.")


def main():
    from urllib.parse import urlparse

    if (
        urlparse(os.environ.get("DATABASE_URL", "")).path
        != "/ownerpilot_rfq_phase11_demo"
    ):
        raise SystemExit("Use only the isolated Phase 1.1 demo DATABASE_URL.")
    migrate()
    writer = PdfWriter()
    source = PdfReader("data/evaluation/rfq/sources/rfq-10-00.pdf")
    for _ in range(20):
        writer.add_page(source.pages[0])
    output = Path(".local/rfq/phase1_1/recovery-scanned.pdf")
    output.parent.mkdir(parents=True, exist_ok=True)
    writer.write(output)
    content = output.read_bytes()
    workspace = uuid4()
    rfq = uuid4()
    doc = uuid4()
    job = uuid4()
    with connection() as conn:
        conn.execute(
            "insert into business_workspaces(id,name,slug) values(%s,'Synthetic restart validation',%s)",
            (workspace, str(workspace)),
        )
        conn.execute(
            "insert into procurement.rfqs(id,workspace_id,title,created_by) values(%s,%s,'Synthetic recovery check','runtime-test')",
            (rfq, workspace),
        )
        conn.execute(
            "insert into procurement.rfq_documents(id,rfq_id,workspace_id,filename,extension,fingerprint,size_bytes,uploaded_by) values(%s,%s,%s,'scanned-recovery.pdf','.pdf',%s,%s,'runtime-test')",
            (doc, rfq, workspace, fingerprint(content), len(content)),
        )
        configuration = {k: getattr(settings(), k) for k in PROCESSING_KEYS}
        configuration["policy"] = "selective-v2"
        conn.execute(
            "insert into procurement.rfq_processing_jobs(id,rfq_id,workspace_id,mode,base_revision,total_documents,requested_by,configuration) values(%s,%s,%s,'deterministic',0,1,'runtime-test',%s)",
            (job, rfq, workspace, Jsonb(configuration)),
        )
    LocalStorage().put(str(workspace), str(doc), content)
    process.apply_async(args=[str(job)])
    parsing = wait_for(job, {"parsing"})
    # Kill the actual Linux worker while OCR is in progress. Session lock releases.
    subprocess.run(
        [
            "docker",
            "kill",
            "-s",
            "SIGKILL",
            "ownerpilot-rfq-phase11-worker-1",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "docker",
            "start",
            "ownerpilot-rfq-phase11-worker-1",
        ],
        check=True,
        capture_output=True,
    )
    recovered = wait_for(job, {"awaiting_review"}, timeout=180)
    for _ in range(3):
        process.apply_async(args=[str(job)])
    # DB checks are authoritative; allow deliveries to be consumed before inspection.
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        time.sleep(0.2)
    with connection() as conn:
        runs = conn.execute(
            "select count(*) as n from procurement.rfq_extraction_runs where job_id=%s",
            (job,),
        ).fetchone()["n"]
        lines = conn.execute(
            "select count(*) as n from procurement.rfq_line_items where rfq_id=%s",
            (rfq,),
        ).fetchone()["n"]
        rfq_record = conn.execute(
            "select current_run_id,revision from procurement.rfqs where id=%s", (rfq,)
        ).fetchone()
        metadata = conn.execute(
            "select metadata from procurement.rfq_extraction_runs where job_id=%s",
            (job,),
        ).fetchone()["metadata"]
    assert runs == 1 and recovered["attempts"] >= 2 and rfq_record["revision"] == 1
    report = {
        "worker_killed_during": parsing["state"],
        "recovered_state": recovered["state"],
        "attempts": recovered["attempts"],
        "repeated_deliveries": 3,
        "published_runs": runs,
        "line_items": lines,
        "revision": rfq_record["revision"],
        "job_id": str(job),
        "policy": metadata["policy"],
        "model_calls": metadata["model_call_count"],
        "queue_wait_ms": metadata["queue_wait_ms"],
        "worker_container": "ownerpilot-rfq-phase11-worker-1",
    }
    Path("docs/rfq/phase1_1/results/final/worker-restart.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report))


if __name__ == "__main__":
    main()
