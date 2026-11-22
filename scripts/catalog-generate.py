"""Fictional authored catalog families and graded queries; no retrieval-generated labels."""

import hashlib
import json
from pathlib import Path

from api.catalog.core import identity

ROOT = Path("data/evaluation/product-catalog")
CATEGORIES = [
    "laptop",
    "workstation",
    "server",
    "processor",
    "memory",
    "ssd",
    "hdd",
    "switch",
    "router",
    "firewall",
    "access_point",
    "monitor",
    "power_supply",
    "cable",
    "adapter",
    "software_license",
    "ups",
]


def main():
    if (ROOT / "manifest.json").exists():
        raise SystemExit("Frozen catalog exists; never overwrite")
    ROOT.mkdir(parents=True)
    rows, products, queries = [], [], []
    for family, category in enumerate(CATEGORIES):
        for variant in range(60):
            product = dict(
                source_id=f"source-{family}-{variant}",
                manufacturer="Northvale",
                mpn=f"00-{family:02}-{variant:03}-I1/O0",
                name=f"Fictional {category} series {family} configuration {variant}",
                description=f"Synthetic {category} equipment for business infrastructure configuration {variant}",
                category=category,
                specs={
                    "capacity": (variant % 6 + 1) * 16,
                    "connector": "type-a" if variant % 2 else "type-c",
                    "pack_size": 1,
                },
                supplier="Fictional Cedar",
                supplier_sku=f"CED-{family}-{variant}",
                price=None,
                currency=None,
                availability=None,
                status="active",
                url=None,
            )
            if variant == 59:
                product["status"] = "obsolete"
            rows.append(product)
            products.append(product)
            if variant % 5 == 0:
                rows.append(
                    {
                        **product,
                        "source_id": f"offer-{family}-{variant}",
                        "supplier": "Fictional Juniper",
                        "manufacturer": "Northvale Systems",
                        "supplier_sku": f"JUN-{family}-{variant}",
                    }
                )
        split = "dev" if family < 6 else "validation" if family < 10 else "heldout"
        base = products[-60]
        for kind in (
            "exact",
            "alias",
            "description",
            "specification",
            "near_identifier",
            "no_match",
        ):
            query = {
                "manufacturer": "Northvale Systems"
                if kind == "alias"
                else "Northvale"
                if kind in {"exact", "near_identifier"}
                else None,
                "mpn": base["mpn"]
                if kind in {"exact", "alias"}
                else base["mpn"] + "X"
                if kind == "near_identifier"
                else None,
                "description": base["description"]
                if kind != "description"
                else f"Need {category.replace('_', ' ')} business infrastructure",
                "category": category,
                "specs": base["specs"] if kind != "no_match" else {"capacity": 999999},
            }
            relevance = {}
            if kind != "no_match":
                for p in products[-60:]:
                    if p["status"] == "active" and p["specs"] == base["specs"]:
                        relevance[identity(p)] = 3 if p["mpn"] == base["mpn"] else 2
            queries.append(
                dict(
                    id=f"q-{family:02}-{kind}",
                    split=split,
                    kind=kind,
                    query=query,
                    relevance=relevance,
                    no_valid_match=kind == "no_match",
                )
            )
    (ROOT / "catalog.json").write_text(json.dumps(rows, indent=2) + "\n")
    (ROOT / "queries.json").write_text(json.dumps(queries, indent=2) + "\n")
    manifest = {
        "version": "fictional-it-catalog/1",
        "seed": "deterministic authored grid/1",
        "source_records": len(rows),
        "canonical_variants": len(products),
        "queries": len(queries),
        "split": "disjoint category families; templates shared, synthetic-only limitation",
        "license": "CC0 fictional generated records",
        "frozen_before_final_evaluation": True,
        "sha256": {
            f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest()
            for f in ["catalog.json", "queries.json"]
        },
    }
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()
