"""Prepare frozen fictional v3 sources via real signed API and local indexing.

The existing fixture adapter is reused without changing any Phase 3.1 script or
artifact. No model research plan or answer is injected here.
"""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from uuid import uuid4

import httpx

from api.rfq.db import connection

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/evaluation/procurement-v3"
PRIVATE = ROOT / ".local/rfq/phase3_2/evaluation-state.json"
WORKER = "ownerpilot-procurement32-validation-worker-1"


def adapter():
    spec = importlib.util.spec_from_file_location(
        "phase32_source_adapter", ROOT / "scripts/procurement31-evaluate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.PRIVATE = PRIVATE
    module.WORKER = WORKER
    module.client.close()
    module.client = httpx.Client(
        base_url="http://127.0.0.1:8042", timeout=60, trust_env=False
    )
    return module


def frozen_data():
    manifest = json.loads((DATA / "manifest.json").read_text())
    raw = (DATA / "scenarios.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == manifest["files"]["scenarios.json"]
    return json.loads(raw), manifest


def setup(module, data):
    if (
        "ownerpilot_rfq_phase3_demo_phase31_validation_phase32"
        not in os.environ["DATABASE_URL"]
    ):
        raise SystemExit("Requires isolated Phase 3.2 validation database")
    if PRIVATE.exists():
        state = json.loads(PRIVATE.read_text())
    else:
        workspace = str(uuid4())
        user = "phase32-fictional-fixture-" + uuid4().hex
        with connection() as conn:
            conn.execute(
                "insert into business_workspaces(id,name,slug) values(%s,'Phase 3.2 independent batch research study',%s)",
                (workspace, workspace),
            )
            conn.execute(
                "insert into workspace_members(workspace_id,user_id,role) values(%s,%s,'owner')",
                (workspace, user),
            )
        state = {
            "workspace": workspace,
            "user": user,
            "cases": {},
            "dataset": "procurement-v3",
        }
        module.save(state)
    if state.get("version"):
        return state
    if not state.get("catalog"):
        catalog = module.request(
            "POST",
            "catalogs",
            state,
            json={
                "name": "Independent fictional procurement-v3 sources",
                "license": "CC0 synthetic",
            },
        )
        state["catalog"] = catalog["id"]
        module.save(state)
    if not state.get("pending_version"):
        preview = module.request(
            "POST",
            f"catalogs/{state['catalog']}/imports/preview",
            state,
            files={
                "file": (
                    "procurement-v3.json",
                    json.dumps(data["catalog"]).encode(),
                    "application/json",
                )
            },
        )
        state.update(pending_version=preview["id"], fingerprint=preview["fingerprint"])
        module.save(state)
    module.request(
        "POST",
        f"catalogs/{state['catalog']}/imports/confirm",
        state,
        json={
            "version_id": state["pending_version"],
            "fingerprint": state["fingerprint"],
        },
    )
    result = module.wait_job(
        "catalog-import-jobs/" + state["pending_version"],
        state,
        {"published", "failed"},
    )
    if result["state"] != "published":
        raise RuntimeError("Real local indexing did not publish")
    state["version"] = state["pending_version"]
    module.save(state)
    return state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--split",
        choices=["development", "validation", "held_out", "all"],
        default="all",
    )
    args = parser.parse_args()
    data, manifest = frozen_data()
    module = adapter()
    state = setup(module, data)
    for case in data["native_scenarios"]:
        if args.split != "all" and case["split"] != args.split:
            continue
        item = module.prepare(case, state)
        print(
            json.dumps(
                {
                    "prepared": case["id"],
                    "lines": len(case["lines"]),
                    "readiness_matches_authored": item["readiness_matches_authored"],
                }
            ),
            flush=True,
        )
    if len(state["cases"]) == 96 and all(
        item.get("complete") for item in state["cases"].values()
    ):
        record = {
            "dataset_sha256": manifest["files"]["scenarios.json"],
            "catalog_version": state["version"],
            "cases": state["cases"],
            "scope": "Authorised synthetic source bindings before final configuration selection; not model answers",
        }
        path = ROOT / "docs/rfq/phase3_2/results/source-bindings.json"
        if not path.exists():
            path.write_text(
                json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n"
            )


if __name__ == "__main__":
    main()
