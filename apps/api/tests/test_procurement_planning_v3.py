"""Real signed API/PostgreSQL with explicitly stubbed model plans, not ML scores."""

import json
from uuid import uuid4

import httpx
import pytest
from conftest import authorization

from api.procurement_agent import runner_v3 as runner
from api.procurement_agent.evidence import PROTOCOL
from api.procurement_agent.evidence_v3 import VERIFIER
from api.procurement_agent.planning import POLICY, COVERAGE, LIMITS
from api.procurement_agent.provider_v3 import PROMPT_VERSION
from api.procurement_agent.runner import run_agent
from api.rfq.db import connection
from api.rfq.worker import process_job

pytestmark = pytest.mark.integration


class ModelFixture:
    strategy = "coverage_native"
    mode = "normal"
    batch_size = 4
    chat_calls = 0

    def health(self):
        return {
            "model": "explicit-planner-fixture",
            "digest": "explicit-fixture-32",
            "prompt_version": PROMPT_VERSION,
            "planning_policy": POLICY,
            "coverage_version": COVERAGE,
            "claim_schema": PROTOCOL,
            "verifier_version": VERIFIER,
            "tool_schema": "procurement-tools/3",
            "orchestration_strategy": self.strategy,
            "batch_size": self.batch_size,
            **LIMITS,
        }

    def chat(self, messages, tools, digest, **kwargs):
        self.chat_calls += 1
        if self.mode == "timeout":
            raise httpx.ReadTimeout("Explicit transport fixture")
        if kwargs.get("finalize"):
            claims = [
                {key: group[key] for key in ["source_key", "receipt_id", "pointers"]}
                for group in kwargs["facts"]
            ]
            if self.mode == "repair" and not kwargs.get("repair"):
                claims[-1]["receipt_id"] = str(uuid4())
            return {"role": "assistant", "content": ""}, json.dumps({"claims": claims})
        if self.mode == "early":
            return {"role": "assistant", "content": ""}, '{"claims":[]}'
        if self.mode == "irrelevant":
            calls = [{"function": {"name": "get_quote_requirements", "arguments": {}}}]
        elif self.mode == "tools_exhausted":
            calls = [
                {"function": {"name": "get_quote_requirements", "arguments": {}}}
                for _ in range(8)
            ]
        else:
            reads = [
                (message["tool_name"], json.loads(message["content"]))
                for message in messages
                if message["role"] == "tool"
            ]
            approved = next(
                (value for name, value in reads if name == "get_approved_rfq"), None
            )
            if approved is None:
                calls = [{"function": {"name": "get_approved_rfq", "arguments": {}}}]
            elif self.strategy == "mandatory_scheduler":
                calls = [
                    {"function": {"name": "get_quote_requirements", "arguments": {}}}
                ]
            elif self.mode == "foreign":
                calls = [
                    {
                        "function": {
                            "name": "get_line_research_batch",
                            "arguments": {"line_ids": [str(uuid4())]},
                        }
                    }
                ]
            else:
                ids = [line["line_id"] for line in approved["lines"]]
                calls = [
                    {
                        "function": {
                            "name": "get_line_research_batch",
                            "arguments": {
                                "line_ids": ids[start : start + self.batch_size]
                            },
                        }
                    }
                    for start in range(0, len(ids), self.batch_size)
                ]
        return {"role": "assistant", "content": "", "tool_calls": calls}, None


def approved_scope(api, count):
    client, workspace, _, user = api

    def request(method, path, **kwargs):
        return client.request(
            method, path, headers=authorization(method, path, workspace, user), **kwargs
        )

    rfq = request(
        "POST", "/api/rfqs", json={"title": "Explicit multi-line planning fixture"}
    ).json()
    path = f"/api/rfqs/{rfq['id']}"
    csv = "Manufacturer,MPN,Description,Qty,UOM\n" + "".join(
        f"Fictional,FX-{index},Unique device {index} {rfq['id']},2,EA\n"
        for index in range(count)
    )
    assert (
        request(
            "POST",
            path + "/documents",
            data={"revision": "0"},
            files={"file": ("fixture.csv", csv.encode(), "text/csv")},
        ).status_code
        == 201
    )
    job = request(
        "POST", path + "/process", json={"revision": 1, "mode": "deterministic"}
    ).json()
    assert process_job(job["id"]) == "awaiting_review"
    detail = request("GET", path).json()
    for item in detail["items"]:
        reviewed = request(
            "PATCH",
            path + f"/line-items/{item['id']}",
            json={
                "revision": detail["revision"],
                "fields": {},
                "review_status": "reviewed",
                "reason": "Explicit independent fixture review",
            },
        )
        assert reviewed.status_code == 200
        detail["revision"] = reviewed.json()["revision"]
    assert (
        request(
            "POST", path + "/approve", json={"revision": detail["revision"]}
        ).status_code
        == 200
    )
    return request, request("GET", path).json()


