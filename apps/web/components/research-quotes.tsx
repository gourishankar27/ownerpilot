"use client";

import {
  cloneElement,
  isValidElement,
  useCallback,
  useEffect,
  useState,
  type FormEvent,
} from "react";
import type {
  CommercialOffer,
  ProcurementLine,
  ProcurementQuote,
  ProcurementSnapshot,
  QuotePolicy,
  ResearchRun,
  RfqDetail,
  ToolReceipt,
} from "@ownerpilot/contracts";
import { rfqApi } from "@/lib/rfq-api";
import { ResearchCoverage } from "./research-coverage";

const box =
  "rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900";
const control =
  "w-full min-w-0 rounded-lg border border-slate-300 bg-transparent px-3 py-2 dark:border-slate-600";
const button =
  "rounded-full bg-teal-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40";
const readable = (value: string) => value.replaceAll("_", " ");
const initialPolicy: QuotePolicy = {
  currency: "USD",
  shipping: null,
  tax_rate: null,
  tax_basis: null,
  valid_until: null,
  pricing: { mode: "markup", rate: "0", discount: "0", surplus: null },
};
function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="grid gap-1 text-sm font-medium">
      {label}
      {isValidElement<{ "aria-label"?: string }>(children)
        ? cloneElement(children, { "aria-label": label })
        : children}
    </label>
  );
}
function Evidence({ value }: { value: unknown }) {
  return (
    <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-slate-50 p-3 text-xs dark:bg-slate-950">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function OfferForm({
  line,
  save,
  busy,
}: {
  line: ProcurementLine;
  save: (
    commercial: CommercialOffer,
    reason: string,
    supersedes: string | null,
  ) => Promise<void>;
  busy: boolean;
}) {
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const get = (name: string) => String(form.get(name) ?? "").trim();
    const commercial: CommercialOffer = {
      supplier: get("supplier"),
      supplier_sku: get("sku") || null,
      price: get("price") || null,
      currency: get("currency") || null,
      price_basis: (get("basis") || null) as CommercialOffer["price_basis"],
      pack_size: get("pack") ? Number(get("pack")) : null,
      minimum_units: get("moq") || null,
      availability: get("availability") as CommercialOffer["availability"],
      lead_time_days: get("lead") ? Number(get("lead")) : null,
      observed_on: get("observed") || null,
      valid_until: get("valid") || null,
      source_reference: get("source"),
      breaks:
        get("breakQty") && get("breakPrice")
          ? [{ minimum_units: get("breakQty"), price: get("breakPrice") }]
          : [],
    };
    await save(commercial, get("reason"), get("supersedes") || null);
  }
  return (
    <details className="rounded-xl border p-3">
      <summary className="cursor-pointer font-medium">
        Attest commercial offer for{" "}
        {line.selection.resolution?.data.product?.mpn ?? "selected product"}
      </summary>
      <p className="my-3 text-sm text-amber-800 dark:text-amber-300">
        This records your source-backed attestation. It is not a verified live
        supplier feed. Leave unknown values empty.
      </p>
      <form
        onSubmit={submit}
        className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
      >
        <Field label="Supersedes prior attestation">
          <select className={control} name="supersedes" defaultValue="">
            <option value="">New independent offer</option>
            {line.offers.attestations.map((offer) => (
              <option key={offer.id} value={offer.id}>
                {offer.data.commercial.supplier} ·{" "}
                {offer.data.commercial.price ?? "Unknown price"} ·{" "}
                {offer.id.slice(0, 8)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Supplier">
          <input className={control} name="supplier" required maxLength={160} />
        </Field>
        <Field label="Supplier SKU">
          <input className={control} name="sku" maxLength={160} />
        </Field>
        <Field label="Supplier price">
          <input
            className={control}
            name="price"
            inputMode="decimal"
            placeholder="Unknown"
          />
        </Field>
        <Field label="Offer currency">
          <select className={control} name="currency" defaultValue="">
            <option value="">Unknown</option>
            {["USD", "EUR", "GBP", "INR", "JPY"].map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </Field>
        <Field label="Price basis">
          <select className={control} name="basis" defaultValue="">
            <option value="">Unknown</option>
            <option value="each">Per individual unit</option>
            <option value="pack">Per pack</option>
          </select>
        </Field>
        <Field label="Units per pack">
          <input
            className={control}
            name="pack"
            type="number"
            min="1"
            max="1000000"
          />
        </Field>
        <Field label="Minimum units to purchase">
          <input className={control} name="moq" inputMode="decimal" />
        </Field>
        <Field label="Availability statement">
          <select
            className={control}
            name="availability"
            defaultValue="unknown"
          >
            <option value="unknown">Unknown</option>
            <option value="available">Available according to source</option>
            <option value="unavailable">Unavailable</option>
          </select>
        </Field>
        <Field label="Source lead time in days">
          <input
            className={control}
            name="lead"
            type="number"
            min="0"
            max="3650"
          />
        </Field>
        <Field label="Source observed on">
          <input className={control} name="observed" type="date" />
        </Field>
        <Field label="Offer valid until">
          <input className={control} name="valid" type="date" />
        </Field>
        <Field label="Quantity break minimum units">
          <input className={control} name="breakQty" inputMode="decimal" />
        </Field>
        <Field label="Quantity break price">
          <input className={control} name="breakPrice" inputMode="decimal" />
        </Field>
        <Field label="Commercial source reference">
          <input className={control} name="source" required maxLength={1000} />
        </Field>
        <Field label="Offer attestation reason">
          <input
            className={control}
            name="reason"
            required
            minLength={5}
            maxLength={1000}
          />
        </Field>
        <div className="self-end">
          <button className={button} disabled={busy}>
            Record user attestation
          </button>
        </div>
      </form>
    </details>
  );
}

export function ResearchQuotes({
  workspace,
  detail,
}: {
  workspace: string;
  detail: RfqDetail | null;
}) {
  const [source, setSource] = useState<ProcurementSnapshot | null>(null);
  const [quotes, setQuotes] = useState<ProcurementQuote[]>([]);
  const [quote, setQuote] = useState<ProcurementQuote | null>(null);
  const [runs, setRuns] = useState<ResearchRun[]>([]);
  const [run, setRun] = useState<ResearchRun | null>(null);
  const [receipts, setReceipts] = useState<ToolReceipt[]>([]);
  const [policy, setPolicy] = useState<QuotePolicy>(initialPolicy);
  const [choices, setChoices] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<unknown>(null);
  const [comparison, setComparison] = useState<{
    line: string;
    data: unknown;
  } | null>(null);
  const approved = detail?.status === "approved";
  const rfq = detail?.id;
  const refresh = useCallback(async () => {
    if (!approved || !rfq) return;
    const [snapshot, rows, research] = await Promise.all([
      rfqApi<ProcurementSnapshot>(`rfqs/${rfq}/selections`, workspace),
      rfqApi<ProcurementQuote[]>(`rfqs/${rfq}/quotes`, workspace),
      rfqApi<ResearchRun[]>(`rfqs/${rfq}/research`, workspace),
    ]);
    setSource(snapshot);
    setQuotes(rows);
    setRuns(research);
  }, [workspace, rfq, approved]);
  useEffect(() => {
    let active = true;
    if (approved && rfq)
      void Promise.all([
        rfqApi<ProcurementSnapshot>(`rfqs/${rfq}/selections`, workspace),
        rfqApi<ProcurementQuote[]>(`rfqs/${rfq}/quotes`, workspace),
        rfqApi<ResearchRun[]>(`rfqs/${rfq}/research`, workspace),
      ])
        .then(([snapshot, rows, research]) => {
          if (active) {
            setSource(snapshot);
            setQuotes(rows);
            setRuns(research);
          }
        })
        .catch((e) => {
          if (active) setMessage(e.message);
        });
    return () => {
      active = false;
    };
  }, [workspace, rfq, approved]);
  const activeRun =
    run &&
    ["queued", "planning", "executing_tools", "verifying"].includes(run.state);
  useEffect(() => {
    if (!activeRun || !run) return;
    const timer = setInterval(() => {
      void Promise.all([
        rfqApi<ResearchRun>(`agent-runs/${run.id}`, workspace),
        rfqApi<ToolReceipt[]>(`agent-runs/${run.id}/tools`, workspace),
      ])
        .then(([value, tools]) => {
          setRun(value);
          setReceipts(tools);
          if (
            !["queued", "planning", "executing_tools", "verifying"].includes(
              value.state,
            )
          )
            void refresh();
        })
        .catch((e) => setMessage(e.message));
    }, 1500);
    return () => clearInterval(timer);
  }, [activeRun, run, workspace, refresh]);
  async function act(work: () => Promise<void>) {
    setBusy(true);
    setMessage("");
    try {
      await work();
    } catch (e) {
      setMessage(
        e instanceof Error ? e.message : "Procurement operation failed",
      );
    } finally {
      setBusy(false);
    }
  }
  async function openQuote(id: string) {
    const value = await rfqApi<ProcurementQuote>(`quotes/${id}`, workspace);
    setQuote(value);
    setPolicy(value.policy);
    setChoices(value.offer_choices);
    setReviewed(false);
    setHistory(null);
  }
  async function openRun(id: string) {
    const [value, tools] = await Promise.all([
      rfqApi<ResearchRun>(`agent-runs/${id}`, workspace),
      rfqApi<ToolReceipt[]>(`agent-runs/${id}/tools`, workspace),
    ]);
    setRun(value);
    setReceipts(tools);
  }
  async function saveQuote(newVersion = false) {
    if (!rfq) return;
    const path = quote
      ? newVersion
        ? `quotes/${quote.id}/new-version`
        : `quotes/${quote.id}`
      : `rfqs/${rfq}/quotes`;
    const value = await rfqApi<ProcurementQuote>(path, workspace, {
      method: quote && !newVersion ? "PATCH" : "POST",
      body: JSON.stringify({
        policy,
        offer_choices: choices,
        reason,
        ...(quote && !newVersion ? { revision: quote.revision } : {}),
      }),
    });
    setQuote(value);
    setReviewed(false);
    await refresh();
    setMessage("Internal draft saved with deterministic calculations.");
  }
  async function decision(action: string) {
    if (!quote) return;
    const value = await rfqApi<ProcurementQuote>(
      `quotes/${quote.id}/${action}`,
      workspace,
      {
        method: "POST",
        body: JSON.stringify({
          revision: quote.revision,
          reason,
          inputs_reviewed: reviewed,
        }),
      },
    );
    setQuote(value);
    setReviewed(false);
    await refresh();
    setMessage(`Quote ${readable(value.state)}.`);
  }
  if (!approved) return null;
  const locked =
    quote &&
    ["approved_internal", "rejected", "superseded", "under_review"].includes(
      quote.state,
    );
  return (
    <section
      aria-label="Procurement research and quotes"
      className={`${box} space-y-6`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-teal-700 dark:text-teal-300">
            Approved RFQ · local research
          </p>
          <h2 className="mt-1 text-2xl font-semibold">
            Research & internal quotations
          </h2>
          <p className="mt-2 max-w-3xl text-sm text-slate-600 dark:text-slate-300">
            Resolve reviewed products, document commercial evidence, and prepare
            an internal quote. Supplier availability and prices remain unknown
            until supported by a dated source.
          </p>
        </div>
        <button
          className={button}
          disabled={busy}
          onClick={() => void act(refresh)}
        >
          Refresh reviewed selections
        </button>
      </div>
      {message && (
        <p
          role="status"
          className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-slate-900"
        >
          {message}
        </p>
      )}
      <div className="space-y-4">
        <h3 className="text-lg font-semibold">
          1. Reviewed selections & commercial evidence
        </h3>
        {source?.lines.map((line) => (
          <article
            key={line.line_id}
            className="space-y-3 rounded-xl border p-4"
          >
            <div className="flex flex-wrap justify-between gap-2">
              <div>
                <h4 className="font-semibold">
                  {line.fields.description?.value ?? "Approved line"}
                </h4>
                <p className="text-sm">
                  {line.quantity ?? "Unknown quantity"}{" "}
                  {line.unit ?? "Unknown unit"} ·{" "}
                  {readable(line.selection.state)}
                </p>
              </div>
              {line.selection.resolution?.data.product && (
                <p className="text-sm font-medium">
                  {line.selection.resolution.data.product.manufacturer} ·{" "}
                  {line.selection.resolution.data.product.mpn}
                </p>
              )}
            </div>
            <details>
              <summary className="cursor-pointer text-sm underline">
                Reviewed identity, compatibility & source evidence
              </summary>
              <Evidence
                value={{
                  resolution: line.selection.resolution,
                  fields: line.fields,
                }}
              />
            </details>
            {line.selection.current_run_id && (
              <form
                className="grid gap-3 sm:grid-cols-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  const form = new FormData(event.currentTarget);
                  const candidate = line.selection.candidates.find(
                    (c) => c.id === form.get("product"),
                  );
                  const sourceRef = candidate?.sources[0] as
                    | { version_id: string }
                    | undefined;
                  void act(async () => {
                    await rfqApi(
                      `rfqs/${rfq}/line-items/${line.line_id}/selection-resolution`,
                      workspace,
                      {
                        method: "POST",
                        body: JSON.stringify({
                          expected_revision: line.selection.revision,
                          run_id: line.selection.current_run_id,
                          decision: candidate ? "select" : "no_match",
                          product_id: candidate?.id ?? null,
                          version_id: sourceRef?.version_id ?? null,
                          alternative_attested:
                            form.get("alternative") === "on",
                          reason: String(form.get("resolutionReason")),
                        }),
                      },
                    );
                    await refresh();
                  });
                }}
              >
                <Field label="Final reviewed product">
                  <select
                    name="product"
                    className={control}
                    defaultValue={
                      line.selection.resolution?.data.product_id ?? ""
                    }
                  >
                    <option value="">Explicit no-match</option>
                    {line.selection.candidates
                      .filter((c) =>
                        ["exact", "compatible_alternative"].includes(
                          c.compatibility.status,
                        ),
                      )
                      .map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.product.manufacturer} {c.product.mpn} ·{" "}
                          {readable(c.compatibility.status)}
                        </option>
                      ))}
                  </select>
                </Field>
                <Field label="Selection resolution reason">
                  <input
                    className={control}
                    name="resolutionReason"
                    required
                    minLength={5}
                    maxLength={1000}
                  />
                </Field>
                <label className="text-sm">
                  <input type="checkbox" name="alternative" /> I reviewed
                  suitability of a compatible alternative. Key equality alone is
                  not compatibility certification.
                </label>
                <button className={button} disabled={busy}>
                  Record authorized resolution
                </button>
              </form>
            )}
            {line.selection.state === "resolved" && (
              <>
                <div className="grid gap-3 md:grid-cols-2">
                  {line.offers.attestations.map((offer) => (
                    <div
                      key={offer.id}
                      className="rounded-lg bg-teal-50 p-3 text-sm dark:bg-teal-950"
                    >
                      <p className="font-semibold">
                        {offer.data.commercial.supplier} · user attested
                      </p>
                      <p>
                        {offer.data.commercial.price ?? "Unknown price"}{" "}
                        {offer.data.commercial.currency ?? "Unknown currency"} /{" "}
                        {offer.data.commercial.price_basis ?? "unknown basis"}
                      </p>
                      <p>
                        {readable(offer.freshness)} ·{" "}
                        {offer.data.commercial.availability}
                      </p>
                      {offer.commercial_review_state && (
                        <p className="font-semibold text-amber-800 dark:text-amber-300">
                          {readable(offer.commercial_review_state)} · requires
                          commercial resolution
                        </p>
                      )}
                      <p className="break-words">
                        Source: {offer.data.commercial.source_reference}
                      </p>
                      <p>
                        Observed{" "}
                        {offer.data.commercial.observed_on ?? "unknown"} · valid
                        through {offer.data.commercial.valid_until ?? "unknown"}
                      </p>
                      <details>
                        <summary>Attestation provenance</summary>
                        <Evidence value={offer} />
                      </details>
                    </div>
                  ))}
                </div>
                <details>
                  <summary className="cursor-pointer text-sm">
                    Imported catalog offers ({line.offers.imported.length}) ·
                    freshness unknown
                  </summary>
                  <Evidence value={line.offers.imported} />
                </details>
                <OfferForm
                  line={line}
                  busy={busy}
                  save={(commercial, attestationReason, supersedes) =>
                    act(async () => {
                      await rfqApi("supplier-offers/attestations", workspace, {
                        method: "POST",
                        body: JSON.stringify({
                          resolution_id: line.selection.resolution?.id,
                          commercial,
                          reason: attestationReason,
                          supersedes_id: supersedes,
                        }),
                      });
                      await refresh();
                      setMessage("User-attested commercial offer recorded.");
                    })
                  }
                />
                <button
                  className="rounded-lg border px-3 py-2 text-sm"
                  disabled={busy}
                  onClick={() =>
                    void act(async () => {
                      const data = await rfqApi(
                        `supplier-offers/resolutions/${line.selection.resolution?.id}/comparison`,
                        workspace,
                      );
                      setComparison({ line: line.line_id, data });
                    })
                  }
                >
                  Compare attested offers
                </button>
                {comparison?.line === line.line_id && (
                  <details open>
                    <summary>
                      Attested price comparison · same currency and purchasing
                      basis only
                    </summary>
                    <Evidence value={comparison.data} />
                  </details>
                )}
              </>
            )}
          </article>
        ))}
      </div>
      <section className="space-y-3" aria-label="Local agent research">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-lg font-semibold">2. Local agent research</h3>
          <button
            className={button}
            disabled={busy || !!activeRun}
            onClick={() =>
              void act(async () => {
                const value = await rfqApi<ResearchRun>(
                  `rfqs/${rfq}/research`,
                  workspace,
                  {
                    method: "POST",
                    body: JSON.stringify({
                      revision: detail.revision,
                      idempotency_key: crypto.randomUUID(),
                      quote_id: quote?.id ?? null,
                    }),
                  },
                );
                setRun(value);
                setReceipts([]);
                await refresh();
              })
            }
          >
            Start local research
          </button>
        </div>
        <p className="text-sm">
          Read-only tools · bounded local model calls · every observation must
          cite a tool receipt. Research cannot approve or submit a quote.
        </p>
        <div className="flex flex-wrap gap-2">
          {runs.map((item) => (
            <button
              className="rounded-lg border px-3 py-2 text-sm"
              key={item.id}
              onClick={() => void act(() => openRun(item.id))}
            >
              {readable(item.state)} · {item.id.slice(0, 8)}
            </button>
          ))}
        </div>
        {run && (
          <div className="space-y-3 rounded-xl border p-4">
            <p role="status">
              Research {readable(run.state)} ·{" "}
              {run.metadata.planning_policy
                ? `Planning ${run.planning_calls ?? 0}/4 · Finalization ${run.finalization_calls ?? 0}/1`
                : `${run.turns ?? 0}/4`}{" "}
              {run.metadata.planning_policy
                ? ""
                : run.metadata.claim_schema
                  ? "initial model turns"
                  : "planning turns"}
              · {receipts.length}/8 tool calls
            </p>
            <p className="break-all text-xs">
              {run.metadata.model} · digest {run.metadata.digest} ·{" "}
              {run.metadata.prompt_version}
            </p>
            <p className="text-sm">
              {run.metadata.claim_schema === "research-citation-only/2"
                ? "Citation-only research · values resolved by the backend"
                : "Legacy research · original exact-value verification"}
            </p>
            {run.metadata.claim_schema && (
              <p className="text-sm">
                Citation corrections {run.repair_attempts ?? 0}/1 · delivery
                attempt {run.attempts ?? 0}
                {run.diagnostics?.stage
                  ? ` · ${run.state === "complete" ? "published" : readable(run.diagnostics.stage)}`
                  : ""}
                {run.diagnostics?.recovered
                  ? " · resumed from durable checkpoints"
                  : ""}
              </p>
            )}
            {run.error && (
              <p className="text-sm text-amber-700 dark:text-amber-300">
                {run.error}
              </p>
            )}
            <ResearchCoverage run={run} receipts={receipts} />
            {activeRun && (
              <button
                className={button}
                onClick={() =>
                  void act(async () => {
                    await rfqApi(`agent-runs/${run.id}/cancel`, workspace, {
                      method: "POST",
                    });
                    await openRun(run.id);
                  })
                }
              >
                Cancel research
              </button>
            )}
            <ol className="space-y-2">
              {receipts.map((receipt) => (
                <li key={receipt.id} className="rounded-lg border p-3 text-sm">
                  <details>
                    <summary className="cursor-pointer">
                      {receipt.ordinal}. {receipt.tool} · {receipt.status} ·{" "}
                      {Math.round(Number(receipt.duration_ms))} ms
                    </summary>
                    <p className="my-2 break-all">
                      Receipt {receipt.id} · {receipt.policy}
                    </p>
                    {receipt.execution_origin && (
                      <p>
                        {receipt.execution_origin === "backend_scheduled"
                          ? "Backend scheduled"
                          : receipt.execution_origin === "model_selected"
                            ? "Native model-selected"
                            : "Legacy native model"}
                        {receipt.call_details?.line_ids
                          ? ` · ${receipt.call_details.line_ids.length} scoped lines · ${receipt.call_details.result_bytes ?? 0} result bytes`
                          : ""}
                      </p>
                    )}
                    {receipt.error && <p>{receipt.error}</p>}
                    <Evidence
                      value={{
                        arguments: receipt.arguments,
                        result: receipt.result,
                      }}
                    />
                  </details>
                </li>
              ))}
            </ol>
            {run.result && (
              <>
                <h4 className="font-semibold">Verified observations</h4>
                {run.result.protocol && (
                  <div
                    className="space-y-2 text-sm"
                    aria-label="Research coverage"
                  >
                    <p className="font-semibold">
                      Research{" "}
                      {run.state === "complete" && run.result.complete
                        ? "complete and published"
                        : "incomplete or awaiting publication"}
                      {run.result.partial ? " · partial evidence saved" : ""}
                    </p>
                    <p>
                      Quote inputs{" "}
                      {run.result.quote_ready
                        ? "ready for human review"
                        : "require human follow-up"}
                      . Research does not approve a quote.
                    </p>
                    {run.result.repaired && (
                      <p>Citations corrected using existing receipts.</p>
                    )}
                    {!!run.result.invalid_citations?.length &&
                      (!run.metadata.planning_policy ||
                        (run.finalization_calls ?? 0) > 0) && (
                        <p role="alert">
                          Rejected citations:{" "}
                          {run.result.invalid_citations
                            .map((item) => readable(item.code))
                            .join(", ")}
                        </p>
                      )}
                    {run.result.coverage?.lines.map((line) => (
                      <details
                        key={line.line_id}
                        className="rounded-lg border p-3"
                      >
                        <summary>
                          Line {line.line_id.slice(0, 8)} ·{" "}
                          {line.complete
                            ? "coverage complete"
                            : "coverage incomplete"}{" "}
                          · {readable(line.selection_state)}
                        </summary>
                        {!!line.missing_tools.length && (
                          <p>
                            Sources still needed:{" "}
                            {line.missing_tools.join(", ")}
                          </p>
                        )}
                        {!!line.missing_citations.length && (
                          <p>
                            {line.missing_citations.length} required citations
                            missing
                          </p>
                        )}
                        {line.unknowns.map((item, index) => (
                          <p key={index}>
                            Unknown {readable(item.field)}
                            {item.offer_id
                              ? ` · offer ${item.offer_id.slice(0, 8)}`
                              : ""}{" "}
                            · {readable(item.state)}
                          </p>
                        ))}
                        {line.commercial_review.map((item) => (
                          <p key={item.offer_id}>
                            Offer {item.offer_id.slice(0, 8)} ·{" "}
                            {readable(item.state)}
                          </p>
                        ))}
                      </details>
                    ))}
                    {!!run.result.coverage?.quote_issues.length && (
                      <p>
                        Quote follow-up:{" "}
                        {run.result.coverage.quote_issues
                          .map(readable)
                          .join(", ")}
                      </p>
                    )}
                  </div>
                )}
                {run.result.claims.map((claim, index) => (
                  <div
                    className="break-words rounded-lg border p-3 text-sm"
                    key={index}
                  >
                    {claim.field_type && (
                      <span className="font-medium">
                        {readable(claim.field_type)} ·{" "}
                      </span>
                    )}
                    {claim.pointer}:{" "}
                    <strong>{String(claim.value ?? "Unknown")}</strong> ·{" "}
                    <span className="text-xs">receipt {claim.receipt_id}</span>
                    {claim.field_type && (
                      <details className="mt-2">
                        <summary>Source and entity associations</summary>
                        <Evidence
                          value={{
                            line_id: claim.line_id,
                            product_id: claim.product_id,
                            offer_id: claim.offer_id,
                            catalog_version: claim.catalog_version,
                            source_fingerprint: claim.source_fingerprint,
                            source_class: claim.data_class,
                          }}
                        />
                      </details>
                    )}
                  </div>
                ))}
                {run.result.limitations.map((text) => (
                  <p className="text-xs" key={text}>
                    {text}
                  </p>
                ))}
              </>
            )}
          </div>
        )}
      </section>
      <section className="space-y-4" aria-label="Internal quote builder">
        <div className="flex flex-wrap justify-between gap-3">
          <h3 className="text-lg font-semibold">3. Internal quote builder</h3>
          <button
            className="rounded-lg border px-3 py-2 text-sm"
            onClick={() => {
              setQuote(null);
              setPolicy(initialPolicy);
              setChoices({});
              setReviewed(false);
              setHistory(null);
            }}
          >
            Start new draft
          </button>
        </div>
        <div className="flex flex-wrap gap-2">
          {quotes.map((item) => (
            <button
              className="rounded-lg border px-3 py-2 text-sm"
              key={item.id}
              onClick={() => void act(() => openQuote(item.id))}
            >
              {readable(item.state)} ·{" "}
              {item.calculation.grand_total ?? "Incomplete"}{" "}
              {item.calculation.currency} · {item.id.slice(0, 8)}
            </button>
          ))}
        </div>
        {quote && (
          <p className="text-sm font-semibold">
            Internal quote {quote.id.slice(0, 8)} · revision {quote.revision} ·{" "}
            {readable(quote.state)}
            {quote.approved_by ? ` · approved by ${quote.approved_by}` : ""}
          </p>
        )}
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            void act(() => saveQuote());
          }}
        >
          <fieldset
            disabled={!!locked || busy}
            className="space-y-4 disabled:opacity-60"
          >
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Field label="Quote currency">
                <select
                  className={control}
                  value={policy.currency}
                  onChange={(e) =>
                    setPolicy({
                      ...policy,
                      currency: e.target.value as QuotePolicy["currency"],
                    })
                  }
                >
                  {["USD", "EUR", "GBP", "INR", "JPY"].map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
              </Field>
              <Field label="Pricing method">
                <select
                  className={control}
                  value={policy.pricing.mode}
                  onChange={(e) =>
                    setPolicy({
                      ...policy,
                      pricing: {
                        ...policy.pricing,
                        mode: e.target.value as "markup" | "margin",
                      },
                    })
                  }
                >
                  <option value="markup">Markup on cost</option>
                  <option value="margin">Gross margin on selling price</option>
                </select>
              </Field>
              <Field label="Pricing rate (0.20 = 20%)">
                <input
                  className={control}
                  value={policy.pricing.rate}
                  onChange={(e) =>
                    setPolicy({
                      ...policy,
                      pricing: { ...policy.pricing, rate: e.target.value },
                    })
                  }
                  required
                  inputMode="decimal"
                />
              </Field>
              <Field label="Discount rate (0 = none)">
                <input
                  className={control}
                  value={policy.pricing.discount}
                  onChange={(e) =>
                    setPolicy({
                      ...policy,
                      pricing: { ...policy.pricing, discount: e.target.value },
                    })
                  }
                  required
                  inputMode="decimal"
                />
              </Field>
              <Field label="Shipping amount">
                <input
                  className={control}
                  placeholder="Unknown; enter 0 if reviewed as free"
                  value={policy.shipping ?? ""}
                  onChange={(e) =>
                    setPolicy({ ...policy, shipping: e.target.value || null })
                  }
                  inputMode="decimal"
                />
              </Field>
              <Field label="Tax rate (0 = reviewed zero)">
                <input
                  className={control}
                  value={policy.tax_rate ?? ""}
                  onChange={(e) =>
                    setPolicy({ ...policy, tax_rate: e.target.value || null })
                  }
                  inputMode="decimal"
                />
              </Field>
              <Field label="Tax basis">
                <select
                  className={control}
                  value={policy.tax_basis ?? ""}
                  onChange={(e) =>
                    setPolicy({
                      ...policy,
                      tax_basis: (e.target.value ||
                        null) as QuotePolicy["tax_basis"],
                    })
                  }
                >
                  <option value="">Unresolved</option>
                  <option value="subtotal">Discounted subtotal</option>
                  <option value="subtotal_plus_shipping">
                    Discounted subtotal + shipping
                  </option>
                </select>
              </Field>
              <Field label="Quote valid until">
                <input
                  className={control}
                  type="date"
                  value={policy.valid_until ?? ""}
                  onChange={(e) =>
                    setPolicy({
                      ...policy,
                      valid_until: e.target.value || null,
                    })
                  }
                />
              </Field>
              <Field label="Pack / MOQ surplus policy">
                <select
                  className={control}
                  value={policy.pricing.surplus ?? ""}
                  onChange={(e) =>
                    setPolicy({
                      ...policy,
                      pricing: {
                        ...policy.pricing,
                        surplus: (e.target.value ||
                          null) as QuotePolicy["pricing"]["surplus"],
                      },
                    })
                  }
                >
                  <option value="">Requires review if surplus</option>
                  <option value="allocate_purchase_cost">
                    Allocate full purchase cost to requested units
                  </option>
                  <option value="bill_purchased">
                    Bill all purchased units
                  </option>
                </select>
              </Field>
            </div>
            {source?.lines.map((line) => (
              <Field
                key={line.line_id}
                label={`Quote offer · ${line.fields.description?.value ?? line.line_id}`}
              >
                <select
                  className={control}
                  value={choices[line.line_id] ?? ""}
                  onChange={(e) =>
                    setChoices((previous) => {
                      const next = { ...previous };
                      if (e.target.value) next[line.line_id] = e.target.value;
                      else delete next[line.line_id];
                      return next;
                    })
                  }
                >
                  <option value="">
                    Unresolved · no commercial offer selected
                  </option>
                  {line.offers.attestations.map((o) => (
                    <option
                      key={o.id}
                      value={o.id}
                      disabled={!!o.commercial_review_state}
                    >
                      {o.data.commercial.supplier} ·{" "}
                      {o.data.commercial.price ?? "Unknown price"}{" "}
                      {o.data.commercial.currency ?? ""} ·{" "}
                      {readable(o.commercial_review_state ?? o.freshness)}
                    </option>
                  ))}
                </select>
              </Field>
            ))}
          </fieldset>
          <Field label="Quote change / review reason">
            <input
              className={control}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              required
              minLength={5}
              maxLength={1000}
            />
          </Field>
          {!locked && (
            <button className={button} disabled={busy}>
              Save & calculate internal draft
            </button>
          )}
          {quote &&
            ["approved_internal", "rejected", "superseded"].includes(
              quote.state,
            ) && (
              <button
                type="button"
                className={button}
                disabled={busy || reason.length < 5}
                onClick={() => void act(() => saveQuote(true))}
              >
                Create new draft version
              </button>
            )}
        </form>
        {quote && (
          <div className="space-y-3 rounded-xl border p-4">
            <p className="text-xl font-semibold">
              {quote.calculation.grand_total ?? "Total unresolved"}{" "}
              {quote.calculation.currency}
            </p>
            <p className="text-sm">
              Subtotal {quote.calculation.subtotal ?? "unknown"} · shipping{" "}
              {quote.calculation.shipping ?? "unknown"} · tax{" "}
              {quote.calculation.tax ?? "unknown"}
            </p>
            {quote.calculation.issues.length > 0 && (
              <ul className="list-disc space-y-1 pl-5 text-sm text-amber-800 dark:text-amber-300">
                {quote.calculation.issues.map((issue) => (
                  <li className="break-words" key={issue}>
                    {readable(issue)}
                  </li>
                ))}
              </ul>
            )}
            {quote.calculation.lines.map((line) => (
              <details key={line.line_id}>
                <summary className="cursor-pointer text-sm">
                  Line {line.line_id.slice(0, 8)} ·{" "}
                  {line.amount ?? "Unknown amount"} · calculation & source
                </summary>
                <Evidence value={line} />
              </details>
            ))}
            <details>
              <summary className="cursor-pointer text-sm">
                Saved quote source snapshot
              </summary>
              <Evidence value={quote.snapshot} />
            </details>
            <label className="block text-sm">
              <input
                type="checkbox"
                checked={reviewed}
                onChange={(e) => setReviewed(e.target.checked)}
              />{" "}
              I reviewed product suitability, source validity, availability,
              pack/MOQ, pricing, discount, shipping and tax inputs.
            </label>
            <div className="flex flex-wrap gap-2">
              {["draft", "incomplete", "changes_requested"].includes(
                quote.state,
              ) && (
                <button
                  className={button}
                  disabled={
                    busy ||
                    !reviewed ||
                    !quote.calculation.complete ||
                    reason.length < 5
                  }
                  onClick={() => void act(() => decision("submit"))}
                >
                  Submit for internal review
                </button>
              )}
              {quote.state === "under_review" && (
                <>
                  <button
                    className={button}
                    disabled={busy || !reviewed || reason.length < 5}
                    onClick={() => void act(() => decision("approve"))}
                  >
                    Approve internally
                  </button>
                  <button
                    className={button}
                    disabled={busy || reason.length < 5}
                    onClick={() => void act(() => decision("request-changes"))}
                  >
                    Request changes
                  </button>
                  <button
                    className={button}
                    disabled={busy || reason.length < 5}
                    onClick={() => void act(() => decision("reject"))}
                  >
                    Reject quote
                  </button>
                </>
              )}
              <button
                className="rounded-lg border px-3 py-2 text-sm"
                onClick={() =>
                  void act(async () =>
                    setHistory(
                      await rfqApi(`quotes/${quote.id}/history`, workspace),
                    ),
                  )
                }
              >
                View quote history
              </button>
              <button
                className="rounded-lg border px-3 py-2 text-sm"
                onClick={() =>
                  void act(async () =>
                    setHistory(
                      await rfqApi(`quotes/${quote.id}/audit`, workspace),
                    ),
                  )
                }
              >
                View quote audit
              </button>
            </div>
            {history !== null && (
              <details open>
                <summary>Persisted revisions and audit evidence</summary>
                <Evidence value={history} />
              </details>
            )}
          </div>
        )}
        <p className="text-xs text-slate-600 dark:text-slate-300">
          Internal approval only. Phase 3 has no quotation delivery, ordering or
          payment action. Approved versions remain immutable.
        </p>
      </section>
    </section>
  );
}
