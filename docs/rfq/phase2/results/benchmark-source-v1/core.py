"""Versioned conservative identity, genuine Okapi BM25 and transparent ranking.

BM25 is implemented directly (k1=1.5,b=.75, positive Robertson IDF).
No database full-text rank is relabeled as BM25. No serialized executable indexes.
"""

from collections import Counter
from decimal import Decimal
import csv
import hashlib
import io
import json
import math
import re
import zipfile

import openpyxl
from pydantic import BaseModel, ConfigDict, Field, field_validator

POLICY = "catalog-rrf/1"
NORMALIZATION = "conservative/1"
TOKENIZER = "technical-bm25/1"
ALIASES = {"northvale systems": "northvale"}  # Authored fictional corpus mapping, v1.


class Product(BaseModel):
    model_config = ConfigDict(extra="forbid", str_max_length=4000)
    source_id: str = Field(min_length=1, max_length=160)
    manufacturer: str = Field(min_length=1, max_length=160)
    mpn: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=300)
    description: str = ""
    category: str = Field(min_length=1, max_length=100)
    specs: dict[str, str | int | float] = Field(default_factory=dict, max_length=40)
    supplier: str = "unknown"
    supplier_sku: str | None = None
    price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    availability: str | None = None
    status: str = "active"
    url: str | None = None

    @field_validator("specs")
    @classmethod
    def specifications(cls, values):
        for key, value in values.items():
            if len(key) > 80 or len(str(value)) > 300:
                raise ValueError("Specification too long")
            if isinstance(value, (int, float)) and (
                not math.isfinite(value) or value < 0
            ):
                raise ValueError("Specifications must be finite and nonnegative")
        return values

    @field_validator("price")
    @classmethod
    def commercial(cls, value):
        if value is not None and not value.is_finite():
            raise ValueError("Price must be finite")
        return value


def comparison(value):
    # Case and identifier punctuation are significant. Only explicit Unicode dashes.
    return re.sub("[\u2010-\u2015\u2212]", "-", value.strip())


def manufacturer(value):
    normalized = " ".join(value.strip().casefold().split())
    return ALIASES.get(normalized, normalized)


