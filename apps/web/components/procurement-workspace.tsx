"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Button as UiButton, type ButtonProps } from "@ownerpilot/ui";
import {
  rfqHeaderFields,
  rfqItemFields,
  type RfqDetail,
  type RfqEvidence,
  type RfqField,
  type RfqJob,
  type RfqLine,
  type RfqList,
} from "@ownerpilot/contracts";
import { rfqApi } from "@/lib/rfq-api";
import { matchesQualityFilter } from "@/lib/rfq-quality";
import { CatalogIntelligence } from "@/components/catalog-intelligence";

const panel =
  "rounded-3xl border border-slate-200 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-slate-900";
const input =
  "w-full rounded-lg border border-slate-300 bg-transparent px-3 py-2 text-sm dark:border-slate-600";
function Button(props: ButtonProps) {
  return (
    <UiButton
      {...props}
      className="inline-flex h-11 items-center justify-center rounded-full bg-teal-700 px-5 text-sm font-semibold text-white hover:bg-teal-900 disabled:cursor-not-allowed disabled:opacity-60"
    />
  );
}
const label = (name: string) =>
  name.replaceAll("_", " ").replace(/\bmpn\b/, "MPN");
const active = (job?: RfqJob) =>
  job &&
  [
    "queued",
    "validating",
    "parsing",
    "extracting",
    "validating_results",
  ].includes(job.state);

