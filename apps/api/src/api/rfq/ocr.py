"""Bounded local OCR with real TSV geometry; no identifier character correction."""

from __future__ import annotations

import csv
from functools import lru_cache
import io
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

from PIL import Image, ImageOps, ImageDraw

from .config import settings
from .contracts import Block, Location
from .storage import DocumentError

OCR_VERSION = "tesseract-geometry/2.1"
LABELS = {
    "line": "line_number",
    "manufacturer": "manufacturer",
    "mpn": "mpn",
    "description": "description",
    "qty": "quantity",
    "quantity": "quantity",
    "uom": "unit",
    "unit": "unit",
    "sku": "requested_sku",
    "price": "requested_unit_price",
}


@lru_cache(maxsize=4)
def engine_version(command: str) -> str:
    if not shutil.which(command):
        raise DocumentError(
            "OCR runtime unavailable. Install Tesseract or use the RFQ worker container."
        )
    try:
        value = subprocess.run(
            [command, "--version"], capture_output=True, timeout=3, check=True
        )
        return value.stdout.decode(errors="replace").splitlines()[0][:120]
    except (OSError, subprocess.SubprocessError) as exc:
        raise DocumentError("OCR runtime could not be started.") from exc


def deskew_angle(image: Image.Image) -> float:
    """Projection-energy search, bounded ±5 degrees; measured heuristic, not confidence."""
    sample = ImageOps.invert(image.convert("L"))
    sample.thumbnail((700, 700))

    def score(angle):
        rotated = sample.rotate(angle, resample=Image.Resampling.BILINEAR, fillcolor=0)
        values = list(
            rotated.resize(
                (1, rotated.height), Image.Resampling.BOX
            ).get_flattened_data()
        )
        return sum((a - b) ** 2 for a, b in zip(values, values[1:]))

    base = score(0)
    best = max((score(angle / 2), angle / 2) for angle in range(-10, 11))
    return best[1] if best[0] > base * 1.08 else 0.0


def remove_ruled_grid(image):
    """Remove long intersecting rules only after observing a multi-row, multi-column grid."""
    gray = image.convert("L")
    dark = ImageOps.invert(gray.point(lambda value: 255 if value > 130 else 0))
    row_values = list(
        dark.resize((1, dark.height), Image.Resampling.BOX).get_flattened_data()
    )
    ys = [i for i, v in enumerate(row_values) if v > 70]

    def clusters(values):
        groups = []
        for value in values:
            if groups and value <= groups[-1][-1] + 2:
                groups[-1].append(value)
            else:
                groups.append([value])
        return groups

    horizontal = clusters(ys)
    if len(horizontal) < 3:
        return image, {}
    top = horizontal[0][0]
    bottom = horizontal[-1][-1]
    strip = dark.crop((0, top, dark.width, bottom + 1))
    xs = [
        i
        for i, v in enumerate(
            strip.resize((strip.width, 1), Image.Resampling.BOX).get_flattened_data()
        )
        if v > 140
    ]
    vertical = clusters(xs)
    if len(vertical) < 3:
        return image, {}
    cleaned = gray.copy()
    draw = ImageDraw.Draw(cleaned)
    left = vertical[0][0]
    right = vertical[-1][-1]
    for group in horizontal:
        draw.rectangle((left - 1, group[0] - 1, right + 1, group[-1] + 1), fill=255)
    for group in vertical:
        draw.rectangle((group[0] - 1, top - 1, group[-1] + 1, bottom + 1), fill=255)
    return cleaned, {
        "horizontal_rules": len(horizontal),
        "vertical_rules": len(vertical),
        "bbox": [left, top, right, bottom],
    }


def original_box(box, size, angle: float, dpi: int):
    """Inverse of PIL rotate(angle, expand=False), PDF points from top-left origin."""
    x0, y0, x1, y1 = box
    w, h = size
    c = math.cos(math.radians(angle))
    s = math.sin(math.radians(angle))
    points = [
        (
            c * (x - w / 2) - s * (y - h / 2) + w / 2,
            s * (x - w / 2) + c * (y - h / 2) + h / 2,
        )
        for x, y in [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]
    ]
    return [
        round(max(0, min(w, min(p[0] for p in points))) * 72 / dpi, 3),
        round(max(0, min(h, min(p[1] for p in points))) * 72 / dpi, 3),
        round(max(0, min(w, max(p[0] for p in points))) * 72 / dpi, 3),
        round(max(0, min(h, max(p[1] for p in points))) * 72 / dpi, 3),
    ]


