"""Freeze two explicit post-selection routing diagnostics, never final eval inputs.

These reproduce the real integration workflow with known authored synthetic values.
They measure a regression mechanism, not independent generalization or selection.
"""

import hashlib
import json
from pathlib import Path


def main():
    root = Path("data/evaluation/rfq-phase11-diagnostics")
    if (root / "manifest.json").exists():
        raise SystemExit("Frozen diagnostics already exist; never overwrite.")
    (root / "sources").mkdir(parents=True)
    (root / "ground_truth").mkdir()
    header = "Manufacturer | MPN | Description | Qty | UOM\n"
    first = "Nimvora | 001-LAP.1 | Laptop refresh | 12 | EA\n"
    cases = [
        (
            "clean",
            header + first,
            [
                dict(
                    manufacturer="Nimvora",
                    mpn="001-LAP.1",
                    description="Laptop refresh",
                    quantity="12",
                    unit="EA",
                )
            ],
        ),
        (
            "partial",
            header
            + first
            + "Item 2: Request 7 EA of Fiber cable; manufacturer AxionEagle; MPN FC-07.\n",
            [
                dict(
                    manufacturer="Nimvora",
                    mpn="001-LAP.1",
                    description="Laptop refresh",
                    quantity="12",
                    unit="EA",
                ),
                dict(
                    manufacturer="AxionEagle",
                    mpn="FC-07",
                    description="Fiber cable",
                    quantity="7",
                    unit="EA",
                ),
            ],
        ),
    ]
    docs = []
    for name, text, items in cases:
        content = text.encode()
        truth = (json.dumps(dict(header={}, items=items), indent=2) + "\n").encode()
        source, labels = f"sources/{name}.txt", f"ground_truth/{name}.json"
        (root / source).write_bytes(content)
        (root / labels).write_bytes(truth)
        docs.append(
            dict(
                id=name,
                source=source,
                truth=labels,
                format="txt",
                layout_group=name,
                difficulty="diagnostic",
                split="dev",
                expected_items=len(items),
                sha256=hashlib.sha256(content).hexdigest(),
                truth_sha256=hashlib.sha256(truth).hexdigest(),
            )
        )
    (root / "manifest.json").write_text(
        json.dumps(
            dict(
                version="phase11-routing-diagnostic/1",
                purpose="Authored post-selection regression diagnostic; no independent evaluation claim",
                documents=docs,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
