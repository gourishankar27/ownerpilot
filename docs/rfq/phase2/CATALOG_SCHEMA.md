# Catalog schema

Migration0004 adds six procurement-owned tables: product_catalogs; catalog_versions (source snapshot, preview and durable job); catalog_products (canonical data, offers, hash and vector); catalog_match_runs; catalog_match_reviews; catalog_audit_events. Foreign keys and uniqueness protect core references; extensible source/spec facts use JSONB. Product key is version+identity. vector(768) enforces dimensions. Model/digest/preprocessing/generation belong to the version.

Optional prices validate as Decimal and serialize as decimal strings; supplied prices require currency. Missing prices/availability remain null. No monetary calculations or fabricated offers. Existing inventory and migrations0001–3 remain unchanged. Rebuild stages a new version rather than rewriting approved RFQs or old matches.
