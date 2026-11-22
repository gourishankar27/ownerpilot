"""Versioned actual-native comparison with an independent authored-fact audit.

Synthetic fixture administration is isolated. The model still chooses native tools;
no business tool sequence or model answer is supplied by this evaluator.
"""

import argparse
import base64
import csv
import hashlib
import hmac
import io
import json
import os
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import httpx
from psycopg.types.json import Jsonb

from api.procurement_agent.evidence import EvidenceResolver
from api.procurement_agent.provider_v2 import LocalModel
from api.procurement_agent.legacy_provider import LocalModel as LegacyLocalModel
from api.procurement_agent.contracts import ResearchSummary
from api.procurement_agent.runner import run_agent
from api.procurement_agent.runner_v2 import calls as receipts
from api.procurement_agent.service import snapshot, digest
from api.rfq.auth import Identity
from api.rfq.db import connection

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/evaluation/procurement-v2"
PRIVATE = ROOT / ".local/rfq/phase3_1/evaluation-state.json"
WORKER = "ownerpilot-procurement31-validation-worker-1"
client = httpx.Client(
    base_url=os.getenv("PROCUREMENT31_API_URL", "http://127.0.0.1:8041"),
    timeout=30,
    trust_env=False,
)


def request(method, path, state, **kwargs):
    now = int(time.time())
    claims = {
        "sub": state["user"],
        "workspace": state["workspace"],
        "iat": now,
        "exp": now + 60,
        "method": method,
        "path": "/api/" + path,
    }
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    signature = hmac.new(
        os.environ["RFQ_AUTH_SECRET"].encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    response = client.request(
        method,
        "/api/" + path,
        headers={"Authorization": f"Bearer {payload}.{signature}"},
        **kwargs,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"HTTP {response.status_code}: {method} {path}; response body omitted"
        )
    return response.json()


def wait_job(path, state, terminal):
    start = time.monotonic()
    while time.monotonic() - start < 180:
        result = request("GET", path, state)
        if result["state"] in terminal:
            return result
        time.sleep(0.25)
    raise RuntimeError("Synthetic source processing timeout")


def save(state):
    PRIVATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def setup(data):
    if (
        "ownerpilot_rfq_phase3_demo_phase31_validation"
        not in os.environ["DATABASE_URL"]
    ):
        raise SystemExit("Requires isolated Phase 3.1 demo database")
    if PRIVATE.exists():
        return json.loads(PRIVATE.read_text())
    workspace = str(uuid4())
    user = "phase31-synthetic-" + uuid4().hex
    with connection() as conn:
        conn.execute(
            "insert into business_workspaces(id,name,slug) values(%s,'Phase 3.1 independent synthetic research study',%s)",
            (workspace, workspace),
        )
        conn.execute(
            "insert into workspace_members(workspace_id,user_id,role) values(%s,%s,'owner')",
            (workspace, user),
        )
    state = {"workspace": workspace, "user": user, "cases": {}}
    save(state)
    return state


def ensure_catalog(state, data):
    if state.get("version"):
        return
    catalog = request(
        "POST",
        "catalogs",
        state,
        json={
            "name": "Fictional v2 procurement sources",
            "license": "CC0 synthetic independent fixtures",
        },
    )
    preview = request(
        "POST",
        f"catalogs/{catalog['id']}/imports/preview",
        state,
        files={
            "file": (
                "fictional-v2.json",
                json.dumps(data["catalog"]).encode(),
                "application/json",
            )
        },
    )
    request(
        "POST",
        f"catalogs/{catalog['id']}/imports/confirm",
        state,
        json={"version_id": preview["id"], "fingerprint": preview["fingerprint"]},
    )
    result = wait_job(
        f"catalog-import-jobs/{preview['id']}", state, {"published", "failed"}
    )
    if result["state"] != "published":
        raise RuntimeError("Actual Nomic indexing failed")
    state.update(catalog=catalog["id"], version=preview["id"])
    save(state)


def prepare(case, state):
    existing = state["cases"].get(case["id"])
    if existing and existing.get("complete"):
        return existing
    if existing:
        raise RuntimeError(
            "Incomplete fixture checkpoint; inspect the recorded RFQ instead of blindly creating duplicates"
        )
    rfq = request(
        "POST",
        "rfqs",
        state,
        json={"title": "Independent synthetic study " + case["id"]},
    )
    path = f"rfqs/{rfq['id']}"
    item = {"rfq_id": rfq["id"], "complete": False}
    state["cases"][case["id"]] = item
    save(state)
    text = io.StringIO()
    writer = csv.writer(text)
    writer.writerow(
        ["Manufacturer", "MPN", "Description", "Qty", "UOM", "Specifications"]
    )
    for line in case["lines"]:
        value = line["request"]
        writer.writerow(
            [
                value["manufacturer"],
                value["mpn"],
                value["description"],
                value["quantity"],
                value["unit"],
                json.dumps(value["specifications"]) if value["specifications"] else "",
            ]
        )
    request(
        "POST",
        path + "/documents",
        state,
        data={"revision": "0"},
        files={"file": (case["id"] + ".csv", text.getvalue().encode(), "text/csv")},
    )
    job = request(
        "POST", path + "/process", state, json={"revision": 1, "mode": "deterministic"}
    )
    item["job_id"] = job["id"]
    save(state)
    result = wait_job("rfq-jobs/" + job["id"], state, {"awaiting_review", "failed"})
    if result["state"] != "awaiting_review":
        raise RuntimeError("Synthetic RFQ parsing failed")
    detail = request("GET", path, state)
    for line in detail["items"]:
        result = request(
            "PATCH",
            path + f"/line-items/{line['id']}",
            state,
            json={
                "revision": detail["revision"],
                "fields": {},
                "review_status": "reviewed",
                "reason": "Independent operator review of fictional source cells",
            },
        )
        detail["revision"] = result["revision"]
    request("POST", path + "/approve", state, json={"revision": detail["revision"]})
    detail = request("GET", path, state)
    item.update(revision=detail["revision"], lines={})
    save(state)
    choices = {}
    for authored in case["lines"]:
        line = next(
            line
            for line in detail["items"]
            if line["fields"]["mpn"]["value"] == authored["request"]["mpn"]
        )
        search = request(
            "POST",
            path + f"/line-items/{line['id']}/matches",
            state,
            json={
                "revision": detail["revision"],
                "versions": [state["version"]],
                "method": "exact_bm25",
            },
        )
        candidate = next(
            (
                candidate
                for candidate in search["candidates"]
                if candidate["product"]["mpn"] == authored["request"]["mpn"]
                and candidate["product"]["manufacturer"]
                == authored["request"]["manufacturer"]
                and candidate["compatibility"]["status"] == "exact"
            ),
            None,
        )
        if authored["selection"] == "resolved" and candidate is None:
            raise RuntimeError("Authored exact identity missing from reviewed catalog")
        positive = authored["selection"] == "resolved"
        request(
            "POST",
            f"catalog-match-runs/{search['id']}/review",
            state,
            json={
                "decision": "select" if positive else "no_match",
                "product_id": candidate["id"] if positive else None,
                "note": "Independent synthetic reviewer decision; unsupported substitutions remain no-match",
            },
        )
        resolution = request(
            "POST",
            path + f"/line-items/{line['id']}/selection-resolution",
            state,
            json={
                "expected_revision": 0,
                "run_id": search["id"],
                "decision": "select" if positive else "no_match",
                "product_id": candidate["id"] if positive else None,
                "version_id": state["version"] if positive else None,
                "reason": "Explicit operator resolution of independently authored source identity",
            },
        )
        binding = {
            "line_id": line["id"],
            "resolution_id": resolution["id"],
            "product_id": resolution["data"].get("product_id"),
            "version_id": resolution["data"].get("version_id"),
            "fingerprint": resolution["data"].get("content_hash"),
            "offers": {},
        }
        item["lines"][authored["key"]] = binding
        save(state)
        for offer in authored["offers"]:
            response = request(
                "POST",
                "supplier-offers/attestations",
                state,
                json={
                    "resolution_id": resolution["id"],
                    "commercial": offer["commercial"],
                    "supersedes_id": binding["offers"].get(offer.get("supersedes")),
                    "reason": "Frozen independent fictional commercial source; human-attested, not live supplier data",
                },
            )
            binding["offers"][offer["key"]] = response["id"]
            save(state)
        if authored.get("chosen_offer"):
            choices[line["id"]] = binding["offers"][authored["chosen_offer"]]
    quote = request(
        "POST",
        path + "/quotes",
        state,
        json={
            "policy": case["quote_policy"],
            "offer_choices": choices,
            "reason": "Explicit frozen operator quote choices; no agent price or policy inputs",
        },
    )
    item.update(
        quote_id=quote["id"],
        quote_ready=quote["calculation"]["complete"],
        complete=True,
    )
    save(state)
    # Label disagreements are recorded, not rewritten to match the implementation.
    item["readiness_matches_authored"] = (
        item["quote_ready"] == case["expected"]["quote_ready"]
    )
    save(state)
    return item


class ObservedLegacy(LegacyLocalModel):
    def __init__(self):
        super().__init__()
        self.stats = []
        self.candidate = None
        self.request_count = 0

    def chat(self, *args, **kwargs):
        original = self.client.stream
        owner = self

        class MeasuredResponse:
            def __init__(self, response):
                self.response = response

            def raise_for_status(self):
                return self.response.raise_for_status()

            def iter_bytes(self):
                raw = bytearray()
                for part in self.response.iter_bytes():
                    raw.extend(part)
                    if len(raw) > 65536:
                        raise ValueError("Response size limit")
                    yield part
                data = json.loads(raw)
                owner.last_stats.update(
                    {
                        key: data[key]
                        for key in [
                            "prompt_eval_count",
                            "eval_count",
                            "total_duration",
                            "load_duration",
                            "prompt_eval_duration",
                            "eval_duration",
                            "done_reason",
                        ]
                        if key in data
                    }
                )

        @contextmanager
        def stream(*a, **kw):
            self.request_count += 1
            self.last_stats["request_started"] = True
            with original(*a, **kw) as response:
                yield MeasuredResponse(response)

        self.client.stream = stream
        self.last_stats = {}
        start = time.perf_counter()
        try:
            message, summary = super().chat(*args, **kwargs)
            if summary:
                try:
                    self.candidate = ResearchSummary.model_validate_json(
                        summary
                    ).model_dump(mode="json")
                except ValueError:
                    self.candidate = {"schema_error": True}
            return message, summary
        finally:
            self.client.stream = original
            self.last_stats["wall_ms"] = (time.perf_counter() - start) * 1000
            self.stats.append(self.last_stats.copy())


def loaded_models():
    try:
        return [
            model["name"]
            for model in httpx.get(
                "http://localhost:11434/api/ps", timeout=3, trust_env=False
            ).json()["models"]
        ]
    except Exception:
        return []


def resource_sample():
    result = {}
    try:
        value = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True,
            timeout=3,
        )
        result["gpu_device_used_mib"] = int(value.strip().splitlines()[0])
    except Exception:
        result["gpu_device_used_mib"] = None
    return result


