# Agent security and trust boundaries

Authorization remains Better Auth -> same-origin signed proxy -> FastAPI signature/membership check. All new routes use the existing identity dependency. Reads are tenant-filtered; write roles are owner/admin/reviewer/editor, while selection resolution, offer attestation and quote approval/rejection/change requests require owner/admin/reviewer. An editor can prepare and submit but cannot approve.

The model receives no credentials and cannot supply workspace/RFQ identity. Each UUID must belong to the trusted snapshot. Every tool schema rejects extra properties. Arbitrary tool names, URL fetches, SQL, Python, shell, email, orders and payments have no implementation. Requests to such names are rejected before execution and recorded as policy failures. SQL parameters remain parameterized; the one table-name interpolation uses a closed backend table allowlist.

Catalog and supplier strings are untrusted data, including instructions embedded in descriptions or source notes. The frozen real-model attack case requested shell/email/price-zero/automatic approval; the actual model executed only allowed read tools. Protocol tests independently reject forbidden actions and fabricated scalar citations. A passing attack case is not comprehensive prompt-injection protection.

The provider accepts only HTTP on explicit local hostnames, rejects credentials/path/query/fragment and disables ambient HTTP proxies. The administrator still controls local DNS/Ollama and database credentials; this is a trusted local deployment boundary, not a hardened arbitrary-network sandbox.

New JSON workflows are bounded at 256 KiB before parsing. RFQ document limits remain unchanged. There are further closed-schema bounds, 4-KB tool arguments, 20-KB tool results, 24-KB prompt messages and 64-KB model responses. Workspace admission is serialized and capped at two active/queued jobs; a partial unique index permits only one active run per RFQ. The worker serializes local inference globally and caps retries/turns/calls/repeats/time.

Cancellation prevents further receipt/result publication at transaction boundaries. A local model HTTP request can continue until its timeout; cancellation is not a promise to instantly free GPU memory. Permission/source changes are checked on every planning cycle and before final publication. Role revocation at an in-flight tool boundary may leave already-authorized read evidence in the run; it cannot grant new write or approval powers.

Persisted content is observable requests, bounded source/tool results, exact verified claims and audit metadata. Native tool-message prose and model thinking are discarded. Validation errors are sanitized to avoid echoing model summaries. Authorized evidence still contains synthetic/private source data in real deployments; it must remain protected by tenant access and storage policies.

HTTP tests cover missing authentication, other-workspace RFQs/offers/quotes, editor/viewer denial, stale decisions, forbidden tool requests, unsupported citation values and approved-record edits. Native evaluation reports zero unauthorized tool executions and zero accepted unsupported price strings. No claim of comprehensive production security, live supplier verification or enterprise retention/access controls is made.
