# Synthetic RFQ dataset v1

48 fictional independent RFQs, 240 labeled line items, deterministic seed 20261119.
16 development documents and 32 held-out documents use disjoint layout groups.
Four samples per layout cover absent manufacturers, ambiguous quantities and similar
part numbers; repeated products remain distinct rows. Formats include CSV, XLSX,
native/repeated-header PDFs, text, prompt injection, scanned and rotated mixed PDFs.
Ground truth is separate from sources. The manifest records source and label hashes.
The held-out manifest was frozen before final evaluation; prompts were not tuned on
its answers. Parser defects found during evaluation and their reruns are documented.

Generation: `pnpm rfq:generate` from repository root. It refuses to overwrite a frozen
manifest. A new dataset version must use a new directory. Source payloads are saved
and hash frozen; regenerated XLSX ZIP timestamps can differ across library versions.

All names, organizations, manufacturers, MPNs and requirements are synthetic. There
are no customer RFQs or proprietary distributor documents. The collection is useful
for engineering checks, but its small template families do not establish real-world
or multilingual accuracy. See docs/rfq/EVALUATION.md for exact metric denominators,
tested subsets, actual results and known limitations.
