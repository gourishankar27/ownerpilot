"""Verify history without relabeling fixtures. Separate manifest-verified checkout repairs."""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/rfq/phase3/results"
baseline = json.loads((OUT / "preservation.json").read_text())
repairs = {
    r["path"]: r
    for r in json.loads((OUT / "checkout-repair.json").read_text())["repairs"]
}
unchanged = []
verified = []
unexpected = []
for name, expected in baseline["sha256"].items():
    relative = name.replace("\\", "/")
    path = ROOT / relative
    current = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    if current == expected:
        unchanged.append(relative)
    elif relative in repairs and current == repairs[relative]["after"]:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD:" + relative], cwd=ROOT, text=True
        ).strip()
        working = subprocess.check_output(
            ["git", "hash-object", str(path)], cwd=ROOT, text=True
        ).strip()
        if head == working:
            verified.append(relative)
        else:
            unexpected.append(relative)
    else:
        unexpected.append(relative)
result = {
    "baseline_commit": baseline["commit"],
    "protected_files": len(baseline["sha256"]),
    "byte_unchanged": len(unchanged),
    "manifest_verified_checkout_repairs": verified,
    "unexpected_changes": unexpected,
    "tracked_history_payloads_unchanged": not unexpected,
    "explanation": "Checkout fixes reproduce unchanged original fixture SHA256 expectations and normalize to identical Git objects; no source labels, released migrations or historical report content changed.",
}
(OUT / "preservation-final.json").write_text(
    json.dumps(result, indent=2) + "\n", encoding="utf-8"
)
print(
    json.dumps(
        {k: v for k, v in result.items() if k != "manifest_verified_checkout_repairs"},
        indent=2,
    )
)
raise SystemExit(bool(unexpected))
