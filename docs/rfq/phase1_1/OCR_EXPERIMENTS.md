# OCR development experiments

Twelve frozen v2 development scans, 60 items; four native-text dev documents are deliberately excluded from this OCR table. They remain in raw 16-document reports. No held-out labels were used to select preprocessing. CER uses Levenshtein distance on raw MPN readings after independent row matching; absent/unmatched rows are full deletions. This is identifier CER, not a page OCR CER. Whole-identifier token error is also retained in summary.json; full-page WER is unmeasured because full-page transcript labels were not authored.

| Strategy | MPN | Quantity | Identifier CER | Item F1 | Median OCR | P95 OCR |
|---|---|---|---|---|---|---|
| legacy | 0/60 (0.00%) | 0/60 (0.00%) | 100.00% | 0.00% | 0.349s | 0.437s |
| enhanced | 0/60 (0.00%) | 0/60 (0.00%) | 100.00% | 0.00% | 0.604s | 0.789s |
| targeted | 0/60 (0.00%) | 0/60 (0.00%) | 100.00% | 0.00% | 0.784s | 0.889s |
| combined | 0/60 (0.00%) | 0/60 (0.00%) | 100.00% | 0.00% | 0.573s | 0.821s |
| enhanced-grid | 0/60 (0.00%) | 36/60 (60.00%) | 45.26% | 79.21% | 0.549s | 0.686s |
| combined-grid | 0/60 (0.00%) | 36/60 (60.00%) | 45.26% | 79.21% | 0.828s | 0.993s |

The initial enhanced/targeted/combined runs failed to reconstruct ruled-grid rows; these failures are preserved. Adding intersecting-rule removal recovered table geometry. Enhanced-grid and combined-grid did not improve exact MPN accuracy. Combined adds targeted PSM7 MPN crops and disagreements, with no demonstrated exact-identifier benefit, so enhanced-v2 was selected. Selection improves observable row structure, not proven MPN recognition.

Selected preprocessing: 300 DPI bounded PDFium rendering; grayscale/autocontrast; projection deskew for mild skew; grid removal only with at least three intersecting long rules per axis; TSV PSM6 page segmentation. Targeted/combined variants retain original readings and alternatives and never substitute O/0, I/1, B/8 or other lookalikes. Region bounding boxes map back to original PDF points, top-left, with inverse deskew.

The diagnostic matrix includes clean raster tables, degraded 950px JPEG55 pages with reduced contrast/light blur, ±2.5–3 degree rotation and deliberately ambiguous identifiers. Independent final rotated pages have a native footer (mixed digital/raster). Adaptive thresholding, a second OCR engine, 90/180 degree orientation detection and whitelists were not implemented or claimed; PIL global thresholding is used internally for geometry/deskew scoring rather than destructive character replacement. Denoising beyond the generated degradation was not shown to help. Rotation beyond ±5 degrees remains unsupported.

Examples (synthetic dev identifiers, no automatic correction):

```json
[
  {
    "id": "v2-00-00",
    "expected": "0O000-01I1-B8/G6_Z2",
    "raw_reading": "00000-0111-B8/G6_Z2"
  },
  {
    "id": "v2-00-00",
    "expected": "0O000-02I1-B8/G6_Z2",
    "raw_reading": "00000-0211-B8/G6_Z2"
  },
  {
    "id": "v2-00-00",
    "expected": "0O000-03I1-B8/G6_Z2",
    "raw_reading": "00000-0311-B8/G6_Z2"
  }
]
```

Each page records engine/config version, DPI, preprocessing, pass/region counts, raw TSV word confidence, elapsed OCR duration and warning/coordinate convention. Confidence is an uncalibrated Tesseract signal. Limits: 24M rendered pixels, 12k words, eight passes, five crops, bounded TSV output and 60-second total page OCR budget by default. Pixel checks precede bitmap allocation. Cache identity includes engine version and relevant OCR configuration so old parser output is never relabelled as new.
