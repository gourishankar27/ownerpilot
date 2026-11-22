# Phase 1.1 baseline

Starting commit: c752ae855bbbe639b2c37ee5774b9a7fd484108e, on the Phase 1 feature branch.
Local main still points to 56d6f6d; the supplied merged-main commit is not present in
the local branch history. No fetch, rebase or overwrite was needed. Work continues
from the actual implemented feature commit on feature/rfq-intelligence-phase-1-1.
The user's untracked docs.zip is preserved.

scripts/rfq-preservation.py captured 128 protected historical reports, screenshots,
dataset v1 files, released SQL migrations and docs.zip before behavior changes.
The manifest is results/baseline/preservation.json. Original processing code is also
frozen under api/rfq/legacy_v1 with its source commit and checksums, so later paired
experiments do not silently substitute new OCR, prompts or validators.

Verified CPU: i9-14900HX; RAM 33,954,377,728 bytes; RTX 4090 Laptop, 16376 MiB VRAM,
driver 610.88. Docker Desktop Linux postgres/redis/worker are running. Baseline native
integration tests use a separately created disposable ownerpilot_rfq_phase11_test DB,
which the live demonstration dispatcher cannot consume. No application DB is reset.
Installed models initially: qwen3.8:27b and qwen3.8-27b-uncensored:latest, about 17 GB.
The user explicitly authorized downloads of qwen3:4b and qwen3:8b (about 7.7 GB total).
No CUDA, NVIDIA driver, OS security or Ollama network-binding change is made.

Baseline non-model suite: 57 passed, one real-model test deliberately deselected,
four existing deprecation warnings. Real baseline hybrid inference, full deterministic
v1 regression, original browser scenarios, frontend checks and dependency versions
are recorded in results/baseline and final validation; pending work is not a pass.
The only preparatory test change redirects screenshots so old evidence is not overwritten.

Completed fresh baseline: original deterministic all32 held-out documents reproduced
56.875% MPN,60% quantity and77.3946% F1. Original hybrid on eight matched IDs
reproduced82.5% MPN,95% quantity,F197.4359%, median134.357ms andP95117.643s.
These fresh measurements are separate from the historical mixed-origin comparison.
Original four browser scenarios, pnpm lint/typecheck/test/build, Python lint/compile
and lock checks passed. The real original27B provider was exercised by that hybrid
benchmark even though its separately gated unit test was deferred to the final suite.

Verified versions: Git2.52, Python3.14.0, uv0.13.9, Node24.12, pnpm10.33,
Docker29.8.2/Compose5.5.1 and Ollama0.40.16. Exact installed dependency/model
metadata is retained in results/final/environment.json. Baseline27B context16384
Ollama ps showed30% CPU/70% GPU residency; the later8192-context benchmark is a
different configuration. The initial baseline build briefly overlapped the original
hybrid measurement; do not claim laboratory-grade isolation for that baseline P95.
