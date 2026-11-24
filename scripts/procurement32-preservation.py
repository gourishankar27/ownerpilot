"""Verify historical bytes, unchanged tests/finance and frozen selection sources."""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/rfq/phase3_2/results"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    frozen = json.loads((OUT / "preservation.json").read_text())
    mismatches = [
        name
        for name, expected in frozen["sha256"].items()
        if not (ROOT / name).exists() or sha(ROOT / name) != expected
    ]
    tests = subprocess.check_output(
        [
            "git",
            "ls-tree",
            "-r",
            "--name-only",
            frozen["base"],
            "apps/api/tests",
            "apps/web/tests",
        ],
        cwd=ROOT,
        text=True,
    ).splitlines()
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", frozen["base"], "--", *tests],
        cwd=ROOT,
        text=True,
    ).splitlines()
    selection = json.loads((OUT / "selection.json").read_text())
    changed_selected = [
        name
        for name, expected in selection["code"].items()
        if sha(ROOT / name) != expected
    ]
    summary = OUT / "evaluation/dev-plan7-v2/summary.json"
    selected_summary_unchanged = (
        sha(summary) == selection["development_and_validation_summary_sha256"]
    )
    report = {
        "protected_files_checked": len(frozen["sha256"]),
        "historical_mismatches": mismatches,
        "original_test_files_checked": len(tests),
        "changed_original_tests": changed,
        "selected_execution_or_grading_changes": changed_selected,
        "selection_summary_unchanged": selected_summary_unchanged,
        "passed": not mismatches
        and not changed
        and not changed_selected
        and selected_summary_unchanged,
    }
    (OUT / "preservation-check.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(report))
    assert report["passed"]


if __name__ == "__main__":
    main()
