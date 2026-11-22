# Phase 1.1 status

Implemented and locally functionally validated with unmet performance targets.

The selected configuration is selective-v2, enhanced-v2 OCR and qwen3:4b with the
full extract_v1 schema, context8192/output4096. Authorized qwen3:4b and qwen3:8b
downloads completed; actual 4B/8B/27B experiments and rejected compact prompts are
preserved. There is no cascade or cloud inference.

All 103 backend tests and six browser scenarios pass. Final evaluation completed
all32 v1 held-out and32 independent v2 documents in each of deterministic, LLM and
hybrid modes:192 attempts, no failed jobs or skipped samples. Completed payloads
can contain empty/incorrect rows; success rate is not quality.

Hybrid MPN accuracy is98/160(61.25%) on v1 and78/160(48.75%) on v2. Independent
scans score0/40 exact MPNs. The real partial-table route made a model call but its
added row had no populated fields. Quality targets remain unmet. A97.46% elapsed
P95 reduction on the matched-eight workload accompanies worse accuracy and is
not an equivalent-quality speedup. Human review remains mandatory.

Real OCR SIGKILL recovery succeeded on attempt2 with one publication after three
repeated deliveries. Populated compatibility reconciliation preserved225 synthetic
rows in27 tables, including auth/history and3 approved RFQs. All128 protected
historical artifacts, v1 data and released migrations remain unchanged.

The [final report](FINAL_IMPLEMENTATION_REPORT.md), [evaluation](EVALUATION_RESULTS.md),
[validation](PHASE1_1_VALIDATION.md) and [Windows runbook](WINDOWS_SETUP.md) contain
measured evidence and reproduction instructions. This is a supervised local demo;
hostile-upload/load certification and real-world accuracy are not established.
No push, deployment or Phase2 implementation was performed.