def read_tsv(text: str):
    words = []
    try:
        for row in csv.DictReader(
            io.StringIO(text), delimiter="\t", quoting=csv.QUOTE_NONE
        ):
            if row.get("level") != "5" or not row.get("text", "").strip():
                continue
            x, y, w, h = [int(row[k]) for k in ("left", "top", "width", "height")]
            confidence = float(row["conf"])
            if w <= 0 or h <= 0 or x < 0 or y < 0:
                raise ValueError
            words.append(
                {
                    "text": row["text"][:500],
                    "box": [x, y, x + w, y + h],
                    "confidence": confidence,
                    "line": (row["block_num"], row["par_num"], row["line_num"]),
                }
            )
            if len(words) > settings().ocr_max_words:
                raise DocumentError("OCR word metadata limit exceeded.")
    except (ValueError, KeyError, TypeError) as exc:
        raise DocumentError("Invalid OCR geometry response.") from exc
    return words


def union_box(words):
    return [
        min(w["box"][0] for w in words),
        min(w["box"][1] for w in words),
        max(w["box"][2] for w in words),
        max(w["box"][3] for w in words),
    ]


def row_groups(words):
    rows = []
    for word in sorted(
        words, key=lambda w: ((w["box"][1] + w["box"][3]) / 2, w["box"][0])
    ):
        center = (word["box"][1] + word["box"][3]) / 2
        existing = next(
            (
                row
                for row in reversed(rows[-3:])
                if abs(center - row["y"])
                <= max(3, (word["box"][3] - word["box"][1]) * 0.55)
            ),
            None,
        )
        if existing:
            existing["words"].append(word)
        else:
            rows.append({"y": center, "words": [word]})
    return [sorted(row["words"], key=lambda w: w["box"][0]) for row in rows]


