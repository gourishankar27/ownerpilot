"""Actual local model strategy comparison; separately attributed source scheduling."""

import argparse
import hashlib
import importlib.util
import json
import subprocess
import time
from pathlib import Path

from fastapi.encoders import jsonable_encoder

from api.procurement_agent.provider_v2 import LocalModel as Phase31Model
from api.procurement_agent.provider_v3 import LocalModel
from api.procurement_agent.runner import run_agent
from api.procurement_agent.runner_v2 import load, calls
from api.procurement_agent.service import digest
from api.rfq.db import connection
from procurement32_oracle import audit

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs/rfq/phase3_2/results"
WORKER = "ownerpilot-procurement32-validation-worker-1"
VARIANTS = [
    "phase31",
    "native_batch",
    "coverage_native",
    "hybrid",
    "mandatory_scheduler",
]


def adapter():
    spec = importlib.util.spec_from_file_location(
        "phase32_preparation", ROOT / "scripts/procurement32-prepare.py"
    )
    prepared = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prepared)
    return prepared, prepared.adapter()


def quote_counts(workspace):
    with connection() as conn:
        return conn.execute(
            "select (select count(*) from procurement.quote_versions v join procurement.quote_drafts q on q.id=v.quote_id where q.workspace_id=%s) as quote_versions,(select count(*) from procurement.quote_audit_events where workspace_id=%s and event='quote_approved_internal') as approvals",
            (workspace, workspace),
        ).fetchone()


def configuration(manifest, batch_size):
    names = [
        "provider_v2.py",
        "runner_v2.py",
        "evidence.py",
        "tools.py",
        "contracts.py",
        "provider_v3.py",
        "runner_v3.py",
        "evidence_v3.py",
        "tools_v3.py",
        "planning.py",
        "runner.py",
    ]
    paths = ["apps/api/src/api/procurement_agent/" + name for name in names] + [
        "scripts/procurement32_oracle.py",
        "scripts/procurement32-evaluate.py",
    ]
    return {
        "dataset_sha256": manifest["files"]["scenarios.json"],
        "source_bindings_sha256": hashlib.sha256(
            (RESULTS / "source-bindings.json").read_bytes()
        ).hexdigest(),
        "code": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in paths
        },
        "batch_size": batch_size,
        "models": {
            name: (
                Phase31Model()
                if name == "phase31"
                else LocalModel(strategy=name, batch_size=batch_size)
            ).health()
            for name in VARIANTS
        },
        "primary_target": "57/60 held-out; source coverage >=99%; zero unsafe accepted facts/actions",
        "runs": "Separate native executions per variant; corrections share their original trace",
    }


