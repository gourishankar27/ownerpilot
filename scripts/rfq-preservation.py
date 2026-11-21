"""Protect released RFQ evidence. Run capture once, verify before delivery."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/rfq/phase1_1/results/baseline/preservation.json"


def paths():
    selected = set((ROOT / "data/evaluation/rfq").rglob("*"))
    selected.update((ROOT / "apps/api/src/api/rfq/migrations").glob("*.sql"))
    selected.update((ROOT / "docs/rfq/results").rglob("*"))
    selected.update((ROOT / "docs/rfq/screenshots").rglob("*"))
    selected.update(p for p in (ROOT / "docs/rfq").glob("*.md") if p.name != "STATUS.md")
    selected.add(ROOT / "docs.zip")
    return sorted(p for p in selected if p.is_file())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["capture", "verify"])
    args = parser.parse_args()
    if args.action == "capture":
        if MANIFEST.exists():
            raise SystemExit("Refusing to replace preservation baseline.")
        record = {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "sha256": {p.relative_to(ROOT).as_posix(): digest(p) for p in paths()}}
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(json.dumps(record, indent=2)+"\n", encoding="utf-8")
        print(f"Captured {len(record['sha256'])} protected files.")
    else:
        record = json.loads(MANIFEST.read_text())
        changed = [name for name, value in record["sha256"].items() if not (ROOT/name).exists() or digest(ROOT/name) != value]
        print(json.dumps({"protected": len(record["sha256"]), "changed": changed}))
        if changed:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