def start(api, monkeypatch, count=4, strategy="coverage_native", mode="normal"):
    request, rfq = approved_scope(api, count)
    model_type = type(
        "ScopedFixture", (ModelFixture,), {"strategy": strategy, "mode": mode}
    )
    monkeypatch.setattr("api.procurement_agent.routes.LocalModel", model_type)
    monkeypatch.setattr(
        "api.procurement_agent.worker.research.apply_async", lambda **kwargs: None
    )
    response = request(
        "POST",
        f"/api/rfqs/{rfq['id']}/research",
        json={"revision": rfq["revision"], "idempotency_key": str(uuid4())},
    )
    assert response.status_code == 202, response.text
    return response.json()["id"], model_type(), request


@pytest.mark.parametrize("count", [1, 2, 4, 8, 12])
def test_native_fixture_multiline_source_and_citation_coverage(api, monkeypatch, count):
    identifier, provider, _ = start(api, monkeypatch, count)
    assert run_agent(identifier, provider) == "complete"
    row = runner.load(identifier)
    assert row["planning_calls"] == 2 and row["finalization_calls"] == 1
    assert row["coverage_state"]["covered_lines"] == count
    assert row["result"]["complete"] and not row["result"]["quote_ready"]
    assert all(
        receipt["execution_origin"] == "model_selected"
        for receipt in runner.calls(identifier)
    )
    assert runner.calls(identifier)[1]["call_details"]["batch_line_count"] == min(
        count, 4
    )
    assert run_agent(identifier, provider) == "terminal"


@pytest.mark.parametrize(
    "strategy", ["native_batch", "coverage_native", "hybrid", "mandatory_scheduler"]
)
def test_attributed_strategy_and_separate_finalization(api, monkeypatch, strategy):
    identifier, provider, _ = start(api, monkeypatch, strategy=strategy)
    assert run_agent(identifier, provider) == "complete"
    rows = runner.calls(identifier)
    if strategy == "mandatory_scheduler":
        assert sum(row["execution_origin"] == "backend_scheduled" for row in rows) == 2
        assert sum(row["execution_origin"] == "model_selected" for row in rows) == 1
    else:
        assert all(row["execution_origin"] == "model_selected" for row in rows)
    assert all("result_bytes" in row["call_details"] for row in rows)


@pytest.mark.parametrize("mode", ["early", "irrelevant", "foreign"])
def test_hybrid_only_completes_missing_mandatory_reads_and_retains_failed_attempts(
    api, monkeypatch, mode
):
    identifier, provider, _ = start(
        api, monkeypatch, count=8, strategy="hybrid", mode=mode
    )
    assert run_agent(identifier, provider) == "complete"
    row = runner.load(identifier)
    assert row["planning_calls"] == 2 and row["finalization_calls"] == 1
    scheduled = [
        r
        for r in runner.calls(identifier)
        if r["execution_origin"] == "backend_scheduled"
    ]
    assert scheduled and all(
        r["tool"] in {"get_approved_rfq", "get_line_research_batch"} for r in scheduled
    )
    assert row["coverage_state"]["covered_lines"] == 8
    if mode == "foreign":
        assert row["result"]["tool_failures"] and any(
            r["status"] == "rejected" for r in runner.calls(identifier)
        )


@pytest.mark.parametrize(
    "mode,code",
    [
        ("early", "planning_budget_exhausted"),
        ("irrelevant", "planning_budget_exhausted"),
        ("tools_exhausted", "tool_budget_exhausted"),
    ],
)
def test_native_missing_coverage_cannot_admit_citation_finalization(
    api, monkeypatch, mode, code
):
    identifier, provider, _ = start(api, monkeypatch, mode=mode)
    assert run_agent(identifier, provider) == "needs_attention"
    row = runner.load(identifier)
    assert row["finalization_calls"] == 0 and row["error"] == code
    assert not row["result"]["complete"]


def test_explicit_capacity_block_has_zero_model_inference(api, monkeypatch):
    identifier, provider, _ = start(api, monkeypatch, count=13)
    assert run_agent(identifier, provider) == "needs_attention"
    row = runner.load(identifier)
    assert row["error"] == "capacity_line_limit" and provider.chat_calls == 0
    assert row["coverage_state"]["capacity"]["line_count"] == 13 and not runner.calls(
        identifier
    )


