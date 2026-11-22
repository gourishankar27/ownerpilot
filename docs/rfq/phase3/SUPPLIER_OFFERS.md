# Local supplier offers and provenance

The production-supported adapter is the authorized local catalog/attestation store. It performs no scraping, distributor API call or supplier communication. Source URLs are retained as evidence strings and never fetched by tools.

Imported Phase 2 offers remain unchanged. Their supplier, SKU, price, currency, source ID, source fingerprint and catalog version are displayed as imported catalog metadata. Ingestion time is not supplier observation time. Imported prices do not automatically become a current approved quote basis.

Authorized reviewers supplement facts through append-only `supplier_offer_attestations`, tied to a current authoritative selection resolution. Inputs include supplier/SKU, decimal price/currency, each/pack price basis, pack size, minimum units, up to 20 quantity breaks, availability, optional stock units/statement, optional lead time/effective date/source URL, source observation date, valid-through date and mandatory source reference. Actor/time/reason and product/catalog/source fingerprints are captured by the backend. A database trigger prevents updates/deletes.

These are explicitly **user-attested** commercial facts. They are not relabeled as a supplier-verified feed. Unknown inputs remain null. Optional stock/effective-date fields are API-supported; the initial form exposes the main commercial fields and one quantity-break row. The API supports additional break tiers. No source stock level, lead time, discount, tax or shipping is invented.

Freshness uses an explicit UTC calendar date, consistently in API/worker: unavailable; not-yet-effective; conflicting future observation; expired validity; unknown missing observation/validity; conflicting inverted dates; or current according to documented attested validity. No arbitrary freshness age is inferred from import time. A current attestation still means source-validity evidence, not live stock confirmation.

Changed offers use `supersedes_id`, same resolution and workspace only. Older evidence remains immutable. A selected superseded offer is blocked. Conflicting active commercial attestations for the same supplier/SKU require explicit supersession; no newest-price heuristic resolves them. Identical active facts can coexist as duplicate evidence. Any new attestation changes the source fingerprint set and requires quote recalculation/review before approval.

Comparisons group by currency, price basis and pack size, preserving unknowns/freshness. A low base price is not automatically the best valid offer. Deterministic purchasing calculations apply MOQ, packs, breaks, available attested stock and the declared surplus policy before calculating a quote.

Superseded or conflicting attestations carry an explicit commercial-review state. The research tools retain that warning; the comparator excludes those entries and lists the reason. The quote form labels and disables them for new choices, while immutable historical evidence remains inspectable. Date-based freshness alone cannot make a superseded commercial revision eligible.
