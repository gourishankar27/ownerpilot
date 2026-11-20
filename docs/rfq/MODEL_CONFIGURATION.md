# Local model configuration

`ollama list` must show the exact configured tag. The verified machine had
`qwen3.8:27b`, digest prefix `aaee06c39dcf`, approximately 17 GB, and a 16 GiB laptop
GPU. Real HTTP inference succeeded; loading/offloading can be slow. No model was
downloaded. Leave RFQ_OLLAMA_MODEL empty until you deliberately choose an installed
local model. For another machine, inspect `ollama list` and its RAM/VRAM first.
Optional downloads are manual (`ollama pull <chosen-tag>`); consult that model's
reported size and allow RAM/VRAM beyond the checkpoint for context/cache.

```powershell
ollama list
ollama serve # only if the existing local service is not running
$env:RFQ_OLLAMA_MODEL='qwen3.8:27b' # tag verified on this development machine
$env:RFQ_OLLAMA_URL='http://localhost:11434'
```

Containers use `http://host.docker.internal:11434`, verified from the worker.
Do not change Ollama to a publicly exposed listener. Provider URLs allow local
loopback and the named Docker hosts only; environment proxies are disabled for
private document HTTP. Remote model tags/remote hosts in the tags response are rejected.

| Setting | Default |
|---|---|
| RFQ_MODEL_TIMEOUT | 180 seconds/call |
| RFQ_MODEL_INPUT_CHARS | 12,000, also constrained by conservative UTF-8 context budget |
| RFQ_MODEL_OUTPUT_TOKENS | 4,096 |
| RFQ_MODEL_CONTEXT | 16,384 (earlier measured runs record 8,192) |
| RFQ_MODEL_TEMPERATURE | 0 |
| RFQ_MODEL_RETRIES | 1 repair/retry after initial attempt |
| RFQ_MAX_CHUNKS | 40, processed sequentially |

The versioned system prompt is `prompts/extract_v1.txt`. No document instructions
or tools are executed. `/api/chat` uses the closed Pydantic JSON schema as `format`,
stream=false and think=false. HTTP response bytes, input, output and total job time
are bounded. Invalid JSON, unexpected keys, incomplete output, wrong model identity
or unverified evidence cannot silently become approved data. A provider failure is
a visible failed/retrying job; no deterministic fallback is labeled LLM success.

Saved metadata includes actual model tag/digest, prompt/parser/schema versions,
temperature/context/output settings, retry count and actual token/duration fields
when Ollama supplies them. No fabricated GPU utilization or calibrated confidence.
Basic liveness is `/health`; readiness health checks list models and ping services
without loading a model. Runtime availability and extraction quality are separate.
