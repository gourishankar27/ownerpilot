| Metric | Deterministic | Local LLM | Hybrid | Target / outcome |
|---|---:|---:|---:|---|
| MPN exact match | 57.50% | 82.50% | 82.50% | >=95% digital target; scans separate |
| Manufacturer exact match | 70.00% | 97.50% | 95.00% | Measured |
| Quantity exact match | 70.00% | 87.50% | 95.00% | >=95% digital target |
| Item precision | 100.00% | 100.00% | 100.00% | Measured |
| Item recall | 70.00% | 100.00% | 95.00% | Measured |
| Item F1 | 82.35% | 100.00% | 97.44% | >=90% supported subset |
| Required-field completeness | 70.00% | 95.83% | 95.00% | Measured |
| Validated extraction payload rate | 100.00% | 100.00% | 100.00% | 100% required |
| Unsupported proposed fields | 0.00% | 1.97% | 0.00% | Flagged, never auto-approved |
| Stored evidence validity | 100.00% | 100.00% | 100.00% | Exact source occurrence |
| Processing success | 100.00% | 100.00% | 100.00% | Includes valid zero-item results |
| End-to-end median seconds | 0.020 | 105.780 | 0.127 | Actual parser + extraction, excludes queue/review |
| End-to-end p95 seconds | 0.444 | 116.527 | 106.450 | Actual parser + extraction, excludes queue/review |
