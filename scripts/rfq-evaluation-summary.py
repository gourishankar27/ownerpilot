"""Aggregate only actual saved runs; keep earlier failures and rechecks explicit."""

import json
from pathlib import Path

from api.rfq.evaluation.run import metrics

ROOT = Path("docs/rfq/results")


def main():
    baseline = json.loads((ROOT / "deterministic-full-final.json").read_text())
    initial = json.loads((ROOT / "llm-stratified.json").read_text())
    recheck = json.loads((ROOT / "llm-ocr-recheck.json").read_text())
    hybrid = json.loads((ROOT / "hybrid-stratified-final.json").read_text())
    replaced = {r["id"] for r in recheck["samples"]}
    combined = [r for r in initial["samples"] if r["id"] not in replaced] + recheck[
        "samples"
    ]
    final = dict(initial)
    final.update(
        {
            "samples": combined,
            "metrics": metrics(combined),
            "combined_from": [
                "llm-stratified.json (6 successful digital samples)",
                "llm-ocr-recheck.json (2 samples after OCR resource-cleanup fix)",
            ],
            "executed_sample_attempts": 10,
            "notes": "Earlier two OCR TypeErrors remain in the initial report. This is an aggregate of actual runs, not a new single run. Six initial samples did not record item-field hallucination counts; that aggregate metric is not measured.",
        }
    )
    final["metrics"]["hallucinated_item_fields_rate"] = None
    final["by_group"] = {}
    (ROOT / "llm-stratified-final.json").write_text(
        json.dumps(final, indent=2) + "\n", encoding="utf-8"
    )
    ids = {r["id"] for r in hybrid["samples"]}
    baseline_rows = [r for r in baseline["samples"] if r["id"] in ids]
    supported = {
        "csv_semicolon",
        "xlsx_multisheet",
        "pdf_repeated_headers",
        "pdf_aligned",
    }
    subsets = {
        "matched_8_documents": {
            "deterministic": metrics(baseline_rows),
            "llm": final["metrics"],
            "hybrid": hybrid["metrics"],
        },
        "clean_table_12_documents": {
            "deterministic": metrics(
                [
                    r
                    for r in baseline["samples"]
                    if r["group"] in supported and r["difficulty"] == "clean"
                ]
            )
        },
        "digital_6_documents": {
            "deterministic": metrics(
                [
                    r
                    for r in baseline_rows
                    if r["group"] not in {"scanned", "mixed_rotated"}
                ]
            ),
            "llm": metrics(
                [r for r in combined if r["group"] not in {"scanned", "mixed_rotated"}]
            ),
            "hybrid": metrics(
                [
                    r
                    for r in hybrid["samples"]
                    if r["group"] not in {"scanned", "mixed_rotated"}
                ]
            ),
        },
        "scanned_mixed_2_documents": {
            "deterministic": metrics(
                [r for r in baseline_rows if r["group"] in {"scanned", "mixed_rotated"}]
            ),
            "llm": recheck["metrics"],
            "hybrid": metrics(
                [
                    r
                    for r in hybrid["samples"]
                    if r["group"] in {"scanned", "mixed_rotated"}
                ]
            ),
        },
    }
    for subset in subsets.values():
        for mode, data in subset.items():
            if mode == "llm" and data.get("documents") != 2:
                data["hallucinated_item_fields_rate"] = None
    summary = {
        "dataset_version": baseline["dataset_version"],
        "manifest_sha256": baseline["manifest_sha256"],
        "hardware": "RTX 4090 Laptop 16376 MiB, driver 610.88; Docker Desktop Linux workers; Windows 11 Python 3.14/Node 24.12; concurrent engineering checks may affect timings",
        "model": "qwen3.8:27b",
        "subsets": subsets,
        "deterministic_full_32": baseline["metrics"],
    }
    (ROOT / "comparison.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    rows = [
        "| Metric | Deterministic | Local LLM | Hybrid | Target / outcome |",
        "|---|---:|---:|---:|---|",
    ]
    comparison = subsets["matched_8_documents"]
    for name, title, target in [
        ("mpn_accuracy", "MPN exact match", ">=95% digital target; scans separate"),
        ("manufacturer_accuracy", "Manufacturer exact match", "Measured"),
        ("quantity_accuracy", "Quantity exact match", ">=95% digital target"),
        ("precision", "Item precision", "Measured"),
        ("recall", "Item recall", "Measured"),
        ("f1", "Item F1", ">=90% supported subset"),
        ("required_completeness", "Required-field completeness", "Measured"),
        ("structured_validity", "Validated extraction payload rate", "100% required"),
        (
            "unsupported_field_rate",
            "Unsupported proposed fields",
            "Flagged, never auto-approved",
        ),
        ("evidence_validity", "Stored evidence validity", "Exact source occurrence"),
        (
            "document_success_rate",
            "Processing success",
            "Includes valid zero-item results",
        ),
    ]:
        values = [
            comparison[mode].get(name) for mode in ("deterministic", "llm", "hybrid")
        ]
        rows.append(
            "| "
            + title
            + " | "
            + " | ".join(
                "not measured" if value is None else f"{100 * value:.2f}%"
                for value in values
            )
            + " | "
            + target
            + " |"
        )
    for stat in ("median", "p95"):
        values = [
            comparison[mode]["latency_ms"][stat] / 1000
            for mode in ("deterministic", "llm", "hybrid")
        ]
        rows.append(
            f"| End-to-end {stat} seconds | "
            + " | ".join(f"{v:.3f}" for v in values)
            + " | Actual parser + extraction, excludes queue/review |"
        )
    (ROOT / "comparison-table.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(json.dumps(summary["subsets"], indent=2))


if __name__ == "__main__":
    main()
