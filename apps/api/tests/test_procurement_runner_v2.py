import json
from uuid import uuid4

import pytest

from api.procurement_agent import runner_v2
from api.procurement_agent.evidence import PROTOCOL, VERIFIER
from api.procurement_agent.provider_v2 import PROMPT_VERSION
from api.rfq.db import connection
from test_procurement_integration import (
    commercial_flow as _commercial_flow,
    catalog_fixture as _catalog_fixture,
)  # noqa: F401

commercial_flow = _commercial_flow
catalog_fixture = _catalog_fixture

pytestmark = pytest.mark.integration


class CitationFixture:
    """Explicit protocol fixture; never counted as a native model measurement."""

    invalid = False
    always_invalid = False
    repair_limit = 1

    def health(self):
        return {
            "digest": "citation-protocol-fixture",
            "prompt_version": PROMPT_VERSION,
            "claim_schema": PROTOCOL,
            "verifier_version": VERIFIER,
            "tool_schema": "procurement-tools/2",
            "max_repair_calls": self.repair_limit,
        }

    def chat(self, messages, tools, expected_digest, **kwargs):
        if kwargs.get("finalize"):
            claims = [
                {key: item[key] for key in ["source_key", "receipt_id", "pointers"]}
                for item in kwargs["facts"]
            ]
            if self.always_invalid or (self.invalid and not kwargs.get("repair")):
                claims[0]["receipt_id"] = str(uuid4())
            return {"role": "assistant", "content": ""}, json.dumps({"claims": claims})
        previous = [
            (message["tool_name"], json.loads(message["content"]))
            for message in messages
            if message["role"] == "tool"
        ]
        if not previous:
            requested = [{"function": {"name": "get_approved_rfq", "arguments": {}}}]
        else:
            approved = next(
                value for name, value in previous if name == "get_approved_rfq"
            )
            requested = [
                {"function": {"name": name, "arguments": {"line_id": line["line_id"]}}}
                for line in approved["data"]["lines"]
                for name in ["get_reviewed_product_selection", "get_supplier_offers"]
            ]
        return {"role": "assistant", "content": "", "tool_calls": requested}, None


def start(flow, monkeypatch, model=CitationFixture):
    _, request, rfq, *_ = flow
    monkeypatch.setattr("api.procurement_agent.routes.LocalModel", model)
    monkeypatch.setattr(
        "api.procurement_agent.worker.research.apply_async", lambda **kwargs: None
    )
    response = request(
        "POST",
        f"/api/rfqs/{rfq['id']}/research",
        json={"revision": rfq["revision"], "idempotency_key": str(uuid4())},
    )
    assert response.status_code == 202, response.text
    return response.json()["id"]


def test_citation_only_api_runner_materialization(commercial_flow, monkeypatch):  # noqa: F811
    identifier = start(commercial_flow, monkeypatch)
    assert runner_v2.run_research(identifier, CitationFixture()) == "complete"
    row = runner_v2.load(identifier)
    assert row["turns"] == 3 and row["repair_attempts"] == 0
    assert (
        row["result"]["coverage"]["complete"] and row["result"]["protocol"] == PROTOCOL
    )
    assert (
        next(fact for fact in row["result"]["claims"] if fact["field_type"] == "price")[
            "value"
        ]
        == "10"
    )
    assert runner_v2.run_research(identifier, CitationFixture()) == "terminal"
    with connection() as conn:
        assert (
            conn.execute(
                "select count(*) as n from procurement.quote_audit_events where subject=%s and event='research_complete'",
                (identifier,),
            ).fetchone()["n"]
            == 1
        )


