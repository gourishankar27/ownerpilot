export interface CatalogSummary {
  id: string;
  name: string;
  active_version: string | null;
  state: string;
  metadata: Record<string, unknown>;
}
export interface CatalogPreview {
  id: string;
  fingerprint: string;
  state: string;
  counts: Record<string, unknown>;
  sample: unknown[];
  specification: unknown;
}
export interface CatalogCandidate {
  id: string;
  product: {
    name: string;
    manufacturer: string;
    mpn: string;
    specs: Record<string, unknown>;
  };
  offers: unknown[];
  sources: unknown[];
  channels: unknown;
  compatibility: { status: string; conflicts: unknown[]; missing: string[] };
}
export interface CatalogMatch {
  id: string;
  outcome: string;
  query: unknown;
  versions: string[];
  candidates: CatalogCandidate[];
  reviews?: unknown[];
}
