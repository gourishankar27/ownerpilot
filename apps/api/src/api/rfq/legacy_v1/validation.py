from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import NAMESPACE_URL, uuid5

import pycountry

from .contracts import Evidence, FieldValue, LineItem

UNITS = {
    "ea": "EA",
    "each": "EA",
    "pcs": "EA",
    "pc": "EA",
    "units": "EA",
    "unit": "EA",
    "box": "BOX",
    "pack": "PACK",
    "set": "SET",
    "license": "LICENSE",
    "licenses": "LICENSE",
    "m": "M",
    "kg": "KG",
}
CRITICAL = ("description", "quantity", "unit")


def normalize(
    name: str,
    raw: str | None,
    evidence: list[Evidence] | None = None,
    corrected: bool = False,
) -> FieldValue:
    field = FieldValue(
        raw=raw,
        value=raw.strip() if raw is not None else None,
        evidence=evidence or [],
        corrected=corrected,
    )
    if not field.value:
        field.value = None
        return field
    field.status = (
        "validated"
        if corrected or (field.evidence and all(e.verified for e in field.evidence))
        else "unverified"
    )
    value = field.value
    if len(value) > 4000:
        field.issues.append("Value exceeds the field length limit.")
    if name in ("quantity", "requested_unit_price"):
        # Only unambiguous English grouping; 1,5 and ranges remain unresolved.
        number = (
            value.replace(",", "")
            if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", value)
            else value
        )
        try:
            if not re.fullmatch(r"[+-]?\d+(\.\d+)?", number):
                raise InvalidOperation
            parsed = Decimal(number)
            if (
                not parsed.is_finite()
                or parsed < 0
                or (name == "quantity" and parsed == 0)
                or parsed >= Decimal("1e14")
                or -parsed.as_tuple().exponent > 6
            ):
                raise InvalidOperation
            field.value = format(parsed, "f")
        except InvalidOperation:
            field.status = "ambiguous"
            field.issues.append(
                "Enter an explicit positive quantity or non-negative price using at most six decimal places."
            )
    elif name == "unit":
        normalized = UNITS.get(value.lower(), value.upper())
        field.value = normalized
        if normalized not in set(UNITS.values()):
            field.issues.append("Unknown unit; reviewer must confirm a supported unit.")
    elif name in ("request_date", "submission_deadline", "required_delivery_date"):
        try:
            field.value = date.fromisoformat(value).isoformat()
        except ValueError:
            field.status = "ambiguous"
            field.issues.append("Date must be unambiguous ISO YYYY-MM-DD.")
    elif name == "contact_email" and not re.fullmatch(
        r"[^\s@]+@[^\s@]+\.[^\s@]+", value
    ):
        field.issues.append("Invalid email address.")
    elif name == "currency":
        field.value = value.upper()
        if not pycountry.currencies.get(alpha_3=field.value):
            field.issues.append(
                "Use an ISO 4217 currency code; currency symbols are ambiguous."
            )
    elif name == "alternatives_allowed":
        aliases = {"yes": "true", "no": "false", "true": "true", "false": "false"}
        if value.lower() in aliases:
            field.value = aliases[value.lower()]
        else:
            field.issues.append(
                "Alternative allowance must be explicitly true or false."
            )
    elif name in ("shipping_address", "billing_address") and len(value) < 8:
        field.issues.append("Address is incomplete; confirm it from the source.")
    elif name in ("mpn", "requested_sku", "customer_part_number"):
        if len(value) > 160 or any(ord(c) < 32 for c in value):
            field.issues.append(
                "Identifier contains invalid characters or exceeds 160 characters."
            )
        # Preserve significant punctuation and zeros; comparison only folds case.
        field.comparison = value.casefold()
    if field.issues and field.status == "validated":
        field.status = "requires_review"
    return field


def stable_item(document_id: str, block_id: str, ordinal: int = 0) -> str:
    return str(uuid5(NAMESPACE_URL, f"rfq:{document_id}:{block_id}:{ordinal}"))


def mark_duplicates(items: list[LineItem]) -> None:
    seen: dict[tuple, LineItem] = {}
    for item in items:
        key = tuple(
            item.fields.get(k, FieldValue()).value
            for k in (
                "manufacturer",
                "mpn",
                "description",
                "quantity",
                "unit",
                "required_delivery_date",
                "specifications",
                "special_requirements",
            )
        )
        if key in seen:
            warning = (
                "Possible duplicate source row; retained separately for human review."
            )
            for row in (seen[key], item):
                if warning not in row.warnings:
                    row.warnings.append(warning)
        else:
            seen[key] = item


def approval_issues(header: dict[str, FieldValue], items: list[LineItem]) -> list[str]:
    issues = []
    active = [i for i in items if i.review_status != "invalid"]
    if not active:
        issues.append("At least one valid line item is required.")
    for item in active:
        if item.review_status != "reviewed":
            issues.append(f"Line {item.id} has not been reviewed.")
        for name in CRITICAL:
            if item.fields.get(name, FieldValue()).status != "validated":
                issues.append(f"Line {item.id}: resolve {name}.")
        for name, field in item.fields.items():
            if (
                field.value is not None
                or (field.raw is not None and not field.corrected)
            ) and field.status != "validated":
                issues.append(f"Line {item.id}: resolve {name} ({field.status}).")
    for name, field in header.items():
        if (
            field.value is not None or (field.raw is not None and not field.corrected)
        ) and field.status != "validated":
            issues.append(f"Header: resolve {name} ({field.status}).")
    return issues
