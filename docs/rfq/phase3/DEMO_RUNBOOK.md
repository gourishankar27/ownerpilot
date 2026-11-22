# Phase 3 demonstration

Use only fictional records. Start the isolated services using WINDOWS_SETUP. Sign up/sign in at `http://localhost:3033`, create a workspace and open Procurement.

1. Create an RFQ with a synthetic CSV containing `Manufacturer,MPN,Description,Qty,UOM`, e.g. Northvale / 000-P3.UI / Fictional device / 2 / EA. Use a unique source payload per workspace because the original duplicate-document protection is retained.
2. Upload, choose deterministic extraction, process, inspect evidence, review the line and approve the RFQ. Approved RFQs remain locked.
3. Import a fictional catalog JSON with matching manufacturer/MPN, category and specs. Preview, confirm, wait for real neural indexing, search the approved line and positively review the exact product.
4. In Research & internal quotations, refresh reviewed selections. Choose the reviewed product and write a resolution reason. Record the authorized resolution. For a compatible alternative, inspect compatibility evidence and attest suitability explicitly. A no-match remains unresolved for commercial quotation.
5. Record a user-attested commercial offer: supplier, price `10`, USD, per individual unit, pack `1`, MOQ `1`, available according to source, observation date, valid-through date, source reference and reason. Do not imply this is a real supplier feed. Empty fields remain unknown. Compare multiple attestations by same currency/basis; resolve changed sources with explicit supersession.
6. Start local research. Inspect the actual tool timeline and expand receipts/evidence. Complete means every accepted observation was verified. Needs attention means a model/provenance/budget issue; do not treat it as successful research or fill missing commercial facts from model prose.
7. Prepare a quote with the explicit attested offer. Enter markup rate `0.20`, discount `0`, shipping `5`, tax `0.10`, tax basis subtotal + shipping and a quote date within the offer's validity. Declare a surplus policy if required. Save and calculate. Two units should total USD `31.90` under this policy.
8. Inspect purchase/billable quantities, unit selling price, discount, tax and source snapshot. Check the commercial review attestation and submit for internal review. Request changes, adjust shipping to reviewed `0`, recalculate USD `26.40`, re-attest and resubmit.
9. An owner/admin/reviewer checks the current revision and sources and approves internally. Reload and open the saved quote; its fields are locked. Inspect revision history and audit events. Further work starts a new draft version; the approved one does not change.
10. Repeat with an expired offer or no selected product: preserve the incomplete line and null grand total; submission/approval must remain blocked. Model outage should leave manual deterministic quotation usable with properly verified inputs.

No quote is emailed or submitted to a customer. No order, supplier contact or payment is created. The end-to-end Playwright case executes this workflow against real local services and real native tool calls; outage-only UI fixtures are labeled separately.

Screenshots: `screenshots/approved-quote.png`, `native-research.png`, `mobile-quote.png`. They contain only fictional records. The complete validation record and remaining quality limitations are in FINAL_IMPLEMENTATION_REPORT.
