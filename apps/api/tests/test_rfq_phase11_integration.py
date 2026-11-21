import pytest
from conftest import authorization
from api.rfq.db import connection
from api.rfq.worker import process_job
from api.rfq.contracts import Proposal

pytestmark = pytest.mark.integration
CSV = b"Description,Qty,MPN,UOM\nLaptop,2,00-X,EA\n"


def request(api, method, path, **kwargs):
    client, workspace, _, user = api
    return client.request(
        method, path, headers=authorization(method, path, workspace, user), **kwargs
    )


def queued(api, content=CSV):
    rfq = request(
        api, "POST", "/api/rfqs", json={"title": "Phase 1.1 synthetic integration"}
    ).json()
    path = f"/api/rfqs/{rfq['id']}"
    assert (
        request(
            api,
            "POST",
            path + "/documents",
            data={"revision": 0},
            files={"file": ("sample.csv", content, "text/csv")},
        ).status_code
        == 201
    )
    response = request(
        api,
        "POST",
        path + "/process",
        json={"revision": 1, "mode": "hybrid", "policy": "selective-v2"},
    )
    assert response.status_code == 202, response.text
    return path, response.json()


def test_policy_snapshot_and_metadata_persistence(api):
    path, job = queued(api)
    assert job["configuration"]["policy"] == "selective-v2"
    assert "model_schema_profile" in job["configuration"]
    assert process_job(job["id"]) == "awaiting_review"
    detail = request(api, "GET", path).json()
    metadata = detail["runs"][0]["metadata"]
    assert metadata["policy"] == "selective-v2" and metadata["model_call_count"] == 0
    assert metadata["queue_wait_ms"] is not None
    assert (
        detail["items"][0]["fields"]["quantity"]["evidence"][0]["row_association"]
        == "verified"
    )


def test_cancel_during_selective_inference_prevents_publication(api, monkeypatch):
    path, job = queued(api, CSV.replace(b"Laptop,2", b"Laptop,"))

    class ExplicitCancellationFixture:
        async def extract(self, blocks):
            with connection() as conn:
                conn.execute(
                    "update procurement.rfq_processing_jobs set state='cancelled' where id=%s",
                    (job["id"],),
                )
            return Proposal.model_validate({"header": {}, "items": []}), {
                "model": "explicit-cancellation-fixture"
            }

    monkeypatch.setattr(
        "api.rfq.selective.OllamaProvider",
        lambda **kwargs: ExplicitCancellationFixture(),
    )
    assert process_job(job["id"]) == "cancelled"
    detail = request(api, "GET", path).json()
    assert not detail["runs"] and detail["jobs"][0]["state"] == "cancelled"


def test_cancel_immediately_before_publication(api, monkeypatch):
    from api.rfq.repository import publish

    path, job = queued(api)

    def cancelled(conn, persisted, result):
        conn.execute(
            "update procurement.rfq_processing_jobs set state='cancelled' where id=%s",
            (persisted["id"],),
        )
        return publish(conn, persisted, result)

    monkeypatch.setattr("api.rfq.worker.publish", cancelled)
    assert process_job(job["id"]) == "cancelled"
    assert not request(api, "GET", path).json()["runs"]


def test_historical_job_configuration_retains_phase1(api):
    path, job = queued(api)
    with connection() as conn:
        conn.execute(
            'update procurement.rfq_processing_jobs set configuration=\'{"policy":"phase1","ocr_strategy":"legacy-v1"}\'::jsonb where id=%s',
            (job["id"],),
        )
    assert process_job(job["id"]) == "awaiting_review"
    detail = request(api, "GET", path).json()
    assert detail["runs"][0]["metadata"]["policy"] == "phase1"
    assert detail["items"][0]["fields"]["mpn"]["value"] == "00-X"
    assert process_job(job["id"]) == "terminal"
