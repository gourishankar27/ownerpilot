"""Derive auditable tables from saved synthetic predictions; no inference or tuning."""

import json
from pathlib import Path

from api.rfq.contracts import Extraction
from api.rfq.evaluation.matching_v2 import match_items
from api.rfq.evaluation.quality_run import aggregate

ROOT = Path("docs/rfq/phase1_1")
RESULTS = ROOT / "results"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def pct(value):
    return "unmeasured" if value is None else f"{value * 100:.2f}%"


def seconds(value):
    return "unmeasured" if value is None else f"{value / 1000:.3f}s"


def table(headers, rows):
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "|" + "|".join(["---"] * len(headers)) + "|",
        ]
        + ["| " + " | ".join(map(str, row)) + " |" for row in rows]
    )


def legacy_metrics(samples):
    counts = {
        k: sum(
            s.get("counts", {}).get("historical_compatible", {}).get(k, 0)
            for s in samples
        )
        for k in ("matches", "mpn_correct", "quantity_correct", "manufacturer_correct")
    }
    truth = sum(s["counts"]["truth_items"] for s in samples)
    pred = sum(s["counts"].get("predicted_items", 0) for s in samples)
    return dict(
        raw_counts=counts,
        truth_items=truth,
        predicted_items=pred,
        f1=2 * counts["matches"] / (truth + pred) if truth + pred else None,
        **{
            k + "_accuracy": counts[k + "_correct"] / truth if truth else None
            for k in ("mpn", "quantity", "manufacturer")
        },
    )


