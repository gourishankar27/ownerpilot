# Local model development benchmarks

The user authorized qwen3:4b and qwen3:8b weight downloads after installed-tag inspection. No paid/cloud inference, driver change or CUDA installation. Development IDs are v2-03-00 and v2-03-01, five prose items each; the full 27B run covers only v2-03-00. Compare model size classes within each profile on identical sources, schemas and prompts. Compact v2/v3 are distinct experiments, not pooled results.

| Model | Profile | Docs | Digest prefix | MPN | Qty | F1 | Validated output | Median | P95 | Cold/warm | Peak GPU/system RAM |
|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen3:4b | compact-v2 | 2 | 359d7dd4bcda | 0.00% | 0.00% | 0.00% | 100.00% | 15.309s | 25.879s | 25.879s/4.739s | 4629MiB/22.10GiB |
| qwen3:8b | compact-v2 | 2 | 500a1f067a9f | 0.00% | 0.00% | 0.00% | 100.00% | 14.406s | 22.605s | 22.605s/6.207s | 6969MiB/22.10GiB |
| qwen3.8:27b | compact-v2 | 2 | aaee06c39dcf | 0.00% | 100.00% | 100.00% | 100.00% | 32.173s | 38.416s | 38.416s/25.929s | 15131MiB/26.73GiB |
| qwen3:4b | compact-v3 | 2 | 359d7dd4bcda | 0.00% | 50.00% | 50.00% | 100.00% | 7.486s | 8.963s | 8.963s/6.009s | 4627MiB/22.52GiB |
| qwen3:8b | compact-v3 | 2 | 500a1f067a9f | 0.00% | 100.00% | 100.00% | 100.00% | 8.809s | 10.170s | 10.170s/7.449s | 6973MiB/22.28GiB |
| qwen3.8:27b | compact-v3 | 2 | aaee06c39dcf | 0.00% | 100.00% | 100.00% | 100.00% | 39.241s | 42.080s | 42.080s/36.402s | 15131MiB/27.33GiB |
| qwen3:4b | full | 2 | 359d7dd4bcda | 100.00% | 100.00% | 100.00% | 100.00% | 28.986s | 30.223s | 30.223s/27.748s | 4631MiB/26.16GiB |
| qwen3:8b | full | 2 | 500a1f067a9f | 100.00% | 100.00% | 100.00% | 100.00% | 42.498s | 43.550s | 43.550s/41.447s | 6971MiB/22.60GiB |
| qwen3.8:27b | full | 1 | aaee06c39dcf | 100.00% | 100.00% | 100.00% | 100.00% | 111.618s | 111.618s | 111.618s/unmeasured | 15131MiB/26.68GiB |

Cold means task models were unloaded before the first document; warm means a second different document with resident weights, not a repeated-response cache. Model-run records retain load/prompt/generation nanoseconds, actual tokens, tokens/sec and request options. Resource samples are whole GPU and whole-system RAM every ~0.5s; they are not process allocations. A sampled peak can miss brief spikes. The 27B full run has no warm observation.

Selection: qwen3:4b, Q4_K_M, full schema/extract_v1, temperature 0, context 8192, output 4096, keep-alive 300s, concurrency one. Both smaller full-schema models achieved 10/10 MPN and quantity with F1=100% on these two dev documents; 4B was faster. Compact schemas omitted identifiers or used incorrect keys despite valid JSON, so they were rejected. This tiny development result is not a general accuracy claim; the independent final results are much lower. No evidence justified a cascade; escalation count is explicitly zero. Deterministic fast paths are excluded from this model-only comparison.

Exact tag digests, checkpoint bytes, quantization, parameter counts and API residency are in models/summary.json and *-resources.json. Ollama ps directly reports 100% GPU for the smaller full models and 27% CPU/73% GPU for the 27B full benchmark at 8192 context. Baseline 27B at 16384 context had separately observed 30% CPU/70% GPU. These are observed runtime residency reports, not percentages inferred from checkpoint size.

Structured-output validity here means completed validated Pydantic payload/document. The provider enforces closed schemas, exact response model identity, done/length checks, bounded retries and one MiB responses. This does not imply all proposed fields are populated, supported or correct. First/second-document differences, small N and no repeated trials limit timing confidence.
