"""Isolated PostgreSQL security/lifecycle tests; explicit fixtures are not agent benchmarks."""

import json
from datetime import date, timedelta
from uuid import uuid4

import pytest
from conftest import authorization
from psycopg.errors import RaiseException

from api.catalog.service import build, retrieve
from api.procurement_agent.runner import run_agent
from api.rfq.db import connection
from test_catalog_integration import catalog_fixture, confirm, approved  # noqa: F401

pytestmark = pytest.mark.integration


@pytest.fixture
def commercial_flow(catalog_fixture, monkeypatch):  # noqa: F811
    api, request, catalog, preview = catalog_fixture
    confirm(request, catalog, preview)
    assert build(preview["id"]) == "published"
    rfq = approved(request)
    line = rfq["items"][0]["id"]
    search = request(
        "POST",
        f"/api/rfqs/{rfq['id']}/line-items/{line}/matches",
        json={"revision": rfq["revision"], "versions": [preview["id"]]},
    ).json()
    product = search["candidates"][0]["id"]
    assert (
        request(
            "POST",
            f"/api/catalog-match-runs/{search['id']}/review",
            json={
                "decision": "select",
                "product_id": product,
                "note": "Explicit exact identity review",
            },
        ).status_code
        == 201
    )
    resolution = request(
        "POST",
        f"/api/rfqs/{rfq['id']}/line-items/{line}/selection-resolution",
        json={
            "expected_revision": 0,
            "run_id": search["id"],
            "decision": "select",
            "product_id": product,
            "version_id": preview["id"],
            "reason": "Authorized final selection resolution",
        },
    )
    assert resolution.status_code == 201, resolution.text
    commercial = {
        "supplier": "Fictional supplier",
        "price": "10",
        "currency": "USD",
        "price_basis": "each",
        "pack_size": 1,
        "minimum_units": "1",
        "availability": "available",
        "observed_on": str(date.today()),
        "valid_until": str(date.today() + timedelta(days=30)),
        "source_reference": "Synthetic signed note SYN-001, not a real quote",
    }
    offer = request(
        "POST",
        "/api/supplier-offers/attestations",
        json={
            "resolution_id": resolution.json()["id"],
            "commercial": commercial,
            "reason": "Synthetic commercial evidence review",
        },
    )
    assert offer.status_code == 201, offer.text
    policy = {
        "currency": "USD",
        "shipping": "5",
        "tax_rate": "0.1",
        "tax_basis": "subtotal_plus_shipping",
        "valid_until": str(date.today() + timedelta(days=7)),
        "pricing": {
            "mode": "markup",
            "rate": "0.2",
            "discount": "0",
            "surplus": "allocate_purchase_cost",
        },
    }
    payload = {
        "policy": policy,
        "offer_choices": {line: offer.json()["id"]},
        "reason": "Prepare synthetic internal quote",
    }
    return (
        api,
        request,
        rfq,
        line,
        search,
        resolution.json(),
        offer.json(),
        payload,
        preview,
    )


def create(flow):
    _, request, rfq, _, _, _, _, payload, _ = flow
    result = request("POST", f"/api/rfqs/{rfq['id']}/quotes", json=payload)
    assert result.status_code == 201, result.text
    return result.json()


def test_quote_review_decimal_approval_immutable_new_version(commercial_flow):
    _, request, _, _, _, _, _, payload, _ = commercial_flow
    quote = create(commercial_flow)
    assert quote["calculation"]["grand_total"] == "31.90"
    path = f"/api/quotes/{quote['id']}"
    assert (
        request(
            "POST",
            path + "/approve",
            json={
                "revision": 1,
                "reason": "Review commercial sources",
                "inputs_reviewed": True,
            },
        ).status_code
        == 409
    )
    assert (
        request(
            "POST",
            path + "/submit",
            json={
                "revision": 1,
                "reason": "Review commercial sources",
                "inputs_reviewed": False,
            },
        ).status_code
        == 422
    )
    submitted = request(
        "POST",
        path + "/submit",
        json={
            "revision": 1,
            "reason": "Review commercial sources",
            "inputs_reviewed": True,
        },
    ).json()
    assert submitted["state"] == "under_review"
    assert request("PATCH", path, json={**payload, "revision": 2}).status_code == 409
    approved_quote = request(
        "POST",
        path + "/approve",
        json={
            "revision": 2,
            "reason": "Verified all commercial evidence",
            "inputs_reviewed": True,
        },
    )
    assert approved_quote.status_code == 200, approved_quote.text
    assert approved_quote.json()["state"] == "approved_internal"
    assert request("PATCH", path, json={**payload, "revision": 3}).status_code == 409
    with pytest.raises(RaiseException), connection() as conn:
        conn.execute(
            "update procurement.quote_drafts set policy='{}' where id=%s",
            (quote["id"],),
        )
    assert request("POST", path + "/new-version", json=payload).status_code == 201
    assert len(request("GET", path + "/history").json()) == 3
    assert len(request("GET", path + "/audit").json()) == 3