def create_run(item, state, provider):
    identity = Identity(state["user"], state["workspace"], "owner")
    with connection() as conn:
        source = snapshot(conn, item["rfq_id"], identity)
        quote = conn.execute(
            "select * from procurement.quote_drafts where id=%s and workspace_id=%s",
            (item["quote_id"], state["workspace"]),
        ).fetchone()
        source.update(
            quote_id=str(quote["id"]),
            quote_revision=quote["revision"],
            quote_policy=quote["policy"],
            quote_choices=quote["offer_choices"],
            catalog_versions=[state["version"]],
        )
        metadata = provider.health()
        if metadata.get("claim_schema"):
            metadata["source_fingerprint"] = digest(source)
        run = conn.execute(
            "insert into procurement.procurement_agent_runs(workspace_id,rfq_id,idempotency_key,snapshot,messages,metadata,actor) values(%s,%s,%s,%s,%s,%s,%s) returning *",
            (
                state["workspace"],
                item["rfq_id"],
                str(uuid4()),
                Jsonb(source),
                Jsonb(
                    [
                        {
                            "role": "user",
                            "content": "Research this approved RFQ with native tools. Start with get_approved_rfq. Workspace and RFQ are trusted job context.",
                        }
                    ]
                ),
                Jsonb(metadata),
                state["user"],
            ),
        ).fetchone()
    return run


