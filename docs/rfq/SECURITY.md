# Security and review boundaries

RFQ endpoints require a server-issued, HMAC-verified, method/path-bound identity with
60-second lifetime, then current database workspace membership. The Next proxy gets
the real Better Auth session; browser headers cannot impersonate a user. Mutations
require same-origin requests. Missing/short shared secrets fail closed even in
development. Viewer roles cannot edit; owners/admins/reviewers can approve; editors
can correct but cannot approve. Every resource lookup is scoped to membership.

There is no authentication bypass or production fixture provider. Existing anonymous
showcase business routes are a pre-existing limitation, remain outside this new
boundary and do not grant access to RFQ data. This change does not claim the entire
legacy application is production multi-tenant secure. PostgreSQL credentials are a
trusted operator boundary; application authorization is not row-level DB security.

Critical approval fields: description, positive requested quantity, recognized unit.
Every populated or unsupported-proposed field must be resolved/confirmed or explicitly
cleared; every included line must be human-reviewed. Missing optional identifiers
remain missing, not invented. Review reasons and actor/time/version are mandatory for
corrections and invalid rows. Approved records cannot be edited or reprocessed.

Workers receive only job IDs, load trusted persisted ownership and sources, serialize
deliveries using DB locks, and publish in one transaction. Cancellation prevents
publication even if an already-started inference finishes. Reprocessing requires an
explicit reason; old runs, manual corrections and approvals cannot be overwritten.
Review forms retain the revision captured when opened, even during polling.

Documents are untrusted data. Local paths are UUID-only; no archives, URLs, macros,
external workbook links or executable web content are supported. Originals and text
are sensitive local data. Logs contain IDs/stages/timing/categories, not document text,
addresses, prompts, credentials or review before/after values. Audit values remain
inside the authenticated database/API. Protect storage and backups with OS permissions
and disk encryption; antivirus/DLP, malware detonation, tenant quotas, retention UI,
per-user rate limiting and independently tamper-proof audit storage are future hardening.

The worker container bounds CPU/memory and deadlines. Native API upload validation
is not a hardened hostile-file sandbox; keep the app local/trusted or add a dedicated
isolated validation service before exposing public uploads. RFQ_AUTH_SECRET is a
server trust key; rotate both ends together. Do not log, commit or expose it.
