"""Controlled dependency/tool faults; these fixtures are not model measurements."""

from contextlib import contextmanager
from uuid import uuid4

import psycopg
import pytest

from api.procurement_agent import runner_v3 as runner, runner_v2
from api.procurement_agent.runner import run_agent
from test_procurement_planning_v3 import ModelFixture, start
from test_procurement_integration import (
    commercial_flow as _commercial_flow,
    catalog_fixture as _catalog_fixture,
)

commercial_flow = _commercial_flow
catalog_fixture = _catalog_fixture
pytestmark = pytest.mark.integration


def test_postgres_disconnect_between_receipts_retains_work_and_recovers(
    api, monkeypatch
):
    identifier, model, _ = start(api, monkeypatch, count=8)
    original_checkpoint = runner.checkpoint
    original_connection = runner.connection
    down = False

    @contextmanager
    def disconnected():
        if down:
            raise psycopg.OperationalError("Explicit controlled PostgreSQL outage")
        with original_connection() as conn:
            yield conn

    def interrupt(run_id, stage, **details):
        nonlocal down
        original_checkpoint(run_id, stage, **details)
        if stage == "receipt_persisted" and len(runner.calls(run_id)) == 2:
            down = True

    monkeypatch.setattr(runner, "connection", disconnected)
    monkeypatch.setattr(runner_v2, "connection", disconnected)
    monkeypatch.setattr(runner, "checkpoint", interrupt)
    with pytest.raises(psycopg.OperationalError):
        run_agent(identifier, model)
    down = False
    prior = runner.calls(identifier)
    monkeypatch.setattr(runner, "checkpoint", original_checkpoint)
    assert len(prior) == 2 and run_agent(identifier, model) == "complete"
    assert runner.calls(identifier)[:2] == prior
    assert runner.load(identifier)["attempts"] == 2


@pytest.mark.parametrize(
    "function",
    [
        {"name": "approve_quote", "arguments": {}},
        {"name": "fetch_url", "arguments": {"url": "http://127.0.0.1/private"}},
        {
            "name": "get_line_research_batch",
            "arguments": {"line_ids": [str(uuid4())], "price": "1"},
        },
    ],
)
def test_unsafe_native_requests_are_rejected_before_hybrid_recovery(
    api, monkeypatch, function
):
    identifier, provider, _ = start(api, monkeypatch, strategy="hybrid")
    original_chat = provider.chat

    def unsafe(messages, tools, digest, **kwargs):
        if not kwargs.get("finalize"):
            return {"role": "assistant", "tool_calls": [{"function": function}]}, None
        return original_chat(messages, tools, digest, **kwargs)

    provider.chat = unsafe
    assert run_agent(identifier, provider) == "complete"
    rows = runner.calls(identifier)
    assert all(row["status"] == "rejected" for row in rows[:2])
    assert all(row["execution_origin"] == "backend_scheduled" for row in rows[2:])
    assert runner.load(identifier)["result"]["tool_failures"]


def test_duplicate_batch_has_no_new_coverage_credit(api, monkeypatch):
    identifier, provider, _ = start(api, monkeypatch)
    original = provider.chat

    def duplicate(*args, **kwargs):
        message, summary = original(*args, **kwargs)
        requested = message.get("tool_calls", [])
        if requested and requested[0]["function"]["name"] == "get_line_research_batch":
            message["tool_calls"] = requested * 3
        return message, summary

    provider.chat = duplicate
    assert run_agent(identifier, provider) == "complete"
    rows = runner.calls(identifier)
    assert rows[1]["call_details"]["contributed_to_coverage"]
    assert not rows[2]["call_details"]["contributed_to_coverage"]
    assert rows[3]["status"] == "rejected" and rows[3]["error"] == "tool_repeat_limit"


def test_changed_attestation_between_batch_receipts_blocks_later_reads(
    commercial_flow, monkeypatch
):
    _, request, rfq, _, _, resolution, offer, _, _ = commercial_flow

    class SplitBatch(ModelFixture):
        def chat(self, messages, tools, digest, **kwargs):
            message, summary = super().chat(messages, tools, digest, **kwargs)
            calls = message.get("tool_calls", [])
            if calls and calls[0]["function"]["name"] == "get_line_research_batch":
                args = calls[0]["function"]["arguments"]
                message["tool_calls"] = [
                    {
                        "function": {
                            "name": "get_line_research_batch",
                            "arguments": {**args, "include": [kind]},
                        }
                    }
                    for kind in ["reviewed_product_selection", "supplier_offers"]
                ]
            return message, summary

    monkeypatch.setattr("api.procurement_agent.routes.LocalModel", SplitBatch)
    monkeypatch.setattr(
        "api.procurement_agent.worker.research.apply_async", lambda **kwargs: None
    )
    response = request(
        "POST",
        f"/api/rfqs/{rfq['id']}/research",
        json={"revision": rfq["revision"], "idempotency_key": str(uuid4())},
    )
    assert response.status_code == 202
    identifier = response.json()["id"]
    original = runner.checkpoint

    def changed(run_id, stage, **details):
        original(run_id, stage, **details)
        if stage == "receipt_persisted" and len(runner.calls(run_id)) == 2:
            assert (
                request(
                    "POST",
                    "/api/supplier-offers/attestations",
                    json={
                        "resolution_id": resolution["id"],
                        "reason": "Controlled between-batch source change",
                        "commercial": {**offer["data"]["commercial"], "price": "999"},
                    },
                ).status_code
                == 201
            )

    monkeypatch.setattr(runner, "checkpoint", changed)
    assert run_agent(identifier, SplitBatch()) == "needs_attention"
    row = runner.load(identifier)
    assert row["error"] == "source_changed" and row["finalization_calls"] == 0
    assert len(runner.calls(identifier)) == 2
    assert all(row["status"] == "succeeded" for row in runner.calls(identifier))
    assert runner.calls(identifier)[1]["arguments"]["include"] == [
        "reviewed_product_selection"
    ]
