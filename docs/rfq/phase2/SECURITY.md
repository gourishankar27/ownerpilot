# Security

Existing Better Auth/HMAC membership applies to all catalog/search/review routes. Imports require write roles; reviews owner/admin/reviewer. Backend verifies approved revision/current run/reviewed line; query/workspace cannot be overridden. SQL tenant/version filters precede fusion. Owned history/audit lookup; stale409, foreign candidate422, duplicate decision409, incompatible selection422. User data is parameterized; only internally allowlisted table names interpolate SQL.

Catalog text is inert; no tool use or URL fetching. Local embedding allowlist prevents remote-provider SSRF. Formula/archive/row/text/vector/result limits apply. No CSV export introduced. Remaining public hardening:quotas, hostile-file corpus, multi-worker load, RLS defense-in-depth, backups/retention, global inference scheduling and request-disconnect cancellation. No public-security certification or deployment.