def final_results():
    matched = {
        s["id"] for s in read(RESULTS / "baseline/hybrid-eight-v1.json")["samples"]
    }
    rows, detail_rows, summary, historical_rows = [], [], {}, []
    groups = {
        "rfq": {
            "clean": {
                "csv_semicolon",
                "xlsx_multisheet",
                "pdf_repeated_headers",
                "pdf_aligned",
            },
            "scanned/mixed": {"scanned", "mixed_rotated"},
            "adversarial": {"prompt_injection"},
        },
        "rfq-v2": {
            "clean": {"invoice_style", "split_tables", "multisheet", "csv_preamble"},
            "scanned/mixed": {"rotated_scan", "lowcontrast_scan"},
            "adversarial": {"injection_quotes"},
        },
    }
    for dataset in ("rfq", "rfq-v2"):
        for mode in ("deterministic", "llm", "hybrid"):
            report = read(RESULTS / f"final/{dataset}-{mode}.json")
            assert (
                report["status"] == "complete"
                and report["actual_samples"] == 32
                and report["skipped_samples"] == 0
            )
            subsets = {
                "all": report["samples"],
                **{
                    name: [s for s in report["samples"] if s["layout_group"] in layouts]
                    for name, layouts in groups[dataset].items()
                },
            }
            if dataset == "rfq":
                subsets["matched-eight"] = [
                    s for s in report["samples"] if s["id"] in matched
                ]
            for name, samples in subsets.items():
                m = aggregate(samples)
                key = f"{dataset}/{mode}/{name}"
                summary[key] = dict(
                    sample_ids=[s["id"] for s in samples],
                    metrics=m,
                    historical_compatible=legacy_metrics(samples),
                )
                c = m["raw_counts"]
                rows.append(
                    [
                        dataset,
                        mode,
                        name,
                        f"{len(samples)}/{c['truth_items']}",
                        f"{c.get('mpn_correct', 0)}/{c['truth_items']} ({pct(m['mpn_accuracy'])})",
                        f"{c.get('quantity_correct', 0)}/{c['truth_items']} ({pct(m['quantity_accuracy'])})",
                        pct(m["f1"]),
                        f"{c.get('matches', 0)}/{c.get('predicted_items', 0)}",
                        f"{m['model_calls']}",
                        seconds(m["latency_ms"]["p95"]),
                        f"{m['failed_documents']}/0",
                    ]
                )
                if name == "all":
                    detail_rows.append(
                        [
                            dataset,
                            mode,
                            pct(m["manufacturer_accuracy"]),
                            pct(m["unit_accuracy"]),
                            pct(m["description_accuracy"]),
                            pct(m["header_accuracy"]),
                            f"{c.get('missed_rows', 0)}/{c.get('unexpected_rows', 0)}",
                            f"{c.get('unsupported_proposals', 0)}/{c.get('populated_fields', 0)}",
                            f"{c.get('unsupported_accepted', 0)}/{c.get('accepted_fields', 0)}",
                            f"{c.get('unresolved_items', 0)}/{c.get('predicted_items', 0)}",
                        ]
                    )
                if dataset == "rfq" and name in {"all", "matched-eight"}:
                    h = legacy_metrics(samples)
                    historical_rows.append(
                        [
                            mode,
                            name,
                            pct(h["mpn_accuracy"]),
                            pct(h["quantity_accuracy"]),
                            pct(h["f1"]),
                        ]
                    )
    save(RESULTS / "final/summary.json", summary)
    baseline = read(RESULTS / "baseline/hybrid-eight-v1.json")["metrics"]
    final = summary["rfq/hybrid/matched-eight"]["metrics"]
    reduction = 1 - final["latency_ms"]["p95"] / baseline["latency_ms"]["p95"]
    gates = []
    for dataset in ("rfq", "rfq-v2"):
        for subset, thresholds in [
            ("clean", (0.98, 0.98, 0.98)),
            ("scanned/mixed", (0.80, 0.95, 0.95)),
        ]:
            m = summary[f"{dataset}/hybrid/{subset}"]["metrics"]
            for metric, target in zip(
                ("mpn_accuracy", "quantity_accuracy", "f1"), thresholds
            ):
                gates.append(
                    dict(
                        dataset=dataset,
                        subset=subset,
                        metric=metric,
                        target=target,
                        actual=m[metric],
                        passed=m[metric] >= target,
                    )
                )
    for metric, target in zip(
        ("mpn_accuracy", "quantity_accuracy", "f1"), (0.95, 0.98, 0.98)
    ):
        gates.append(
            dict(
                dataset="rfq",
                subset="matched-eight",
                metric=metric,
                target=target,
                actual=final[metric],
                passed=final[metric] >= target,
            )
        )
    gates.append(
        dict(
            dataset="rfq",
            subset="matched-eight",
            metric="p95_reduction_against_fresh_phase1",
            target=0.5,
            actual=reduction,
            passed=reduction >= 0.5,
            qualification="Quality differs; faster errors/empty outputs do not establish equivalent-quality speedup.",
        )
    )
    all_counts = [
        summary[f"{dataset}/{mode}/all"]["metrics"]["raw_counts"]
        for dataset in ("rfq", "rfq-v2")
        for mode in ("deterministic", "llm", "hybrid")
    ]
    unsupported = sum(c.get("unsupported_accepted", 0) for c in all_counts)
    gates.append(
        dict(
            dataset="both",
            subset="all-six-configurations",
            metric="accepted_unsupported_critical_fields",
            target=0,
            actual=unsupported,
            passed=unsupported == 0,
            accepted_field_denominator=sum(
                c.get("accepted_fields", 0) for c in all_counts
            ),
            qualification="Literal support/status definition across all accepted fields, a superset of critical fields; semantic errors are reported separately.",
        )
    )
    workflows = read(RESULTS / "final/real-workflows.json")
    denied = (
        workflows["cross_workspace_evidence_status"]
        == workflows["cross_workspace_download_status"]
        == 404
    )
    gates.append(
        dict(
            dataset="real-local-workflows",
            subset="cross-workspace-evidence-and-download",
            metric="observed_authorization_violations",
            target=0,
            actual=0 if denied else 1,
            passed=denied,
            qualification="Two real cross-workspace checks plus regression authorization cases; not a comprehensive security audit.",
        )
    )
    recovery = read(RESULTS / "final/worker-restart.json")
    duplicates = max(0, recovery["published_runs"] - 1)
    gates.append(
        dict(
            dataset="real-worker-recovery",
            subset="three-repeated-deliveries",
            metric="duplicate_publications",
            target=0,
            actual=duplicates,
            passed=duplicates == 0,
            qualification="One observed published run after SIGKILL recovery and three repeated deliveries.",
        )
    )
    save(RESULTS / "final/performance-gates.json", gates)
    lines = [
        "# Final evaluation results",
        "",
        "All six executions completed: 192 document/configuration attempts, zero failed jobs and zero skipped samples. A valid completed job can contain empty or erroneous rows; success is not extraction accuracy. Each set has 32 documents and 160 expected items. Configurations were frozen before final evaluation; final labels were never supplied to prompts.",
        "",
        "The independent v2 results expose substantial generalization failures. Milestone performance targets are unmet. Assignment/2.0 is the primary evaluator; the historical matcher is reported separately. Every subset below comes from the same full execution, without combining rechecks.",
        "",
        table(
            [
                "Set",
                "Mode",
                "Subset",
                "Docs/items",
                "MPN correct",
                "Qty correct",
                "F1",
                "Matches/predictions",
                "Calls",
                "P95",
                "Failures/skips",
            ],
            rows,
        ),
        "",
        "Clean means the four declared structured digital layout families per set. Scanned/mixed means eight raster/mixed pages per set. Adversarial means four instruction/quoted-output documents per set. Prose documents are included in all and matched-eight where selected, but excluded from clean. The complete per-layout/per-format breakdown and all raw numerators are in each report and summary.json.",
        "",
        table(
            [
                "Set",
                "Mode",
                "Manufacturer",
                "Unit",
                "Description exact",
                "Header exact",
                "Missed/unexpected",
                "Unsupported proposals/populated",
                "Unsupported accepted/accepted",
                "Unresolved/predicted",
            ],
            detail_rows,
        ),
        "",
        "Literal support is distinct from semantic correctness: unsupported accepted is zero by the recorded occurrence/status check, while erroneous_item_fields remains nonzero. An empty generated row can count as an unexpected prediction. Duplicate-warning counts are conservative warnings, not adjudicated duplicate truth. Human-review burden is unresolved-item count, not measured reviewer minutes.",
        "",
        "## Historical-compatible rescore of the new predictions",
        "",
        table(["Mode", "Subset", "MPN", "Quantity", "F1"], historical_rows),
        "",
        f"Fresh original Phase 1 hybrid, eight identical IDs: MPN {pct(baseline['mpn_accuracy'])}, quantity {pct(baseline['quantity_accuracy'])}, F1 {pct(baseline['f1'])}, P95 {seconds(baseline['latency_ms']['p95'])}. New hybrid P95 is {seconds(final['latency_ms']['p95'])}, a {pct(reduction)} reduction, with different and generally worse quality. This meets the elapsed-time target only; it is not an equivalent-quality throughput claim. The original published historical P95 (106.450s) is a separate mixed-origin historical reference, not this fresh baseline.",
        "",
        "See performance-gates.json for every predeclared performance target. See EVALUATION_METHODOLOGY.md for denominators, missing measurements, label/split limitations and matching assumptions.",
        "",
    ]
    (ROOT / "EVALUATION_RESULTS.md").write_text("\n".join(lines), encoding="utf-8")


