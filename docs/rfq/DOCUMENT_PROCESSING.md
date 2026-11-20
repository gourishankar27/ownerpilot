# Document processing

Uploads allow PDF, CSV, XLSX and UTF-8 TXT only. Extension, MIME, signature/structure,
byte size, encryption, ZIP entries/decompressed size/compression ratio, PDF page count
and binary-text detection are checked. Original names are display metadata; only
server UUIDs form storage paths. SHA-256 duplicates are workspace-scoped. Originals
are immutable filesystem objects outside the web root and download as attachments.
Storage is a small Protocol plus local filesystem implementation.

Default limits: 20 MiB/file, 10 files/RFQ, 50 PDF pages/file, 20 sheets, 10,000 total
workbook rows, 100 columns, 80 MiB expanded workbook/page stream, 500,000 text chars,
24 million OCR pixels/page, 60 seconds/OCR page, 2,000 items/RFQ, 40 model chunks,
1,800 seconds/job and 3 worker attempts. Container memory/CPU limits additionally
bound parsers that allocate before checking decoded content size. Upload middleware
limits request bytes before multipart spooling; reverse-proxy limits are also advised.

CSV handles comma/semicolon/tab/pipe and preambles. XLSX retains sheet, actual row,
column and leading-zero display formats; formula cells are ignored with warnings,
macros/external links rejected, and no formulas executed. Header aliases distinguish
MPN, customer part number and requested SKU. Missing headers produce no guessed items.

PDF uses pypdf layout text extraction page by page. Pages with fewer than 24
alphanumeric characters are rendered through PDFium and Tesseract. Mixed PDFs retain
page order and record OCR pages/time. This is a practical heuristic, not a guarantee:
partially scanned pages with a substantial native-text footer may need manual review.
English is the default OCR language; rotation/degradation may reduce quality. Blank
pages remain warnings; encrypted/corrupt PDFs and absent OCR give explicit errors.

ParsedDocument contains parser/version, blocks, source text, cells, page/sheet/row,
supported spans, warnings and timings. Field evidence includes document hash, actual
location, exact excerpt, method, identity and time. A model's proposed block/excerpt
and literal value must occur in the actual extracted content. Unsupported generated
values remain null/unverified with raw proposals for review. Source occurrence does
not establish semantic correctness; human approval remains required.

Normalization preserves MPN punctuation/zeros; case-folding is a separate comparison
representation. Quantity/price parse through Decimal, dates accept ISO only, currency
uses ISO 4217, and email/unit/address checks flag uncertainty. Locale decimal commas,
ranges and unsupported units require review. Possible duplicate rows are retained,
never automatically merged. Reviewer changes retain original extracted raw strings,
normalized current values and audit history. No model confidence probability is used.