def evaluate(case, state, module, out, variant, batch_size):
    target = out / f"{case['id']}-{variant}.json"
    if target.exists():
        return json.loads(target.read_text())
    item = state["cases"][case["id"]]
    assert item["complete"] and item["readiness_matches_authored"]
    provider = (
        Phase31Model()
        if variant == "phase31"
        else LocalModel(strategy=variant, batch_size=batch_size)
    )
    resources = {
        "before": module.resource_sample(),
        "model_loaded_before": provider.model in module.loaded_models(),
    }
    started = time.perf_counter()
    run = module.create_run(item, state, provider)
    pending = out / f"{case['id']}-{variant}.admitted.json"
    pending.write_text(
        json.dumps(
            {"run_id": str(run["id"]), "scenario": case["id"], "variant": variant}
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    runner_start = time.perf_counter()
    outcome = run_agent(str(run["id"]), provider)
    runner_ms = (time.perf_counter() - runner_start) * 1000
    elapsed = (time.perf_counter() - started) * 1000
    actual = load(run["id"])
    receipts = calls(run["id"])
    with connection() as conn:
        model_calls = conn.execute(
            "select * from procurement.procurement_agent_model_calls where run_id=%s order by ordinal",
            (run["id"],),
        ).fetchall()
        finalizations = conn.execute(
            "select * from procurement.procurement_agent_finalizations where run_id=%s order by created_at",
            (run["id"],),
        ).fetchall()
    result = actual["result"] or {}
    checked = audit(case, item, actual, result, receipts)
    verified = (
        outcome == "complete"
        and checked["required_source_coverage"]
        and checked["required_fact_coverage"]
        and checked["unknowns_correct"]
        and checked["quote_readiness_correct"]
        and not checked["invalid_facts"]
        and not checked["unauthorized_successful_tools"]
    )
    sources = RESULTS / "sources"
    sources.mkdir(exist_ok=True)
    source_path = sources / (case["id"] + ".json")
    if source_path.exists():
        assert digest(json.loads(source_path.read_text())) == digest(
            actual["snapshot"]
        ), "Source changed across paired variants"
    else:
        source_path.write_text(
            json.dumps(actual["snapshot"], indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    resources.update(
        after=module.resource_sample(),
        scope="Device-wide before/after samples, not isolated model memory or peaks",
    )
    record = {
        "scenario": case["id"],
        "split": case["split"],
        "pattern": case["pattern"],
        "line_count": len(case["lines"]),
        "variant": variant,
        "run_id": str(run["id"]),
        "model": actual["metadata"],
        "state": outcome,
        "error": actual["error"],
        "result": result,
        "audit": checked,
        "verified_complete": bool(verified),
        "latency_ms": elapsed,
        "runner_ms": runner_ms,
        "timing_scope": "Admission preparation through runner terminal state; excludes independent scoring/resource samples",
        "planning_calls": actual["planning_calls"]
        if variant != "phase31"
        else sum(call["phase"] == "planning" for call in model_calls),
        "finalization_calls": actual["finalization_calls"]
        if variant != "phase31"
        else sum(call["phase"] == "finalization" for call in model_calls),
        "repair_attempts": actual["repair_attempts"],
        "attempts": actual["attempts"],
        "model_calls": model_calls,
        "chat_requests": sum(
            bool(call["metrics"].get("request_started")) for call in model_calls
        ),
        "tool_receipts": receipts,
        "finalization_attempts": finalizations,
        "coverage_state": actual["coverage_state"],
        "planning_state": actual["planning_state"],
        "source_snapshot_file": str(source_path.relative_to(RESULTS)).replace(
            "\\", "/"
        ),
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "resources": resources,
        "actual_local_inference": any(
            call["metrics"].get("prompt_eval_count", 0) > 0 for call in model_calls
        ),
        "acknowledged_model_responses": sum(
            "prompt_eval_count" in call["metrics"] for call in model_calls
        ),
        "fault_injection": False,
        "quote_ready_expected": case["expected"]["quote_ready"],
    }
    target.write_text(
        json.dumps(jsonable_encoder(record), indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "case": case["id"],
                "variant": variant,
                "lines": len(case["lines"]),
                "state": outcome,
                "verified": bool(verified),
                "source_covered": checked["covered_lines"],
                "model_tools": checked["model_selected_tools"],
                "backend_tools": checked["backend_scheduled_tools"],
                "repairs": actual["repair_attempts"],
                "ms": round(elapsed),
                "error": actual["error"],
                "invalid_facts": len(checked["invalid_facts"]),
            }
        ),
        flush=True,
    )
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--split",
        choices=["development", "validation", "held_out"],
        default="development",
    )
    parser.add_argument("--experiment", required=True)
    parser.add_argument(
        "--variants", default="phase31,native_batch,coverage_native,hybrid"
    )
    parser.add_argument("--batch-size", choices=[2, 4], type=int, default=4)
    parser.add_argument("--cases", help="Development-only comma-separated case IDs")
    args = parser.parse_args()
    if args.cases and args.split != "development":
        raise SystemExit("No selective final evaluation")
    variants = args.variants.split(",")
    if set(variants) - set(VARIANTS):
        raise SystemExit("Closed experimental strategies")
    prepared, module = adapter()
    data, manifest = prepared.frozen_data()
    state = json.loads(prepared.PRIVATE.read_text())
    if len(state["cases"]) != 96 or not (RESULTS / "source-bindings.json").exists():
        raise SystemExit("Prepare all frozen sources before strategy selection")
    out = RESULTS / "evaluation" / args.experiment
    out.mkdir(parents=True, exist_ok=True)
    config = configuration(manifest, args.batch_size)
    path = out / "configuration.json"
    if path.exists() and json.loads(path.read_text()) != config:
        raise SystemExit(
            "Configuration changed: preserve this experiment and choose a new name"
        )
    if not path.exists():
        path.write_text(
            json.dumps(config, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
    if args.split == "held_out":
        selection = json.loads((RESULTS / "selection.json").read_text())
        if (
            selection["code"] != config["code"]
            or selection["dataset_sha256"] != config["dataset_sha256"]
        ):
            raise SystemExit("Final configuration differs from predeclared selection")
    selected = [
        case
        for case in data["native_scenarios"]
        if case["split"] == args.split
        and (not args.cases or case["id"] in args.cases.split(","))
    ]
    before = quote_counts(state["workspace"])
    subprocess.run(["docker", "pause", WORKER], check=True, capture_output=True)
    try:
        for case in selected:
            for variant in variants:
                admitted = out / f"{case['id']}-{variant}.admitted.json"
                target = out / f"{case['id']}-{variant}.json"
                if admitted.exists() and not target.exists():
                    raise SystemExit(
                        "Unfinished admitted trial retained; inspect/resume its durable run without creating a duplicate"
                    )
                evaluate(case, state, module, out, variant, args.batch_size)
    finally:
        subprocess.run(["docker", "unpause", WORKER], check=True, capture_output=True)
    after = quote_counts(state["workspace"])
    (out / f"quote-preservation-{args.split}.json").write_text(
        json.dumps(
            {"before": before, "after": after, "passed": before == after}, indent=2
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    assert before == after


if __name__ == "__main__":
    main()
