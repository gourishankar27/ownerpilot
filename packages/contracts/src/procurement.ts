import type { CatalogCandidate } from "./catalog";
import type { RfqField } from "./rfq";

export interface CommercialOffer {
  supplier: string;
  supplier_sku?: string | null;
  price: string | null;
  currency: string | null;
  price_basis: "each" | "pack" | null;
  pack_size: number | null;
  minimum_units: string | null;
  breaks: { minimum_units: string; price: string }[];
  availability: "available" | "unavailable" | "unknown";
  lead_time_days?: number | null;
  observed_on: string | null;
  valid_until: string | null;
  source_reference: string;
}
export interface OfferAttestation {
  commercial_review_state?: "superseded" | "conflicting_information";
  id: string;
  resolution_id: string;
  actor: string;
  reason: string;
  created_at: string;
  freshness: string;
  data: {
    commercial: CommercialOffer;
    source_fingerprint: string;
    product_id: string;
    version_id: string;
  };
}
export interface SelectionResolution {
  id: string;
  revision: number;
  actor: string;
  reason: string;
  data: {
    product_id?: string;
    version_id?: string;
    decision: string;
    compatibility?: { status: string };
    product?: { name: string; mpn: string; manufacturer: string };
    sources?: { version_id: string; content_hash: string }[];
  };
}
export interface ProcurementLine {
  line_id: string;
  quantity: string | null;
  unit: string | null;
  fields: Record<string, RfqField>;
  selection: {
    state: string;
    revision: number;
    resolution: SelectionResolution | null;
    current_run_id: string | null;
    candidates: CatalogCandidate[];
  };
  offers: {
    imported: Record<string, unknown>[];
    attestations: OfferAttestation[];
  };
}
export interface ProcurementSnapshot {
  rfq_id: string;
  revision: number;
  lines: ProcurementLine[];
}
export interface QuotePolicy {
  currency: "USD" | "EUR" | "GBP" | "INR" | "JPY";
  shipping: string | null;
  tax_rate: string | null;
  tax_basis: "subtotal" | "subtotal_plus_shipping" | null;
  valid_until: string | null;
  pricing: {
    mode: "markup" | "margin";
    rate: string;
    discount: string;
    surplus: "allocate_purchase_cost" | "bill_purchased" | null;
  };
}
export interface QuoteCalculation {
  version: string;
  currency: string;
  complete: boolean;
  subtotal: string | null;
  shipping: string | null;
  tax: string | null;
  grand_total: string | null;
  issues: string[];
  lines: {
    line_id: string;
    requested_quantity: string | null;
    purchased_quantity?: string;
    billable_quantity?: string;
    purchase_cost?: string;
    selling_unit_price?: string;
    discount_amount?: string;
    amount: string | null;
    price_source?: string;
    issues: string[];
  }[];
}
export interface ProcurementQuote {
  id: string;
  revision: number;
  state: string;
  snapshot: ProcurementSnapshot;
  policy: QuotePolicy;
  offer_choices: Record<string, string>;
  calculation: QuoteCalculation;
  prepared_by: string;
  approved_by: string | null;
  approved_at: string | null;
}
export interface ResearchRun {
  id: string;
  state: string;
  turns: number;
  attempts: number;
  repair_attempts?: number;
  diagnostics?: { stage?: string; recovered?: boolean; error_code?: string };
  error: string | null;
  metadata: {
    model: string;
    digest: string;
    prompt_version: string;
    claim_schema?: string;
    verifier_version?: string;
  };
  result?: {
    protocol?: string;
    complete?: boolean;
    partial?: boolean;
    quote_ready?: boolean;
    repaired?: boolean;
    invalid_citations?: { code: string; pointer?: string }[];
    coverage?: {
      complete: boolean;
      quote_issues: string[];
      lines: {
        line_id: string;
        complete: boolean;
        selection_state: string;
        missing_tools: string[];
        missing_citations: unknown[];
        unknowns: { field: string; state: string; offer_id?: string }[];
        commercial_review: { offer_id: string; state: string }[];
      }[];
    };
    claims: {
      receipt_id: string;
      pointer: string;
      value: string | number | boolean | null;
      field_type?: string;
      line_id?: string;
      product_id?: string | null;
      offer_id?: string | null;
      catalog_version?: string | null;
      source_fingerprint?: string;
      data_class?: string;
    }[];
    limitations: string[];
  } | null;
}
export interface ToolReceipt {
  id: string;
  ordinal: number;
  tool: string;
  status: string;
  policy: string;
  duration_ms: string | number;
  arguments: Record<string, unknown>;
  result: unknown;
  error: string | null;
}
