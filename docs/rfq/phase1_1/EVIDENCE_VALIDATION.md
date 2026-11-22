# Evidence and correctness

Evidence stores immutable document ID/fingerprint, exact block identity/excerpt, observed location and extraction method. Added nullable fields distinguish source occurrence, row association, column association, source eligibility, association reason, raw OCR/confidence and alternative readings. Old JSON remains readable with unknown associations.

| Check | Meaning | Limitation |
|---|---|---|
| Occurrence | Proposed value is inside a nonempty exact excerpt in a selected block | A literal can belong to a different field or row |
| Location/version | Block belongs to the parsed document and its fingerprint | OCR text can differ from the visible page |
| Eligibility | Instructions, fake system messages and quoted examples are excluded by explicit heuristics | Pattern detection is not comprehensive hostile-input classification |
| Row | Field shares its item's source anchor and eligible source block | A paragraph block can contain more than one semantic fact |
| Column | Exact value matches the recognized field's source cell | Unknown layouts have no trustworthy column denominator |
| Type | Quantity/unit/date/identifier checks plus explicit prose/header labels | Source validity does not imply commercial or catalog truth |
| Human | Explicit review/correction and approval audit | Human verification is a separate act from automatic validation |

Wrong-row quantities or manufacturers cannot become trusted solely because the text occurs on the page. Recognized price/quantity and customer-PN/MPN columns must agree. Shipping/billing header labels must match. Unsupported values remain raw unverified proposals with no accepted normalized value; known structural mismatches require review. Model block IDs from outside the selected document/chunk are rejected. Multiple values and OCR alternatives remain visible.

Original identifier case, leading zeros and punctuation are preserved. Comparison normalization maps Unicode hyphen forms in a separate comparison field; it does not rewrite raw or accepted values. No lookalike substitution or universal MPN dictionary is used. Catalog truth is deferred.

Actual word/cell geometry uses original PDF page points from the top-left, including inverse deskew. No invented coordinates, image crops or source highlighting are introduced. Existing document-download and evidence endpoints retain workspace authorization. UI shows raw/normalized/alternative readings, uncalibrated OCR confidence, structural status and human review distinctly. Filters cover reviewed, critical, unsupported, association, OCR disagreement, conflicting and duplicate-warning rows.

Approval remains stricter than automatic field acceptance: every active row must be reviewed; populated unresolved/ambiguous/conflicting fields must be corrected or cleared. Revision checks, audit history, prior extraction versions and approved immutability remain. Reprocessing creates a new version and requires an explicit reason; it cannot silently rewrite an approval.

Observed zero unsupported accepted fields in final evaluation refers to literal evidence/status checks. It does not mean zero wrong quantities, zero OCR errors or perfect association. Label-based row/column accuracy and erroneous-item-field counts are separate metrics. Security fixtures and real cross-workspace evidence/download404 checks passed. Adversarial extraction quality remains poor even when forged instructions do not produce accepted fake values; the model has no agent tools or external URL access.
