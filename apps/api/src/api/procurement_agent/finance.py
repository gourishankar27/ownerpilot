"""Authoritative Decimal calculations; unknown commercial inputs never become zero."""

from datetime import date, datetime, timezone
from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_CEILING,
    ROUND_HALF_UP,
    localcontext,
)
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr

VERSION = "quote-decimal/1"
MINOR_UNITS = {"USD": 2, "EUR": 2, "GBP": 2, "INR": 2, "JPY": 0}


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PriceBreak(Closed):
    minimum_units: StrictStr = Field(max_length=40)
    price: StrictStr = Field(max_length=40)


class Commercial(Closed):
    supplier: str = Field(min_length=1, max_length=160)
    supplier_sku: str | None = Field(default=None, max_length=160)
    price: StrictStr | None = Field(default=None, max_length=40)
    currency: str | None = Field(default=None, max_length=3)
    price_basis: Literal["each", "pack"] | None = None
    pack_size: int | None = Field(default=None, ge=1, le=1000000, strict=True)
    minimum_units: StrictStr | None = Field(default=None, max_length=40)
    breaks: list[PriceBreak] = Field(default_factory=list, max_length=20)
    availability: Literal["available", "unavailable", "unknown"] = "unknown"
    lead_time_days: int | None = Field(default=None, ge=0, le=3650, strict=True)
    observed_on: date | None = None
    valid_until: date | None = None
    source_reference: str = Field(min_length=1, max_length=1000)
    source_url: str | None = Field(default=None, max_length=1000)
    stock_units: StrictStr | None = Field(default=None, max_length=40)
    availability_statement: str | None = Field(default=None, max_length=1000)
    effective_on: date | None = None


class Pricing(Closed):
    mode: Literal["markup", "margin"]
    rate: StrictStr = Field(max_length=40)
    discount: StrictStr = Field(max_length=40)
    surplus: Literal["allocate_purchase_cost", "bill_purchased"] | None = None


class QuotePolicy(Closed):
    currency: Literal["USD", "EUR", "GBP", "INR", "JPY"]
    shipping: StrictStr | None = Field(default=None, max_length=40)
    tax_rate: StrictStr | None = Field(default=None, max_length=40)
    tax_basis: Literal["subtotal", "subtotal_plus_shipping"] | None = None
    valid_until: date | None = None
    pricing: Pricing


def number(raw, *, positive=False, maximum="1000000000000"):
    if not isinstance(raw, (str, Decimal)) or isinstance(raw, bool):
        raise ValueError("Financial inputs must be decimal strings")
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError):
        raise ValueError("Invalid decimal input") from None
    if (
        not value.is_finite()
        or value < 0
        or (positive and value <= 0)
        or value > Decimal(maximum)
        or len(value.as_tuple().digits) > 28
        or abs(value.as_tuple().exponent) > 12
    ):
        raise ValueError("Financial input outside supported range")
    return value


def freshness(offer: Commercial, today: date | None = None):
    today = today or datetime.now(timezone.utc).date()
    if offer.availability == "unavailable":
        return "unavailable"
    if offer.effective_on and offer.effective_on > today:
        return "not_yet_effective"
    if offer.observed_on and offer.observed_on > today:
        return "conflicting_information"
    if offer.valid_until and offer.valid_until < today:
        return "expired"
    if not offer.observed_on or not offer.valid_until:
        return "unknown_freshness"
    if offer.valid_until < offer.observed_on:
        return "conflicting_information"
    return "current_according_to_attested_validity"


