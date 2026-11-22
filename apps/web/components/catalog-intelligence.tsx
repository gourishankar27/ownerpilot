"use client";

import { useEffect, useState, useCallback } from "react";
import type {
  RfqDetail,
  CatalogSummary as Catalog,
  CatalogPreview as Preview,
  CatalogMatch as Match,
} from "@ownerpilot/contracts";
import { rfqApi } from "@/lib/rfq-api";

export function CatalogIntelligence({
  workspace,
  detail,
}: {
  workspace: string;
  detail: RfqDetail | null;
}) {
  const [catalogs, setCatalogs] = useState<Catalog[]>([]);
  const [selected, setSelected] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [message, setMessage] = useState("");
  const [job, setJob] = useState<{
    id: string;
    state: string;
    error?: string;
    metadata?: unknown;
  } | null>(null);
  const [match, setMatch] = useState<Match | null>(null);
  const [note, setNote] = useState("");
  const [history, setHistory] = useState<{ id: string; created_at: string }[]>(
    [],
  );
  const [line, setLine] = useState("");
  const [retrievalMethod, setRetrievalMethod] = useState("reranked");
  const [busy, setBusy] = useState(false);
  const [records, setRecords] = useState<unknown[] | null>(null);
  const [recordOffset, setRecordOffset] = useState(0);
  const refresh = useCallback(async () => {
    if (workspace) setCatalogs(await rfqApi<Catalog[]>("catalogs", workspace));
  }, [workspace]);
  useEffect(() => {
    let active = true;
    if (workspace)
      void rfqApi<Catalog[]>("catalogs", workspace)
        .then((value) => {
          if (active) setCatalogs(value);
        })
        .catch((e) => {
          if (active) setMessage(e.message);
        });
    return () => {
      active = false;
    };
  }, [workspace]);
  useEffect(() => {
    if (!job || !["queued", "building"].includes(job.state)) return;
    const timer = setInterval(
      () =>
        void rfqApi<{ id: string; state: string }>(
          `catalog-import-jobs/${job.id}`,
          workspace,
        )
          .then((value) => {
            setJob(value);
            if (value.state === "published") void refresh();
          })
          .catch((e) => setMessage(e.message)),
      1500,
    );
    return () => clearInterval(timer);
  }, [job, workspace, refresh]);
  async function action(work: () => Promise<void>) {
    setBusy(true);
    setMessage("");
    try {
      await work();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Catalog operation failed");
    } finally {
      setBusy(false);
    }
  }
  if (!workspace) return null;
  return (
    <section
      aria-label="Catalog Intelligence"
      className="min-w-0 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm space-y-4"
    >
      <h2 className="text-xl font-semibold">Catalog Intelligence</h2>
      <p>
        Import licensed or synthetic structured catalogs. Matching uses
        reviewed, approved RFQ values. Product selection does not create an
        order or quote.
      </p>
      {message && <p role="status">{message}</p>}
      <form
        className="flex gap-3 flex-wrap"
        action={(form) =>
          action(async () => {
            const created = await rfqApi<Catalog>("catalogs", workspace, {
              method: "POST",
              body: JSON.stringify({
                name: form.get("name"),
                license: form.get("license"),
              }),
            });
            setSelected(created.id);
            await refresh();
          })
        }
      >
        <input
          aria-label="Catalog name"
          name="name"
          required
          placeholder="Catalog name"
          className="border rounded p-2"
        />
        <input
          aria-label="Catalog license"
          name="license"
          required
          placeholder="Source / license"
          className="border rounded p-2"
        />
        <button disabled={busy} className="underline">
          Create catalog
        </button>
      </form>
      <label>
        Catalog scope{" "}
        <select
          aria-label="Catalog scope"
          value={selected}
          onChange={(e) => {
            setSelected(e.target.value);
            setPreview(null);
            setMatch(null);
          }}
          className="border rounded p-2"
        >
          <option value="">Select catalog</option>
          {catalogs.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} · {c.state ?? "not indexed"}
            </option>
          ))}
        </select>
      </label>
      {selected && (
        <>
          <p className="text-sm">
            Indexed products:{" "}
            {String(
              catalogs.find((c) => c.id === selected)?.metadata
                ?.canonical_products ?? "not indexed",
            )}{" "}
            · Offers:{" "}
            {String(
              catalogs.find((c) => c.id === selected)?.metadata?.offers ??
                "unknown",
            )}{" "}
            · Embedding model:{" "}
            {String(
              catalogs.find((c) => c.id === selected)?.metadata?.model ??
                "not recorded",
            )}
          </p>
          <details>
            <summary>Index provenance</summary>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs">
              {JSON.stringify(
                catalogs.find((c) => c.id === selected)?.metadata ?? {},
                null,
                2,
              )}
            </pre>
          </details>
          <button
            className="underline"
            disabled={busy}
            onClick={() =>
              action(async () => {
                setRecords(
                  await rfqApi<unknown[]>(
                    `catalogs/${selected}/products?limit=25&offset=${recordOffset}`,
                    workspace,
                  ),
                );
              })
            }
          >
            View indexed products
          </button>
          {records && (
            <div>
              <pre className="text-xs overflow-auto max-h-80">
                {JSON.stringify(records, null, 2)}
              </pre>
              <button
                className="underline mr-4"
                disabled={recordOffset === 0}
                onClick={() => {
                  setRecordOffset(Math.max(0, recordOffset - 25));
                  setRecords(null);
                }}
              >
                Previous product page
              </button>
              <button
                className="underline"
                disabled={records.length < 25}
                onClick={() => {
                  setRecordOffset(recordOffset + 25);
                  setRecords(null);
                }}
              >
                Next product page
              </button>
            </div>
          )}
          <form
            className="space-y-2"
            action={(form) =>
              action(async () => {
                setPreview(
                  await rfqApi<Preview>(
                    `catalogs/${selected}/imports/preview`,
                    workspace,
                    { method: "POST", body: form },
                  ),
                );
              })
            }
          >
            <input
              aria-label="Catalog file"
              name="file"
              type="file"
              accept=".csv,.xlsx,.json"
              required
            />
            <label>
              Column mapping (JSON)
              <input
                aria-label="Catalog column mapping"
                name="mapping"
                defaultValue="{}"
                className="border rounded p-2"
              />
            </label>
            <button disabled={busy} className="underline">
              Preview catalog import
            </button>
          </form>
          {preview && (
            <div aria-label="Catalog import preview">
              <h3>Import preview</h3>
              <p>
                {String(preview.counts.source_rows)} source rows ·{" "}
                {String(preview.counts.canonical_products)} canonical products ·{" "}
                {String(preview.counts.grouped_offers)} grouped offers
              </p>
              <details>
                <summary>Column mapping and sample records</summary>
                <pre className="overflow-auto max-h-80 whitespace-pre-wrap break-all text-xs">
                  {JSON.stringify(
                    {
                      counts: preview.counts,
                      mapping: preview.specification,
                      sample: preview.sample,
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>
              <button
                disabled={busy}
                className="underline"
                onClick={() =>
                  action(async () => {
                    const value = await rfqApi<{
                      job_id: string;
                      state: string;
                    }>(`catalogs/${selected}/imports/confirm`, workspace, {
                      method: "POST",
                      body: JSON.stringify({
                        version_id: preview.id,
                        fingerprint: preview.fingerprint,
                      }),
                    });
                    setJob({ id: value.job_id, state: value.state });
                  })
                }
              >
                Confirm catalog import
              </button>
            </div>
          )}
          {job && (
            <div aria-label="Catalog indexing status">
              Index status: {job.state} {job.error}
              <details>
                <summary>Index model and timings</summary>
                <pre className="text-xs overflow-auto whitespace-pre-wrap break-all">
                  {JSON.stringify(job.metadata, null, 2)}
                </pre>
              </details>
            </div>
          )}
          <button
            disabled={busy}
            className="underline"
            onClick={() =>
              action(async () => {
                const result = await rfqApi<{ job_id: string }>(
                  `catalogs/${selected}/rebuild-index`,
                  workspace,
                  { method: "POST" },
                );
                setJob({ id: result.job_id, state: "queued" });
              })
            }
          >
            Rebuild catalog index
          </button>
        </>
      )}
      <h3 className="font-semibold">Approved RFQ product matching</h3>
      <label className="block min-w-0 text-sm">
        Catalog retrieval method
        <select
          aria-label="Catalog retrieval method"
          className="w-full min-w-0 max-w-full rounded-lg border border-slate-300 bg-transparent px-3 py-2 dark:border-slate-600"
          value={retrievalMethod}
          onChange={(event) => setRetrievalMethod(event.target.value)}
        >
          <option value="reranked">
            Full hybrid + compatibility (requires embeddings)
          </option>
          <option value="exact">
            Exact manufacturer / MPN (works without embeddings)
          </option>
          <option value="bm25">Keyword BM25 (works without embeddings)</option>
          <option value="sql">
            SQL text search (works without embeddings)
          </option>
          <option value="exact_bm25">
            Exact + keyword BM25 (works without embeddings)
          </option>
        </select>
      </label>
      {detail?.status !== "approved" ? (
        <p>Approve and review an RFQ before searching for catalog products.</p>
      ) : (
        <>
          <label className="block min-w-0">
            Approved line{" "}
            <select
              aria-label="Approved catalog match line"
              className="w-full min-w-0 max-w-full rounded-lg border border-slate-300 bg-transparent px-3 py-2 text-sm dark:border-slate-600"
              value={line}
              onChange={(e) => {
                const id = e.target.value;
                setLine(id);
                setMatch(null);
                void rfqApi<{ id: string; created_at: string }[]>(
                  `rfqs/${detail.id}/line-items/${id}/matches`,
                  workspace,
                )
                  .then(setHistory)
                  .catch((err) => setMessage(err.message));
              }}
            >
              <option value="">Select reviewed line</option>
              {detail.items
                .filter((i) => i.review_status === "reviewed")
                .map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.fields.description?.value} ·{" "}
                    {i.fields.mpn?.value ?? "MPN unknown"}
                  </option>
                ))}
            </select>
          </label>
          <button
            disabled={
              busy ||
              !line ||
              !catalogs.find((c) => c.id === selected)?.active_version
            }
            className="underline"
            onClick={() =>
              action(async () => {
                const version = catalogs.find(
                  (c) => c.id === selected,
                )?.active_version;
                const value = await rfqApi<Match>(
                  `rfqs/${detail.id}/line-items/${line}/matches`,
                  workspace,
                  {
                    method: "POST",
                    body: JSON.stringify({
                      revision: detail.revision,
                      versions: [version],
                      method: retrievalMethod,
                    }),
                  },
                );
                setMatch(value);
                setHistory(
                  await rfqApi(
                    `rfqs/${detail.id}/line-items/${line}/matches`,
                    workspace,
                  ),
                );
              })
            }
          >
            Find matching products
          </button>
        </>
      )}
      {history.length > 0 && (
        <label>
          Search history{" "}
          <select
            aria-label="Catalog search history"
            defaultValue=""
            onChange={(e) =>
              action(async () => {
                const run = await rfqApi<{
                  id: string;
                  result: Match;
                  reviews: unknown[];
                }>(`catalog-match-runs/${e.target.value}`, workspace);
                setMatch({ ...run.result, id: run.id, reviews: run.reviews });
              })
            }
          >
            <option value="" disabled>
              Select search run
            </option>
            {history.map((h) => (
              <option key={h.id} value={h.id}>
                {h.created_at}
              </option>
            ))}
          </select>
        </label>
      )}
      {match && (
        <div aria-label="Catalog matching results" className="space-y-3">
          <p>{match.outcome.replaceAll("_", " ")}</p>
          <details>
            <summary>Approved query and catalog versions</summary>
            <pre className="text-xs overflow-auto">
              {JSON.stringify(
                { query: match.query, versions: match.versions },
                null,
                2,
              )}
            </pre>
          </details>
          <label>
            Selection review note{" "}
            <input
              aria-label="Catalog review note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              className="border rounded p-2"
            />
          </label>
          {match.candidates.map((c) => (
            <article key={c.id} className="border rounded p-3">
              <h4>{c.product.name}</h4>
              <p>
                {c.product.manufacturer} · {c.product.mpn} ·{" "}
                {c.compatibility.status.replaceAll("_", " ")}
              </p>
              <dl className="mt-2 grid grid-cols-2 gap-2 text-sm">
                {Object.entries(c.product.specs).map(([key, value]) => (
                  <div key={key}>
                    <dt className="text-slate-500">
                      {key.replaceAll("_", " ")}
                    </dt>
                    <dd>{String(value)}</dd>
                  </div>
                ))}
              </dl>
              <p className="text-sm">
                Missing required attributes:{" "}
                {c.compatibility.missing.join(", ") || "none recorded"} ·
                Conflicts: {c.compatibility.conflicts.length}
              </p>
              <details>
                <summary>Offers, source evidence and ranking</summary>
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs">
                  {JSON.stringify(
                    {
                      specifications: c.product.specs,
                      differences: c.compatibility.conflicts,
                      missing: c.compatibility.missing,
                      offers: c.offers,
                      sources: c.sources,
                      retrieval: c.channels,
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>
              {["select", "reject"].map((decision) => (
                <button
                  key={decision}
                  disabled={
                    busy ||
                    !note ||
                    (decision === "select" &&
                      !["exact", "compatible_alternative"].includes(
                        c.compatibility.status,
                      ))
                  }
                  className="underline mr-4"
                  onClick={() =>
                    action(async () => {
                      await rfqApi(
                        `catalog-match-runs/${match.id}/review`,
                        workspace,
                        {
                          method: "POST",
                          body: JSON.stringify({
                            decision,
                            product_id: c.id,
                            note,
                          }),
                        },
                      );
                      setMessage("Product review saved with audit history.");
                    })
                  }
                >
                  {decision === "select"
                    ? "Select product"
                    : "Reject candidate"}
                </button>
              ))}
            </article>
          ))}
          <button
            disabled={busy || !note}
            className="underline"
            onClick={() =>
              action(async () => {
                await rfqApi(
                  `catalog-match-runs/${match.id}/review`,
                  workspace,
                  {
                    method: "POST",
                    body: JSON.stringify({ decision: "no_match", note }),
                  },
                );
                setMessage("No-match decision saved.");
              })
            }
          >
            Record no valid match
          </button>
          {match.reviews && (
            <pre aria-label="Catalog saved reviews">
              {JSON.stringify(match.reviews, null, 2)}
            </pre>
          )}
        </div>
      )}
    </section>
  );
}
