# Synthetic RFQ demonstration

Follow WINDOWS_SETUP's disposable path to preserve existing business data. Run web,
API and Linux worker, with the same private RFQ_AUTH_SECRET on web/API and an explicitly
installed local model configured. The application is at localhost:3000/procurement.

1. Sign up/sign in using the normal app authentication. On Overview create a new
   workspace. Procurement's workspace selector lists only current memberships.
2. Create an RFQ titled `Synthetic hardware refresh`, optionally supply a customer.
3. Select one or more files from `data/evaluation/rfq/sources`. For a quick clean
   demonstration use `rfq-04-00.csv`, `rfq-05-00.xlsx` or `rfq-06-00.pdf`.
   Each document is fictional. Choose files individually in separate RFQs for benchmarks.
4. Upload. Select Hybrid or Deterministic tables only and start processing. The UI
   shows actual job stages, parsed document counts and attempts. Text requests use
   the real local model in Hybrid mode; there is no success fallback if it is absent.
5. Open an extracted MPN or quantity. The evidence panel names the actual file,
   worksheet/page/row/column, exact excerpt, method and fingerprint.
6. Review each line, correct a value if needed, and enter a review reason. All
   supported fields are editable. Mark non-product rows invalid or add a missing
   product manually. Confirm required description, positive quantity and unit.
7. Review header fields; resolve conflicts, invalid email/date/currency and any
   unsupported generated value. Missing optional values may remain absent. Every
   active row must be reviewed before the approval button enables.
8. Check the explicit human-review acknowledgement and approve. Reload, reselect
   the RFQ and verify the persisted approval and corrected values. The version is
   locked. Processing history exposes parser/model settings; audit shows before/after.
9. An unapproved RFQ can be reprocessed with a nonempty reason. Its old runs and
   corrections remain in history. A stale editor save returns 409 and asks for reload.

Use `rfq-10-00.pdf` to exercise OCR and `rfq-11-00.pdf` for mixed/rotated pages.
OCR quality is materially weaker than clean table extraction; inspect every identifier.
Use `rfq-08-00.txt` for real LLM prose extraction and `rfq-09-00.txt` for adversarial
document text. No tools, external messages, purchases or quotes are executed.

`pnpm rfq:e2e` drives the real signup, workspace, upload, Celery processing, evidence,
correction, approval and reload flow. It saves synthetic screenshots in
`docs/rfq/screenshots/evidence.png` and `approved.png`. A separately named UI test
simulates model unavailability; it is not a model-quality result.