def test_single_correction_and_unknown_values_are_independently_resolved(
    api, monkeypatch
):
    identifier, provider, _ = start(api, monkeypatch, mode="repair")
    assert run_agent(identifier, provider) == "complete"
    row = runner.load(identifier)
    assert (
        row["repair_attempts"] == 1
        and row["finalization_calls"] == 1
        and row["planning_calls"] == 2
    )
    assert row["result"]["prior_invalid_citations"]


@pytest.mark.parametrize(
    "stage",
    [
        "planning_request",
        "receipt_persisted",
        "coverage_updated",
        "finalization_received",
        "evidence_materialized",
        "before_publication",
    ],
)
def test_controlled_death_preserves_work_and_consumed_budgets(api, monkeypatch, stage):
    identifier, provider, _ = start(api, monkeypatch, count=8)
    original = runner.checkpoint
    interrupted = False

    def crash(run_id, current, **details):
        nonlocal interrupted
        original(run_id, current, **details)
        if current == stage and not interrupted:
            interrupted = True
            raise SystemExit("Explicit controlled crash fixture")

    monkeypatch.setattr(runner, "checkpoint", crash)
    with pytest.raises(SystemExit):
        run_agent(identifier, provider)
    before = runner.load(identifier)
    prior = runner.calls(identifier)
    assert run_agent(identifier, provider) == "complete"
    after = runner.load(identifier)
    assert (
        after["attempts"] == 2 and after["planning_calls"] >= before["planning_calls"]
    )
    assert after["planning_calls"] <= 4 and after["finalization_calls"] == 1
    assert all(
        any(
            old["id"] == new["id"] and old["result"] == new["result"]
            for new in runner.calls(identifier)
        )
        for old in prior
    )
    with connection() as conn:
        assert (
            conn.execute(
                "select count(*) as n from procurement.quote_audit_events where subject=%s and event='research_complete'",
                (identifier,),
            ).fetchone()["n"]
            == 1
        )


def test_cancellation_during_batch_prevents_receipt_commit_and_publication(
    api, monkeypatch
):
    identifier, provider, request = start(api, monkeypatch)
    original = runner.execute

    def cancel(name, args, run):
        result = original(name, args, run)
        if name == "get_line_research_batch":
            assert (
                request("POST", f"/api/agent-runs/{identifier}/cancel").status_code
                == 200
            )
        return result

    monkeypatch.setattr(runner, "execute", cancel)
    assert run_agent(identifier, provider) == "cancelled"
    assert (
        len(runner.calls(identifier)) == 1
        and runner.load(identifier)["finalization_calls"] == 0
    )


def test_revocation_and_cross_workspace_access_are_enforced(api, monkeypatch):
    identifier, provider, request = start(api, monkeypatch)
    with connection() as conn:
        conn.execute(
            "insert into workspace_members(workspace_id,user_id,role) values(%s,%s,'owner')",
            (api[2], api[3]),
        )
    response = api[0].get(
        f"/api/agent-runs/{identifier}",
        headers=authorization("GET", f"/api/agent-runs/{identifier}", api[2], api[3]),
    )
    assert response.status_code == 404
    with connection() as conn:
        conn.execute(
            "delete from workspace_members where workspace_id=%s and user_id=%s",
            (api[1], api[3]),
        )
    assert run_agent(identifier, provider) == "needs_attention"
    assert runner.load(identifier)[
        "error"
    ] == "permission_revoked" and not runner.calls(identifier)


def test_model_or_policy_pin_mismatch_does_not_resume_with_new_configuration(
    api, monkeypatch
):
    identifier, provider, _ = start(api, monkeypatch)
    provider.strategy = "hybrid"
    assert run_agent(identifier, provider) == "needs_attention"
    assert runner.load(identifier)["error"] == "model_or_policy_mismatch"


def test_timeout_and_original_deadline_never_reset_budget(api, monkeypatch):
    identifier, provider, _ = start(api, monkeypatch, mode="timeout")
    assert run_agent(identifier, provider) == "needs_attention"
    assert runner.load(identifier)["planning_calls"] == 1
    identifier, provider, _ = start(api, monkeypatch)
    with connection() as conn:
        conn.execute(
            "update procurement.procurement_agent_runs set created_at=now()-interval '241 seconds' where id=%s",
            (identifier,),
        )
    assert run_agent(identifier, provider) == "needs_attention"
    assert runner.load(identifier)["error"] == "budget_exhausted" and not runner.calls(
        identifier
    )
