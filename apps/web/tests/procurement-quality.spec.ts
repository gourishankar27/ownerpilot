import { test, expect } from "@playwright/test";
import { resolve } from "node:path";
import { signupSynthetic } from "./rfq-account";

test("explicit UI fixture: quality filters and OCR association evidence remain distinct", async ({
  page,
}) => {
  const evidence = {
    document_id: "synthetic-doc",
    fingerprint: "0".repeat(64),
    block_id: "page:1:row:2",
    location: {
      page: 1,
      sheet: null,
      row: 2,
      column: "B",
      start: null,
      end: null,
      bbox: [10, 20, 80, 35],
    },
    excerpt: "00-O1",
    method: "tesseract",
    identity: "explicit-ui-fixture",
    verified: true,
    source_occurrence: true,
    row_association: "verified",
    column_association: "unverified",
    association_reason: "Synthetic wrong-column fixture",
    raw_ocr: "00-O1",
    alternatives: ["OO-01"],
    ocr_confidence: 74.3,
    extracted_at: "2026-11-19T00:00:00Z",
  };
  const field = (
    value: string | null,
    status = "validated",
    sources: unknown[] = [],
  ) => ({
    raw: value,
    value,
    comparison: null,
    status,
    issues: [],
    evidence: sources,
    corrected: false,
  });
  const summary = {
    id: "fixture-rfq",
    title: "Explicit fixture quality queue",
    status: "awaiting_review",
    revision: 1,
    created_at: "2026-11-19T00:00:00Z",
    updated_at: "2026-11-19T00:00:00Z",
    approved_by: null,
    approved_at: null,
  };
  const detail = {
    ...summary,
    header: {},
    current_run_id: "fixture-run",
    role: "owner",
    documents: [
      {
        id: "synthetic-doc",
        filename: "synthetic-fixture.pdf",
        fingerprint: "0".repeat(64),
        size_bytes: 100,
        status: "parsed",
        created_at: summary.created_at,
      },
    ],
    jobs: [],
    runs: [
      {
        id: "fixture-run",
        created_at: summary.created_at,
        schema_version: "rfq.v1",
        metadata: {
          policy: "selective-v2",
          model_call_count: 1,
          ocr_strategy: "combined-v2",
          duration_ms: 1234,
          routing: [
            {
              document_id: "synthetic-doc",
              coverage: { candidate_rows: null, deterministic_rows: 1 },
              selected_blocks: ["page:1:row:2"],
              tasks: [
                {
                  source: "page:1:row:2",
                  reasons: ["field_association_or_ocr_uncertainty"],
                  model_eligible: true,
                },
              ],
            },
          ],
        },
      },
    ],
    approval_issues: ["Resolve synthetic OCR disagreement"],
    items: [
      {
        id: "fixture-one",
        extraction_method: "hybrid",
        review_status: "pending",
        warnings: [],
        fields: {
          description: field("Fixture OCR row"),
          mpn: field("00-O1", "ambiguous", [evidence]),
          quantity: field("2"),
          unit: field("EA"),
          manufacturer: field("Fictional Maker"),
        },
      },
      {
        id: "fixture-two",
        extraction_method: "deterministic",
        review_status: "pending",
        warnings: [],
        fields: {
          description: field("Fixture missing quantity"),
          quantity: field(null, "missing"),
          unit: field("EA"),
          mpn: field("FIX-2"),
          manufacturer: field("Fictional Maker"),
        },
      },
    ],
  };
  await page.route("**/api/procurement-workspaces", (route) =>
    route.fulfill({
      json: [
        { id: "fixture-workspace", name: "Explicit UI fixture", role: "owner" },
      ],
    }),
  );
  await page.route("**/api/procurement/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("rfq-health"))
      return route.fulfill({
        json: {
          database: true,
          redis: true,
          worker: true,
          model: { available: false, reason: "Explicit UI fixture" },
        },
      });
    if (path.endsWith("/rfqs"))
      return route.fulfill({
        json: {
          items: [summary],
          total: 1,
          counts: { awaiting_review: 1 },
          jobs: {},
          limit: 25,
          offset: 0,
        },
      });
    if (path.endsWith("/fixture-rfq")) return route.fulfill({ json: detail });
    return route.fulfill({ json: [] });
  });
  await page.goto("/procurement");
  await page
    .getByRole("button", { name: /Explicit fixture quality queue/ })
    .click();
  await expect(
    page.getByRole("region", { name: "Extraction quality summary" }),
  ).toContainText("selective-v2");
  await page
    .getByText("Processing decisions and timing", { exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Extraction quality summary" }),
  ).toContainText("Model source selected");
  await expect(
    page.getByRole("region", { name: "Extraction quality summary" }),
  ).toContainText("1.23 seconds");
  await page.getByLabel("Review queue filter").selectOption("ocr");
  await expect(page.getByText("Showing 1 of 2 items.")).toBeVisible();
  await page.getByRole("button", { name: /00-O1/ }).click();
  const inspector = page.getByRole("complementary", {
    name: "Source evidence",
  });
  await expect(inspector).toContainText("Row association: verified");
  await expect(inspector).toContainText("Column association: unverified");
  await expect(inspector).toContainText("OCR disagreement: OO-01");
  await expect(inspector).toContainText("uncalibrated");
  await page.getByLabel("Review queue filter").selectOption("critical");
  await expect(
    page.getByRole("button", { name: /Fixture missing quantity/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Approve reviewed RFQ", exact: true }),
  ).toBeDisabled();
});

test("real Linux OCR shows source geometry and heuristic confidence", async ({
  page,
}) => {
  const id = await signupSynthetic(page, "ocr");
  const workspace = await page.request.post("/api/workspaces", {
    data: { name: "Synthetic OCR lab", slug: `ocr-${id}` },
  });
  expect(workspace.ok(), await workspace.text()).toBeTruthy();
  await page.goto("/procurement");
  await expect(page.getByLabel("Workspace")).toContainText("Synthetic OCR lab");
  await page.getByLabel("RFQ title").fill("Synthetic grid OCR review");
  await page.getByRole("button", { name: "Create RFQ", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "Synthetic grid OCR review",
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByLabel("RFQ documents")
    .setInputFiles(
      resolve("../../data/evaluation/rfq-v2/sources/v2-00-00.pdf"),
    );
  await page
    .getByRole("button", { name: "Upload documents", exact: true })
    .click();
  await expect(page.getByText(/v2-00-00.pdf · uploaded/)).toBeVisible();
  await page.getByLabel("Extraction mode").selectOption("deterministic");
  await page
    .getByRole("button", { name: "Start processing", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Review line", exact: true }).first(),
  ).toBeVisible({ timeout: 60000 });
  await expect(
    page.getByRole("region", { name: "Extraction quality summary" }),
  ).toContainText("Model calls: 0");
  await expect(page.getByText(/OCR-derived/).first()).toBeVisible();
  await page
    .locator("tbody tr")
    .first()
    .locator("td")
    .nth(2)
    .getByRole("button")
    .click();
  const inspector = page.getByRole("complementary", {
    name: "Source evidence",
  });
  await expect(inspector).toContainText("Raw OCR reading:");
  await expect(inspector).toContainText("top-left");
  await expect(inspector).toContainText("uncalibrated");
  await page.screenshot({
    path: `${process.env.RFQ_SCREENSHOT_DIR ?? "../../.local/rfq/screenshots"}/ocr-actual.png`,
    fullPage: true,
  });
});
