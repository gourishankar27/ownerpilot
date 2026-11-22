# Evidence resolution and coverage

`apps/api/src/api/procurement_agent/evidence.py` is the common resolution service. The runner and evaluator use it for production semantics; the benchmark separately checks materialized values and associations against authored source facts.

Validation order: verify pinned snapshot digest; require same run and successful tool receipt; check workspace when present; validate tool schema/version and scope; match receipt sources to the immutable approved snapshot; register only typed semantic fields; validate each subject-bound pointer; resolve its original scalar; deduplicate semantic facts; calculate required coverage. Receipt tables are scoped through their run foreign key and the authorized run API. The model cannot supply a receipt document.

Every fact records receipt ID, pointer, backend field type, original value, known/unknown state, run/workspace/RFQ/revision, line, selection, product, catalog version, supplier offer, source fingerprint and data class where applicable. `None` stays JSON null; unknown availability stays the source enum `unknown`; price `"0"` stays a known zero. Python booleans never pass integer checks. Decimal strings remain strings without float conversion or approximate comparisons.

A raw source reference containing a numeric string is not a price field. A price/currency pointer from another offer is rejected even if the scalar matches. Object references, arbitrary descriptions and fabricated fields are rejected. Contradictory repeated semantic facts are rejected; exact repeats are deduplicated.

Each approved line requires the approved RFQ read, reviewed selection read and supplier-offer read. Required citations include selection state and, for each attestation, price, currency, availability and freshness. Conflict/supersession states require citations as well. Missing prices and unknown availability can be correctly researched. No-match selections and lines with no attested offers can complete after those sources are inspected and the selection state is cited.

The backend derives missing lead time, stock, dates and other unknowns from the pinned snapshot; they are labelled separately from model-selected facts. `model_selected` and source bindings remain available in the persisted fact. Quote readiness is evaluated independently using the unchanged financial engine and human quote inputs; absent quote policy means readiness is unknown/blocked. Research completeness does not imply commercial completeness or human approval.

Valid facts survive alongside invalid citations as partial evidence. Any unresolved current citation error or required coverage gap blocks completion. One corrected set can be unioned with valid prior facts, re-resolved and independently checked. Initial rejected-reference history remains in immutable finalization records.