def test_single_durable_repair_preserves_partial_and_uses_no_extra_business_tools(
    commercial_flow, monkeypatch
):  # noqa: F811
    class Repair(CitationFixture):
        invalid = True

    identifier = start(commercial_flow, monkeypatch, Repair)
    assert runner_v2.run_research(identifier, Repair()) == "complete"
    row = runner_v2.load(identifier)
    assert (
        row["repair_attempts"] == 1
        and row["turns"] == 3
        and len(runner_v2.calls(identifier)) == 3
    )
    assert row["result"]["prior_invalid_citations"] and row["result"]["complete"]
    with connection() as conn:
        attempts = conn.execute(
            "select * from procurement.procurement_agent_finalizations where run_id=%s order by created_at",
            (identifier,),
        ).fetchall()
        assert (
            len(attempts) == 2
            and attempts[0]["resolution"]["partial"]
            and not attempts[0]["resolution"]["complete"]
        )
        assert [
            row["phase"]
            for row in conn.execute(
                "select phase from procurement.procurement_agent_model_calls where run_id=%s order by ordinal",
                (identifier,),
            ).fetchall()
        ] == ["planning", "planning", "finalization", "repair"]


@pytest.mark.parametrize("repair_limit", [0, 1])
def test_repair_budget_failures_remain_attention(
    commercial_flow, monkeypatch, repair_limit
):  # noqa: F811
    class Invalid(CitationFixture):
        always_invalid = True

    Invalid.repair_limit = repair_limit
    identifier = start(commercial_flow, monkeypatch, Invalid)
    assert runner_v2.run_research(identifier, Invalid()) == "needs_attention"
    row = runner_v2.load(identifier)
    assert (
        row["repair_attempts"] == repair_limit
        and row["result"]["partial"]
        and not row["result"]["complete"]
    )
    assert len(runner_v2.calls(identifier)) == 3


@pytest.mark.parametrize(
    "stage",
    [
        "planning",
        "receipt_persisted",
        "finalization_received",
        "evidence_materialized",
        "before_publication",
    ],
)
def test_controlled_crashes_resume_durable_work_without_resetting_counters(
    commercial_flow, monkeypatch, stage
):  # noqa: F811
    identifier = start(commercial_flow, monkeypatch)
    original = runner_v2.checkpoint
    interrupted = False

    def crash(run_id, current):
        nonlocal interrupted
        original(run_id, current)
        if current == stage and not interrupted:
            interrupted = True
            raise SystemExit("Explicit controlled worker death fixture")

    monkeypatch.setattr(runner_v2, "checkpoint", crash)
    with pytest.raises(SystemExit):
        runner_v2.run_research(identifier, CitationFixture())
    before = runner_v2.load(identifier)
    receipts = runner_v2.calls(identifier)
    assert runner_v2.run_research(identifier, CitationFixture()) == "complete"
    after = runner_v2.load(identifier)
    final = runner_v2.calls(identifier)
    assert (
        after["attempts"] == 2
        and after["turns"] >= before["turns"]
        and after["turns"] <= 4
    )
    assert all(
        any(old["id"] == new["id"] and old["result"] == new["result"] for new in final)
        for old in receipts
    )
    assert len(final) == 3
    with connection() as conn:
        assert (
            conn.execute(
                "select count(*) as n from procurement.quote_audit_events where subject=%s and event='research_complete'",
                (identifier,),
            ).fetchone()["n"]
            == 1
        )


def test_cancel_during_repair_never_publishes_completion(commercial_flow, monkeypatch):  # noqa: F811
    _, request, *_ = commercial_flow

    class Cancel(CitationFixture):
        invalid = True

        def chat(self, *args, **kwargs):
            if kwargs.get("repair"):
                assert (
                    request("POST", f"/api/agent-runs/{identifier}/cancel").status_code
                    == 200
                )
            return super().chat(*args, **kwargs)

    identifier = start(commercial_flow, monkeypatch, Cancel)
    assert runner_v2.run_research(identifier, Cancel()) == "cancelled"
    row = runner_v2.load(identifier)
    assert row["state"] == "cancelled" and row["repair_attempts"] == 1
    assert row["result"]["partial"] and not row["result"]["complete"]


def test_revocation_and_stale_source_block_new_model_requests(
    commercial_flow, monkeypatch
):  # noqa: F811
    api, request, rfq, line, search, resolution, offer, payload, preview = (
        commercial_flow
    )
    identifier = start(commercial_flow, monkeypatch)
    with connection() as conn:
        conn.execute(
            "delete from workspace_members where workspace_id=%s and user_id=%s",
            (api[1], api[3]),
        )
    assert runner_v2.run_research(identifier, CitationFixture()) == "needs_attention"
    assert (
        runner_v2.load(identifier)["diagnostics"]["error_code"] == "permission_revoked"
    )
    assert not runner_v2.calls(identifier)


