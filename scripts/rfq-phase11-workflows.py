"""Real HTTP -> Redis -> Linux worker workflows, isolated synthetic demo DB only.

Uses the configured trusted proxy signing key without printing or persisting it.
No fixture provider, in-process worker, or direct publication is used.
"""

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import time
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from api.rfq.db import connection


def main():
    if urlparse(os.environ["DATABASE_URL"]).path != "/ownerpilot_rfq_phase11_demo":
        raise SystemExit("Use only the isolated synthetic Phase 1.1 demo database.")
    workspace, other, user = str(uuid4()), str(uuid4()), "phase11-" + str(uuid4())
    with connection() as conn:
        for identifier in (workspace, other):
            conn.execute(
                "insert into business_workspaces(id,name,slug) values(%s,'Synthetic Phase 1.1 workflows',%s)",
                (identifier, identifier),
            )
            conn.execute(
                "insert into workspace_members(workspace_id,user_id,role) values(%s,%s,'owner')",
                (identifier, user),
            )
    client = httpx.Client(base_url="http://127.0.0.1:8011", timeout=30)

    def request(method, path, *, tenant=workspace, expected=200, **kwargs):
        now = int(time.time())
        claims = dict(
            sub=user, workspace=tenant, iat=now, exp=now + 60, method=method, path=path
        )
        payload = (
            base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
        )
        signature = hmac.new(
            os.environ["RFQ_AUTH_SECRET"].encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        response = client.request(
            method,
            path,
            headers={"Authorization": f"Bearer {payload}.{signature}"},
            **kwargs,
        )
        assert response.status_code == expected, (
            method,
            path,
            response.status_code,
            response.text,
        )
        return (
            response.json()
            if response.headers.get("content-type", "").startswith("application/json")
            else None
        )

    def workflow(name, filename, content, mode):
        started = time.perf_counter()
        created = request(
            "POST",
            "/api/rfqs",
            expected=201,
            json={"title": "Synthetic Phase 1.1 " + name},
        )
        path = "/api/rfqs/" + created["id"]
        mime = {".csv": "text/csv", ".txt": "text/plain", ".pdf": "application/pdf"}[
            Path(filename).suffix
        ]
        document = request(
            "POST",
            path + "/documents",
            expected=201,
            data={"revision": 0},
            files={"file": (filename, content, mime)},
        )
        job = request(
            "POST",
            path + "/process",
            expected=202,
            json={"revision": 1, "mode": mode, "policy": "selective-v2"},
        )
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            detail = request("GET", path)
            persisted = next(j for j in detail["jobs"] if j["id"] == job["id"])
            if persisted["state"] in {"awaiting_review", "failed", "cancelled"}:
                break
            time.sleep(0.25)
        assert persisted["state"] == "awaiting_review", persisted
        metadata = detail["runs"][0]["metadata"]
        record = dict(
            name=name,
            path=path,
            job_id=job["id"],
            document_id=document["id"],
            state=persisted["state"],
            item_count=len(detail["items"]),
            end_to_end_ms=(time.perf_counter() - started) * 1000,
            metadata=metadata,
            items=detail["items"],
        )
        print(
            json.dumps(
                {k: record[k] for k in ("name", "state", "item_count", "end_to_end_ms")}
            ),
            flush=True,
        )
        return record, detail

    records = []
    clean, detail = workflow(
        "clean table",
        "clean.csv",
        b"Manufacturer,MPN,Description,Qty,UOM\nNimvora,00-LAP.1,Laptop refresh,2,EA\n",
        "hybrid",
    )
    assert clean["metadata"]["model_call_count"] == 0
    records.append(clean)
    path = clean["path"]
    request(
        "POST", path + "/approve", expected=422, json={"revision": detail["revision"]}
    )
    request("GET", path + "/evidence", tenant=other, expected=404)
    request(
        "GET",
        path + "/documents/" + clean["document_id"] + "/download",
        tenant=other,
        expected=404,
    )
    item = detail["items"][0]
    saved = request(
        "PATCH",
        path + "/line-items/" + item["id"],
        json=dict(
            revision=detail["revision"],
            fields={"quantity": "3"},
            reason="Explicit synthetic reviewer correction",
            review_status="reviewed",
        ),
    )
    request("POST", path + "/approve", json={"revision": saved["revision"]})
    approved = request("GET", path)
    request(
        "POST",
        path + "/reprocess",
        expected=409,
        json={
            "revision": approved["revision"],
            "mode": "hybrid",
            "reason": "Synthetic immutability check",
        },
    )
    assert (
        approved["status"] == "approved"
        and approved["items"][0]["fields"]["quantity"]["raw"] == "2"
        and approved["items"][0]["fields"]["quantity"]["value"] == "3"
    )
    digital, _ = workflow(
        "digital PDF",
        "digital.pdf",
        Path("data/evaluation/rfq-v2/sources/v2-04-00.pdf").read_bytes(),
        "deterministic",
    )
    records.append(digital)
    scanned, _ = workflow(
        "grid OCR",
        "grid.pdf",
        Path("data/evaluation/rfq-v2/sources/v2-00-00.pdf").read_bytes(),
        "deterministic",
    )
    records.append(scanned)
    partial, _ = workflow(
        "partial table",
        "partial.txt",
        b"Manufacturer | MPN | Description | Qty | UOM\nNimvora | 001-LAP.1 | Laptop refresh | 12 | EA\nItem 2: Request 7 EA of Fiber cable; manufacturer AxionEagle; MPN FC-07.\n",
        "hybrid",
    )
    assert (
        partial["metadata"]["model_call_count"] >= 1
        and partial["metadata"]["merge"]["original_deterministic_rows"] >= 1
    )
    records.append(partial)
    model, _ = workflow(
        "genuine local model",
        "prose.txt",
        Path("data/evaluation/rfq-v2/sources/v2-03-00.txt").read_bytes(),
        "llm",
    )
    assert model["metadata"]["model_call_count"] >= 1
    records.append(model)
    report = dict(
        transport="real localhost HTTP, signed trusted proxy claims",
        worker="ownerpilot-rfq-phase11-worker-1",
        fixture_provider=False,
        workspace=workspace,
        reviewer=user,
        cross_workspace_evidence_status=404,
        cross_workspace_download_status=404,
        pre_review_approval_status=422,
        approved_reprocessing_status=409,
        approved_rfq_id=approved["id"],
        correction_preserves_raw=True,
        workflows=records,
    )
    Path("docs/rfq/phase1_1/results/final/real-workflows.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
