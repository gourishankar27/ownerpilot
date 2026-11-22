"""Closed request contracts. Workspace and actor always come from authentication."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from .finance import Closed, Commercial, QuotePolicy


class ResolutionInput(Closed):
    expected_revision: int = Field(ge=0, strict=True)
    run_id: UUID
    decision: Literal["select", "no_match"]
    product_id: str | None = Field(default=None, max_length=160)
    version_id: UUID | None = None
    alternative_attested: bool = Field(default=False, strict=True)
    reason: str = Field(min_length=5, max_length=1000)


class AttestationInput(Closed):
    resolution_id: UUID
    commercial: Commercial
    source_offer_id: str | None = Field(default=None, max_length=160)
    supersedes_id: UUID | None = None
    reason: str = Field(min_length=5, max_length=1000)


class QuoteInput(Closed):
    policy: QuotePolicy
    offer_choices: dict[str, UUID] = Field(default_factory=dict, max_length=100)
    reason: str = Field(min_length=5, max_length=1000)


class QuoteEdit(QuoteInput):
    revision: int = Field(ge=1, strict=True)


class QuoteDecision(Closed):
    revision: int = Field(ge=1, strict=True)
    reason: str = Field(min_length=5, max_length=1000)
    inputs_reviewed: bool = Field(default=False, strict=True)


class ResearchInput(Closed):
    revision: int = Field(ge=0, strict=True)
    quote_id: UUID | None = None
    idempotency_key: str = Field(
        min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9-]+$"
    )


class Empty(Closed):
    pass


class Line(Closed):
    line_id: UUID


class Search(Line):
    method: Literal["exact", "bm25", "sql", "exact_bm25", "reranked"] = "exact_bm25"


class Offer(Closed):
    offer_id: UUID


class Claim(Closed):
    receipt_id: UUID
    pointer: str = Field(max_length=300, pattern=r"^/")
    value: str | int | bool | None


class ResearchSummary(Closed):
    claims: list[Claim] = Field(max_length=20)
