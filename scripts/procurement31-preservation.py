"""Check protected historical bytes, original test files and additive frozen corpora."""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/rfq/phase3_1/results"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    original = json.loads((OUT / "preservation.json").read_text())
    legacy = json.loads((OUT / "legacy-source.json").read_text())
    wrong = [
        name
        for name, expected in original["sha256"].items()
        if not (ROOT / name).exists() or sha(ROOT / name) != expected
    ]
    provider = ROOT / "apps/api/src/api/procurement_agent/provider.py"
    copy = provider.with_name("legacy_provider.py")
    base = original["head"]
    test_files = subprocess.check_output(
        [
            "git",
            "ls-tree",
            "-r",
            "--name-only",
            base,
            "apps/api/tests",
            "apps/web/tests",
        ],
        cwd=ROOT,
        text=True,
    ).splitlines()
    changed_tests = subprocess.check_output(
        ["git", "diff", "--name-only", base, "--", *test_files], cwd=ROOT, text=True
    ).splitlines()
    finance_changed = subprocess.check_output(
        [
            "git",
            "diff",
            "--name-only",
            base,
            "--",
            "apps/api/src/api/procurement_agent/finance.py",
            "apps/api/src/api/procurement_agent/service.py",
        ],
        cwd=ROOT,
        text=True,
    ).splitlines()
    datasets = {}
    for name in ["procurement-v2", "procurement-finance-v2"]:
        directory = ROOT / "data/evaluation" / name
        manifest = json.loads((directory / "manifest.json").read_text())
        datasets[name] = all(
            sha(directory / path) == expected
            for path, expected in manifest["files"].items()
        )
    result = {
        "files_checked": len(original["sha256"]),
        "mismatches": wrong,
        "legacy_provider_identical": sha(provider)
        == sha(copy)
        == legacy["provider_sha256"],
        "original_tools_identical": sha(provider.with_name("tools.py"))
        == legacy["tools_sha256"],
        "original_test_files_checked": len(test_files),
        "changed_original_tests": changed_tests,
        "changed_finance_or_service": finance_changed,
        "frozen_new_datasets": datasets,
    }
    result["passed"] = (
        not wrong
        and result["legacy_provider_identical"]
        and result["original_tools_identical"]
        and not changed_tests
        and not finance_changed
        and all(datasets.values())
    )
    (OUT / "final-preservation.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(result))
    assert result["passed"]


if __name__ == "__main__":
    main()