export function ProcurementWorkspace() {
  const [workspaces, setWorkspaces] = useState<
    { id: string; name: string; role: string }[]
  >([]);
  const [workspace, setWorkspace] = useState("");
  const [list, setList] = useState<RfqList | null>(null);
  const [detail, setDetail] = useState<RfqDetail | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("");
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);
  const [qualityFilter, setQualityFilter] = useState("all");
  const [evidence, setEvidence] = useState<{
    name: string;
    field: RfqField;
    reviewed?: boolean;
  } | null>(null);
  const [editing, setEditing] = useState<RfqLine | "header" | "new" | null>(
    null,
  );
  const [editingRevision, setEditingRevision] = useState(0);
  function beginReview(target: RfqLine | "header" | "new") {
    if (!detail) return;
    setEditingRevision(detail.revision);
    setEditing(target);
  }
  const [health, setHealth] = useState<{
    model: { available: boolean; reason?: string; model?: string };
    worker: boolean;
    redis: boolean;
  } | null>(null);

  useEffect(() => {
    let valid = true;
    fetch("/api/procurement-workspaces", { cache: "no-store" })
      .then(async (response) => {
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail);
        if (valid) {
          setWorkspaces(data);
          setWorkspace(data[0]?.id ?? "");
        }
      })
      .catch((e) => {
        if (valid) setError(e.message);
      });
    return () => {
      valid = false;
    };
  }, []);

  const reload = useCallback(async () => {
    if (!workspace) return;
    const query = new URLSearchParams({
      search,
      limit: "25",
      offset: String(offset),
    });
    if (filter) query.set("status", filter);
    const [rows, current] = await Promise.all([
      rfqApi<RfqList>(`rfqs?${query}`, workspace),
      selected
        ? rfqApi<RfqDetail>(`rfqs/${selected}`, workspace)
        : Promise.resolve(null),
    ]);
    setList(rows);
    setDetail(current);
  }, [workspace, search, offset, filter, selected]);

  useEffect(() => {
    let valid = true;
    const refresh = () =>
      reload().catch((e) => {
        if (valid) setError(e.message);
      });
    void refresh();
    const timer = setInterval(refresh, 4000);
    return () => {
      valid = false;
      clearInterval(timer);
    };
  }, [reload]);

  useEffect(() => {
    if (workspace)
      rfqApi<NonNullable<typeof health>>("rfq-health", workspace)
        .then(setHealth)
        .catch(() => setHealth(null));
  }, [workspace]);

  async function action(task: () => Promise<void>, message: string) {
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await task();
      await reload();
      setSuccess(message);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed.");
    } finally {
      setBusy(false);
    }
  }

  async function create(form: FormData) {
    await action(async () => {
      const rfq = await rfqApi<RfqDetail>("rfqs", workspace, {
        method: "POST",
        body: JSON.stringify({
          title: form.get("title"),
          customer_name: form.get("customer") || null,
        }),
      });
      setSelected(rfq.id);
      setDetail(null);
    }, "RFQ created. Upload your documents below.");
  }

  async function upload(form: FormData) {
    if (!detail) return;
    await action(async () => {
      let revision = detail.revision;
      for (const file of form.getAll("files")) {
        if (!(file instanceof File) || !file.size) continue;
        const payload = new FormData();
        payload.set("file", file);
        payload.set("revision", String(revision));
        await rfqApi(`rfqs/${detail.id}/documents`, workspace, {
          method: "POST",
          body: payload,
        });
        revision++;
      }
    }, "Documents uploaded. Choose an extraction mode and start processing.");
  }

  async function process(form: FormData) {
    if (!detail) return;
    const again = Boolean(detail.current_run_id);
    await action(async () => {
      const job = await rfqApi<RfqJob>(
        `rfqs/${detail.id}/${again ? "reprocess" : "process"}`,
        workspace,
        {
          method: "POST",
          body: JSON.stringify({
            revision: detail.revision,
            mode: form.get("mode"),
            reason: form.get("reason") ?? "",
          }),
        },
      );
      if (job.dispatch_warning) setError(job.dispatch_warning);
    }, "Processing job saved.");
  }

  const locked =
    busy || detail?.status === "approved" || Boolean(active(detail?.jobs[0]));
  return (
    <div className="space-y-5">
      <header className={panel}>
        <p className="text-xs uppercase tracking-widest text-teal-700">
          Procurement
        </p>
        <h1 className="mt-2 text-3xl font-semibold">RFQ Intelligence</h1>
        <p className="mt-2 text-sm text-slate-500">
          Turn procurement documents into traceable requests, review every line,
          and approve when ready.
        </p>
        <label className="mt-4 block text-sm">
          Workspace
          <select
            aria-label="Workspace"
            className={input}
            value={workspace}
            onChange={(e) => {
              setWorkspace(e.target.value);
              setSelected(null);
              setDetail(null);
              setEditing(null);
              setList(null);
              setOffset(0);
            }}
          >
            {workspaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name} · {w.role}
              </option>
            ))}
          </select>
        </label>
        {workspaces.length === 0 && (
          <p className="mt-3 text-sm">
            Sign in and create a workspace from Overview to begin.{" "}
            <Link className="underline" href="/auth/sign-in">
              Sign in
            </Link>{" "}
            ·{" "}
            <Link className="underline" href="/dashboard">
              Overview
            </Link>
          </p>
        )}
        {health && (
          <p className="mt-3 text-xs">
            Worker: {health.worker ? "available" : "unavailable"} · Broker:{" "}
            {health.redis ? "available" : "unavailable"} · Model:{" "}
            {health.model.available ? health.model.model : health.model.reason}
          </p>
        )}
      </header>
      {error && (
        <div
          role="alert"
          aria-label="Procurement error"
          className="rounded-xl bg-red-50 p-4 text-sm text-red-800"
        >
          {error}
          <button
            className="ml-3 underline"
            onClick={() => void action(reload, "Reloaded current data.")}
          >
            Reload
          </button>
        </div>
      )}
      {success && (
        <p
          role="status"
          className="rounded-xl bg-teal-50 p-4 text-sm text-teal-900"
        >
          {success}
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {[
          [
            "Total RFQs",
            Object.values(list?.counts ?? {}).reduce((a, b) => a + b, 0),
          ],
          [
            "Processing",
            Object.entries(list?.jobs ?? {})
              .filter(([s]) =>
                [
                  "queued",
                  "validating",
                  "parsing",
                  "extracting",
                  "validating_results",
                ].includes(s),
              )
              .reduce((n, [, v]) => n + v, 0),
          ],
          ["Awaiting review", list?.counts.awaiting_review ?? 0],
          ["Approved", list?.counts.approved ?? 0],
          ["Failed jobs", list?.jobs.failed ?? 0],
        ].map(([name, count]) => (
          <div className={panel} key={name}>
            <p className="text-xs text-slate-500">{name}</p>
            <p className="mt-2 text-2xl font-semibold">{list ? count : "—"}</p>
          </div>
        ))}
      </div>
      <section className={panel}>
        <h2 className="font-semibold">Create RFQ</h2>
        <form className="mt-3 grid gap-3 sm:grid-cols-2" action={create}>
          <input
            className={input}
            name="title"
            aria-label="RFQ title"
            placeholder="RFQ title"
            required
            maxLength={160}
          />
          <input
            className={input}
            name="customer"
            aria-label="Customer name"
            placeholder="Customer or organization (optional)"
            maxLength={300}
          />
          <Button disabled={busy || !workspace} type="submit">
            Create RFQ
          </Button>
        </form>
      </section>
      <section className={panel}>
        <h2 className="font-semibold">Recent RFQs</h2>
        <div className="mt-3 flex gap-3">
          <input
            className={input}
            aria-label="Search RFQs"
            placeholder="Search titles"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setOffset(0);
            }}
          />
          <select
            className={input}
            aria-label="Filter status"
            value={filter}
            onChange={(e) => {
              setFilter(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All statuses</option>
            <option value="draft">Draft</option>
            <option value="awaiting_review">Awaiting review</option>
            <option value="approved">Approved</option>
          </select>
        </div>
        {!list && (
          <p className="mt-4 text-sm">
            {workspace ? "Loading RFQs…" : "Select a workspace to load RFQs."}
          </p>
        )}
        {list?.items.length === 0 && (
          <p className="mt-4 text-sm">No RFQs found.</p>
        )}
        <ul className="mt-3 divide-y divide-slate-100">
          {list?.items.map((rfq) => (
            <li key={rfq.id}>
              <button
                className="flex w-full justify-between gap-3 py-3 text-left text-sm hover:text-teal-700"
                onClick={() => {
                  setSelected(rfq.id);
                  setDetail(null);
                  setEditing(null);
                  setEvidence(null);
                }}
              >
                <span>{rfq.title}</span>
                <span>
                  {label(rfq.status)} ·{" "}
                  {new Date(rfq.updated_at).toLocaleDateString()}
                </span>
              </button>
            </li>
          ))}
        </ul>
        <div className="mt-3 flex gap-3">
          <button
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - 25))}
          >
            Previous
          </button>
          <button
            disabled={!list || offset + 25 >= list.total}
            onClick={() => setOffset(offset + 25)}
          >
            Next
          </button>
        </div>
      </section>
      {selected && !detail && <p role="status">Loading RFQ details…</p>}
      <CatalogIntelligence
        key={`${workspace}:${detail?.id ?? "none"}`}
        workspace={workspace}
        detail={detail}
      />
      {detail && (
        <section className={`${panel} space-y-5`}>
          <div>
            <h2 className="text-xl font-semibold">{detail.title}</h2>
            <p className="text-sm">
              {label(detail.status)} · revision {detail.revision} ·{" "}
              {detail.items.length} line items
            </p>
          </div>
          <section
            aria-label="Extraction quality summary"
            className="rounded-xl border border-teal-200 p-3 text-sm"
          >
            <h3 className="font-semibold">Extraction quality</h3>
            <p>
              Policy:{" "}
              {String(detail.runs[0]?.metadata.policy ?? "phase1 (historical)")}{" "}
              · Model calls:{" "}
              {String(
                detail.runs[0]?.metadata.model_call_count ?? "not recorded",
              )}{" "}
              · OCR strategy:{" "}
              {String(detail.runs[0]?.metadata.ocr_strategy ?? "not recorded")}
            </p>
            <p>
              {
                detail.items.filter(
                  (item) => item.extraction_method === "deterministic",
                ).length
              }{" "}
              deterministic rows ·{" "}
              {
                detail.items.filter(
                  (item) => item.extraction_method !== "deterministic",
                ).length
              }{" "}
              model-assisted or human rows.
            </p>
            <p>
              Source occurrence and structural association are separate checks.
              Raw OCR confidence is an uncalibrated engine indicator. Every
              included row still needs human review.
            </p>
            <ProcessingDecisions detail={detail} />
            {detail.runs.length > 1 && (
              <p className="mt-2 text-amber-700">
                This is a new extraction version. Previous corrections and
                source snapshots remain in the audit and processing history.
              </p>
            )}
          </section>
          {detail.status === "approved" && (
            <p
              role="status"
              className="rounded-xl bg-teal-50 p-3 text-teal-900"
            >
              Approved by {detail.approved_by} on{" "}
              {new Date(detail.approved_at!).toLocaleString()}. This version is
              locked.
            </p>
          )}
          <div>
            <h3 className="font-semibold">Documents</h3>
            <ul className="mt-2 text-sm">
              {detail.documents.map((doc) => (
                <li key={doc.id}>
                  {doc.filename} · {doc.status} ·{" "}
                  {doc.size_bytes.toLocaleString()} bytes · SHA-256{" "}
                  {doc.fingerprint.slice(0, 12)}…
                </li>
              ))}
            </ul>
            <form action={upload} className="mt-3 flex flex-wrap gap-3">
              <input
                aria-label="RFQ documents"
                name="files"
                type="file"
                multiple
                required
                accept=".pdf,.csv,.xlsx,.txt"
                disabled={locked}
              />
              <Button type="submit" disabled={locked}>
                Upload documents
              </Button>
            </form>
            <p className="mt-2 text-xs text-slate-500">
              PDF, CSV, XLSX, UTF-8 TXT. Default 20 MiB per file, 50 PDF pages.
              Formulas are ignored.
            </p>
          </div>
          <form action={process} className="flex flex-wrap gap-3">
            <select
              name="mode"
              aria-label="Extraction mode"
              className={input + " max-w-xs"}
              disabled={locked}
              defaultValue="hybrid"
            >
              <option value="hybrid">
                Hybrid: tables first, local model for text
              </option>
              <option value="deterministic">Deterministic tables only</option>
              <option value="llm">Local model for all documents</option>
            </select>
            {detail.current_run_id && (
              <input
                name="reason"
                aria-label="Reprocessing reason"
                required
                placeholder="Reason for reprocessing"
                className={input}
              />
            )}
            <Button type="submit" disabled={locked || !detail.documents.length}>
              {detail.current_run_id
                ? "Reprocess documents"
                : "Start processing"}
            </Button>
          </form>
          {detail.jobs.map((job) => (
            <div
              key={job.id}
              className="rounded-xl bg-slate-100 p-3 text-sm dark:bg-slate-800"
            >
              <p className="font-semibold">Job: {label(job.state)}</p>
              <p>
                {job.completed_documents}/{job.total_documents} documents parsed
                · attempt {job.attempts} · {job.mode}
                {job.started_at && job.finished_at
                  ? ` · ${((Date.parse(job.finished_at) - Date.parse(job.started_at)) / 1000).toFixed(1)} seconds`
                  : ""}
              </p>
              <ol className="mt-2 flex flex-wrap gap-2 text-xs">
                {[
                  "queued",
                  "validating",
                  "parsing",
                  "extracting",
                  "validating_results",
                  "awaiting_review",
                ].map((s) => (
                  <li
                    key={s}
                    className={
                      job.state === s
                        ? "font-bold text-teal-700"
                        : "text-slate-500"
                    }
                  >
                    {label(s)}
                  </li>
                ))}
              </ol>
              {job.error_message && (
                <p className="mt-2 text-red-700">
                  {job.error_message}{" "}
                  {job.retryable
                    ? "A bounded retry is queued."
                    : "Resolve the issue and start a new processing job."}
                </p>
              )}
              {active(job) && (
                <button
                  className="mt-2 underline"
                  disabled={busy}
                  onClick={() =>
                    void action(async () => {
                      await rfqApi(`rfq-jobs/${job.id}/cancel`, workspace, {
                        method: "POST",
                      });
                    }, "Cancellation recorded. Current inference may finish, but cannot publish.")
                  }
                >
                  Cancel job
                </button>
              )}
            </div>
          ))}
          <div>
            <div className="flex justify-between">
              <h3 className="font-semibold">Header fields</h3>
              <button
                className="text-sm underline"
                disabled={locked}
                onClick={() => beginReview("header")}
              >
                Edit header
              </button>
            </div>
            <dl className="mt-3 grid gap-3 sm:grid-cols-2">
              {rfqHeaderFields.map((name) => (
                <div key={name} className="text-sm">
                  <dt className="capitalize text-slate-500">{label(name)}</dt>
                  <dd>
                    <FieldButton
                      name={name}
                      field={detail.header[name]}
                      onClick={setEvidence}
                    />
                  </dd>
                </div>
              ))}
            </dl>
          </div>
          <div>
            <div className="flex justify-between">
              <h3 className="font-semibold">Line items</h3>
              <button
                className="text-sm underline"
                disabled={locked || !detail.current_run_id}
                onClick={() => beginReview("new")}
              >
                Add line item
              </button>
            </div>
            <div className="mt-3 overflow-x-auto">
              <label className="mb-3 block text-sm">
                Review queue filter
                <select
                  aria-label="Review queue filter"
                  value={qualityFilter}
                  onChange={(event) => setQualityFilter(event.target.value)}
                  className={input}
                >
                  <option value="all">All items</option>
                  <option value="reviewed">Reviewed items</option>
                  <option value="critical">
                    Missing or unresolved critical fields
                  </option>
                  <option value="source">Unverified source</option>
                  <option value="association">
                    Ambiguous source association
                  </option>
                  <option value="ocr">OCR disagreement</option>
                  <option value="conflicting">Conflicting values</option>
                  <option value="duplicates">Potential duplicates</option>
                </select>
              </label>
              <p className="mb-2 text-xs">
                Showing{" "}
                {
                  detail.items.filter((item) =>
                    matchesQualityFilter(item, qualityFilter),
                  ).length
                }{" "}
                of {detail.items.length} items.
              </p>
              <table className="w-full text-left text-sm">
                <thead>
                  <tr>
                    {[
                      "Description",
                      "Manufacturer",
                      "MPN",
                      "Quantity",
                      "Unit",
                      "Review",
                      "",
                    ].map((h, i) => (
                      <th className="p-2" key={i}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {detail.items
                    .filter((item) => matchesQualityFilter(item, qualityFilter))
                    .map((item) => (
                      <tr key={item.id} className="border-t border-slate-200">
                        {[
                          "description",
                          "manufacturer",
                          "mpn",
                          "quantity",
                          "unit",
                        ].map((name) => (
                          <td className="p-2" key={name}>
                            <FieldButton
                              name={name}
                              field={item.fields[name]}
                              onClick={(selection) =>
                                setEvidence({
                                  ...selection,
                                  reviewed: item.review_status === "reviewed",
                                })
                              }
                            />
                          </td>
                        ))}
                        <td className="p-2">
                          {item.review_status}
                          <p className="text-xs text-slate-500">
                            {item.extraction_method} ·{" "}
                            {Object.values(item.fields).some((field) =>
                              field.evidence.some(
                                (source) =>
                                  source.method === "tesseract" ||
                                  source.raw_ocr != null ||
                                  source.ocr_confidence != null,
                              ),
                            )
                              ? "OCR-derived"
                              : "native source"}
                          </p>
                          {item.warnings.map((w) => (
                            <p key={w} className="text-xs text-amber-700">
                              {w}
                            </p>
                          ))}
                        </td>
                        <td className="p-2">
                          <button
                            className="underline"
                            disabled={locked}
                            onClick={() => beginReview(item)}
                          >
                            Review line
                          </button>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
            {!detail.items.length && (
              <p className="mt-3 text-sm">
                No extracted items yet. Process a document to begin review.
              </p>
            )}
          </div>
          {evidence && (
            <aside
              aria-label="Source evidence"
              className="rounded-xl border border-teal-300 p-4"
            >
              <div className="flex justify-between">
                <h3 className="font-semibold">
                  Source evidence · {label(evidence.name)}
                </h3>
                <button onClick={() => setEvidence(null)}>Close</button>
              </div>
              <p className="mt-2 text-sm">
                Current: {evidence.field.value ?? "Unresolved"} · Original:{" "}
                {evidence.field.raw ?? "Missing"} ·{" "}
                {evidence.field.corrected
                  ? "User corrected; original extraction is retained in history"
                  : "Extracted value"}
              </p>
              <p className="text-xs">
                Human review:{" "}
                {evidence.reviewed
                  ? "row reviewed"
                  : evidence.field.corrected
                    ? "user-corrected field"
                    : "pending or consult audit history"}
                .
              </p>
              {evidence.field.issues.map((issue) => (
                <p key={issue} className="text-sm text-amber-700">
                  {issue}
                </p>
              ))}
              {evidence.field.evidence.length ? (
                evidence.field.evidence.map((source, i) => (
                  <EvidenceView key={i} source={source} detail={detail} />
                ))
              ) : (
                <p className="mt-3 text-sm">
                  No source evidence was available. Verify manually before
                  confirming this value.
                </p>
              )}
            </aside>
          )}
          {editing && (
            <ReviewForm
              key={typeof editing === "string" ? editing : editing.id}
              editing={editing}
              detail={detail}
              busy={busy}
              close={() => setEditing(null)}
              save={async (fields, reason, reviewStatus) => {
                await action(async () => {
                  const suffix =
                    editing === "header"
                      ? "header"
                      : editing === "new"
                        ? "line-items"
                        : `line-items/${editing.id}`;
                  await rfqApi(`rfqs/${detail.id}/${suffix}`, workspace, {
                    method: editing === "new" ? "POST" : "PATCH",
                    body: JSON.stringify({
                      revision: editingRevision,
                      fields,
                      reason,
                      review_status: reviewStatus,
                    }),
                  });
                  setEditing(null);
                }, "Review saved with audit history.");
              }}
            />
          )}
          <div className="rounded-xl border border-slate-200 p-4">
            <h3 className="font-semibold">Human approval</h3>
            <p className="mt-2 text-sm">
              Confirm every active line and resolve all populated unverified
              fields. Invalid rows are excluded. No order or quotation is sent.
            </p>
            {detail.approval_issues.length > 0 && (
              <ul className="mt-2 list-inside list-disc text-xs text-amber-700">
                {detail.approval_issues.slice(0, 10).map((issue, i) => (
                  <li key={i}>{issue}</li>
                ))}
                {detail.approval_issues.length > 10 && (
                  <li>
                    And {detail.approval_issues.length - 10} more requirements.
                  </li>
                )}
              </ul>
            )}
            <form
              className="mt-3 space-y-3"
              action={async (form) => {
                await action(async () => {
                  await rfqApi(`rfqs/${detail.id}/approve`, workspace, {
                    method: "POST",
                    body: JSON.stringify({
                      revision: detail.revision,
                      reason: form.get("reason") ?? "",
                    }),
                  });
                }, "RFQ approved and locked.");
              }}
            >
              <label className="block text-sm">
                <input type="checkbox" required disabled={locked} /> I reviewed
                the source documents, fields, and line items.
              </label>
              <input
                className={input}
                name="reason"
                aria-label="Approval note"
                placeholder="Approval note (optional)"
                disabled={locked}
              />
              <Button
                type="submit"
                disabled={
                  locked ||
                  !!detail.approval_issues.length ||
                  !["owner", "admin", "reviewer"].includes(detail.role)
                }
              >
                Approve reviewed RFQ
              </Button>
            </form>
          </div>
          <details>
            <summary className="cursor-pointer text-sm font-semibold">
              Extraction and processing history
            </summary>
            {detail.runs.map((run) => (
              <div key={run.id} className="mt-3 text-xs">
                <p>
                  {new Date(run.created_at).toLocaleString()} ·{" "}
                  {run.schema_version} · {run.id}
                </p>
                <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap">
                  {JSON.stringify(run.metadata, null, 2)}
                </pre>
              </div>
            ))}
            <AuditHistory
              id={detail.id}
              workspace={workspace}
              revision={detail.revision}
            />
          </details>
        </section>
      )}
    </div>
  );
}

function metadataRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function ProcessingDecisions({ detail }: { detail: RfqDetail }) {
  const metadata = detail.runs[0]?.metadata ?? {};
  const routing = Array.isArray(metadata.routing) ? metadata.routing : [];
  const merge = metadataRecord(metadata.merge);
  const duration = (value: unknown) =>
    typeof value === "number" && Number.isFinite(value)
      ? `${(value / 1000).toFixed(2)} seconds`
      : "not recorded";
  if (!routing.length && metadata.duration_ms === undefined) return null;
  return (
    <details className="mt-2">
      <summary className="cursor-pointer font-medium">
        Processing decisions and timing
      </summary>
      <p className="mt-2">
        Processing: {duration(metadata.duration_ms)} · Queue wait:{" "}
        {duration(metadata.queue_wait_ms)} · OCR: {duration(metadata.ocr_ms)} ·
        Model: {duration(metadata.model_ms)}
      </p>
      {Object.keys(merge).length > 0 && (
        <p>
          Repaired rows: {String(merge.repaired_rows ?? "not recorded")} · Added
          model rows: {String(merge.added_model_rows ?? "not recorded")} ·
          Unresolved fields:{" "}
          {String(merge.remaining_unresolved_fields ?? "not recorded")}
        </p>
      )}
      {routing.map((raw, index) => {
        const route = metadataRecord(raw);
        const coverage = metadataRecord(route.coverage);
        const tasks = Array.isArray(route.tasks) ? route.tasks : [];
        const selected = Array.isArray(route.selected_blocks)
          ? route.selected_blocks
          : [];
        const filename = detail.documents.find(
          (document) => document.id === route.document_id,
        )?.filename;
        return (
          <div key={index} className="mt-2 border-t border-teal-100 pt-2">
            <p>
              {filename ?? "Source document"} · Observable candidate rows:{" "}
              {String(coverage.candidate_rows ?? "unknown")} · Deterministic
              rows: {String(coverage.deterministic_rows ?? "not recorded")}
            </p>
            {tasks.length ? (
              <ul className="list-inside list-disc text-xs">
                {tasks.slice(0, 20).map((rawTask, taskIndex) => {
                  const task = metadataRecord(rawTask);
                  const reasons = Array.isArray(task.reasons)
                    ? task.reasons.filter(
                        (reason) => typeof reason === "string",
                      )
                    : [];
                  return (
                    <li key={taskIndex}>
                      {String(task.source ?? "Unresolved source")} ·{" "}
                      {selected.includes(task.source)
                        ? "Model source selected"
                        : "Human review pending"}
                      : {reasons.map((reason) => label(reason)).join("; ")}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p>No unresolved source tasks recorded.</p>
            )}
            {tasks.length > 20 && (
              <p>
                Showing 20 of {tasks.length} tasks; full details are in history.
              </p>
            )}
          </div>
        );
      })}
    </details>
  );
}

function FieldButton({
  name,
  field,
  onClick,
}: {
  name: string;
  field?: RfqField;
  onClick: (value: { name: string; field: RfqField }) => void;
}) {
  if (!field) return <span className="text-slate-400">Missing</span>;
  return (
    <button
      className="text-left underline decoration-dotted underline-offset-4"
      onClick={() => onClick({ name, field })}
    >
      {field.corrected
        ? (field.value ?? "Cleared")
        : (field.value ?? field.raw ?? "Missing")}
      <span className="ml-1 text-xs text-slate-500">
        ({field.corrected ? "corrected" : field.status})
      </span>
    </button>
  );
}

function EvidenceView({
  source,
  detail,
}: {
  source: RfqEvidence;
  detail: RfqDetail;
}) {
  const loc = source.location;
  return (
    <div className="mt-3 border-t border-slate-200 pt-3 text-sm">
      <p>
        {detail.documents.find((d) => d.id === source.document_id)?.filename ??
          source.document_id}{" "}
        · {loc.page ? `page ${loc.page}` : ""}{" "}
        {loc.sheet ? `sheet ${loc.sheet}` : ""}{" "}
        {loc.row ? `row ${loc.row}` : ""}
        {loc.column ? ` column ${loc.column}` : ""}
      </p>
      <blockquote className="mt-2 whitespace-pre-wrap rounded-lg bg-slate-100 p-3 dark:bg-slate-800">
        {source.excerpt}
      </blockquote>
      <p className="mt-1 text-xs">
        {source.method} · {source.identity} ·{" "}
        {source.verified ? "Source verified" : "Unverified"} · SHA-256{" "}
        {source.fingerprint}
      </p>
      <p className="mt-2 text-xs">
        Source occurrence:{" "}
        {(source.source_occurrence ?? source.verified)
          ? "verified literal excerpt"
          : "unverified"}{" "}
        · Row association: {source.row_association ?? "not recorded"} · Column
        association: {source.column_association ?? "not observed"}.
      </p>
      {source.association_reason && (
        <p className="text-xs">{source.association_reason}</p>
      )}
      {source.raw_ocr != null && (
        <p className="mt-2 text-xs">
          Raw OCR reading: {source.raw_ocr} · Normalized current value is shown
          above.
        </p>
      )}
      {!!source.alternatives?.length && (
        <p className="text-xs text-amber-700">
          OCR disagreement: {source.alternatives.join(" / ")}. Confirm visually;
          no character substitution was inferred.
        </p>
      )}
      {source.ocr_confidence != null && (
        <p className="text-xs">
          Raw Tesseract confidence: {source.ocr_confidence.toFixed(1)}{" "}
          (uncalibrated, not an accuracy percentage).
        </p>
      )}
      {loc.bbox && (
        <p className="text-xs">
          Observed geometry, PDF points from original page top-left: [
          {loc.bbox.join(", ")}]. No source highlighting is fabricated.
        </p>
      )}
    </div>
  );
}

function ReviewForm({
  editing,
  detail,
  busy,
  close,
  save,
}: {
  editing: RfqLine | "header" | "new";
  detail: RfqDetail;
  busy: boolean;
  close: () => void;
  save: (
    fields: Record<string, string | null>,
    reason: string,
    status: string,
  ) => Promise<void>;
}) {
  const names = editing === "header" ? rfqHeaderFields : rfqItemFields;
  const original =
    editing === "header"
      ? detail.header
      : editing === "new"
        ? {}
        : editing.fields;
  return (
    <form
      aria-label="Review editor"
      className="space-y-3 rounded-xl border border-teal-300 p-4"
      action={async (form) => {
        const fields: Record<string, string | null> = {};
        for (const name of names) {
          const value = String(form.get(name) ?? "").trim();
          fields[name] = value || null;
        }
        await save(
          fields,
          String(form.get("reason") ?? ""),
          String(form.get("review_status") ?? "reviewed"),
        );
      }}
    >
      <h3 className="font-semibold">
        {editing === "header" ? "Review header" : "Review line item"}
      </h3>
      <div className="grid gap-3 sm:grid-cols-2">
        {names.map((name) => (
          <label key={name} className="text-xs capitalize">
            {label(name)}
            <input
              aria-label={`Edit ${label(name)}`}
              name={name}
              className={input}
              defaultValue={
                original[name]?.corrected
                  ? (original[name]?.value ?? "")
                  : (original[name]?.value ?? original[name]?.raw ?? "")
              }
              maxLength={4000}
            />
            <span className="normal-case text-slate-500">
              Extracted: {original[name]?.raw ?? "missing"}
            </span>
          </label>
        ))}
      </div>
      {editing !== "header" && (
        <label className="block text-sm">
          Review status
          <select
            name="review_status"
            aria-label="Review status"
            className={input}
            defaultValue="reviewed"
          >
            <option value="reviewed">Reviewed</option>
            <option value="invalid">
              Invalid row (exclude from approved data)
            </option>
            <option value="pending">Pending</option>
          </select>
        </label>
      )}
      <input
        className={input}
        aria-label="Review reason"
        name="reason"
        placeholder="Review reason or source used"
        required
        maxLength={1000}
      />
      <div className="flex gap-3">
        <Button type="submit" disabled={busy}>
          Save review
        </Button>
        <button type="button" onClick={close}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function AuditHistory({
  id,
  workspace,
  revision,
}: {
  id: string;
  workspace: string;
  revision: number;
}) {
  const [events, setEvents] = useState<
    {
      id: number;
      event: string;
      actor: string;
      created_at: string;
      details: unknown;
    }[]
  >([]);
  useEffect(() => {
    rfqApi<typeof events>(`rfqs/${id}/audit`, workspace)
      .then(setEvents)
      .catch(() => setEvents([]));
  }, [id, workspace, revision]);
  return (
    <ul className="mt-3 space-y-2 text-xs">
      {events.map((e) => (
        <li key={e.id}>
          <details>
            <summary>
              {new Date(e.created_at).toLocaleString()} · {label(e.event)} ·{" "}
              {e.actor}
            </summary>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap">
              {JSON.stringify(e.details, null, 2)}
            </pre>
          </details>
        </li>
      ))}
    </ul>
  );
}
