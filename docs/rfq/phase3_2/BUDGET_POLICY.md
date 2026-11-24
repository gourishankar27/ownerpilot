# Explicit budget policy

New policy `procurement-planning/2` uses this deliberately changed envelope. Old prompt/version executions keep their old limits.

| Category | Phase 3.2 limit |
| --- | ---: |
| Approved lines | 12 |
| Native planning requests | 4 |
| Initial citation finalization | 1 |
| Citation correction | 1 |
| Total admitted model requests | 6 |
| Tool RPCs, including rejected/duplicate requests | 8 |
| Equivalent tool requests | 2 |
| Batch size | 4 selected; 2 experimental |
| Batch result | 32,768 UTF-8 bytes |
| Provider response | 65,536 bytes |
| Context | 8,192 tokens |
| Planning output | 1,600 tokens |
| Finalization/correction output | 4,096 tokens |
| Provider HTTP timeout | 60 seconds |
| Total research deadline | 240 seconds from original creation |
| Worker delivery attempts | 3 |

The larger finalization output allowance is explicit: twelve-line reference inventories can exceed the previous output envelope. Citation request schema `research-citation-only/2` is unchanged; only pointers/receipt/source keys are accepted, with at most 32 groups. The model never emits business values.

Preflight estimates line result sizes, required reference groups and minimum macro-RPCs. It rejects empty or over-twelve-line scope, unsupported batch sizes, more than 32 required groups, impossible tool capacity and a single source exceeding the bounded output envelope. Runtime serialization is the final byte limit. Estimates are not evidence reads.

Large scopes terminate with `capacity_*` attention before inference. There is no automatic continuation. A human can create a separately reviewed scoped RFQ, preserving explicit approval of its boundaries. The product never silently processes a prefix as a complete research report.

Model call admission is durable before HTTP. A lost request consumes its call. A lost finalization may therefore require attention even though receipts survive; it does not gain an extra finalization. Correction and original deadlines do not reset on restart. The global PostgreSQL advisory lock releases on real worker death.

The 240-second deadline is checked at admission, execution checkpoints and publication. An HTTP request admitted just before expiry may continue until its separate 60-second transport timeout; it cannot publish after the research deadline. This is a publication deadline, not a guarantee that the remote Ollama computation is forcibly cancelled at exactly 240 seconds.
