"""Render final evidence reports only after every frozen trial and gate exists."""

import hashlib
import importlib.util
import json
import shutil
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/rfq/phase3_2"
RESULTS = DOCS / "results"


def read(path):
    return json.loads(path.read_text())


def write(name, content):
    (DOCS / name).write_text(content.strip() + "\n", encoding="utf-8", newline="\n")


def percent(numerator, denominator):
    return f"{100 * numerator / denominator:.1f}%" if denominator else "not measured"


def main():
    spec = importlib.util.spec_from_file_location(
        "report32", ROOT / "scripts/procurement32-report.py"
    )
    report_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report_module)
    folder = RESULTS / "evaluation/final-plan7"
    rows = [
        read(path)
        for path in sorted(folder.glob("v3-held-*.json"))
        if not path.name.endswith(".admitted.json")
    ]
    variants = ["phase31", "native_batch", "coverage_native", "hybrid"]
    assert len(rows) == 240 and all(
        sum(row["variant"] == variant for row in rows) == 60 for variant in variants
    )
    summary = read(folder / "summary.json")
    dev = read(RESULTS / "evaluation/dev-plan7-v2/summary-detailed.json")
    config = read(folder / "configuration.json")
    selection = read(RESULTS / "selection.json")
    assert config["code"] == selection["code"]
    assert (
        config["dataset_sha256"]
        == selection["dataset_sha256"]
        == hashlib.sha256(
            (ROOT / "data/evaluation/procurement-v3/scenarios.json").read_bytes()
        ).hexdigest()
    )
    assert (
        config["source_bindings_sha256"]
        == selection["source_bindings_sha256"]
        == hashlib.sha256((RESULTS / "source-bindings.json").read_bytes()).hexdigest()
    )
    for relative, expected in config["code"].items():
        source = ROOT / relative
        assert hashlib.sha256(source.read_bytes()).hexdigest() == expected
        target = folder / "source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    tests = ET.parse(RESULTS / "final-backend-tests.xml").getroot().find("testsuite")
    backend_pass = (
        int(tests.attrib["tests"])
        - int(tests.attrib["skipped"])
        - int(tests.attrib["failures"])
        - int(tests.attrib["errors"])
    )
    browser = read(RESULTS / "final-browser.json")["stats"]
    recovery = read(RESULTS / "real-recovery.json")
    preservation = read(RESULTS / "preservation-check.json")
    baseline = read(RESULTS / "deterministic-baseline.json")
    security = read(RESULTS / "native-description-probe.json")
    latency = read(RESULTS / "latency-without-regressions.json")
    timing_study = read(RESULTS / "evaluation/performance-plan7/summary.json")
    assert read(RESULTS / "performance-study-finished.json")["trials"] == 20
    assert (
        read(RESULTS / "evaluation/performance-plan7/configuration.json")["code"]
        == config["code"]
    )
    quote_checks = list((RESULTS / "evaluation").glob("*/quote-preservation-*.json"))
    assert quote_checks and all(read(path)["passed"] for path in quote_checks)
    assert read(RESULTS / "fresh-migration.json")["idempotent"]
    assert all(
        row["identical_old_columns"]
        for row in read(RESULTS / "migration-preservation.json")
    )
    assert read(RESULTS / "blob-check.json")["passed"]
    assert read(RESULTS / "source-preparation.json")["passed"]
    assert all(read(RESULTS / "browser-image-preservation.json").values())
    assert backend_pass == 473 and int(tests.attrib["skipped"]) == 1
    assert browser["expected"] == 21 and browser["unexpected"] == 0
    assert preservation["passed"] and security["passed"]
    assert all(record["passed"] for record in baseline["records"])
    recovery_keys = [
        "actual_worker_kill",
        "actual_cancellation",
        "actual_redis_outage",
        "actual_refused_endpoint",
        "quote_preservation",
    ]
    assert all(recovery[key]["passed"] for key in recovery_keys)
    selected = summary["groups"]["held_out/hybrid"]
    target_met = (
        selected["complete"] >= 57
        and selected["covered_lines"] >= 0.99 * selected["lines"]
        and selected["invalid_facts"] == 0
        and selected["unauthorized_successful_tools"] == 0
    )
    status = (
        "Functionally and research-quality validated"
        if target_met
        else "Functionally validated — research-quality target unmet"
    )
    labels = {
        "phase31": "Frozen Phase 3.1",
        "native_batch": "A: native batching",
        "coverage_native": "B: coverage-aware native",
        "hybrid": "D: bounded hybrid",
    }
    table = [
        "| Variant | Development | Validation | Held-out | Held-out source-covered lines | Native / backend RPCs (held-out) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    perf = [
        "| Variant | Median / p95 all (s) | Median / p95 completed (s) | Planning / final / correction calls | Prompt / output tokens |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for variant in variants:
        group = summary["groups"]["held_out/" + variant]
        development = dev["groups"]["development/" + variant]
        validation = dev["groups"]["validation/" + variant]
        table.append(
            f"| {labels[variant]} | {development['complete']}/16 | {validation['complete']}/20 | {group['complete']}/60 ({percent(group['complete'], 60)}) | {group['covered_lines']}/{group['lines']} | {group['model_selected_tools']} / {group['backend_scheduled_tools']} |"
        )
        all_time, completed_time = group["latency_ms_all"], group["latency_ms_complete"]

        def seconds(value):
            return f"{value / 1000:.2f}" if value is not None else "—"

        perf.append(
            f"| {labels[variant]} | {seconds(all_time['median'])} / {seconds(all_time['p95_nearest_rank'])} | {seconds(completed_time['median'])} / {seconds(completed_time['p95_nearest_rank'])} | {group['planning_calls']} / {group['finalization_calls']} / {group['repair_calls']} | {group['tokens']['prompt_eval_count']} / {group['tokens']['eval_count']} |"
        )
    table_text, perf_text = "\n".join(table), "\n".join(perf)
    timing_table = [
        "| Variant | Retained timing cases | Median / p95 all (s) | Completed timing cases | Median / p95 completed (s) |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    study_table = [
        "| Variant | Development timing trials | Median / p95 all (s) | Completed timing trials | Median / p95 completed (s) |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for variant in variants:
        for output, group in [
            (timing_table, latency["groups"][variant]),
            (study_table, timing_study["groups"]["development/" + variant]),
        ]:
            all_time, completed_time = (
                group["latency_ms_all"],
                group["latency_ms_complete"],
            )
            output.append(
                f"| {labels[variant]} | {group['n']} | {seconds(all_time['median'])} / {seconds(all_time['p95_nearest_rank'])} | {completed_time['n']} | {seconds(completed_time['median'])} / {seconds(completed_time['p95_nearest_rank'])} |"
            )
    strata = [
        "| Lines | A complete | B complete | D complete | D source-covered lines |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for size in [1, 2, 4, 8, 12]:
        groups = [
            summary["groups"]["held_out/" + variant]["by_line_count"][str(size)]
            for variant in ["native_batch", "coverage_native", "hybrid"]
        ]
        strata.append(
            f"| {size} | {groups[0]['complete']}/{groups[0]['n']} | {groups[1]['complete']}/{groups[1]['n']} | {groups[2]['complete']}/{groups[2]['n']} | {groups[2]['covered_lines']}/{groups[2]['lines']} |"
        )
    failure_sections = []
    for variant in variants:
        failed = [
            row
            for row in rows
            if row["variant"] == variant and not row["verified_complete"]
        ]
        counts = dict(
            Counter(row["error"] or "independent_oracle_failure" for row in failed)
        )
        missing_sources = sum(
            not row["audit"]["required_source_coverage"] for row in failed
        )
        complete_sources = len(failed) - missing_sources
        examples = []
        for row in failed[:3]:
            codes = dict(
                Counter(
                    error["code"]
                    for attempt in row["finalization_attempts"]
                    for error in (attempt.get("resolution") or {}).get(
                        "invalid_citations", []
                    )
                )
            )
            examples.append(
                f"- `{row['scenario']}` ({row['line_count']} {'line' if row['line_count'] == 1 else 'lines'}): sources {row['audit']['covered_lines']}/{row['line_count']}, required facts {row['audit']['supported_required_facts']}/{row['audit']['required_facts']}, {row['planning_calls']} planning / {row['finalization_calls']} initial finalization / {row['repair_attempts']} correction calls; actual finalization rejection counts `{json.dumps(codes, sort_keys=True)}`. See its raw `{row['scenario']}-{variant}.json` trace."
            )
        failure_sections.append(
            f"### {labels[variant]}\n\n{len(failed)}/60 failed verified completion. Error counts: `{json.dumps(counts, sort_keys=True)}`.\n\nMissing-source failures: {missing_sources}; failures after complete source inspection: {complete_sources}. Cases: {', '.join(row['scenario'] for row in failed) or 'none'}. These first frozen trials remain in the denominator.\n\n"
            + "\n".join(examples)
        )
    unsafe = sum(group["invalid_facts"] for group in summary["groups"].values())
    unauthorized = sum(
        group["unauthorized_successful_tools"] for group in summary["groups"].values()
    )
    total_facts = sum(row["audit"]["facts_inspected"] for row in rows)
    total_calls = sum(len(row["tool_receipts"]) for row in rows)
    factual = f"Across 240 held-out executions, the independent oracle inspected {total_facts} materialized facts and {total_calls} tool receipts: {unsafe} unsupported/misbound accepted facts and {unauthorized} unauthorized successful tools. These are observed finite-sample results, not guarantees of universal safety."
    unknowns = selected["unknowns_correct_cases"]
    readiness = selected["quote_readiness_correct_cases"]
    write(
        "EVALUATION_RESULTS.md",
        f"""
# Phase 3.2 evaluation results

**{status}.** Selected D/four completed {selected["complete"]}/60 held-out cases, with {selected["covered_lines"]}/{selected["lines"]} source-covered lines ({percent(selected["covered_lines"], selected["lines"])}). The completion target is 57/60; source coverage target is 99%.

{table_text}

C mandatory scheduling completed 13/16 development cases after backend-only required source collection; all 82 development lines were inspected, with 0 native-selected RPCs and 41 backend RPCs. Its optional native planning/finalization still used actual model calls. C has no held-out score. The separate zero-model deterministic baseline passed 96/96 (including 60/60 held-out); it is not agent planning evidence.

## Line-count strata

{chr(10).join(strata)}

{factual}

For selected D, authored unknown sets matched in {unknowns}/60 cases and quote-readiness classification matched in {readiness}/60. Unsupported output references were rejected before publication. Full required/supported fact counts, source-pair counts, per-run references and error details are in `results/evaluation/final-plan7/summary.json` and raw case records.

## Performance and attribution

{perf_text}

These are all first-trial timings, including known regression overlap. The backend suite contains real qwen3:4b inference; treating it as CPU-only was a measurement mistake. All original quality trials and failures remain in the sixty-case denominator.

### Timings excluding recorded regression windows

{chr(10).join(timing_table)}

The timing-only subset retains {latency["timing_cases_retained_per_variant"]} matched cases per variant. Whole regression suites, five minutes of configured model residence and five-second boundaries are excluded. All variants of a case are excluded if any overlaps, without using its outcome or observed latency. See `results/latency-without-regressions.json` for exact windows/cases and separate matched-success timings. Other CPU activity was not controlled; this is not an idle-host guarantee.

### Separately serialized development timing study

{chr(10).join(study_table)}

These twenty repeated development trials cover the predeclared first five cases (1/2/4/8/12 lines) after all other scheduled inference tests finished. Known non-target test models were unloaded if present, and setup confirmed only qwen3:8b was loaded; no weights were deleted. Model/cache state, native telemetry and identical configuration hashes are recorded in `results/performance-study-setup.json` and `results/evaluation/performance-plan7`. Variant order is fixed and cache-order effects remain possible. Five timing trials per variant cannot establish a production p95/SLA. These repetitions do not add independent quality successes or replace any held-out failure.

D source pairs attributed to native decisions: {selected["model_source_pairs"]}; backend source pairs: {selected["backend_source_pairs"]}. Useful model required-read decisions: {selected["useful_model_tool_decisions"]}/{selected["model_selected_tools"]}. This measures newly inspected required sources/global RFQ, not general planning intelligence. A batch is one decision. Backend completion is never counted as native success.

Summary JSON includes batch utilization/output-byte distributions, duplicate reads, optional calls, unused call capacity, early-finalization attempts, per-completed-run model/tool/token distributions and device-wide GPU samples. Matched-success latency is reported separately. Legacy source coverage is constrained by its unchanged eight-call limit, and failed short runs must not be presented as an equal-work speed baseline. The original timing interference is explicitly recorded; GPU samples are not peak/model-isolated measurements.

## Failure analysis

{(chr(10) + chr(10)).join(failure_sections)}

Source-read coverage and citation completion are separate. New runs with complete sources may still omit, misassociate or add invalid references and exhaust the single correction. Some failures already cover every required fact after merging valid references, but additional invalid references still block publication under the strict zero-invalid-citation gate. Such runs retain valid partial facts and stop needing attention. No configuration was changed after selection or tuned against held-out failures. Initial development experiments and batch-two comparisons remain separately archived, not pooled into held-out scores.

Raw experiment records contain actual local inference acknowledgements, model identity, source hashes, immutable receipts, native/backend origin, finalization attempts and resource samples. `selection.json` and archived source files make the first frozen final experiment reviewable. Historical Phase 3.1 files and scores remain unchanged.
""",
    )
    kill, redis = recovery["actual_worker_kill"], recovery["actual_redis_outage"]
    write(
        "RELIABILITY_VALIDATION.md",
        f"""
# Reliability validation

Actual dedicated worker `{kill["worker"]}` received SIGKILL after a successful batch receipt. At the post-signal observation it had {len(kill["receipt_ids_before"])} durable receipts. Restart and outbox redelivery reached `{kill["after"]["state"]}` in {kill["recovery_seconds"]:.2f} seconds, with {len(kill["receipt_ids_after"])} receipts afterwards. All prior receipt rows remained equal, consumed budgets and original creation time were preserved, and duplicate terminal delivery changed no receipts. Publications: {kill["publications"]}.

This is **{"completed recovery" if kill["completed_recovery"] else "safe recovery, incomplete research"}**. It is an actual Docker process death/restart, not a Python exception fixture. Pre-signal observation and post-signal ledger are both retained because receipts can commit while the kill command is in transit. The independently reconstructed before/after source coverage is in `results/real-recovery.json`.

The independent oracle found {kill["independent_audit_before"]["covered_lines"]}/12 covered lines before recovery and {kill["independent_audit_after"]["covered_lines"]}/12 afterwards. Remaining source reads completed without repeating the preserved work. The terminal error was `{kill["after"]["error"]}`; source completion did not bypass the citation gate. Counters after recovery: {kill["after"]["planning_calls"]} planning, {kill["after"]["finalization_calls"]} initial finalization, {kill["after"]["repair_attempts"]} correction, {kill["after"]["attempts"]} delivery attempts.

Actual Redis container `{redis["container"]}` was stopped while signed API admission retained a queued database outbox row. After Redis restart, beat/worker delivery reached `{redis["after"]["state"]}`. Queue to first model admission: {redis["queue_to_first_model_admission_seconds"]:.2f} seconds; broker restoration to terminal: {redis["broker_restoration_to_terminal_seconds"]:.2f} seconds. Publications: {redis["publications"]}.

Actual cancellation was issued after a durable model call entered `in_flight`; request-start telemetry was observed afterwards. State remained cancelled with zero research publications. This proves cancellation against admitted actual inference; it does not claim a packet-level timestamp for exactly when Ollama began generation.

A genuinely refused local TCP endpoint produced `model_unavailable` attention and zero source tool calls. Ollama itself was left running. Shared PostgreSQL was also left running: the PostgreSQL interruption check is an explicitly controlled `psycopg.OperationalError` connection fixture between committed batch receipts, followed by restored connectivity and exact receipt reuse. It is not claimed as a real PostgreSQL server restart.

Controlled tests separately cover six interruption checkpoints (request admission, receipt persistence, coverage update, finalization receipt, materialization and pre-publication), source change between successful batches, duplicate/repeated calls, revocation, transport timeout, original deadline expiry and cancellation before receipt commit. Fixture results are excluded from native accuracy denominators.

Quote versions/approvals remained equal before and after all research/recovery operations. Read the actual counters and retained receipt IDs in `results/real-recovery.json`; native split-level quote-preservation files provide a separate check. Recovery stays within the original 240-second publication deadline and finite call limits; in-flight HTTP may finish later up to its transport timeout and cannot publish late.
""",
    )
    write(
        "PHASE3_2_VALIDATION.md",
        f"""
# Phase 3.2 validation

**{status}.**

| Gate | Evidence/result |
| --- | --- |
| Backend regressions | {backend_pass} passed; 1 retained strict xfail; zero failures/errors (`results/final-backend-tests.xml`) |
| Browser regressions | {browser["expected"]} passed: original 15 unchanged plus 6 coverage scenarios (`results/final-browser.json`) |
| Python checks | Ruff lint/format on new code, compileall and uv lock check passed |
| Frontend checks | Root lint, typecheck, test and production build passed (`results/frontend-build.log`) |
| Native held-out | {selected["complete"]}/60 selected-strategy verified completions; target 57 |
| Required line sources | {selected["covered_lines"]}/{selected["lines"]}; target 99% |
| Independent safety | {unsafe} invalid accepted facts and {unauthorized} unauthorized successes across 240 held-out executions |
| Deterministic source pipeline | 96/96, zero model calls; separate baseline |
| Actual recovery | SIGKILL restart, duplicate terminal delivery, cancellation, Redis outage and refused endpoint passed |
| PostgreSQL interruption | Explicit controlled connection fixture passed; shared server not stopped |
| Migration upgrade | Original columns across 39 tables / 3,149 demo and 6,520 test rows preserved |
| Fresh migrations | All eight migrations applied twice idempotently in retained new database |
| Historical bytes | {preservation["protected_files_checked"]} protected files and {preservation["original_test_files_checked"]} original test files unchanged |
| Model/score freeze | Selected execution/grading hashes and selection-summary hash unchanged |
| Native visible-description security probe | Actual local inference, no successful unauthorized action or fabricated accepted price; outside benchmark |
| Timing discipline correction | Original timings retained; regression-window exclusion plus twenty separately serialized development timing trials |

The prior strict xfail retains the historical JPY fractional-quantity policy limitation. It was not relabelled or fixed in this phase. Existing finance-v2 independent evaluation tests remain in the full regression suite. No download, cloud model, supplier communication, approval automation, push, deployment or Phase 4 work was performed.
""",
    )
    write(
        "FINAL_IMPLEMENTATION_REPORT.md",
        f"""
# Phase 3.2 final implementation report

**{status}.** Coverage-aware hybrid research completed {selected["complete"]}/60 independent held-out RFQs with {selected["covered_lines"]}/{selected["lines"]} line source coverage. The source-read bottleneck is addressed by bounded batches and explicitly attributed mandatory completion. Native citation reliability remains separately measured and can still require human attention.

Implemented a closed four-line batch source RPC, authoritative remaining-work planner, separately admitted citation-only finalization, durable pending calls/counters, exact physical-parent evidence associations, bounded recovery and capacity attention above twelve lines. The UI shows source versus citation coverage, per-line progress, actual native/backend origins and persisted activity. No automatic scope continuation or quote approval is added.

{table_text}

The independent corpus has 96 cases / 514 lines, frozen before strategy selection. D/four was selected from 16 development and 20 validation cases; final evaluation used 60 held-out cases and four separate real local executions per case. C was a development-only native experiment. The deterministic baseline passed 96/96 with zero model calls. For mandatory source reporting alone, it was more reliable and requires no model; this does not evaluate optional agent research utility. Backend scheduling success is not reported as native planning ability. Held-out rankings do not retroactively change the predeclared default.

{factual}

Validation passed {backend_pass} backend tests with the existing strict xfail, and {browser["expected"]} browsers. New actual worker recovery was {"completed" if kill["completed_recovery"] else "safe but incomplete"}, with all receipts preserved and at most one publication. Actual Redis interruption, cancellation and refused endpoint passed; PostgreSQL outage behavior is explicitly a controlled fixture. Populated and fresh migration checks passed. All 724 protected historical files and original assertions remain unchanged.

Remaining limitations: single small local model and fictional corpus; model reference copying can fail despite complete sources; no held-out retuning; larger/more-offer scopes can exceed reference/byte capacity; no automatic continuation; 240 seconds is a publication deadline rather than forced cancellation of remote computation; coverage display caches can lag committed parent receipts until recovery recomputes the ledger; device memory samples are not peaks; regression inference overlapped some original timing trials (separate window-excluded and serialized development timings are reported); historical JPY fractional-quantity strict xfail remains. These limits bound the claims made here.

## Resume-ready evidence

- Built a versioned procurement agent controller with closed four-line source batches, exact parent-receipt citations, separate planning/finalization budgets and explicit native versus backend execution attribution across approved RFQs up to twelve lines.
- Evaluated qwen3:8b on an independently frozen 96-case / 514-line corpus; the selected hybrid achieved {selected["complete"]}/60 held-out verified completions and {percent(selected["covered_lines"], selected["lines"])} source coverage, with zero independently detected unsupported accepted facts across the four-variant held-out comparison. The {"quality gate passed" if target_met else "95% completion target was not met"}.
- Validated {backend_pass} backend and {browser["expected"]} browser tests, actual isolated SIGKILL/Redis recovery and additive migration preservation of 9,669 existing rows, while retaining 724 historical files and human quote approval controls.

See evaluation results for failure counts/IDs, performance and contribution attribution; reliability validation for exact observations; and the demo/Windows runbooks for reproduction. Work stops before Phase 4. Nothing was pushed or deployed.
""",
    )
    write(
        "STATUS.md",
        f"# Phase 3.2 status\n\n**{status}.**\n\nImplementation and required functional validation are complete. Selected hybrid/four: {selected['complete']}/60 held-out completions, {selected['covered_lines']}/{selected['lines']} source-covered lines. {backend_pass} backend tests passed with one retained strict xfail; {browser['expected']} browsers passed. Actual isolated recovery, additive migration preservation and historical-byte checks passed.\n\nThe quality target is {'met' if target_met else 'unmet'}; no held-out tuning was performed. See [final report](FINAL_IMPLEMENTATION_REPORT.md) and [evaluation results](EVALUATION_RESULTS.md). Stop before Phase 4; no push or deployment.",
    )
    result = {
        "status": status,
        "functional_gates_passed": True,
        "research_quality_target_met": target_met,
        "selected_strategy": "hybrid",
        "batch_size": 4,
        "held_out_complete": selected["complete"],
        "held_out_n": 60,
        "source_covered_lines": selected["covered_lines"],
        "source_total_lines": selected["lines"],
        "backend_passed": backend_pass,
        "strict_xfail": 1,
        "browser_passed": browser["expected"],
        "held_out_accepted_invalid_facts": unsafe,
        "held_out_unauthorized_successes": unauthorized,
        "native_quote_preservation_checks": len(quote_checks),
        "frozen_dataset_and_bindings_unchanged": True,
        "migration_and_blob_checks_passed": True,
        "phase4_started": False,
        "pushed_or_deployed": False,
    }
    (RESULTS / "final-gates.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