def identity(product):
    return hashlib.sha256(
        json.dumps(
            [
                manufacturer(product["manufacturer"]),
                comparison(product["mpn"]),
                product["category"],
                product["specs"],
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()


def canonical_text(product, specifications=True):
    return " ".join(
        str(product.get(k, ""))
        for k in ["manufacturer", "name", "category", "description"]
    ) + (
        " " + json.dumps(product.get("specs", {}), sort_keys=True)
        if specifications
        else ""
    )


def tokens(text):
    # Keep complete identifiers while also exposing component tokens for prose.
    intact = re.findall(r"[\w]+(?:[-./][\w]+)*", text.casefold())
    return intact + [
        part
        for token in intact
        if re.search(r"[-./_]", token)
        for part in re.split(r"[-./_]", token)
    ]


class BM25:
    def __init__(self, documents):
        self.docs = [Counter(tokens(d)) for d in documents]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.average = sum(self.lengths) / max(1, len(self.docs))
        self.df = Counter(t for d in self.docs for t in d)

    def scores(self, query):
        scores = []
        for doc, length in zip(self.docs, self.lengths):
            score = 0.0
            for token in set(tokens(query)):
                frequency = doc.get(token, 0)
                if frequency:
                    idf = math.log(
                        1
                        + (len(self.docs) - self.df[token] + 0.5)
                        / (self.df[token] + 0.5)
                    )
                    score += (
                        idf
                        * frequency
                        * 2.5
                        / (
                            frequency
                            + 1.5 * (0.25 + 0.75 * length / (self.average or 1))
                        )
                    )
            scores.append(score)
        return scores


MAPPINGS = {
    "brand": "manufacturer",
    "manufacturer part number": "mpn",
    "product name": "name",
    "product description": "description",
    "supplier sku": "supplier_sku",
    "unit price": "price",
    "product specifications": "specs",
}


def parse_catalog(filename, content, mapping=None):
    if not content or len(content) > 10 * 1024 * 1024:
        raise ValueError("Catalog must be 1 byte to 10 MiB")
    suffix = filename.lower().rsplit(".", 1)[-1]
    if suffix == "json":
        rows = json.loads(content)
        if not isinstance(rows, list):
            raise ValueError("JSON must be an array of product objects")
    elif suffix == "csv":
        text = content.decode("utf-8-sig")
        if "\0" in text:
            raise ValueError("NUL is not CSV text")
        rows = list(csv.DictReader(io.StringIO(text), strict=True))
    elif suffix == "xlsx":
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if (
                len(archive.infolist()) > 1000
                or sum(f.file_size for f in archive.infolist()) > 40 * 1024 * 1024
            ):
                raise ValueError("Workbook decompression limit")
        book = openpyxl.load_workbook(
            io.BytesIO(content), read_only=True, data_only=False
        )
        try:
            if len(book.worksheets) != 1:
                raise ValueError("Select a single-sheet catalog")
            sheet = book.active
            if sheet.max_row > 5001 or sheet.max_column > 40:
                raise ValueError("Workbook row/column limit")
            iterator = sheet.iter_rows(values_only=True)
            header = next(iterator)
            if len(set(header)) != len(header):
                raise ValueError("Duplicate workbook columns")
            rows = [dict(zip(header, values)) for values in iterator]
        finally:
            book.close()
    else:
        raise ValueError("Use CSV, XLSX or JSON")
    if not 1 <= len(rows) <= 5000:
        raise ValueError("Catalog requires 1 to 5000 rows")
    output, seen = [], set()
    detected = {}
    for row in rows:
        if not isinstance(row, dict) or len(row) > 40:
            raise ValueError("Invalid catalog row")
        normalized = {}
        for key, value in row.items():
            key = str(key).strip()
            target = (mapping or {}).get(
                key, MAPPINGS.get(key.casefold(), key.casefold())
            )
            if target in normalized:
                raise ValueError("Ambiguous mapping; confirm distinct columns")
            detected[key] = target
            if isinstance(value, str) and value.startswith("="):
                raise ValueError("Formulas are not catalog facts")
            normalized[target] = value
        if isinstance(normalized.get("specs"), str):
            normalized["specs"] = json.loads(normalized["specs"])
        for optional in ("price", "currency", "supplier_sku", "availability", "url"):
            if normalized.get(optional) == "":
                normalized[optional] = None
        parsed = Product.model_validate(normalized).model_dump(mode="json")
        if parsed["price"] is not None and not parsed["currency"]:
            raise ValueError("A supplied price requires currency")
        if parsed["source_id"] in seen:
            raise ValueError("Duplicate source identifier")
        seen.add(parsed["source_id"])
        output.append(parsed)
    return output, detected


def group_products(rows):
    grouped = {}
    for row in rows:
        key = identity(row)
        if key not in grouped:
            grouped[key] = {"id": key, "data": row, "offers": []}
        grouped[key]["offers"].append(
            {
                k: row[k]
                for k in (
                    "source_id",
                    "supplier",
                    "supplier_sku",
                    "price",
                    "currency",
                    "availability",
                    "url",
                )
            }
        )
    return list(grouped.values())


def compatibility(query, product):
    conflicts, missing = [], []
    for key, required in query.get("specs", {}).items():
        actual = product.get("specs", {}).get(key)
        if actual is None:
            missing.append(key)
        elif str(actual).casefold() != str(required).casefold():
            conflicts.append(
                {"attribute": key, "requested": required, "catalog": actual}
            )
    if query.get("category") and product.get("category") != query["category"]:
        conflicts.append(
            {
                "attribute": "category",
                "requested": query["category"],
                "catalog": product.get("category"),
            }
        )
    if product.get("status") != "active":
        conflicts.append({"attribute": "status", "catalog": product.get("status")})
    exact = bool(
        query.get("mpn")
        and comparison(query["mpn"]) == comparison(product["mpn"])
        and query.get("manufacturer")
        and manufacturer(query["manufacturer"]) == manufacturer(product["manufacturer"])
    )
    if conflicts:
        status = "incompatible"
    elif missing:
        status = "insufficient_information"
    elif exact:
        status = "exact"
    elif query.get("specs") and query.get("category"):
        status = "compatible_alternative"
    else:
        status = "possible_alternative"
    return {
        "status": status,
        "exact_identity": exact,
        "conflicts": conflicts,
        "missing": missing,
    }


def fuse(channels, limit=20):
    merged = {}
    for channel, candidates in channels.items():
        for rank, (key, score) in enumerate(candidates[:50], 1):
            candidate = merged.setdefault(key, {"id": key, "score": 0, "channels": {}})
            candidate["score"] += 1 / (60 + rank)
            candidate["channels"][channel] = {"score": float(score), "rank": rank}
    return sorted(
        merged.values(),
        key=lambda c: (-int("exact" in c["channels"]), -c["score"], c["id"]),
    )[:limit]
