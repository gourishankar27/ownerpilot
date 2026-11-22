"""Independent benchmark accounting and declared-policy deterministic quote baseline."""

import hashlib
import json
import math
import statistics
import time
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

from api.procurement_agent.finance import QuotePolicy, calculate
from api.procurement_agent.tools import verify

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/rfq/phase3/results"
data = json.loads((ROOT / "data/evaluation/procurement-v1/scenarios.json").read_text())
records = [
    json.loads(path.read_text())
    for path in (OUT / "agent").glob("*.json")
    if path.name != "summary.json"
]
policy = QuotePolicy.model_validate(data["finance"][0]["policy"])
quotes = []
unsupported = []
for record in records:
    case = next(case for case in data["research"] if case["id"] == record["scenario"])
    start = time.perf_counter()
    calculation = calculate(
        [
            {
                "line_id": record["deterministic"]["facts"]["line_id"],
                "quantity": "2",
                "offer_id": record["deterministic"]["facts"]["attestations"][0]["id"],
                "offer": case["commercial"],
            }
        ],
        policy,
        date(2026, 11, 21),
    )
    quotes.append(
        {
            "scenario": case["id"],
            "split": case["split"],
            "quote_complete": calculation["complete"],
            "latency_ms": (time.perf_counter() - start) * 1000,
            "calculation": calculation,
            "source": "Same frozen human-attested offer and frozen declared policy; no model facts or implicit shipping/tax assumptions",
        }
    )
    candidate = record["native_without_verifier"].get("candidate") or {}
    for claim in candidate.get("claims", []):
        try:
            verify(json.dumps({"claims": [claim]}), record["tools"])
        except ValueError as exc:
            unsupported.append(
                {"scenario": case["id"], "claim": claim, "reason": str(exc)}
            )
held = [r for r in records if r["split"] == "held_out"]


def p95(values):
    return sorted(values)[math.ceil(0.95 * len(values)) - 1]


toolcalls = [tool for record in records for tool in record["tools"]]
candidate_total = sum(
    r["native_without_verifier"]["valid_claims"]
    + r["native_without_verifier"]["unsupported_claims"]
    for r in records
)
root = ET.parse(OUT / "all-tests.xml").getroot()
suite = root if root.tag == "testsuite" else root.find("testsuite")
result = {
    "native_runs": len(records),
    "development_runs": len(records) - len(held),
    "held_out_runs": len(held),
    "verified_complete": sum(r["verified"]["state"] == "complete" for r in records),
    "held_out_verified_complete": sum(
        r["verified"]["state"] == "complete" for r in held
    ),
    "tool_calls": len(toolcalls),
    "successful_authorized_tool_calls": sum(
        t["status"] == "succeeded" for t in toolcalls
    ),
    "model_calls": sum(r["model_calls"] for r in records),
    "candidate_claims": candidate_total,
    "source_supported_candidate_claims": candidate_total - len(unsupported),
    "unsupported_candidate_claims": unsupported,
    "accepted_claims": sum(r["verified"]["accepted_claims"] for r in records),
    "accepted_unsupported_claims": sum(
        r["verified"]["unsupported_accepted"] for r in records
    ),
    "research_median_ms": statistics.median(
        r["verified"]["latency_ms"] for r in records
    ),
    "research_p95_ms": p95([r["verified"]["latency_ms"] for r in records]),
    "deterministic_fact_listing_median_ms": statistics.median(
        r["deterministic"]["latency_ms"] for r in records
    ),
    "deterministic_fact_listing_p95_ms": p95(
        [r["deterministic"]["latency_ms"] for r in records]
    ),
    "deterministic_quote_preparation_complete": sum(
        q["quote_complete"] for q in quotes
    ),
    "deterministic_quote_preparation_median_ms": statistics.median(
        q["latency_ms"] for q in quotes
    ),
    "deterministic_quote_preparation_p95_ms": p95([q["latency_ms"] for q in quotes]),
    "finance_frozen_standalone_cases": 34,
    "finance_frozen_batch_cases": 20,
    "finance_frozen_batch_lines": 200,
    "known_bad_batch_total_labels": 1,
    "pytest": {
        "tests": int(suite.get("tests")),
        "failures": int(suite.get("failures")),
        "errors": int(suite.get("errors")),
        "skipped_including_xfail": int(suite.get("skipped")),
    },
    "limitations": [
        "10 actual model runs, 8 held-out; small synthetic sample",
        "200 financial lines are templated batches, not native-agent tasks",
        "Deterministic policy is fixed human input; research cannot fill missing commercial facts",
        "Final prompt was not retuned after held-out evaluation",
        "Known frozen JPY oracle total defect retained, not relabeled",
    ],
}
(OUT / "paired-quote-baseline.json").write_text(
    json.dumps(quotes, indent=2) + "\n", encoding="utf-8"
)
(OUT / "measured-summary.json").write_text(
    json.dumps(result, indent=2) + "\n", encoding="utf-8"
)
print(
    json.dumps(
        {k: v for k, v in result.items() if k != "unsupported_candidate_claims"},
        indent=2,
    )
)
hashes = {
    path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
    for folder in [ROOT / "data/evaluation/procurement-v1", ROOT / "docs/rfq/phase3"]
    for path in folder.rglob("*")
    if path.is_file() and path.name != "artifact-hashes.json"
}
(OUT / "artifact-hashes.json").write_text(
    json.dumps({"sha256": hashes}, indent=2) + "\n", encoding="utf-8"
)
