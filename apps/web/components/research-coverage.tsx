import type { ResearchRun, ToolReceipt } from "@ownerpilot/contracts";

const readable = (value: string) => value.replaceAll("_", " ");

export function ResearchCoverage({
  run,
  receipts,
}: {
  run: ResearchRun;
  receipts: ToolReceipt[];
}) {
  if (!run.metadata.planning_policy) return null;
  const work = run.coverage_state;
  const model = receipts.filter(
    (receipt) => receipt.execution_origin === "model_selected",
  ).length;
  const backend = receipts.filter(
    (receipt) => receipt.execution_origin === "backend_scheduled",
  ).length;
  return (
    <section
      aria-label="Coverage-aware planning"
      className="space-y-3 rounded-xl border p-4 text-sm"
    >
      <h4 className="font-semibold">
        Source inspection and citation verification
      </h4>
      <p>
        Strategy: {readable(run.metadata.orchestration_strategy ?? "pending")} ·
        batch limit {run.metadata.batch_size ?? 4} lines
      </p>
      <p>
        Native model-selected tool calls: {model} · Backend scheduled tool
        calls: {backend}
      </p>
      {backend > 0 && (
        <p>
          Backend policy filled missing mandatory reads. Receipt labels show
          each contribution.
        </p>
      )}
      {work ? (
        <>
          <p className="font-semibold">
            Source coverage: {work.covered_lines} of {work.total_lines} lines ·
            Remaining: {Math.max(0, work.total_lines - work.covered_lines)}
          </p>
          <p>
            Approved RFQ:{" "}
            {work.approved_rfq_read ? "inspected" : "not yet inspected"}
          </p>
          {work.capacity && !work.capacity.supported && (
            <div
              role="alert"
              className="rounded-lg border border-amber-400 p-3"
            >
              <p>
                Research scope exceeds safe capacity. Maximum demonstrated
                scope: {work.capacity.maximum_lines} lines.
              </p>
              <p>{work.capacity.continuation_guidance}</p>
            </div>
          )}
          {work.capacity && (
            <p>
              Automatic continuation:{" "}
              {work.capacity.continuation_available
                ? "available"
                : "unavailable"}{" "}
              · source and output limits remain enforced.
            </p>
          )}
          <div className="grid gap-2 sm:grid-cols-2">
            {work.lines?.map((line) => {
              const citations = run.result?.coverage?.lines.find(
                (item) => item.line_id === line.line_id,
              );
              const verified =
                citations?.complete && !run.result?.invalid_citations?.length;
              return (
                <details key={line.line_id} className="rounded-lg border p-3">
                  <summary>
                    Line {line.line_id.slice(0, 8)} ·{" "}
                    {line.source_covered
                      ? "sources inspected"
                      : "required reads missing"}
                  </summary>
                  <p>
                    Reviewed selection:{" "}
                    {line.selection_inspected ? "inspected" : "not inspected"}
                  </p>
                  <p>
                    Supplier offers:{" "}
                    {line.offers_inspected ? "inspected" : "not inspected"}
                  </p>
                  <p>
                    Required citations:{" "}
                    {verified ? "verified" : "awaiting verification"}
                  </p>
                  {!!line.missing_tools.length && (
                    <p>
                      Missing: {line.missing_tools.map(readable).join(", ")}
                    </p>
                  )}
                  <p className="break-all text-xs">
                    Recorded receipts for this line:{" "}
                    {line.receipt_ids.join(", ") || "none"}
                  </p>
                  {!!line.failed_receipts.length && (
                    <p>
                      Unsuccessful source attempts:{" "}
                      {line.failed_receipts.length}
                    </p>
                  )}
                </details>
              );
            })}
          </div>
        </>
      ) : (
        <p>
          Waiting for the coverage planner; no source inspection is recorded
          yet.
        </p>
      )}
      <details>
        <summary>Recorded research activity</summary>
        <ol className="mt-2 space-y-1 border-l pl-4">
          {run.planning_state?.timeline?.map((event, index) => (
            <li key={`${event.at}-${index}`}>
              <time dateTime={event.at}>
                {new Date(event.at).toLocaleTimeString()}
              </time>{" "}
              · {readable(event.stage)}
              {event.origin
                ? ` · ${event.origin === "backend_scheduled" ? "Backend scheduled" : "Native model-selected"}`
                : ""}
              {event.covered_lines !== undefined
                ? ` · ${event.covered_lines}/${event.total_lines} source-covered lines`
                : ""}
              {event.lines !== undefined || event.line_count !== undefined
                ? ` · ${event.lines ?? event.line_count} lines`
                : ""}
              {event.status ? ` · ${readable(event.status)}` : ""}
            </li>
          ))}
        </ol>
      </details>
    </section>
  );
}
