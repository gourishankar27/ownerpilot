"""Fresh citation-only runs on a migrated CLONE of the original ten-case sources.

Original v1 traces stay historical; their source/offer fingerprints must match.
Run after the larger benchmark so inference timing is not overlapped.
"""

import importlib.util
import json
import os
from pathlib import Path
from uuid import uuid4

from psycopg.types.json import Jsonb

from api.config import get_settings
from api.procurement_agent.provider_v2 import LocalModel
from api.procurement_agent.service import snapshot, stable_source, digest
from api.rfq.auth import Identity
from api.rfq.db import connection

ROOT = Path(__file__).resolve().parents[1]


def main():
    info = json.loads(
        (ROOT / "docs/rfq/phase3_1/results/migration-preservation.json").read_text()
    )
    target = info["new_clone_retained"]
    assert target.startswith("ownerpilot_phase31_migration_")
    os.environ["DATABASE_URL"] = os.environ["DATABASE_URL"].replace(
        "ownerpilot_rfq_phase3_demo_phase31_validation", target
    )
    get_settings.cache_clear()
    spec = importlib.util.spec_from_file_location(
        "phase31_eval", ROOT / "scripts/procurement31-evaluate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    state = json.loads((ROOT / ".local/rfq/phase3/evaluation-state.json").read_text())
    cases = json.loads(
        (ROOT / "data/evaluation/procurement-v1/scenarios.json").read_text()
    )["research"]
    out = ROOT / "docs/rfq/phase3_1/results/historical-comparison"
    out.mkdir(parents=True, exist_ok=True)
    (out / "configuration.json").write_text(
        json.dumps(
            {
                "model": LocalModel().health(),
                "clone": target,
                "comparison": "Historical v1 traces versus fresh v2 traces with identical source identities and commercial attestations",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    identity = Identity(state["user"], state["workspace"], "owner")

    def create(item, state, provider):
        with connection() as conn:
            source = snapshot(conn, item["rfq_id"], identity)
            source.update(quote_id=None, catalog_versions=[state["version"]])
            metadata = {**provider.health(), "source_fingerprint": digest(source)}
            return conn.execute(
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
                                "content": "Research this approved RFQ with native tools.",
                            }
                        ]
                    ),
                    Jsonb(metadata),
                    state["user"],
                ),
            ).fetchone()

    module.create_run = create
    for original in cases:
        recorded = json.loads(
            (ROOT / f"docs/rfq/phase3/results/agent/{original['id']}.json").read_text()
        )
        item = state["cases"][original["id"]]
        with connection() as conn:
            old = conn.execute(
                "select snapshot from procurement.procurement_agent_runs where id=%s",
                (recorded["run_id"],),
            ).fetchone()["snapshot"]
            source = snapshot(conn, item["rfq_id"], identity)
        assert stable_source(old) == stable_source(source), (
            "Source changed; cannot claim matched ten-case comparison"
        )
        line = source["lines"][0]
        assert len(line["offers"]["attestations"]) == 1
        expected_freshness = (
            "expired"
            if original["id"] == "expired_offer"
            else "unknown_freshness"
            if original["id"] == "unknown_source_date"
            else "unavailable"
            if original["id"] == "unavailable"
            else "current_according_to_attested_validity"
        )
        assert line["offers"]["attestations"][0]["freshness"] == expected_freshness
        product = line["selection"]["resolution"]["data"]
        item.update(
            complete=True,
            quote_ready=False,
            readiness_matches_authored=True,
            lines={
                "line0": {
                    "line_id": line["line_id"],
                    "product_id": product["product_id"],
                    "version_id": product["version_id"],
                    "fingerprint": product["content_hash"],
                    "offers": {"offer0": item["offer_id"]},
                }
            },
        )
        case = {
            "id": original["id"],
            "split": original["split"],
            "pattern": original["id"],
            "lines": [
                {
                    "key": "line0",
                    "selection": "resolved",
                    "request": {"quantity": "2"},
                    "offers": [
                        {
                            "key": "offer0",
                            "commercial": original["commercial"],
                            "expected_freshness": expected_freshness,
                            "expected_review_state": "active_attestation",
                        }
                    ],
                }
            ],
            "expected": {
                "quote_ready": False,
                "allowed_tools": [
                    "get_approved_rfq",
                    "get_reviewed_product_selection",
                    "search_catalog",
                    "get_product_details",
                    "get_supplier_offers",
                    "compare_supplier_offers",
                    "check_offer_freshness",
                    "get_quote_requirements",
                    "calculate_quote_preview",
                    "get_source_evidence",
                ],
            },
        }
        module.evaluate(case, state, out, "citation_repair")


if __name__ == "__main__":
    main()
