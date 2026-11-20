import pytest
from conftest import authorization
from api.rfq.db import connection, migrate
from api.rfq.worker import process_job

pytestmark = pytest.mark.integration
CSV = b"Manufacturer,MPN,Description,Qty,UOM\nNimvora,001-AB.2,Laptop,12,EA\n"


def call(api, method, path, **kwargs):
    client, workspace, _, user = api
    return client.request(
        method, path, headers=authorization(method, path, workspace, user), **kwargs
    )


def new_rfq(api):
    result = call(api, "POST", "/api/rfqs", json={"title": "Synthetic validation"})
    assert result.status_code == 201, result.text
    return result.json()


def processed(api):
    rfq = new_rfq(api)
    path = f"/api/rfqs/{rfq['id']}"
    assert (
        call(
            api,
            "POST",
            path + "/documents",
            data={"revision": 0},
            files={"file": ("sample.csv", CSV, "text/csv")},
        ).status_code
        == 201
    )
    result = call(
        api, "POST", path + "/process", json={"revision": 1, "mode": "deterministic"}
    )
    assert result.status_code == 202, result.text
    job = result.json()
    assert process_job(job["id"]) == "awaiting_review"
    return path, job, call(api, "GET", path).json()


def test_migration_repeat_and_existing_data(api):
    _, workspace, _, _ = api
    with connection() as conn:
        before = conn.execute(
            "select * from business_workspaces where id=%s", (workspace,)
        ).fetchone()
    migrate()
    migrate()
    with connection() as conn:
        after = conn.execute(
            "select * from business_workspaces where id=%s", (workspace,)
        ).fetchone()
        assert before == after
        assert conn.execute(
            "select extversion from pg_extension where extname='vector'"
        ).fetchone()


def test_authorization(api):
    client, workspace, other, user = api
    assert client.get("/api/rfqs").status_code == 401
    assert (
        client.get(
            "/api/rfqs",
            headers=authorization("GET", "/api/rfqs", workspace, user, age=30),
        ).status_code
        == 200
    )
    assert (
        client.get(
            "/api/rfqs",
            headers=authorization("GET", "/api/rfqs", workspace, user, True),
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/api/rfqs", headers=authorization("GET", "/api/rfqs", other, user)
        ).status_code
        == 403
    )
    rfq = new_rfq(api)
    with connection() as conn:
        conn.execute(
            "insert into workspace_members(workspace_id,user_id,role) values(%s,%s,'owner')",
            (other, user),
        )
    assert (
        client.get(
            f"/api/rfqs/{rfq['id']}",
            headers=authorization("GET", f"/api/rfqs/{rfq['id']}", other, user),
        ).status_code
        == 404
    )


def test_upload_duplicate_and_stale(api):
    rfq = new_rfq(api)
    path = f"/api/rfqs/{rfq['id']}/documents"
    assert (
        call(
            api,
            "POST",
            path,
            data={"revision": 0},
            files={"file": ("../../sample.csv", CSV, "text/csv")},
        ).status_code
        == 201
    )
    assert (
        call(
            api,
            "POST",
            path,
            data={"revision": 0},
            files={"file": ("again.csv", CSV, "text/csv")},
        ).status_code
        == 409
    )
    assert (
        call(
            api,
            "POST",
            path,
            data={"revision": 1},
            files={"file": ("again.csv", CSV, "text/csv")},
        ).status_code
        == 409
    )
    assert (
        call(
            api,
            "POST",
            path,
            data={"revision": 1},
            files={"file": ("bad.pdf", b"bad", "application/pdf")},
        ).status_code
        == 422
    )


def test_review_approval_retry_safety(api):
    path, job, detail = processed(api)
    assert detail["status"] == "awaiting_review" and len(detail["items"]) == 1
    assert process_job(job["id"]) == "terminal"
    item = detail["items"][0]
    revision = detail["revision"]
    assert (
        call(api, "POST", path + "/approve", json={"revision": revision}).status_code
        == 422
    )
    edit = {
        "revision": revision,
        "fields": {"quantity": "15"},
        "reason": "Verified synthetic source correction",
        "review_status": "reviewed",
    }
    assert (
        call(api, "PATCH", path + f"/line-items/{item['id']}", json=edit).status_code
        == 200
    )
    assert (
        call(api, "PATCH", path + f"/line-items/{item['id']}", json=edit).status_code
        == 409
    )
    final = call(api, "GET", path).json()
    assert final["items"][0]["fields"]["quantity"]["raw"] == "12"
    assert final["items"][0]["fields"]["quantity"]["value"] == "15"
    assert (
        call(
            api, "POST", path + "/approve", json={"revision": final["revision"]}
        ).status_code
        == 200
    )
    approved = call(api, "GET", path).json()
    assert approved["approved_by"] == api[3]
    assert (
        call(
            api,
            "POST",
            path + "/reprocess",
            json={"revision": approved["revision"], "reason": "change"},
        ).status_code
        == 409
    )
    events = call(api, "GET", path + "/audit").json()
    assert {"rfq_created", "extraction_published", "line_reviewed", "rfq_approved"} <= {
        e["event"] for e in events
    }


