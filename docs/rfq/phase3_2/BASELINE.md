# Phase 3.2 baseline

Initial HEAD was `66edae0233b6dd8de8c105cd3c014dc03462725b` on the Phase 3.1 feature branch, with a clean worktree. The requested main commit `f26aae4f38c8b32efc2ba94f6e28f2c595de5395` exists and has the same tree. Work continues on `feature/rfq-intelligence-phase-3-2` from that main commit.

Fresh baseline: 386 backend tests passed, one strict expected failure (JPY fractional-quantity limitation), and 15 browser tests passed. Root lint, typecheck and production build passed. See `results/baseline-tests.xml` and `results/baseline-browser.json`. These are fresh checks; Phase 3.1 historical scores remain historical.

The installed local model is qwen3:8b, digest `500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41`, with completion, tools and thinking capabilities. No weights were downloaded. See `results/baseline-model.json`.

Verified host: Intel Core i9-14900HX (32 logical processors), 32 GiB RAM, NVIDIA RTX 4090 Laptop GPU with 16,376 MiB memory, driver 610.88; Python 3.14.0, Node 24.12.0, pnpm 10.33.0, Docker 29.8.2 and Ollama 0.40.17. See `results/runtime-hardware.json`. Benchmark device memory samples are recorded per trial; they are not isolated model peaks.

`results/preservation.json` freezes 724 historical files, including released migrations, evaluation data and the original execution/verifier modules. New validation uses a cloned database, Redis 6385, API 8042 and web 3042. Existing service instances and databases are retained.
