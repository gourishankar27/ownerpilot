# Human approval policy

An approved RFQ and reviewed line are required. Phase 2 match reviews are per-actor evidence, not an implicit global winner. The latest search supersedes prior search context; reviews on that current search are resolved collectively. Same-product positive reviews form consensus; differing selections, rejection of a selected product or selection + no-match are conflicts. No selection, rejection and explicit no-match remain visible.

Even consensus requires an explicit final authorized resolution before quotation. The append-only resolution binds the exact canonical product, catalog version, positive review, review-set digest, source fingerprints and a reason. It never picks the newest reviewer arbitrarily. Selecting a `compatible_alternative` additionally requires a suitability attestation. `possible_alternative`, `insufficient_information` and `incompatible` are rejected. Phase 2 key-based checks are not OEM/electrical/software compatibility certification.

New searches/reviews invalidate the old resolution until an authorized reviewer resolves the current context. Stale/superseded catalogs block it. Source queries lock published catalog/version rows during decisions; new search/review writes serialize with RFQ-dependent decisions. Immutable offer additions also serialize on the RFQ.

Quote preparation is editable only before submission or after explicit changes requested. Submit requires a deterministic complete calculation and human confirmation that suitability, validity, availability, pack/MOQ, pricing, discounts, shipping and tax were reviewed. Reviewer/admin/owner can approve only an `under_review` current revision. An editor cannot approve.

The backend rechecks approved RFQ revision, selection resolution/review digest, active catalogs, attestation fingerprint set, freshness, policy completeness and calculation on submit and approve. Stale tabs receive 409. Duplicate decisions do not append an approval/version. Decisions lock the quote row, so concurrent reviewers cannot both approve the same revision.

An approved quote is immutable in API and PostgreSQL. New commercial facts require a new draft lineage; prior approval stays unchanged. Internal approval is not external quote delivery. The system has no email, customer submission, purchase order or payment action in Phase 3.

The same authorized owner can prepare and approve an internal quote in this milestone. Segregation-of-duties policies, enterprise signatures and independent approver assignment are future work, not silently assumed controls.
