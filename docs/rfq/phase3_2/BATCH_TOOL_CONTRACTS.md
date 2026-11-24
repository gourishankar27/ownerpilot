# Batch tool contract

Registry `procurement-tools/3` preserves the previous tools and adds `get_line_research_batch`:

```json
{"line_ids":["approved-line-uuid"],"include":["reviewed_product_selection","supplier_offers"]}
```

The request is closed: one to four distinct UUIDs and one or two distinct literal read types. The backend authorizes every line against the trusted job snapshot before reading any child. No workspace, RFQ, actor, URL, commercial value, association or policy override is accepted. Batch-two experiments enforce the stricter per-run two-line limit in addition to the shared schema maximum of four.

One immutable parent receipt contains `lines`, `requested_line_ids` and `complete: true`. Every requested line appears exactly once, in request order, with `source_status: inspected` and exactly the requested selection/offers sections. The result is capped at 32,768 UTF-8 bytes; overflow fails the whole batch. No truncation or successful partial parent is emitted. Existing individual read caps remain enforced.

One batch is one tool decision and one durable receipt, regardless of lines inspected. `execution_origin` is assigned by the controller, never accepted from model arguments. `call_details` records scope, source read names, pinned source fingerprint, reason, result bytes, batch utilization and actual new coverage contribution.

The verifier validates the complete parent before accepting any of its children. Temporary child views share the parent's ID and exist only in memory for the frozen semantic checks. All emitted facts use the real parent receipt and physical pointers such as `/data/lines/2/offers/attestations/0/price`. Typed values, line/product/selection/offer associations, revision, catalog version and fingerprints must all match. Equal scalar values on different lines or offers do not make their references interchangeable.

The tests reject omitted/duplicated children, partial parents, extra fields, wrong order, wrong owner, cross-line/cross-offer pointers, fingerprint changes, malformed UUIDs, excessive size and malicious overrides. No synthetic child receipt is persisted or presented as executed work.
