"""Separate known regression/GPU interference from immutable accuracy trials."""

import importlib.util
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs/rfq/phase3_2/results"


def parse(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def main():
    windows = []
    for name in [
        "regression-tests.xml",
        "regression-469.xml",
        "final-backend-tests.xml",
    ]:
        suite = ET.parse(RESULTS / name).getroot().find("testsuite")
        real = next(
            case
            for case in suite.findall("testcase")
            if case.attrib["name"] == "test_real_ollama"
        )
        assert real.find("skipped") is None
        start = parse(suite.attrib["timestamp"]) - timedelta(seconds=5)
        end = parse(suite.attrib["timestamp"]) + timedelta(
            seconds=float(suite.attrib["time"]) + 305
        )
        windows.append(
            {
                "suite": name,
                "start_utc": start.isoformat(),
                "end_utc": end.isoformat(),
                "real_qwen4_test_seconds": float(real.attrib["time"]),
                "method": "Conservatively exclude the entire regression suite, 300 seconds of configured model residence afterwards and 5 seconds of boundary padding",
            }
        )
    folder = RESULTS / "evaluation/final-plan7"
    rows = [
        json.loads(path.read_text())
        for path in sorted(folder.glob("v3-held-*.json"))
        if not path.name.endswith(".admitted.json")
    ]
    assert len(rows) == 240
    excluded = {}
    for row in rows:
        calls = row["model_calls"]
        start = min(parse(call["created_at"]) for call in calls) - timedelta(seconds=5)
        end = max(
            parse(call["finished_at"] or call["created_at"]) for call in calls
        ) + timedelta(seconds=5)
        matches = [
            window["suite"]
            for window in windows
            if start <= parse(window["end_utc"]) and end >= parse(window["start_utc"])
        ]
        if matches:
            excluded.setdefault(row["scenario"], []).append(
                {"variant": row["variant"], "windows": matches}
            )
    retained = [row for row in rows if row["scenario"] not in excluded]
    spec = importlib.util.spec_from_file_location(
        "latency_report32", ROOT / "scripts/procurement32-report.py"
    )
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)
    variants = ["phase31", "native_batch", "coverage_native", "hybrid"]
    assert len(retained) == 4 * (60 - len(excluded))
    common = set.intersection(
        *[
            {
                row["scenario"]
                for row in retained
                if row["variant"] == variant and row["verified_complete"]
            }
            for variant in variants
        ]
    )
    result = {
        "accuracy_denominator_unchanged": "All first frozen trials remain in the 60-case accuracy denominator per variant; no native trial was rerun",
        "measurement_issue": "The full backend suite includes actual qwen3:4b inference. It was initially mistaken for CPU-only work. Two regression suites overlapped held-out timing; the earlier suite overlapped development work.",
        "windows": windows,
        "trial_interval_method": "First model admission through last recorded model-call finish, padded by 5 seconds; inference and tool execution are within this interval",
        "matched_case_exclusion": "Exclude every variant for a case if any variant overlaps a recorded window; independent of its outcome or observed latency",
        "excluded_cases": excluded,
        "timing_cases_retained_per_variant": 60 - len(excluded),
        "limitation": "Other CPU/host activity was not controlled. These are practical local validation timings, not idle-host or isolated-GPU measurements.",
        "groups": {
            variant: report.summarize(
                [row for row in retained if row["variant"] == variant]
            )
            for variant in variants
        },
        "matched_successful_cases": sorted(common),
        "matched_successful_latency_ms": {
            variant: report.distribution(
                [
                    row["latency_ms"]
                    for row in retained
                    if row["variant"] == variant and row["scenario"] in common
                ]
            )
            for variant in variants
        },
    }
    (RESULTS / "latency-without-regressions.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "accuracy_cases_per_variant": 60,
                "timing_cases_retained_per_variant": result[
                    "timing_cases_retained_per_variant"
                ],
                "excluded_cases": sorted(excluded),
            }
        )
    )


if __name__ == "__main__":
    main()
