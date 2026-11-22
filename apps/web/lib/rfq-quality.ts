import type { RfqLine } from "@ownerpilot/contracts";

export function matchesQualityFilter(item: RfqLine, filter: string) {
  const fields = Object.values(item.fields);
  const evidence = fields.flatMap((field) => field.evidence);
  switch (filter) {
    case "reviewed":
      return item.review_status === "reviewed";
    case "critical":
      return ["description", "quantity", "unit"].some(
        (name) => item.fields[name]?.status !== "validated",
      );
    case "source":
      return fields.some((field) => field.status === "unverified");
    case "association":
      return evidence.some(
        (source) =>
          source.row_association === "unverified" ||
          source.row_association === "unknown" ||
          source.column_association === "unverified",
      );
    case "ocr":
      return evidence.some((source) => (source.alternatives?.length ?? 0) > 0);
    case "conflicting":
      return fields.some((field) => field.status === "conflicting");
    case "duplicates":
      return item.warnings.some((warning) => /duplicate/i.test(warning));
    default:
      return true;
  }
}