def edit_distance(a, b):
    prior = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        row = [i]
        for j, y in enumerate(b, 1):
            row.append(min(row[-1] + 1, prior[j] + 1, prior[j - 1] + (x != y)))
        prior = row
    return prior[-1]


def ocr_results():
    matrix, rows = {}, []
    root = Path("data/evaluation/rfq-v2")
    manifest = {d["id"]: d for d in read(root / "manifest.json")["documents"]}
    for name in (
        "legacy",
        "enhanced",
        "targeted",
        "combined",
        "enhanced-grid",
        "combined-grid",
    ):
        report = read(RESULTS / f"ocr/{name}.json")
        samples = [s for s in report["samples"] if s["layout_group"] != "dev_text_rows"]
        m = aggregate(samples)
        errors = chars = wrong_tokens = identifiers = 0
        examples = []
        for sample in samples:
            expected = read(root / manifest[sample["id"]]["truth"])["items"]
            result = (
                Extraction.model_validate(sample["predictions"])
                if sample["success"]
                else Extraction()
            )
            pairs = {
                p["truth"]: p["prediction"]
                for p in match_items(expected, result.items)
                if not p["ambiguous"]
            }
            for i, item in enumerate(expected):
                field = result.items[pairs[i]].fields["mpn"] if i in pairs else None
                actual = (field.raw or field.value or "") if field else ""
                wanted = item["mpn"] or ""
                errors += edit_distance(wanted, actual)
                chars += len(wanted)
                wrong_tokens += actual != wanted
                identifiers += 1
                if len(examples) < 3 and actual != wanted:
                    examples.append(
                        dict(id=sample["id"], expected=wanted, raw_reading=actual)
                    )
        matrix[name] = dict(
            metrics=m,
            character_errors=errors,
            reference_characters=chars,
            identifier_token_errors=wrong_tokens,
            identifiers=identifiers,
            cer=errors / chars,
            identifier_token_error_rate=wrong_tokens / identifiers,
            examples=examples,
        )
        rows.append(
            [
                name,
                f"{m['raw_counts'].get('mpn_correct', 0)}/60 ({pct(m['mpn_accuracy'])})",
                f"{m['raw_counts'].get('quantity_correct', 0)}/60 ({pct(m['quantity_accuracy'])})",
                pct(errors / chars),
                pct(m["f1"]),
                seconds(m["ocr_ms"]["median"]),
                seconds(m["ocr_ms"]["p95"]),
            ]
        )
    save(RESULTS / "ocr/summary.json", matrix)
    (ROOT / "OCR_EXPERIMENTS.md").write_text(
        "\n".join(
            [
                "# OCR development experiments",
                "",
                "Twelve frozen v2 development scans, 60 items; four native-text dev documents are deliberately excluded from this OCR table. They remain in raw 16-document reports. No held-out labels were used to select preprocessing. CER uses Levenshtein distance on raw MPN readings after independent row matching; absent/unmatched rows are full deletions. This is identifier CER, not a page OCR CER. Whole-identifier token error is also retained in summary.json; full-page WER is unmeasured because full-page transcript labels were not authored.",
                "",
                table(
                    [
                        "Strategy",
                        "MPN",
                        "Quantity",
                        "Identifier CER",
                        "Item F1",
                        "Median OCR",
                        "P95 OCR",
                    ],
                    rows,
                ),
                "",
                "The initial enhanced/targeted/combined runs failed to reconstruct ruled-grid rows; these failures are preserved. Adding intersecting-rule removal recovered table geometry. Enhanced-grid and combined-grid did not improve exact MPN accuracy. Combined adds targeted PSM7 MPN crops and disagreements, with no demonstrated exact-identifier benefit, so enhanced-v2 was selected. Selection improves observable row structure, not proven MPN recognition.",
                "",
                "Selected preprocessing: 300 DPI bounded PDFium rendering; grayscale/autocontrast; projection deskew for mild skew; grid removal only with at least three intersecting long rules per axis; TSV PSM6 page segmentation. Targeted/combined variants retain original readings and alternatives and never substitute O/0, I/1, B/8 or other lookalikes. Region bounding boxes map back to original PDF points, top-left, with inverse deskew.",
                "",
                "The diagnostic matrix includes clean raster tables, degraded 950px JPEG55 pages with reduced contrast/light blur, ±2.5–3 degree rotation and deliberately ambiguous identifiers. Independent final rotated pages have a native footer (mixed digital/raster). Adaptive thresholding, a second OCR engine, 90/180 degree orientation detection and whitelists were not implemented or claimed; PIL global thresholding is used internally for geometry/deskew scoring rather than destructive character replacement. Denoising beyond the generated degradation was not shown to help. Rotation beyond ±5 degrees remains unsupported.",
                "",
                "Examples (synthetic dev identifiers, no automatic correction):",
                "",
                "```json",
                json.dumps(matrix["enhanced-grid"]["examples"], indent=2),
                "```",
                "",
                "Each page records engine/config version, DPI, preprocessing, pass/region counts, raw TSV word confidence, elapsed OCR duration and warning/coordinate convention. Confidence is an uncalibrated Tesseract signal. Limits: 24M rendered pixels, 12k words, eight passes, five crops, bounded TSV output and 60-second total page OCR budget by default. Pixel checks precede bitmap allocation. Cache identity includes engine version and relevant OCR configuration so old parser output is never relabelled as new.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def model_results():
    matrix, rows = {}, []
    names = [
        ("compact-v2", "", "qwen3-4b-compact"),
        ("compact-v2", "", "qwen3-8b-compact"),
        ("compact-v2", "", "qwen3_8-27b-compact"),
        ("compact-v3", "prompt-v3/", "qwen3-4b-compact"),
        ("compact-v3", "prompt-v3/", "qwen3-8b-compact"),
        ("compact-v3", "prompt-v3/", "qwen3_8-27b-compact"),
        ("full", "full-smaller/", "qwen3-4b-full"),
        ("full", "full-smaller/", "qwen3-8b-full"),
        ("full", "", "qwen3_8-27b-full"),
    ]
    for profile, folder, name in names:
        report = read(RESULTS / f"models/{folder}{name}.json")
        resources = read(RESULTS / f"models/{folder}{name}-resources.json")
        m = report["metrics"]
        observations = resources.get("resource_samples", [])
        peak_gpu = max((s["gpu_memory_mib"] for s in observations), default=None)
        peak_ram = max((s["system_ram_used_bytes"] for s in observations), default=None)
        model = resources["model"]
        samples = report["samples"]
        times = [s["timings"]["latency_ms"] for s in samples]
        runs = [r for s in samples for r in s.get("metadata", {}).get("model_runs", [])]
        key = f"{profile}/{model}"
        matrix[key] = dict(
            metrics=m,
            tag=resources["tag"],
            peak_gpu_mib=peak_gpu,
            peak_system_ram_bytes=peak_ram,
            resident_after=resources["resident_after"],
            ollama_ps=resources["ollama_ps"],
            cold_ms=times[0],
            warm_ms=times[1] if len(times) > 1 else None,
            model_runs=runs,
        )
        rows.append(
            [
                model,
                profile,
                len(samples),
                resources["tag"]["digest"][:12],
                pct(m["mpn_accuracy"]),
                pct(m["quantity_accuracy"]),
                pct(m["f1"]),
                pct(m["structured_output_validity"]),
                seconds(m["latency_ms"]["median"]),
                seconds(m["latency_ms"]["p95"]),
                f"{seconds(times[0])}/{seconds(times[1]) if len(times) > 1 else 'unmeasured'}",
                f"{peak_gpu}MiB/{peak_ram / 2**30:.2f}GiB",
            ]
        )
    save(RESULTS / "models/summary.json", matrix)
    (ROOT / "MODEL_BENCHMARKS.md").write_text(
        "\n".join(
            [
                "# Local model development benchmarks",
                "",
                "The user authorized qwen3:4b and qwen3:8b weight downloads after installed-tag inspection. No paid/cloud inference, driver change or CUDA installation. Development IDs are v2-03-00 and v2-03-01, five prose items each; the full 27B run covers only v2-03-00. Compare model size classes within each profile on identical sources, schemas and prompts. Compact v2/v3 are distinct experiments, not pooled results.",
                "",
                table(
                    [
                        "Model",
                        "Profile",
                        "Docs",
                        "Digest prefix",
                        "MPN",
                        "Qty",
                        "F1",
                        "Validated output",
                        "Median",
                        "P95",
                        "Cold/warm",
                        "Peak GPU/system RAM",
                    ],
                    rows,
                ),
                "",
                "Cold means task models were unloaded before the first document; warm means a second different document with resident weights, not a repeated-response cache. Model-run records retain load/prompt/generation nanoseconds, actual tokens, tokens/sec and request options. Resource samples are whole GPU and whole-system RAM every ~0.5s; they are not process allocations. A sampled peak can miss brief spikes. The 27B full run has no warm observation.",
                "",
                "Selection: qwen3:4b, Q4_K_M, full schema/extract_v1, temperature 0, context 8192, output 4096, keep-alive 300s, concurrency one. Both smaller full-schema models achieved 10/10 MPN and quantity with F1=100% on these two dev documents; 4B was faster. Compact schemas omitted identifiers or used incorrect keys despite valid JSON, so they were rejected. This tiny development result is not a general accuracy claim; the independent final results are much lower. No evidence justified a cascade; escalation count is explicitly zero. Deterministic fast paths are excluded from this model-only comparison.",
                "",
                "Exact tag digests, checkpoint bytes, quantization, parameter counts and API residency are in models/summary.json and *-resources.json. Ollama ps directly reports 100% GPU for the smaller full models and 27% CPU/73% GPU for the 27B full benchmark at 8192 context. Baseline 27B at 16384 context had separately observed 30% CPU/70% GPU. These are observed runtime residency reports, not percentages inferred from checkpoint size.",
                "",
                "Structured-output validity here means completed validated Pydantic payload/document. The provider enforces closed schemas, exact response model identity, done/length checks, bounded retries and one MiB responses. This does not imply all proposed fields are populated, supported or correct. First/second-document differences, small N and no repeated trials limit timing confidence.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def ablation_results():
    rows = []
    for policy in ("phase1", "selective-v2"):
        for mode in ("deterministic", "hybrid"):
            r = read(RESULTS / f"ablation/{policy}-{mode}.json")
            m = r["metrics"]
            rows.append(
                [
                    policy + "/" + mode,
                    pct(m["mpn_accuracy"]),
                    pct(m["quantity_accuracy"]),
                    pct(m["f1"]),
                    m["model_calls"],
                    seconds(m["latency_ms"]["p95"]),
                ]
            )
    text = [
        "# Extraction ablations",
        "",
        "Post-selection regression diagnostics: one clean pipe table and one table plus an unresolved prose row, three authored expected items across two documents. These are explicit development diagnostics outside v1/v2 and were not used to revise the frozen configuration. Same qwen3:4b, full schema, context8192/output4096. TXT parsing avoids OCR as a confounder.",
        "",
        table(["Configuration", "MPN", "Quantity", "F1", "Model calls", "P95"], rows),
        "",
        "The old any-items fast path makes no model calls for the partial document. The new router selects its unresolved source block and makes a bounded call; real recovery quality is still poor. An empty generated row is preserved as unresolved and cannot be approved without review/correction. Fixture-provider merge tests separately prove that supported repairs retain reliable deterministic values; fixture results are excluded from measured quality.",
        "",
        "OCR-only contribution is measured with deterministic extraction in OCR_EXPERIMENTS.md; geometry reconstruction and association changes are coupled there, so it is not a pure recognition-only causal estimate. Model-size and prompt/schema contributions are separated within the matched development experiments in MODEL_BENCHMARKS.md. Wrong-row/column verifier tests isolate association rejection using authored proposals; no stand-alone quantitative association ablation is claimed. No cascade was selected or measured. There is no unsupported assertion that every code change caused the aggregate quality delta.",
        "",
    ]
    (ROOT / "EXTRACTION_ABLATIONS.md").write_text("\n".join(text), encoding="utf-8")


if __name__ == "__main__":
    final_results()
    ocr_results()
    model_results()
    ablation_results()
    print("Derived final, OCR, model and ablation reports from saved predictions.")
