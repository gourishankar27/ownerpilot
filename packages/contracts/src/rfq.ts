// Versioned RFQ wire contract. Decimal-compatible values travel as strings.
export const rfqSchemaVersion = "rfq.v1" as const;
export type RfqFieldStatus =
  | "validated"
  | "missing"
  | "ambiguous"
  | "conflicting"
  | "unverified"
  | "requires_review";
export type RfqLocation = {
  page: number | null;
  sheet: string | null;
  row: number | null;
  column: string | null;
  start: number | null;
  end: number | null;
  bbox: number[] | null;
};
export type RfqEvidence = {
  document_id: string;
  fingerprint: string;
  block_id: string;
  location: RfqLocation;
  excerpt: string;
  method: string;
  identity: string;
  verified: boolean;
  extracted_at: string;
};
export type RfqField = {
  raw: string | null;
  value: string | null;
  comparison: string | null;
  status: RfqFieldStatus;
  issues: string[];
  evidence: RfqEvidence[];
  corrected: boolean;
};
export type RfqLine = {
  id: string;
  fields: Record<string, RfqField>;
  extraction_method: string;
  review_status: "pending" | "reviewed" | "invalid";
  warnings: string[];
};
export type RfqJob = {
  id: string;
  state:
    | "queued"
    | "validating"
    | "parsing"
    | "extracting"
    | "validating_results"
    | "awaiting_review"
    | "failed"
    | "cancelled";
  mode: string;
  attempts: number;
  completed_documents: number;
  total_documents: number;
  started_at: string | null;
  finished_at: string | null;
  error_category: string | null;
  error_message: string | null;
  retryable: boolean;
  dispatch_warning?: string;
};
export type RfqDocument = {
  id: string;
  filename: string;
  fingerprint: string;
  size_bytes: number;
  status: string;
  created_at: string;
};
export type RfqSummary = {
  id: string;
  title: string;
  status: "draft" | "awaiting_review" | "approved";
  revision: number;
  created_at: string;
  updated_at: string;
  approved_by: string | null;
  approved_at: string | null;
};
export type RfqDetail = RfqSummary & {
  header: Record<string, RfqField>;
  current_run_id: string | null;
  items: RfqLine[];
  documents: RfqDocument[];
  jobs: RfqJob[];
  runs: {
    id: string;
    schema_version: string;
    metadata: Record<string, unknown>;
    created_at: string;
  }[];
  approval_issues: string[];
  role: string;
};
export type RfqList = {
  items: RfqSummary[];
  total: number;
  counts: Record<string, number>;
  jobs: Record<string, number>;
  limit: number;
  offset: number;
};
export const rfqHeaderFields = [
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
] as const;
export const rfqItemFields = [
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
] as const;
