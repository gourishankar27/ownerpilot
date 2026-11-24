"""Archive exact experimental code and hash the complete public evidence bundle."""

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/rfq/phase3_2"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert (DOCS / "results/final-gates.json").exists()
    archived = 0
    for path in sorted((DOCS / "results/evaluation").glob("*/configuration.json")):
        config = json.loads(path.read_text())
        for relative, expected in config["code"].items():
            target = path.parent / "source" / relative
            if not target.exists():
                original = ROOT / relative
                assert sha(original) == expected, (
                    f"Missing original experimental code: {relative}"
                )
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(original, target)
            assert sha(target) == expected
            archived += 1
    manifest = DOCS / "results/artifact-manifest.json"
    paths = sorted(
        path
        for directory in [DOCS, ROOT / "data/evaluation/procurement-v3"]
        for path in directory.rglob("*")
        if path.is_file() and path != manifest
    )
    result = {
        "scope": "Public Phase 3.2 documentation, source archives, datasets and actual validation/evaluation evidence",
        "experimental_code_files_verified": archived,
        "files": {
            str(path.relative_to(ROOT)).replace("\\", "/"): sha(path) for path in paths
        },
    }
    manifest.write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {"files_hashed": len(paths), "experimental_code_files_verified": archived}
        )
    )


if __name__ == "__main__":
    main()
