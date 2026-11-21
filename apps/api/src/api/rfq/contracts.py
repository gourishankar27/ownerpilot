from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator

SCHEMA_VERSION = "rfq.v1"
HEADER_FIELDS = (
    "external_rfq_number",
    "customer_name",
    "request_date",
    "submission_deadline",
    "contact_name",
    "contact_email",
    "shipping_address",
    "billing_address",
    "currency",
    "delivery_requirements",
    "general_instructions",
)
ITEM_FIELDS = (
    "line_number",
    "manufacturer",
    "mpn",
    "customer_part_number",
    "requested_sku",
    "description",
    "quantity",
    "unit",
    "required_delivery_date",
    "requested_unit_price",
    "currency",
    "alternatives_allowed",
    "specifications",
    "special_requirements",
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Location(StrictModel):
    page: int | None = None
    sheet: str | None = None
    row: int | None = None
    column: str | None = None
    start: int | None = None
    end: int | None = None
    bbox: list[float] | None = None


class Block(StrictModel):
    id: str
    text: str
    location: Location
    method: str
    cells: list[str] | None = None
    cell_locations: list[Location] | None = None
    metadata: dict = Field(default_factory=dict)


class ParsedDocument(StrictModel):
    document_id: str
    fingerprint: str
    parser: str
    blocks: list[Block]
    warnings: list[str] = Field(default_factory=list)
    pages: int = 0
    ocr_pages: list[int] = Field(default_factory=list)
    duration_ms: float = 0
    ocr_ms: float = 0
    metadata: dict = Field(default_factory=dict)


class Evidence(StrictModel):
    document_id: str
    fingerprint: str
    block_id: str
    location: Location
    excerpt: str
    method: str
    identity: str
    verified: bool
    source_occurrence: bool | None = None
    row_association: Literal["verified", "unverified", "unknown"] = "unknown"
    column_association: Literal["verified", "unverified", "unknown"] = "unknown"
    association_reason: str | None = None
    raw_ocr: str | None = None
    alternatives: list[str] = Field(default_factory=list)
    ocr_confidence: float | None = None
    source_eligible: bool = True
    extracted_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class FieldValue(StrictModel):
    raw: str | None = None
    value: str | None = None
    comparison: str | None = None
    status: Literal[
        "validated",
        "missing",
        "ambiguous",
        "conflicting",
        "unverified",
        "requires_review",
    ] = "missing"
    issues: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    corrected: bool = False


class LineItem(StrictModel):
    id: str
    fields: dict[str, FieldValue]
    extraction_method: str
    review_status: Literal["pending", "reviewed", "invalid"] = "pending"
    warnings: list[str] = Field(default_factory=list)


class Extraction(StrictModel):
    schema_version: Literal["rfq.v1"] = SCHEMA_VERSION
    header: dict[str, FieldValue] = Field(default_factory=dict)
    items: list[LineItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class ProposedField(StrictModel):
    value: str | None
    block_id: str | None
    excerpt: str | None


# Explicit properties keep the generation schema closed to arbitrary field names.

ProposedHeader = create_model(
    "ProposedHeader",
    __base__=StrictModel,
    **{name: (ProposedField | None, None) for name in HEADER_FIELDS},
)
ProposedItem = create_model(
    "ProposedItem",
    __base__=StrictModel,
    **{name: (ProposedField | None, None) for name in ITEM_FIELDS},
)


class Proposal(StrictModel):
    header: ProposedHeader  # type: ignore[valid-type]
    items: list[ProposedItem] = Field(max_length=250)  # type: ignore[valid-type]


CompactValues = create_model(
    "CompactValues",
    __base__=StrictModel,
    **{name: (str | None, None) for name in ITEM_FIELDS},
)


class CompactRow(StrictModel):
    source: str = Field(max_length=300)
    values: CompactValues  # type: ignore[valid-type]


class CompactHeader(StrictModel):
    field: Literal[*HEADER_FIELDS]
    value: str = Field(max_length=4000)
    source: str = Field(max_length=300)


class CompactProposal(StrictModel):
    header: list[CompactHeader] = Field(default_factory=list, max_length=30)
    items: list[CompactRow] = Field(max_length=250)


class CreateRfq(StrictModel):
    title: str = Field(min_length=1, max_length=160)
    customer_name: str | None = Field(None, max_length=300)

    @field_validator("title")
    @classmethod
    def nonblank_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("RFQ title cannot be blank.")
        return value.strip()


class RevisionRequest(StrictModel):
    revision: int = Field(ge=0)
    reason: str = Field(default="", max_length=1000)


class ProcessRequest(RevisionRequest):
    mode: Literal["deterministic", "llm", "hybrid"] = "hybrid"
    policy: Literal["phase1", "selective-v2"] = "selective-v2"


class EditRequest(RevisionRequest):
    fields: dict[str, str | None] = Field(default_factory=dict, max_length=20)
    review_status: Literal["pending", "reviewed", "invalid"] = "reviewed"


class RfqDto(BaseModel):
    schema_version: Literal["rfq.v1"] = SCHEMA_VERSION
    id: UUID
    workspace_id: UUID
    title: str
    status: Literal["draft", "awaiting_review", "approved"]
    revision: int
    header: dict[str, FieldValue]
    current_run_id: UUID | None
    created_by: str
    approved_by: str | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DocumentDto(BaseModel):
    id: UUID
    rfq_id: UUID
    workspace_id: UUID
    filename: str
    extension: str
    fingerprint: str
    size_bytes: int
    status: str
    uploaded_by: str
    created_at: datetime


class JobDto(BaseModel):
    id: UUID
    rfq_id: UUID
    workspace_id: UUID
    state: Literal[
        "queued",
        "validating",
        "parsing",
        "extracting",
        "validating_results",
        "awaiting_review",
        "failed",
        "cancelled",
    ]
    mode: Literal["deterministic", "llm", "hybrid"]
    base_revision: int
    attempts: int
    completed_documents: int
    total_documents: int
    stage_started_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    retryable: bool
    error_category: str | None
    error_message: str | None
    requested_by: str
    created_at: datetime
    dispatch_warning: str | None = None
    configuration: dict = Field(default_factory=dict)


class RunDto(BaseModel):
    id: UUID
    job_id: UUID
    schema_version: str
    metadata: dict
    created_at: datetime


class DetailDto(RfqDto):
    items: list[LineItem]
    documents: list[DocumentDto]
    jobs: list[JobDto]
    runs: list[RunDto]
    approval_issues: list[str]
    role: str


class ListDto(BaseModel):
    items: list[RfqDto]
    total: int
    counts: dict[str, int]
    jobs: dict[str, int]
    limit: int
    offset: int


class AuditDto(BaseModel):
    id: int
    rfq_id: UUID
    workspace_id: UUID
    actor: str
    event: str
    run_id: UUID | None
    details: dict
    created_at: datetime
