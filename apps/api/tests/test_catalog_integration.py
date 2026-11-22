import json
from uuid import uuid4

import pytest
from conftest import authorization
from api.catalog.service import build
from api.rfq.worker import process_job
from api.rfq.db import connection

pytestmark = pytest.mark.integration
ROW = dict(
    source_id="synthetic-source",
    manufacturer="Northvale",
    mpn="000-TEST.1",
    name="Synthetic device",
    category="memory",
    specs={"capacity": 32},
)


@pytest.fixture
def catalog_fixture(api, monkeypatch):
    class ExplicitEmbeddingFixture:
        model = "explicit-fixture"

        def health(self):
            return {
                "model": self.model,
                "digest": "fixture-digest",
                "dimension": 768,
                "preprocessing": "explicit-fixture",
            }

        def encode(self, texts, **kwargs):
            return [[1.0] + [0.0] * 767 for _ in texts]

    monkeypatch.setattr("api.catalog.service.Embeddings", ExplicitEmbeddingFixture)
    monkeypatch.setattr("api.catalog.routes.dispatch", lambda version: None)
    client, workspace, _, user = api

    def request(method, path, **kwargs):
        return client.request(
            method, path, headers=authorization(method, path, workspace, user), **kwargs
        )

    catalog = request(
        "POST",
        "/api/catalogs",
        json={"name": "Explicit integration fixture", "license": "Synthetic"},
    ).json()
    preview = request(
        "POST",
        f"/api/catalogs/{catalog['id']}/imports/preview",
        files={
            "file": ("fixture.json", json.dumps([ROW]).encode(), "application/json")
        },
    ).json()
    return api, request, catalog, preview


def confirm(request, catalog, preview):
    return request(
        "POST",
        f"/api/catalogs/{catalog['id']}/imports/confirm",
        json={"version_id": preview["id"], "fingerprint": preview["fingerprint"]},
    )


def approved(request):
    rfq = request(
        "POST", "/api/rfqs", json={"title": "Synthetic catalog boundary"}
    ).json()
    path = f"/api/rfqs/{rfq['id']}"
    request(
        "POST",
        path + "/documents",
        data={"revision": 0},
        files={
            "file": (
                "x.csv",
                b"Manufacturer,MPN,Description,Qty,UOM\nNorthvale,000-TEST.1,Synthetic device,2,EA\n",
                "text/csv",
            )
        },
    )
    job = request(
        "POST", path + "/process", json={"revision": 1, "mode": "deterministic"}
    ).json()
    assert process_job(job["id"]) == "awaiting_review"
    detail = request("GET", path).json()
    item = detail["items"][0]
    saved = request(
        "PATCH",
        path + f"/line-items/{item['id']}",
        json={
            "revision": detail["revision"],
            "fields": {},
            "reason": "Explicit source review",
            "review_status": "reviewed",
        },
    ).json()
    assert (
        request(
            "POST", path + "/approve", json={"revision": saved["revision"]}
        ).status_code
        == 200
    )
    return request("GET", path).json()


def test_idempotent_import_and_publication(catalog_fixture):
    _, request, catalog, preview = catalog_fixture
    assert preview["counts"]["canonical_products"] == 1
    assert confirm(request, catalog, preview).status_code == 202
    assert build(preview["id"]) == "published"
    assert confirm(request, catalog, preview).status_code == 202
    assert build(preview["id"]) == "terminal"
    with connection() as conn:
        assert (
            conn.execute(
                "select count(*) as n from procurement.catalog_products where version_id=%s",
                (preview["id"],),
            ).fetchone()["n"]
            == 1
        )


def test_confirm_hash_and_workspace_boundaries(catalog_fixture):
    api, request, catalog, preview = catalog_fixture
    assert (
        request(
            "POST",
            f"/api/catalogs/{catalog['id']}/imports/confirm",
            json={"version_id": preview["id"], "fingerprint": "0" * 64},
        ).status_code
        == 409
    )
    client, _, other, user = api
    with connection() as conn:
        conn.execute(
            "insert into workspace_members(workspace_id,user_id,role) values(%s,%s,'owner')",
            (other, user),
        )
    path = f"/api/catalog-import-jobs/{preview['id']}"
    assert (
        client.get(path, headers=authorization("GET", path, other, user)).status_code
        == 404
    )


def test_approved_query_selection_audit_and_stale_index(catalog_fixture):
    _, request, catalog, preview = catalog_fixture
    confirm(request, catalog, preview)
    assert build(preview["id"]) == "published"
    detail = approved(request)
    item = detail["items"][0]
    path = f"/api/rfqs/{detail['id']}/line-items/{item['id']}/matches"
    assert (
        request(
            "POST",
            path,
            json={"revision": detail["revision"] - 1, "versions": [preview["id"]]},
        ).status_code
        == 409
    )
    result = request(
        "POST", path, json={"revision": detail["revision"], "versions": [preview["id"]]}
    ).json()
    assert (
        result["query"]["mpn"] == "000-TEST.1"
        and result["candidates"][0]["compatibility"]["status"] == "exact"
    )
    review_path = f"/api/catalog-match-runs/{result['id']}/review"
    payload = {
        "decision": "select",
        "product_id": result["candidates"][0]["id"],
        "note": "Verified synthetic fixture",
    }
    assert request("POST", review_path, json=payload).status_code == 201
    assert request("POST", review_path, json=payload).status_code == 409
    assert (
        len(request("GET", f"/api/catalog-match-runs/{result['id']}/audit").json()) == 2
    )
    assert (
        request("GET", f"/api/catalog-match-runs/{result['id']}").json()["reviews"][0][
            "decision"
        ]
        == "select"
    )
    with connection() as conn:
        conn.execute(
            "update procurement.catalog_versions set state='superseded' where id=%s",
            (preview["id"],),
        )
    assert (
        request(
            "POST",
            path,
            json={"revision": detail["revision"], "versions": [preview["id"]]},
        ).status_code
        == 409
    )


def test_unapproved_rfq_cannot_search(catalog_fixture):
    _, request, _, preview = catalog_fixture
    rfq = request("POST", "/api/rfqs", json={"title": "Unapproved"}).json()
    assert (
        request(
            "POST",
            f"/api/rfqs/{rfq['id']}/line-items/{uuid4()}/matches",
            json={"revision": 0, "versions": [preview["id"]]},
        ).status_code
        == 409
    )


def test_failed_embedding_does_not_publish(catalog_fixture, monkeypatch):
    _, request, catalog, preview = catalog_fixture

    class ExplicitFailureFixture:
        def health(self):
            raise RuntimeError("Explicit injected embedding outage")

    monkeypatch.setattr("api.catalog.service.Embeddings", ExplicitFailureFixture)
    confirm(request, catalog, preview)
    assert build(preview["id"]) == "failed"
    assert (
        request("GET", f"/api/catalogs/{catalog['id']}").json()["catalog"][
            "active_version"
        ]
        is None
    )
    with connection() as conn:
        assert (
            conn.execute(
                "select count(*) as n from procurement.catalog_products where version_id=%s",
                (preview["id"],),
            ).fetchone()["n"]
            == 0
        )


def test_viewer_import_denied(catalog_fixture):
    api, request, _, _ = catalog_fixture
    with connection() as conn:
        conn.execute(
            "update workspace_members set role='viewer' where workspace_id=%s",
            (api[1],),
        )
    assert (
        request(
            "POST", "/api/catalogs", json={"name": "Denied", "license": "Synthetic"}
        ).status_code
        == 403
    )