def test_stale_revision_changes_requested_reject(commercial_flow):
    _, request, _, _, _, _, _, payload, _ = commercial_flow
    quote = create(commercial_flow)
    path = f"/api/quotes/{quote['id']}"
    assert request("PATCH", path, json={**payload, "revision": 0}).status_code == 422
    assert request("PATCH", path, json={**payload, "revision": 9}).status_code == 409
    assert (
        request(
            "POST",
            path + "/submit",
            json={
                "revision": 1,
                "reason": "Explicit evidence review",
                "inputs_reviewed": True,
            },
        ).status_code
        == 200
    )
    changed = request(
        "POST",
        path + "/request-changes",
        json={"revision": 2, "reason": "Need commercial price revision"},
    ).json()
    assert changed["state"] == "changes_requested"
    edited = request("PATCH", path, json={**payload, "revision": 3}).json()
    assert edited["revision"] == 4
    request(
        "POST",
        path + "/submit",
        json={
            "revision": 4,
            "reason": "Reviewed edited commercial evidence",
            "inputs_reviewed": True,
        },
    )
    assert (
        request(
            "POST",
            path + "/reject",
            json={"revision": 5, "reason": "Commercial proposal declined"},
        ).json()["state"]
        == "rejected"
    )


def test_cross_workspace_and_role_denials(commercial_flow):
    api, request, rfq, _, _, _, offer, payload, _ = commercial_flow
    client, workspace, other, user = api
    quote = create(commercial_flow)
    with connection() as conn:
        conn.execute(
            "insert into workspace_members(workspace_id,user_id,role) values(%s,%s,'owner')",
            (other, user),
        )
        conn.execute(
            "update workspace_members set role='editor' where workspace_id=%s and user_id=%s",
            (workspace, user),
        )
    for path in [
        f"/api/quotes/{quote['id']}",
        f"/api/supplier-offers/attestations/{offer['id']}",
        f"/api/rfqs/{rfq['id']}/selections",
    ]:
        assert (
            client.get(
                path, headers=authorization("GET", path, other, user)
            ).status_code
            == 404
        )
        assert client.get(path).status_code == 401
    assert (
        request(
            "POST",
            f"/api/quotes/{quote['id']}/approve",
            json={
                "revision": 1,
                "reason": "Attempt editor approval",
                "inputs_reviewed": True,
            },
        ).status_code
        == 403
    )
    with connection() as conn:
        conn.execute(
            "update workspace_members set role='viewer' where workspace_id=%s and user_id=%s",
            (workspace, user),
        )
    assert (
        request("POST", f"/api/rfqs/{rfq['id']}/quotes", json=payload).status_code
        == 403
    )


def test_unknown_commercial_facts_block_approval(commercial_flow):
    _, request, rfq, _, _, _, _, payload, _ = commercial_flow
    incomplete = {**payload, "offer_choices": {}}
    quote = request("POST", f"/api/rfqs/{rfq['id']}/quotes", json=incomplete).json()
    assert (
        quote["state"] == "incomplete" and quote["calculation"]["grand_total"] is None
    )
    assert (
        request(
            "POST",
            f"/api/quotes/{quote['id']}/submit",
            json={
                "revision": 1,
                "reason": "Unknown offer cannot be approved",
                "inputs_reviewed": True,
            },
        ).status_code
        == 409
    )


