# Catalog ingestion

CSV UTF8, single-sheet XLSX or JSON arrays. Required:source_id,manufacturer,mpn,name,category. Optional:description,specs,supplier,supplier_sku,price,currency,availability,status,url. Frozen example:data/evaluation/product-catalog/catalog.json.

Bounds:10MiB,5000 rows,40 columns/spec keys,40MiB expanded workbook and1000 ZIP entries. CSV stops at its row budget. Formulas, duplicate source IDs, ambiguous mappings, malformed prices and negative/nonfinite numeric specs fail. Explicit JSON column mappings can resolve aliases; no manufacturer inference from descriptions.

Preview freezes source hash, mapping and normalization; confirmation binds ownership/fingerprint. Repeated confirmation is idempotent. Canonical/grouped-offer counts are estimates, not comprehensive prior-source reconciliation. Different specs sharing an identifier remain distinct, with review warnings. Vectors/products/active-pointer publish atomically; old active version survives another pending import. Original rows remain versioned.