def test_reprocess_preserves_versions(api):
    path, job, detail = processed(api)
    item = detail["items"][0]
    assert (
        call(
            api,
            "PATCH",
            path + f"/line-items/{item['id']}",
            json={
                "revision": detail["revision"],
                "fields": {"quantity": "20"},
                "reason": "manual change",
            },
        ).status_code
        == 200
    )
    detail = call(api, "GET", path).json()
    result = call(
        api,
        "POST",
        path + "/reprocess",
        json={
            "revision": detail["revision"],
            "mode": "deterministic",
            "reason": "Explicitly re-evaluate original source",
        },
    )
    assert result.status_code == 202, result.text
    assert process_job(result.json()["id"]) == "awaiting_review"
    new = call(api, "GET", path).json()
    assert (
        len(new["runs"]) == 2 and new["items"][0]["fields"]["quantity"]["value"] == "12"
    )
    with connection() as conn:
        previous = conn.execute(
            "select data from procurement.rfq_line_items where run_id=%s",
            (detail["current_run_id"],),
        ).fetchone()
        assert previous["data"]["fields"]["quantity"]["value"] == "20"


def test_viewer_cannot_approve(api):
    path, job, detail = processed(api)
    with connection() as conn:
        conn.execute(
            "update workspace_members set role='viewer' where workspace_id=%s",
            (api[1],),
        )
    assert (
        call(
            api, "POST", path + "/approve", json={"revision": detail["revision"]}
        ).status_code
        == 403
    )


def test_worker_recovery_and_cancel(api):
    rfq = new_rfq(api)
    path = f"/api/rfqs/{rfq['id']}"
    assert (
        call(
            api,
            "POST",
            path + "/documents",
            data={"revision": 0},
            files={"file": ("sample.csv", CSV, "text/csv")},
        ).status_code
        == 201
    )
    job = call(
        api, "POST", path + "/process", json={"revision": 1, "mode": "deterministic"}
    ).json()
    with connection() as conn:
        conn.execute(
            "update procurement.rfq_processing_jobs set state='parsing',attempts=1 where id=%s",
            (job["id"],),
        )
    assert process_job(job["id"]) == "awaiting_review"
    detail = call(api, "GET", path).json()
    assert detail["jobs"][0]["attempts"] == 2
    next_job = call(
        api,
        "POST",
        path + "/reprocess",
        json={
            "revision": detail["revision"],
            "mode": "deterministic",
            "reason": "cancel test",
        },
    ).json()
    assert (
        call(api, "POST", f"/api/rfq-jobs/{next_job['id']}/cancel").status_code == 200
    )
    assert process_job(next_job["id"]) == "terminal"


def queued(api):
    rfq = new_rfq(api)
    path = f"/api/rfqs/{rfq['id']}"
    assert (
        call(
            api,
            "POST",
            path + "/documents",
            data={"revision": 0},
            files={"file": ("sample.csv", CSV, "text/csv")},
        ).status_code
        == 201
    )
    job = call(
        api, "POST", path + "/process", json={"revision": 1, "mode": "deterministic"}
    ).json()
    return path, job


def test_concurrent_delivery_lock(api):
    path, job = queued(api)
    with connection() as conn:
        conn.execute("select pg_advisory_lock(hashtextextended(%s,0))", (job["id"],))
        assert process_job(job["id"]) == "already_running"
        conn.execute("select pg_advisory_unlock(hashtextextended(%s,0))", (job["id"],))
    assert process_job(job["id"]) == "awaiting_review"
    assert len(call(api, "GET", path).json()["items"]) == 1


def test_bounded_model_retries_and_atomic_failure(api, monkeypatch):
    from api.rfq.provider import ProviderError

    path, job = queued(api)

    async def unavailable(*args, **kwargs):
        raise ProviderError("model_unavailable", True)

    monkeypatch.setattr("api.rfq.worker.extract", unavailable)
    assert process_job(job["id"]) == "retry_queued"
    assert process_job(job["id"]) == "retry_queued"
    assert process_job(job["id"]) == "failed"
    detail = call(api, "GET", path).json()
    assert detail["current_run_id"] is None and not detail["items"]
    assert detail["jobs"][0]["attempts"] == 3 and not detail["jobs"][0]["retryable"]