def authored_audit(case, item, facts, tool_calls):
    bindings = {
        binding["line_id"]: (authored, binding)
        for authored in case["lines"]
        for binding in [item["lines"][authored["key"]]]
    }
    invalid = []
    seen = set()
    expected = set()
    unknowns_correct = True
    for line, binding in bindings.values():
        expected.add((binding["line_id"], None, "selection_state"))
        for offer in line["offers"]:
            for kind in ["price", "currency", "availability", "freshness"]:
                expected.add(
                    (binding["line_id"], binding["offers"][offer["key"]], kind)
                )
            if offer["expected_review_state"] != "active_attestation":
                expected.add(
                    (
                        binding["line_id"],
                        binding["offers"][offer["key"]],
                        "review_state",
                    )
                )
    for fact in facts:
        pair = bindings.get(fact.get("line_id"))
        if pair is None:
            # RFQ-global metadata is not a commercial claim.
            if fact.get("line_id") is not None:
                invalid.append({"code": "unknown_line"})
            continue
        line, binding = pair
        kind = fact["field_type"]
        offer_id = fact.get("offer_id")
        wanted = None
        known = False
        if (
            fact.get("product_id") != binding["product_id"]
            or fact.get("catalog_version") != binding["version_id"]
        ):
            invalid.append({"code": "product_association", "field": kind})
            continue
        if kind == "selection_state":
            wanted = line["selection"]
            known = True
        elif kind == "quantity":
            wanted = line["request"]["quantity"]
            known = True
        elif offer_id:
            offer = next(
                (
                    offer
                    for offer in line["offers"]
                    if binding["offers"][offer["key"]] == offer_id
                ),
                None,
            )
            if offer is None:
                invalid.append({"code": "offer_association", "field": kind})
                continue
            if kind == "freshness":
                wanted = offer["expected_freshness"]
                known = True
            elif kind == "review_state":
                wanted = offer["expected_review_state"]
                known = True
            elif kind in offer["commercial"]:
                wanted = offer["commercial"][kind]
                known = True
            if fact.get("source_fingerprint") != binding["fingerprint"]:
                invalid.append({"code": "fingerprint_association", "field": kind})
        if known and (
            type(fact["value"]) is not type(wanted) or fact["value"] != wanted
        ):
            invalid.append(
                {
                    "code": "unsupported_scalar",
                    "field": kind,
                    "line_id": binding["line_id"],
                    "offer_id": offer_id,
                }
            )
            unknowns_correct = False
        elif known:
            seen.add((binding["line_id"], offer_id, kind))
    allowed = set(case["expected"]["allowed_tools"])
    valid_tools = all(
        call["tool"] in allowed
        and (
            not call["arguments"].get("line_id")
            or str(call["arguments"]["line_id"]) in bindings
        )
        for call in tool_calls
    )
    required_tools = any(
        call["tool"] == "get_approved_rfq" and call["status"] == "succeeded"
        for call in tool_calls
    ) and all(
        any(
            call["tool"] == name
            and str(call["arguments"].get("line_id")) == line
            and call["status"] == "succeeded"
            for call in tool_calls
        )
        for line in bindings
        for name in ["get_reviewed_product_selection", "get_supplier_offers"]
    )
    return {
        "invalid_claims": invalid,
        "required_fact_coverage": not (expected - seen),
        "required_facts": len(expected),
        "supported_required_facts": len(expected & seen),
        "source_tool_coverage": required_tools,
        "tool_arguments_authorized": valid_tools,
        "unknown_values_correct": unknowns_correct,
        "facts_inspected": len(facts),
    }