def test_superseded_search_invalidates_selection_and_quote(commercial_flow):
    _, request, rfq, line, _, _, _, _, preview = commercial_flow
    quote = create(commercial_flow)
    assert (
        request(
            "POST",
            f"/api/rfqs/{rfq['id']}/line-items/{line}/matches",
            json={"revision": rfq["revision"], "versions": [preview["id"]]},
        ).status_code
        == 201
    )
    view = request("GET", f"/api/rfqs/{rfq['id']}/selections").json()
    assert view["lines"][0]["selection"]["state"] == "superseded_search_or_review"
    assert (
        request(
            "POST",
            f"/api/quotes/{quote['id']}/submit",
            json={
                "revision": 1,
                "reason": "Must re-review new search",
                "inputs_reviewed": True,
            },
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "method,channels",
    [
        ("exact", ["exact"]),
        ("bm25", ["bm25"]),
        ("sql", ["sql_fts"]),
        ("exact_bm25", ["exact", "bm25"]),
    ],
)
def test_lexical_retrieval_survives_embedding_outage(
    commercial_flow, monkeypatch, method, channels
):
    api, request, rfq, line, _, _, _, _, preview = commercial_flow

    class Offline:
        def __init__(self):
            raise AssertionError("Non-vector retrieval must not instantiate provider")

    monkeypatch.setattr("api.catalog.service.Embeddings", Offline)
    result = retrieve(
        api[1],
        [preview["id"]],
        {
            "manufacturer": "Northvale",
            "mpn": "000-TEST.1",
            "description": "Synthetic device",
        },
        method,
    )
    assert (
        result["executed_channels"] == channels and result["model"]["invoked"] is False
    )
    response = request(
        "POST",
        f"/api/rfqs/{rfq['id']}/line-items/{line}/matches",
        json={
            "revision": rfq["revision"],
            "versions": [preview["id"]],
            "method": method,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["executed_channels"] == channels


def test_vector_digest_mismatch_and_outage_never_silent_fallback(commercial_flow):
    api, _, _, _, _, _, _, _, preview = commercial_flow

    class Stale:
        def health(self):
            return {"model": "explicit-fixture", "digest": "different"}

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        retrieve(api[1], [preview["id"]], {}, "reranked", Stale())
    assert exc.value.status_code == 409

    class Offline:
        def health(self):
            raise ValueError("Embedding service offline")

    with pytest.raises(RuntimeError, match="vector channel unavailable"):
        retrieve(api[1], [preview["id"]], {}, "reranked", Offline())


class ExplicitNativeFixture:
    """Protocol fixture for runner mechanics; excluded from real-model metrics."""

    def health(self):
        return {"digest": "explicit-protocol-fixture"}

    def chat(self, messages, tools, expected_digest, **kwargs):
        if len(messages) == 1:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "get_approved_rfq", "arguments": {}}}
                ],
            }, None
        results = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
        if len(results) == 1:
            line = results[0]["data"]["lines"][0]["line_id"]
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "get_supplier_offers",
                            "arguments": {"line_id": line},
                        }
                    }
                ],
            }, None
        result = results[-1]
        return {"role": "assistant", "content": ""}, json.dumps(
            {
                "claims": [
                    {
                        "receipt_id": result["receipt_id"],
                        "pointer": "/data/selection_state",
                        "value": "resolved",
                    }
                ]
            }
        )


def research_start(flow, monkeypatch):
    _, request, rfq, *_ = flow
    monkeypatch.setattr(
        "api.procurement_agent.routes.LocalModel", ExplicitNativeFixture
    )
    monkeypatch.setattr(
        "api.procurement_agent.worker.research.apply_async", lambda **kwargs: None
    )
    payload = {"revision": rfq["revision"], "idempotency_key": str(uuid4())}
    result = request("POST", f"/api/rfqs/{rfq['id']}/research", json=payload)
    assert result.status_code == 202, result.text
    return result.json(), payload