def test_publication_transaction_rolls_back(api, monkeypatch):
    path, job = queued(api)

    def fail(*args, **kwargs):
        raise RuntimeError("simulated transaction interruption")

    monkeypatch.setattr("api.rfq.repository.save_item", fail)
    assert process_job(job["id"]) == "failed"
    detail = call(api, "GET", path).json()
    assert (
        not detail["runs"] and not detail["items"] and detail["current_run_id"] is None
    )


def test_broker_outage_retains_job(api, monkeypatch):
    from api.rfq.worker import process

    def offline(**kwargs):
        raise ConnectionError("explicit test broker outage")

    monkeypatch.setattr(process, "apply_async", offline)
    path, job = queued(api)
    assert job["dispatch_warning"] and job["state"] == "queued"
    assert process_job(job["id"]) == "awaiting_review"


def test_header_manual_and_invalid_row_review(api):
    path, job, detail = processed(api)
    result = call(
        api,
        "PATCH",
        path + "/header",
        json={
            "revision": detail["revision"],
            "fields": {"external_rfq_number": "MANUAL-001", "contact_email": "invalid"},
            "reason": "Human source check",
        },
    )
    assert result.status_code == 200
    current = call(api, "GET", path).json()
    assert any("contact_email" in issue for issue in current["approval_issues"])
    result = call(
        api,
        "POST",
        path + "/line-items",
        json={
            "revision": current["revision"],
            "fields": {"description": "Excluded row", "quantity": "0"},
            "reason": "Not a requested product",
            "review_status": "invalid",
        },
    )
    assert result.status_code == 201, result.text
    current = call(api, "GET", path).json()
    assert len(current["items"]) == 2 and any(
        item["review_status"] == "invalid" for item in current["items"]
    )
    assert (
        call(
            api,
            "PATCH",
            path + "/header",
            json={
                "revision": current["revision"],
                "fields": {"contact_email": None},
                "reason": "No verified contact present",
            },
        ).status_code
        == 200
    )


def test_body_limit_before_multipart(api):
    client, workspace, _, user = api
    path = "/api/rfqs"
    headers = authorization("POST", path, workspace, user) | {
        "content-length": str(30 * 1024 * 1024)
    }
    response = client.post(path, headers=headers, content=b"small actual body")
    assert response.status_code == 413


def test_database_loss_is_sanitized(api, monkeypatch):
    from contextlib import contextmanager
    import psycopg

    @contextmanager
    def unavailable():
        raise psycopg.OperationalError(
            "sensitive connection details must not reach the response"
        )
        yield

    monkeypatch.setattr("api.rfq.auth.connection", unavailable)
    response = call(api, "GET", "/api/rfqs")
    assert response.status_code == 503
    assert "sensitive" not in response.text and "Database" in response.text


def test_reviewer_can_clear_unverified_proposals_without_losing_original(api):
    from api.rfq.contracts import FieldValue
    from api.rfq.repository import load_rfq, items, save_item
    from psycopg.types.json import Jsonb

    path, job, detail = processed(api)
    with connection() as conn:
        rfq = load_rfq(conn, detail["id"], api[1], True)
        item = items(conn, rfq)[0]
        item.fields["mpn"] = FieldValue(raw="UNSUPPORTED-PROPOSAL", status="unverified")
        save_item(conn, rfq, item)
        conn.execute(
            "update procurement.rfqs set header=%s where id=%s",
            (
                Jsonb(
                    {
                        "contact_email": FieldValue(
                            raw="unsupported@example.test", status="unverified"
                        ).model_dump()
                    }
                ),
                detail["id"],
            ),
        )
    result = call(
        api,
        "PATCH",
        path + f"/line-items/{item.id}",
        json={
            "revision": detail["revision"],
            "fields": {"mpn": None},
            "reason": "No verified MPN; explicitly cleared proposed value",
            "review_status": "reviewed",
        },
    )
    assert result.status_code == 200
    result = call(
        api,
        "PATCH",
        path + "/header",
        json={
            "revision": result.json()["revision"],
            "fields": {"contact_email": None},
            "reason": "No sourced contact email",
        },
    )
    assert result.status_code == 200
    current = call(api, "GET", path).json()
    field = current["items"][0]["fields"]["mpn"]
    assert (
        field["value"] is None
        and field["raw"] == "UNSUPPORTED-PROPOSAL"
        and field["corrected"]
    )
    assert not current["approval_issues"]
    assert (
        call(
            api, "POST", path + "/approve", json={"revision": current["revision"]}
        ).status_code
        == 200
    )
