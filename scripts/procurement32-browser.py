"""Run unchanged historical and new browser scenarios, preserving old images."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs/rfq/phase3_2/results"


def main():
    runtime = json.loads((ROOT / ".local/rfq/phase3_2/runtime-env.json").read_text())
    environment = {
        **os.environ,
        **runtime,
        "RFQ_WEB_URL": "http://localhost:3042",
        "RFQ_SCREENSHOT_DIR": "../../docs/rfq/phase3_2/screenshots/regression",
    }
    snapshots = {
        path: path.read_bytes()
        for path in (ROOT / "docs/rfq/phase3_1/screenshots").glob("*.png")
    }
    target = ROOT / "docs/rfq/phase3_2/screenshots/regression"
    target.mkdir(parents=True, exist_ok=True)
    try:
        execution = subprocess.run(
            ["pnpm.cmd", "exec", "playwright", "test"],
            cwd=ROOT / "apps/web",
            env=environment,
        )
    finally:
        for path, original in snapshots.items():
            if path.read_bytes() != original:
                (target / ("phase31-" + path.name)).write_bytes(path.read_bytes())
                path.write_bytes(original)
        current = ROOT / ".local/rfq/playwright-results.json"
        if current.exists():
            (RESULTS / "final-browser.json").write_bytes(current.read_bytes())
        preservation = {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            == hashlib.sha256(original).hexdigest()
            for path, original in snapshots.items()
        }
        (RESULTS / "browser-image-preservation.json").write_text(
            json.dumps(preservation, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        assert all(preservation.values())
    raise SystemExit(execution.returncode)


if __name__ == "__main__":
    main()