def test_durable_agent_receipts_idempotence_and_cancellation(
    commercial_flow, monkeypatch
):
    _, request, rfq, *_ = commercial_flow
    run, payload = research_start(commercial_flow, monkeypatch)
    assert (
        request("POST", f"/api/rfqs/{rfq['id']}/research", json=payload).json()["id"]
        == run["id"]
    )
    assert run_agent(run["id"], ExplicitNativeFixture()) == "complete"
    assert run_agent(run["id"], ExplicitNativeFixture()) == "terminal"
    tools = request("GET", f"/api/agent-runs/{run['id']}/tools").json()
    assert len(tools) == 2 and all(t["status"] == "succeeded" for t in tools)
    assert (
        request("GET", f"/api/agent-runs/{run['id']}").json()["result"]["claims"][0][
            "value"
        ]
        == "resolved"
    )
    second, _ = research_start(commercial_flow, monkeypatch)
    request("POST", f"/api/agent-runs/{second['id']}/cancel")
    assert run_agent(second["id"], ExplicitNativeFixture()) == "terminal"
    assert request("GET", f"/api/agent-runs/{second['id']}/tools").json() == []


def test_agent_rejects_malicious_native_tool_request(commercial_flow, monkeypatch):
    class Attack(ExplicitNativeFixture):
        def chat(self, *args):
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "run_shell",
                            "arguments": {"command": "echo attack"},
                        }
                    }
                ],
            }, None

    run, _ = research_start(commercial_flow, monkeypatch)
    assert run_agent(run["id"], Attack()) == "needs_attention"
    _, request, *_ = commercial_flow
    receipts = request("GET", f"/api/agent-runs/{run['id']}/tools").json()
    assert (
        receipts[0]["status"] == "rejected"
        and receipts[0]["policy"] == "policy_or_data_error"
    )


def test_conflicting_review_requires_explicit_authorized_resolution(commercial_flow):
    api, request, rfq, line, search, resolution, _, _, preview = commercial_flow
    with connection() as conn:
        conn.execute(
            "insert into procurement.catalog_match_reviews(run_id,actor,decision,product_id,note) values(%s,'independent-synthetic-reviewer','reject',%s,'Explicit contradictory source review')",
            (search["id"], resolution["data"]["product_id"]),
        )
    view = request("GET", f"/api/rfqs/{rfq['id']}/selections").json()["lines"][0][
        "selection"
    ]
    assert view["state"] == "superseded_search_or_review"
    stale = request(
        "POST",
        f"/api/rfqs/{rfq['id']}/line-items/{line}/selection-resolution",
        json={
            "expected_revision": 0,
            "run_id": search["id"],
            "decision": "select",
            "product_id": resolution["data"]["product_id"],
            "version_id": preview["id"],
            "reason": "Resolve disagreement after independent review",
        },
    )
    assert stale.status_code == 409
    resolved = request(
        "POST",
        f"/api/rfqs/{rfq['id']}/line-items/{line}/selection-resolution",
        json={
            "expected_revision": 1,
            "run_id": search["id"],
            "decision": "select",
            "product_id": resolution["data"]["product_id"],
            "version_id": preview["id"],
            "reason": "Resolve disagreement after independent review",
        },
    )
    assert resolved.status_code == 201
    assert (
        request("GET", f"/api/rfqs/{rfq['id']}/selections").json()["lines"][0][
            "selection"
        ]["state"]
        == "resolved"
    )


