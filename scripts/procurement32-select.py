"""Freeze selection from completed development/validation, before held-out runs."""

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs/rfq/phase3_2/results"


def main():
    path = RESULTS / "selection.json"
    if path.exists():
        raise SystemExit("Selection already frozen; no overwrite")
    experiment = RESULTS / "evaluation/dev-plan7-v2"
    summary = json.loads((experiment / "summary.json").read_text())
    config = json.loads((experiment / "configuration.json").read_text())
    assert not list((RESULTS / "evaluation").glob("*/v3-held-*.json"))
    for variant in ["phase31", "native_batch", "coverage_native", "hybrid"]:
        assert summary["groups"]["development/" + variant]["n"] == 16
        assert summary["groups"]["validation/" + variant]["n"] == 20
    for relative, expected in config["code"].items():
        source = ROOT / relative
        assert hashlib.sha256(source.read_bytes()).hexdigest() == expected
        destination = experiment / "source" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    result = {
        "selected_at_utc": datetime.now(timezone.utc).isoformat(),
        "held_out_used": False,
        "strategy": "hybrid",
        "batch_size": 4,
        "code": config["code"],
        "dataset_sha256": config["dataset_sha256"],
        "source_bindings_sha256": config["source_bindings_sha256"],
        "rationale": "Hybrid 16/16 development and 19/20 validation with full source coverage; coverage-native 14/16 and 19/20; native batching 14/16 and 17/20. Scheduler-only source collection reached all lines but native citations completed 13/16 development. Batch two needed more backend calls and reduced native coverage. Select bounded hybrid/four; retain explicit backend attribution.",
        "targets": {
            "held_out_cases": 60,
            "minimum_verified_complete": 57,
            "minimum_line_source_coverage": 0.99,
            "maximum_unsupported_accepted_facts": 0,
            "maximum_unauthorized_successful_tools": 0,
        },
        "tuning_after_selection": False,
        "development_and_validation_summary_sha256": hashlib.sha256(
            (experiment / "summary.json").read_bytes()
        ).hexdigest(),
        "required_held_out_variants": [
            "phase31",
            "native_batch",
            "coverage_native",
            "hybrid",
        ],
    }
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(
        json.dumps(
            {
                key: result[key]
                for key in ["strategy", "batch_size", "held_out_used", "targets"]
            }
        )
    )


if __name__ == "__main__":
    main()