def calculate(lines, policy: QuotePolicy, today: date | None = None):
    today = today or datetime.now(timezone.utc).date()
    minor = Decimal(1).scaleb(-MINOR_UNITS[policy.currency])

    def money(value):
        if not value.is_finite() or abs(value) > Decimal("1000000000000000000"):
            raise ValueError("Financial amount exceeds supported quote range")
        try:
            return value.quantize(minor, rounding=ROUND_HALF_UP)
        except InvalidOperation:
            raise ValueError(
                "Financial amount precision exceeds supported range"
            ) from None

    warnings, output = [], []
    with localcontext() as context:
        context.prec = 40
        rate = number(policy.pricing.rate, maximum="10")
        if policy.pricing.mode == "margin" and rate >= 1:
            raise ValueError("Gross margin must be below 1")
        discount = number(policy.pricing.discount, maximum="1")
        if policy.shipping is None:
            warnings.append("shipping_unresolved")
        if policy.tax_rate is None or policy.tax_basis is None:
            warnings.append("tax_policy_unresolved")
        if policy.valid_until is None or policy.valid_until < today:
            warnings.append("quote_validity_unresolved_or_expired")
        if not lines:
            warnings.append("no_quote_lines")
        subtotal = Decimal(0)
        discount_total = Decimal(0)
        for line in lines:
            issues = []
            record = {
                "line_id": line["line_id"],
                "requested_quantity": line.get("quantity"),
                "offer_id": line.get("offer_id"),
                "amount": None,
            }
            if not line.get("offer"):
                issues.append("price_and_offer_unresolved")
            else:
                offer = Commercial.model_validate(line["offer"])
                state = freshness(offer, today)
                record.update(
                    price_freshness=state,
                    cost_currency=offer.currency,
                    price_source=offer.source_reference,
                )
                if state != "current_according_to_attested_validity":
                    issues.append(state)
                if offer.availability != "available":
                    issues.append("availability_not_attested_available")
                if offer.price is None:
                    issues.append("price_unresolved")
                if offer.currency != policy.currency:
                    issues.append("currency_conversion_evidence_required")
                if (
                    offer.pack_size is None
                    or offer.minimum_units is None
                    or offer.price_basis is None
                ):
                    issues.append("purchasing_unit_conversion_unresolved")
                if (
                    policy.valid_until
                    and offer.valid_until
                    and policy.valid_until > offer.valid_until
                ):
                    issues.append("quote_outlives_offer_validity")
                if not line.get("quantity"):
                    issues.append("quantity_unresolved")
                if not issues:
                    quantity = number(
                        line["quantity"], positive=True, maximum="1000000"
                    )
                    pack = Decimal(offer.pack_size)
                    minimum = number(offer.minimum_units, maximum="1000000")
                    packs = (max(quantity, minimum) / pack).to_integral_value(
                        rounding=ROUND_CEILING
                    )
                    purchased = packs * pack
                    surplus = purchased - quantity
                    if offer.stock_units is not None and purchased > number(
                        offer.stock_units, maximum="1000000"
                    ):
                        issues.append(
                            "attested_stock_insufficient_for_purchase_quantity"
                        )
                    record.update(
                        packs=str(packs),
                        purchased_quantity=str(purchased),
                        surplus=str(surplus),
                        minimum_units=str(minimum),
                        pack_size=offer.pack_size,
                        price_basis=offer.price_basis,
                    )
                    if issues:
                        pass
                    elif surplus and policy.pricing.surplus is None:
                        issues.append("surplus_policy_requires_review")
                    else:
                        unit_price = number(offer.price)
                        chosen = None
                        eligible = []
                        for tier in offer.breaks:
                            threshold = number(
                                tier.minimum_units, positive=True, maximum="1000000"
                            )
                            tier_price = number(tier.price)
                            if threshold <= purchased:
                                eligible.append((threshold, tier_price))
                        if len({t[0] for t in eligible}) != len(eligible):
                            raise ValueError("Conflicting quantity price breaks")
                        if eligible:
                            chosen = max(eligible, key=lambda pair: pair[0])
                            unit_price = chosen[1]
                        cost = money(
                            unit_price
                            * (packs if offer.price_basis == "pack" else purchased)
                        )
                        billable = (
                            purchased
                            if policy.pricing.surplus == "bill_purchased"
                            else quantity
                        )
                        base = cost / billable
                        selling = money(
                            base * (1 + rate)
                            if policy.pricing.mode == "markup"
                            else base / (1 - rate)
                        )
                        gross = money(selling * billable)
                        deduction = money(gross * discount)
                        amount = gross - deduction
                        if amount > Decimal("1000000000000000000"):
                            raise ValueError("Quote line amount limit")
                        record.update(
                            purchase_cost=str(cost),
                            billable_quantity=str(billable),
                            selling_unit_price=str(selling),
                            gross=str(gross),
                            discount_amount=str(deduction),
                            amount=str(amount),
                            quantity_break={
                                "minimum_units": str(chosen[0]),
                                "price": str(chosen[1]),
                            }
                            if chosen
                            else None,
                        )
                        subtotal += amount
                        discount_total += deduction
            record["issues"] = issues
            output.append(record)
            warnings.extend(f"{line['line_id']}:{issue}" for issue in issues)
        total = None
        shipping = None
        tax = None
        if not warnings:
            shipping = money(number(policy.shipping))
            tax_rate = number(policy.tax_rate, maximum="1")
            tax = money(
                (
                    subtotal + shipping
                    if policy.tax_basis == "subtotal_plus_shipping"
                    else subtotal
                )
                * tax_rate
            )
            total = money(subtotal + shipping + tax)
        return {
            "version": VERSION,
            "rounding": "ROUND_HALF_UP;unit then line then tax; currency minor units",
            "currency": policy.currency,
            "policy": policy.model_dump(mode="json"),
            "lines": output,
            "subtotal": str(money(subtotal))
            if not any(r["issues"] for r in output)
            else None,
            "discount_total": str(money(discount_total))
            if not any(r["issues"] for r in output)
            else None,
            "shipping": str(shipping) if shipping is not None else None,
            "tax": str(tax) if tax is not None else None,
            "grand_total": str(total) if total is not None else None,
            "issues": warnings,
            "complete": not warnings,
        }