def test_changed_offer_requires_supersession_and_recalculation(commercial_flow):
    _, request, rfq, line, _, resolution, offer, payload, _ = commercial_flow
    quote = create(commercial_flow)
    changed = {**offer["data"]["commercial"], "price": "11"}
    newer = request(
        "POST",
        "/api/supplier-offers/attestations",
        json={
            "resolution_id": resolution["id"],
            "commercial": changed,
            "reason": "Explicit changed commercial source",
        },
    )
    assert newer.status_code == 201
    assert (
        request(
            "POST",
            f"/api/quotes/{quote['id']}/submit",
            json={
                "revision": 1,
                "reason": "Stale commercial evidence must block",
                "inputs_reviewed": True,
            },
        ).status_code
        == 409
    )
    conflicted = request(
        "PATCH", f"/api/quotes/{quote['id']}", json={**payload, "revision": 1}
    ).json()
    assert any(
        "conflicting_supplier" in issue for issue in conflicted["calculation"]["issues"]
    )
    # Supersede both contradictory branches explicitly; no implicit newest-price preference.
    third = request(
        "POST",
        "/api/supplier-offers/attestations",
        json={
            "resolution_id": resolution["id"],
            "commercial": changed,
            "supersedes_id": offer["id"],
            "reason": "Explicitly supersede original source",
        },
    ).json()
    assert third["data"]["supersedes_id"] == offer["id"]
    chosen = {**payload, "offer_choices": {line: third["id"]}, "revision": 2}
    calculated = request("PATCH", f"/api/quotes/{quote['id']}", json=chosen).json()
    assert calculated["calculation"]["complete"] is True
    offers = request("GET", f"/api/rfqs/{rfq['id']}/selections").json()["lines"][0][
        "offers"
    ]["attestations"]
    assert (
        next(entry for entry in offers if entry["id"] == offer["id"])[
            "commercial_review_state"
        ]
        == "superseded"
    )
    comparison = request(
        "GET", f"/api/supplier-offers/resolutions/{resolution['id']}/comparison"
    ).json()
    assert {
        entry["price"] for group in comparison["groups"].values() for entry in group
    } == {"11"}
    assert {entry["offer_id"] for entry in comparison["excluded"]} == {offer["id"]}


def test_no_match_resolution_preserved_and_cannot_quote(commercial_flow):
    _, request, rfq, line, search, _, _, payload, _ = commercial_flow
    result = request(
        "POST",
        f"/api/rfqs/{rfq['id']}/line-items/{line}/selection-resolution",
        json={
            "expected_revision": 1,
            "run_id": search["id"],
            "decision": "no_match",
            "reason": "Authorized no suitable product outcome",
        },
    )
    assert result.status_code == 201
    result = request(
        "POST", f"/api/rfqs/{rfq['id']}/quotes", json={**payload, "offer_choices": {}}
    ).json()
    assert (
        result["state"] == "incomplete"
        and result["snapshot"]["lines"][0]["selection"]["state"] == "no_match"
    )


def test_repeat_limit_and_planning_budget(commercial_flow, monkeypatch):
    class Loop(ExplicitNativeFixture):
        def chat(self, *args, **kwargs):
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "get_approved_rfq", "arguments": {}}}
                ],
            }, None

    run, _ = research_start(commercial_flow, monkeypatch)
    assert run_agent(run["id"], Loop()) == "needs_attention"
    _, request, *_ = commercial_flow
    receipts = request("GET", f"/api/agent-runs/{run['id']}/tools").json()
    assert len(receipts) == 3 and receipts[-1]["status"] == "rejected"
    assert "Repeated equivalent" in receipts[-1]["error"]


def test_stale_catalog_blocks_quote_and_attestation(commercial_flow):
    _, request, rfq, _, _, resolution, offer, payload, preview = commercial_flow
    quote = create(commercial_flow)
    with connection() as conn:
        conn.execute(
            "update procurement.catalog_versions set state='superseded' where id=%s",
            (preview["id"],),
        )
    assert (
        request("GET", f"/api/rfqs/{rfq['id']}/selections").json()["lines"][0][
            "selection"
        ]["state"]
        == "stale_catalog"
    )
    assert (
        request(
            "POST",
            "/api/supplier-offers/attestations",
            json={
                "resolution_id": resolution["id"],
                "commercial": offer["data"]["commercial"],
                "reason": "Cannot attest a stale product",
            },
        ).status_code
        == 409
    )

    assert (
        request(
            "POST",
            f"/api/quotes/{quote['id']}/submit",
            json={
                "revision": 1,
                "reason": "Stale catalog approval must fail",
                "inputs_reviewed": True,
            },
        ).status_code
        == 409
    )


def test_compatible_alternative_requires_suitability_attestation(commercial_flow):
    _, request, rfq, line, search, resolution, _, _, preview = commercial_flow
    with connection() as conn:
        result = conn.execute(
            "select result from procurement.catalog_match_runs where id=%s",
            (search["id"],),
        ).fetchone()["result"]
        result["candidates"][0]["compatibility"]["status"] = "compatible_alternative"
        from psycopg.types.json import Jsonb

        conn.execute(
            "update procurement.catalog_match_runs set result=%s where id=%s",
            (Jsonb(result), search["id"]),
        )
    payload = {
        "expected_revision": 1,
        "run_id": search["id"],
        "decision": "select",
        "product_id": resolution["data"]["product_id"],
        "version_id": preview["id"],
        "reason": "Independent alternative compatibility review",
    }
    path = f"/api/rfqs/{rfq['id']}/line-items/{line}/selection-resolution"
    assert request("POST", path, json=payload).status_code == 422
    assert (
        request(
            "POST", path, json={**payload, "alternative_attested": True}
        ).status_code
        == 201
    )