def legacy_facts(run, rows):
    # Independent audit only. The original stored result is never upgraded or rewritten.
    shadow = {
        **run,
        "metadata": {**run["metadata"], "source_fingerprint": digest(run["snapshot"])},
    }
    resolver = EvidenceResolver(shadow, rows)
    facts = []
    for claim in (run.get("result") or {}).get("claims", []):
        for source in resolver.sources.values():
            if (
                str(source.receipt["id"]) != claim["receipt_id"]
                or claim["pointer"] not in source.fields
            ):
                continue
            kind, value = source.fields[claim["pointer"]]
            facts.append(
                {
                    "field_type": kind,
                    "value": claim["value"],
                    "pointer": claim["pointer"],
                    **source.binding,
                }
            )
            break
    return facts


def evaluate(case, state, out, variant):
    target = out / f"{case['id']}-{variant}.json"
    if target.exists():
        return json.loads(target.read_text())
    item = prepare(case, state)
    provider = ObservedLegacy() if variant == "legacy" else LocalModel()
    before = resource_sample()
    loaded = loaded_models()
    subprocess.run(["docker", "pause", WORKER], check=True, capture_output=True)
    try:
        run = create_run(item, state, provider)
        started = time.perf_counter()
        outcome = run_agent(str(run["id"]), provider)
        elapsed = (time.perf_counter() - started) * 1000
        with connection() as conn:
            actual = conn.execute(
                "select * from procurement.procurement_agent_runs where id=%s",
                (run["id"],),
            ).fetchone()
            attempts = conn.execute(
                "select * from procurement.procurement_agent_finalizations where run_id=%s order by created_at",
                (run["id"],),
            ).fetchall()
            metrics = conn.execute(
                "select * from procurement.procurement_agent_model_calls where run_id=%s order by ordinal",
                (run["id"],),
            ).fetchall()
        rows = receipts(run["id"])
        result = actual["result"] or {}
        facts = (
            legacy_facts(actual, rows)
            if variant == "legacy"
            else result.get("claims", [])
        )
        audit = authored_audit(case, item, facts, rows)
        initial = attempts[0]["resolution"] if attempts else result
        initial_audit = authored_audit(
            case,
            item,
            initial.get("claims", []) if variant != "legacy" else facts,
            rows,
        )
        initial_ms = (
            (attempts[0]["created_at"] - actual["created_at"]).total_seconds() * 1000
            if attempts
            else elapsed
        )
        stats = (
            provider.stats
            if variant == "legacy"
            else [row["metrics"] for row in metrics]
        )
        record = {
            "scenario": case["id"],
            "split": case["split"],
            "pattern": case["pattern"],
            "variant": variant,
            "run_id": str(run["id"]),
            "model": actual["metadata"],
            "state": outcome,
            "error": actual["error"],
            "source_snapshot": actual["snapshot"],
            "result": result,
            "initial_result": initial,
            "audit": audit,
            "initial_audit": initial_audit,
            "verified_complete": outcome == "complete"
            and audit["required_fact_coverage"]
            and audit["source_tool_coverage"]
            and not audit["invalid_claims"],
            "initial_verified_complete": bool(initial.get("complete"))
            and initial_audit["required_fact_coverage"]
            and initial_audit["source_tool_coverage"]
            and not initial_audit["invalid_claims"],
            "quote_ready_expected": case["expected"]["quote_ready"],
            "deterministic_quote_ready": item["quote_ready"],
            "quote_ready_matches_authored": item["readiness_matches_authored"],
            "latency_ms": elapsed,
            "initial_latency_ms": initial_ms,
            "turns": actual["turns"],
            "repair_attempts": actual["repair_attempts"],
            "model_stats": stats,
            "actual_chat_requests": provider.request_count
            if variant == "legacy"
            else sum(bool(row["metrics"].get("request_started")) for row in metrics),
            "tool_receipts": rows,
            "finalization_attempts": attempts,
            "legacy_candidate": provider.candidate if variant == "legacy" else None,
            "resources": {
                "before": before,
                "after": resource_sample(),
                "model_loaded_before": provider.model in loaded,
                "scope": "Device-wide before/after samples, not an isolated peak or model-only memory measurement",
            },
            "actual_local_model": True,
            "fault_injection": False,
            "deterministic_baseline": {
                "source_report_complete": True,
                "quote_ready": item["quote_ready"],
                "expected_quote_ready": case["expected"]["quote_ready"],
            },
        }
        from fastapi.encoders import jsonable_encoder

        target.write_text(
            json.dumps(jsonable_encoder(record), indent=2) + "\n", encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "case": case["id"],
                    "variant": variant,
                    "state": outcome,
                    "verified": record["verified_complete"],
                    "tools": len(rows),
                    "repairs": actual["repair_attempts"],
                    "ms": round(elapsed),
                    "error": actual["error"],
                }
            ),
            flush=True,
        )
        return record
    finally:
        subprocess.run(["docker", "unpause", WORKER], check=True, capture_output=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--split",
        choices=["development", "validation", "held_out", "all"],
        default="development",
    )
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--variants", default="legacy,citation_repair")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((DATA / "manifest.json").read_text())
    raw = (DATA / "scenarios.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == manifest["files"]["scenarios.json"]
    data = json.loads(raw)
    out = ROOT / "docs/rfq/phase3_1/results/evaluation" / args.experiment
    out.mkdir(parents=True, exist_ok=True)
    code = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in [
            "apps/api/src/api/procurement_agent/provider_v2.py",
            "apps/api/src/api/procurement_agent/evidence.py",
            "apps/api/src/api/procurement_agent/runner_v2.py",
            "apps/api/src/api/procurement_agent/contracts.py",
            "apps/api/src/api/procurement_agent/tools.py",
        ]
    }
    config = {
        "dataset_sha256": manifest["files"]["scenarios.json"],
        "code": code,
        "model": LocalModel().health(),
    }
    config_path = out / "configuration.json"
    if config_path.exists() and json.loads(config_path.read_text()) != config:
        raise SystemExit(
            "Changed model/code requires a new experiment name; existing attempts must be preserved"
        )
    if not config_path.exists():
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    state = setup(data)
    ensure_catalog(state, data)
    selected = [
        case
        for case in data["native_scenarios"]
        if args.split == "all" or case["split"] == args.split
    ]
    for case in selected:
        if args.prepare_only:
            item = prepare(case, state)
            print(
                json.dumps(
                    {
                        "prepared": case["id"],
                        "quote_label_matches": item["readiness_matches_authored"],
                    }
                ),
                flush=True,
            )
        else:
            for variant in args.variants.split(","):
                if variant not in {"legacy", "citation_repair"}:
                    raise SystemExit("Closed benchmark variants")
                evaluate(case, state, out, variant)


if __name__ == "__main__":
    main()
