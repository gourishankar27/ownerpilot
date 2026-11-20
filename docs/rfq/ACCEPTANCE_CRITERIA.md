# Phase 1 acceptance gates

Completion requires preserved existing behavior; persisted workspace RFQs; bounded
PDF/CSV/XLSX/TXT uploads; digital and scanned parsing (OCR blockers must be explicit);
real local inference (runtime blockers explicit); atomic source-linked extraction;
deterministic validation; durable retry-safe jobs; human corrections and auditable
approval; labeled synthetic data and actual measured metrics; executed unit,
integration, browser and regression checks; reproducible documentation.

Targets: >=95% exact MPN and quantity match and >=90% detection F1 on supported clean
documents; no silently accepted invalid outputs, unauthorized workspace access or
duplicate delivery records. Targets are not results. Scanned results are separate.
Use `implemented with validation pending` or `partially complete` if mandatory gates
remain unverified or fail. STATUS and PHASE1_VALIDATION record the actual outcome.
