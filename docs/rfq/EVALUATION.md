# Measured RFQ evaluation

Frozen `synthetic-rfq-v1`: 48 fictional documents, 240 labeled items, seed 20261119;
16 development and 32 held-out documents use disjoint layout groups. The runner checks
manifest/source/truth hashes. Labels are used only for scoring, never sent to extraction.
This small template collection does not establish real-world/multilingual accuracy.

Deterministic extraction processed all 32 held-out documents. LLM and hybrid compare
the first sample in each of eight held-out groups (40 items), selected with
`--stratified`; the other 24 were not model-evaluated due to runtime. The prompt was
not tuned on held-out answers. Parser defects found during evaluation were fixed.
Initial failures remain in `deterministic-full.json` and `llm-stratified.json`.
The final LLM aggregate combines six actual initial digital successes and two actual
OCR rechecks: eight selected samples, ten execution attempts, zero skipped samples.
It is explicitly an aggregate, not a new single run. No fixture-provider quality data.

## Metric definitions

- One-to-one item matching prioritizes exact MPN, otherwise SequenceMatcher description
  similarity >=0.7; descending greedy selection uses each truth/prediction once.
  Quantity is never used for matching. Duplicate predictions cannot inflate recall.
- MPN/manufacturer/quantity exact match divides correct matched values by **all expected
  items**; missed detections count as errors. Null manufacturer labels may match null.
  MPN comparison retains case/punctuation. Unresolved raw quantity ranges are not correct
  normalized nulls. Clean digital and scanned results are separate.
- Precision = matches/predictions; recall = matches/expected items; F1 is harmonic mean.
  No detections gives zero recall/F1. Near-identical products can make matching ambiguous.
- Required completeness = populated description/quantity/unit on matched rows divided
  by 3 × expected items. Presence alone is not semantic correctness.
- Structured validity = schema-validated final extraction payloads / attempted documents.
  Deterministic payloads are typed too; this does not imply they generated LLM JSON.
  Invalid JSON/extra keys are rejected by the provider tests.
- Processing success = completed parser/extraction contracts / attempted documents.
  A valid empty-items result can succeed while item recall remains zero.
- Unsupported proposed-field rate = populated/raw proposed fields without verified
  source evidence / populated/raw proposed fields. Such fields remain unresolved.
  Stored evidence validity = exactly verified source excerpts / stored excerpts. It
  excludes missing/unverified proposed citations; read it with unsupported-field rate.
- Item-field hallucination/error rate = populated item values disagreeing with matched
  labels (or in unmatched rows) / populated item values. This includes OCR errors.
  Six initial LLM samples predate this counter; its aggregate is **not measured**.
- Duplicate behavior counts flagged rows, retained separately. Differing quantities,
  dates or specifications are not automatically merged.
- Latency covers parsing plus extraction/validation, excluding queue wait/upload/review.
  Median/nearest-rank P95 use successful samples; failed durations remain per sample.
  OCR, deterministic extraction and actual model latency are separate. Eight-sample
  P95 is unstable. No heuristic score is represented as calibrated model accuracy.

## Results

The actual comparison table is [results/comparison-table.md](results/comparison-table.md),
with full subset numbers in [results/comparison.json](results/comparison.json).

| Subset | Mode | Exact MPN | Exact quantity | Item F1 | Target outcome |
|---|---|---:|---:|---:|---|
| 12 clean tables, 60 items | Deterministic | 98.33% | 98.33% | 99.16% | Pass 95/95/90 on this subset |
| 6 digital documents, 30 items | LLM | 100% | 83.33% | 100% | Quantity target missed |
| 6 digital documents, 30 items | Hybrid | 100% | 100% | 100% | Pass on this small subset |
| 2 scanned/mixed documents, 10 items | LLM | 30% | 100% | 100% | Scans reported separately; weak MPN |
| 2 scanned/mixed documents, 10 items | Hybrid | 30% | 80% | 88.89% | Weak OCR/partial tables |
| All 32 held-out documents, 160 items | Deterministic | 56.88% | 60% | 77.39% | Prose unsupported by table baseline |

Across the matched eight documents, hybrid achieved 82.5% MPN, 95% quantity and 97.44%
item F1. LLM achieved 82.5%, 87.5% and 100%. Deterministic achieved 57.5%, 70% and
82.35%. All final selected documents processed, with 100% typed payload validity.
LLM proposed-field evidence failures were 1.97%; these were blocked for review.
Stored citations were 100% exact source matches, which does not prove OCR correctness.
Hybrid median/P95 were 0.127/106.450 seconds; LLM 105.780/116.527 seconds;
deterministic 0.020/0.444 seconds on the matched subset.

The LLM sometimes supplies quantities with unverifiable excerpts; conservative evidence
validation leaves them unresolved. Scans misread significant MPN characters. Hybrid
uses a detected table even if incomplete, avoiding model overwrite but missing some
rows. Initial targets do not establish universal supported-document performance.

Recorded model: actual installed `qwen3.8:27b`, about 17 GB, digest per call; temperature
0, context 8192, output limit 4096, input chars 12000, timeout 180 seconds, one retry,
prompt extract_v1, parser ownerpilot-parser/1.0. Default context later became 16384
with a conservative UTF-8 input budget; saved measurements retain actual configuration.
Hardware: RTX 4090 Laptop, 16376 MiB, driver 610.88; Windows 11 and Docker Desktop
Linux parser workers. Concurrent engineering checks may affect latency.

## Reproduction

Run sequentially from repository root after WINDOWS_SETUP; do not run a recovery
kill test during a benchmark. The configured model must already be installed.

```powershell
$env:RFQ_OLLAMA_MODEL='qwen3.8:27b'
docker compose -f infra/docker-compose.rfq-validation.yml run --rm --no-deps -v "${PWD}:/workspace" -w /workspace -e PYTHONPATH=/workspace/apps/api/src worker python -m api.rfq.evaluation.run --mode deterministic --output docs/rfq/results/deterministic-full-final.json
docker compose -f infra/docker-compose.rfq-validation.yml run --rm --no-deps -v "${PWD}:/workspace" -w /workspace -e PYTHONPATH=/workspace/apps/api/src -e RFQ_MODEL_CONTEXT=8192 worker python -m api.rfq.evaluation.run --mode llm --stratified --output docs/rfq/results/llm-new-run.json
docker compose -f infra/docker-compose.rfq-validation.yml run --rm --no-deps -v "${PWD}:/workspace" -w /workspace -e PYTHONPATH=/workspace/apps/api/src -e RFQ_MODEL_CONTEXT=8192 worker python -m api.rfq.evaluation.run --mode hybrid --stratified --output docs/rfq/results/hybrid-stratified-final.json
python -m uv run --project apps/api python scripts/rfq-evaluation-summary.py
```

The summary reconstructs the recorded aggregate from its named initial/recheck files.
A fresh single LLM run should be read directly instead of implying identical earlier
conditions. Omit `--stratified` for the full held-out model set; expect substantial
runtime. `--ids` selects explicit diagnostics. New prompt work needs development data,
not tuning against these held-out labels.