def ocr_page(image: Image.Image, page: int, strategy: str, dpi: int):
    cfg = settings()
    started = time.perf_counter()
    if (
        image.width < 10
        or image.height < 10
        or image.width * image.height > cfg.ocr_max_pixels
    ):
        raise DocumentError(
            "PDF page exceeds OCR pixel limit or has invalid dimensions."
        )
    if not shutil.which(cfg.ocr_command):
        raise DocumentError(
            "OCR runtime unavailable. Install Tesseract or use the RFQ worker container."
        )
    version = engine_version(cfg.ocr_command)
    enhanced = strategy in {"enhanced-v2", "combined-v2"}
    targeted = strategy in {"targeted-v2", "combined-v2"}
    operations = []
    grid = {}
    angle = 0.0
    working = image
    if enhanced:
        working = ImageOps.autocontrast(image.convert("L"))
        operations = ["grayscale", "autocontrast"]
        angle = deskew_angle(working)
        if angle:
            working = working.rotate(
                angle, resample=Image.Resampling.BICUBIC, fillcolor=255
            )
            operations.append(f"deskew:{angle}")
        working, grid = remove_ruled_grid(working)
        if grid:
            operations.append("remove_observed_grid_rules")
    passes = 0

    def run(source, psm, tsv=True):
        nonlocal passes
        remaining = cfg.ocr_timeout - (time.perf_counter() - started)
        if passes >= cfg.ocr_max_passes or remaining <= 0:
            raise DocumentError("OCR page pass/time budget exceeded.")
        passes += 1
        with tempfile.TemporaryDirectory(prefix="rfq-ocr-") as temp:
            path = Path(temp) / "page.png"
            source.save(path)
            args = [
                cfg.ocr_command,
                str(path),
                "stdout",
                "-l",
                cfg.ocr_language,
                "--psm",
                str(psm),
            ]
            if tsv:
                args.append("tsv")
            try:
                completed = subprocess.run(
                    args, capture_output=True, timeout=remaining, check=False
                )
            except subprocess.TimeoutExpired as exc:
                raise DocumentError(
                    "OCR page timed out. Reduce page complexity or resolution."
                ) from exc
            if completed.returncode:
                raise DocumentError(
                    "OCR failed. Check language data and image quality."
                )
            if len(completed.stdout) > 4 * 1024 * 1024:
                raise DocumentError("OCR response byte limit exceeded.")
            return completed.stdout.decode("utf-8", errors="replace")

    words = read_tsv(run(working, 6 if enhanced else 3))
    blocks = []
    columns = []
    boundaries = []
    regions = 0
    disagreements = 0
    for row_number, row in enumerate(row_groups(words), 1):
        box = union_box(row)
        if grid and (box[1] > grid["bbox"][3] or box[3] < grid["bbox"][1]):
            columns = []
            boundaries = []
        identified = [
            (w, LABELS.get(re.sub(r"[^a-z]", "", w["text"].lower()))) for w in row
        ]
        identified = [(w, name) for w, name in identified if name]
        names = {name for _, name in identified}
        if "description" in names and "quantity" in names and len(names) >= 3:
            columns = [name for _, name in identified]
            # Geometry is inferred from observed header positions, never invented boxes.
            separators = [
                (w["box"][0] + w["box"][2]) / 2 for w in row if w["text"] == "|"
            ]
            if len(separators) == len(columns) - 1:
                boundaries = [0] + separators + [working.width]
            else:
                boundaries = (
                    [0]
                    + [
                        (a[0]["box"][2] + b[0]["box"][0]) / 2
                        for a, b in zip(identified, identified[1:])
                    ]
                    + [working.width]
                )
        cell_words = []
        if columns:
            for left, right in zip(boundaries, boundaries[1:]):
                cell_words.append(
                    [
                        w
                        for w in row
                        if left <= (w["box"][0] + w["box"][2]) / 2 < right
                        and w["text"] != "|"
                    ]
                )
        raw_text = " ".join(w["text"] for w in row)
        cells = (
            [" ".join(w["text"] for w in cell) for cell in cell_words]
            if columns
            else None
        )
        locations = []
        cell_metadata = []
        for index, cell in enumerate(cell_words):
            actual = union_box(cell) if cell else None
            locations.append(
                Location(
                    page=page,
                    row=row_number,
                    column=chr(65 + index),
                    bbox=original_box(actual, working.size, angle, dpi)
                    if actual
                    else None,
                )
            )
            readings = []
            confidence = (
                sum(w["confidence"] for w in cell) / len(cell) if cell else None
            )
            raw = cells[index]
            if (
                targeted
                and columns[index] == "mpn"
                and cell
                and "mpn" not in names
                and regions < cfg.ocr_max_regions
                and passes < cfg.ocr_max_passes
            ):
                left, right = boundaries[index : index + 2]
                crop = working.crop(
                    (
                        max(0, int(left) + 2),
                        max(0, box[1] - 4),
                        min(working.width, int(right) - 2),
                        min(working.height, box[3] + 4),
                    )
                )
                alternative = run(crop, 7, False).strip()
                regions += 1
                if alternative and alternative != raw:
                    readings.append(alternative)
                    disagreements += 1
            cell_metadata.append(
                {
                    "raw": raw,
                    "confidence": confidence,
                    "alternatives": readings,
                    "disagreement": bool(readings),
                }
            )
        blocks.append(
            Block(
                id=f"page:{page}:row:{row_number}",
                text=" | ".join(cells) if cells else raw_text,
                location=Location(
                    page=page,
                    row=row_number,
                    bbox=original_box(box, working.size, angle, dpi),
                ),
                method="tesseract",
                cells=cells,
                cell_locations=locations or None,
                metadata={
                    "raw_ocr": raw_text,
                    "cells": cell_metadata,
                    "words": [
                        {
                            "text": w["text"],
                            "bbox": original_box(w["box"], working.size, angle, dpi),
                            "confidence": w["confidence"],
                        }
                        for w in row
                    ],
                    "coordinate_convention": "PDF points; original page top-left origin; inverse deskew bounding rectangle",
                    "table_columns": columns.copy(),
                    "ocr_version": OCR_VERSION,
                    "source_eligible": True,
                },
            )
        )
    return blocks, {
        "page": page,
        "engine": version,
        "configuration": OCR_VERSION,
        "strategy": strategy,
        "dpi": dpi,
        "operations": operations,
        "deskew_angle": angle,
        "passes": passes,
        "regions": regions,
        "disagreements": disagreements,
        "duration_ms": (time.perf_counter() - started) * 1000,
        "orientation": "No 90/180-degree correction inferred; unresolved orientation requires review",
    }