def test_pinned_protocol_change_requires_new_execution(commercial_flow, monkeypatch):  # noqa: F811
    identifier = start(commercial_flow, monkeypatch)

    class Wrong(CitationFixture):
        def health(self):
            return {**super().health(), "prompt_version": "unexpected-new-prompt"}

    assert runner_v2.run_research(identifier, Wrong()) == "needs_attention"
    assert (
        runner_v2.load(identifier)["diagnostics"]["error_code"]
        == "model_or_protocol_mismatch"
    )


def test_changed_attestation_during_inference_blocks_publication(
    commercial_flow, monkeypatch
):
    _, request, _, _, _, resolution, offer, _, _ = commercial_flow

    class Mutated(CitationFixture):
        def chat(self, *args, **kwargs):
            response = super().chat(*args, **kwargs)
            if kwargs.get("finalize"):
                changed = {
                    "resolution_id": resolution["id"],
                    "reason": "Explicit concurrent source mutation fixture",
                    "commercial": {**offer["data"]["commercial"], "price": "999"},
                }
                assert (
                    request(
                        "POST", "/api/supplier-offers/attestations", json=changed
                    ).status_code
                    == 201
                )
            return response

    identifier = start(commercial_flow, monkeypatch, Mutated)
    assert runner_v2.run_research(identifier, Mutated()) == "needs_attention"
    row = runner_v2.load(identifier)
    assert row["error"] == "source_changed" and not row["result"]


def test_repair_cannot_request_business_tools(commercial_flow, monkeypatch):
    class ToolRepair(CitationFixture):
        invalid = True

        def chat(self, *args, **kwargs):
            if kwargs.get("repair"):
                return {
                    "role": "assistant",
                    "tool_calls": [
                        {"function": {"name": "get_approved_rfq", "arguments": {}}}
                    ],
                }, None
            return super().chat(*args, **kwargs)

    identifier = start(commercial_flow, monkeypatch, ToolRepair)
    assert runner_v2.run_research(identifier, ToolRepair()) == "needs_attention"
    row = runner_v2.load(identifier)
    assert (
        row["error"] == "citation_repair_tool_request" and row["repair_attempts"] == 1
    )
    assert len(runner_v2.calls(identifier)) == 3


def test_unknown_pinned_protocol_never_falls_back_to_legacy(
    commercial_flow, monkeypatch
):
    from api.procurement_agent.runner import run_agent

    identifier = start(commercial_flow, monkeypatch)
    with connection() as conn:
        conn.execute(
            'update procurement.procurement_agent_runs set metadata=metadata||\'{"claim_schema":"unsupported/99"}\'::jsonb where id=%s',
            (identifier,),
        )
    assert run_agent(identifier, CitationFixture()) == "needs_attention"
    assert runner_v2.load(identifier)["error"] == "unsupported_pinned_protocol"
    assert not runner_v2.calls(identifier)


def test_death_during_correction_does_not_reset_consumed_repair_budget(
    commercial_flow, monkeypatch
):
    class Repair(CitationFixture):
        invalid = True

    identifier = start(commercial_flow, monkeypatch, Repair)
    original = runner_v2.checkpoint

    def crash(run_id, stage):
        original(run_id, stage)
        if stage == "citation_repair":
            raise SystemExit("Explicit controlled death during admitted correction")

    monkeypatch.setattr(runner_v2, "checkpoint", crash)
    with pytest.raises(SystemExit):
        runner_v2.run_research(identifier, Repair())
    before = runner_v2.load(identifier)
    prior = runner_v2.calls(identifier)
    assert before["repair_attempts"] == 1 and before["result"]["partial"]
    monkeypatch.setattr(runner_v2, "checkpoint", original)
    assert runner_v2.run_research(identifier, Repair()) == "needs_attention"
    after = runner_v2.load(identifier)
    assert after["error"] == "repair_budget_exhausted"
    assert after["repair_attempts"] == 1 and after["turns"] == before["turns"]
    assert runner_v2.calls(identifier) == prior and not after["result"]["complete"]
