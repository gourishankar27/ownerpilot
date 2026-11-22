# Read-only tool registry

All tools have closed Pydantic schemas with `additionalProperties=false`. UUIDs and enums are validated. No tool accepts workspace, actor, RFQ identity, revision, endpoint URL, SQL or code from the model.

| Tool | Arguments | Local implementation |
|---|---|---|
| get_approved_rfq | `{}` | Approved snapshot identity, quantities, units, descriptions |
| get_reviewed_product_selection | line_id | Current authoritative state, resolution and compatibility evidence |
| search_catalog | line_id, bounded method enum | Approved query, authorized pinned catalog version(s), exact/BM25/SQL/hybrid retrieval |
| get_product_details | line_id | Resolved canonical identity/specs/version/fingerprint |
| get_supplier_offers | line_id | Imported metadata separately from flattened user attestations; decimal strings |
| compare_supplier_offers | line_id | Base-price groups by currency, price basis and pack size; no FX |
| check_offer_freshness | offer_id | Authorized attestation observation/validity and state |
| get_quote_requirements | `{}` | Approved quantities/units and user-declared quote policy, if supplied |
| calculate_quote_preview | `{}` | Deterministic calculation with a human-selected quote's policy/offers, or explicit missing-policy state |
| get_source_evidence | line_id | Bounded approved-field evidence and catalog references |

Missing or unresolved products remain explicit. A retrieved alternative does not become selected by being returned by a tool. Search records executed channels and fails clearly when a requested vector channel cannot execute; exact/lexical methods never instantiate the embedding provider.

The comparator does not claim the lowest base price is the best valid offer: stock, freshness, MOQ, packs, breaks, shipping/tax and review still matter. The quote engine evaluates purchased quantities, not just requested units. Unsupported currencies are not aggregated.

Source URLs are strings only. There is no URL fetch, browser, email, ordering, payment, general database query, shell or code tool. The API comparison view uses this same scoped pure comparator without impersonating a model-selected call or creating research receipts.
