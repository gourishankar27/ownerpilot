"""Serialized development-only latency study, separate from first held-out scores."""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs/rfq/phase3_2/results"


def main():
    assert json.loads((RESULTS / "native-description-probe.json").read_text())["passed"]
    assert (
        json.loads((RESULTS / "final-browser.json").read_text())["stats"]["unexpected"]
        == 0
    )
    destination = RESULTS / "performance-study-setup.json"
    if destination.exists():
        raise SystemExit("Retain initial timing-study setup; inspect before resuming")
    client = httpx.Client(
        base_url="http://127.0.0.1:11434", timeout=30, trust_env=False
    )
    before = client.get("/api/ps").raise_for_status().json()
    known_other_models = {"qwen3:4b", "nomic-embed-text:v1.5"}
    stopped = []
    for model in before["models"]:
        name = model["name"]
        if name in known_other_models:
            subprocess.run(
                [shutil.which("ollama"), "stop", name],
                check=True,
                capture_output=True,
                env={**os.environ, "OLLAMA_HOST": "127.0.0.1:11434"},
            )
            stopped.append(name)
    after = client.get("/api/ps").raise_for_status().json()
    assert all(model["name"] == "qwen3:8b" for model in after["models"]), (
        "Unexpected concurrent model; no quiet-study claim"
    )
    cases = [f"v3-dev-{number:02d}" for number in range(1, 6)]
    declaration = {
        "declared_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "Development latency only; not an independent accuracy benchmark or a replacement for any held-out trial",
        "cases": cases,
        "variants": ["phase31", "native_batch", "coverage_native", "hybrid"],
        "code_or_model_changes": False,
        "conditioning": "All scheduled other inference/test workloads finished; unload only the known non-target test models; retain qwen3:8b model/cache state. No idle-host/peak-memory guarantee.",
        "loaded_before": before,
        "models_stopped_without_deleting_weights": stopped,
        "loaded_after": after,
    }
    destination.write_text(
        json.dumps(declaration, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/procurement32-evaluate.py"),
            "--split",
            "development",
            "--experiment",
            "performance-plan7",
            "--cases",
            ",".join(cases),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/procurement32-report.py"),
            "--experiment",
            "performance-plan7",
        ],
        check=True,
        cwd=ROOT,
    )
    (RESULTS / "performance-study-finished.json").write_text(
        json.dumps(
            {
                "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                "experiment": "performance-plan7",
                "trials": 20,
                "accuracy_denominator_changed": False,
                "loaded_after": client.get("/api/ps").raise_for_status().json(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print("Serialized development timing study finished", flush=True)


if __name__ == "__main__":
    main()