def test_duplicate_approval_never_adds_a_version(commercial_flow):
    _, request, *_ = commercial_flow
    quote = create(commercial_flow)
    path = f"/api/quotes/{quote['id']}"
    request(
        "POST",
        path + "/submit",
        json={
            "revision": 1,
            "reason": "Review all commercial inputs",
            "inputs_reviewed": True,
        },
    )
    payload = {
        "revision": 2,
        "reason": "Independent commercial approval",
        "inputs_reviewed": True,
    }
    assert request("POST", path + "/approve", json=payload).status_code == 200
    assert request("POST", path + "/approve", json=payload).status_code == 409
    assert len(request("GET", path + "/history").json()) == 3


def test_procurement_body_size_is_bounded(api):
    client, workspace, _, user = api
    path = "/api/supplier-offers/attestations"
    assert (
        client.post(
            path,
            content="x" * 262145,
            headers=authorization("POST", path, workspace, user),
        ).status_code
        == 413
    )


def test_concurrent_approvals_publish_once(commercial_flow):
    from concurrent.futures import ThreadPoolExecutor

    _, request, *_ = commercial_flow
    quote = create(commercial_flow)
    path = f"/api/quotes/{quote['id']}"
    request(
        "POST",
        path + "/submit",
        json={
            "revision": 1,
            "reason": "Reviewed all financial sources",
            "inputs_reviewed": True,
        },
    )

    def approve(index):
        return request(
            "POST",
            path + "/approve",
            json={
                "revision": 2,
                "reason": f"Concurrent review attempt {index}",
                "inputs_reviewed": True,
            },
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        codes = list(executor.map(approve, [1, 2]))
    assert sorted(codes) == [200, 409]
    assert len(request("GET", path + "/history").json()) == 3


def test_missing_tool_response_outage_and_retry_cap(commercial_flow, monkeypatch):
    import httpx

    run, _ = research_start(commercial_flow, monkeypatch)

    def outage(*args):
        raise httpx.ReadTimeout("Explicit tool outage fixture")

    monkeypatch.setattr("api.procurement_agent.runner.execute", outage)
    assert run_agent(run["id"], ExplicitNativeFixture()) == "needs_attention"
    _, request, *_ = commercial_flow
    receipts = request("GET", f"/api/agent-runs/{run['id']}/tools").json()
    assert receipts[0]["status"] == "failed" and "ReadTimeout" in receipts[0]["error"]
    second, _ = research_start(commercial_flow, monkeypatch)
    with connection() as conn:
        conn.execute(
            "update procurement.procurement_agent_runs set attempts=3 where id=%s",
            (second["id"],),
        )
    assert run_agent(second["id"], ExplicitNativeFixture()) == "failed"


def test_foreign_research_receipts_and_quote_history_denied(
    commercial_flow, monkeypatch
):
    from conftest import authorization

    api, request, rfq, *_ = commercial_flow
    client, workspace, other, user = api
    quote = create(commercial_flow)
    run, _ = research_start(commercial_flow, monkeypatch)
    with connection() as conn:
        conn.execute(
            "insert into workspace_members(workspace_id,user_id,role) values(%s,%s,'owner')",
            (other, user),
        )
    for path in [
        f"/api/agent-runs/{run['id']}",
        f"/api/agent-runs/{run['id']}/tools",
        f"/api/agent-runs/{run['id']}/evidence",
        f"/api/quotes/{quote['id']}/history",
        f"/api/quotes/{quote['id']}/audit",
    ]:
        assert (
            client.get(
                path, headers=authorization("GET", path, other, user)
            ).status_code
            == 404
        )
    request("POST", f"/api/agent-runs/{run['id']}/cancel")
