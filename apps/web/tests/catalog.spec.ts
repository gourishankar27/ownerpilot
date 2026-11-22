import { test, expect } from "@playwright/test";
import { signupSynthetic } from "./rfq-account";

test("real catalog preview indexing approved matching selection and persisted history", async ({
  page,
}) => {
  test.setTimeout(180000);
  const id = await signupSynthetic(page, "catalog");
  const workspace = await page.request.post("/api/workspaces", {
    data: { name: "Synthetic catalog lab", slug: `catalog-${id}` },
  });
  expect(workspace.ok()).toBeTruthy();
  await page.goto("/procurement");
  await page.getByLabel("RFQ title").fill("Approved synthetic catalog request");
  await page.getByRole("button", { name: "Create RFQ", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "Approved synthetic catalog request",
      exact: true,
    }),
  ).toBeVisible();
  await page.getByLabel("RFQ documents").setInputFiles({
    name: "synthetic.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "Manufacturer,MPN,Description,Qty,UOM\nNorthvale,000-CAT.1,Memory module,2,EA\n",
    ),
  });
  await page
    .getByRole("button", { name: "Upload documents", exact: true })
    .click();
  await expect(page.getByText(/synthetic.csv · uploaded/)).toBeVisible();
  await page.getByLabel("Extraction mode").selectOption("deterministic");
  await page
    .getByRole("button", { name: "Start processing", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Review line", exact: true })
    .waitFor({ timeout: 60000 });
  await page.getByRole("button", { name: "Review line", exact: true }).click();
  await page
    .getByLabel("Review reason", { exact: true })
    .fill("Verified synthetic source");
  await page.getByRole("button", { name: "Save review", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Approve reviewed RFQ", exact: true }),
  ).toBeEnabled();
  await page.getByRole("checkbox").check();
  await page
    .getByRole("button", { name: "Approve reviewed RFQ", exact: true })
    .click();
  await expect(page.getByText(/This version is locked/)).toBeVisible();
  await page.getByLabel("Catalog name").fill("Fictional memory catalog");
  await page.getByLabel("Catalog license").fill("CC0 fictional source");
  await page
    .getByRole("button", { name: "Create catalog", exact: true })
    .click();
  await page.getByLabel("Catalog file").setInputFiles({
    name: "catalog.json",
    mimeType: "application/json",
    buffer: Buffer.from(
      JSON.stringify([
        {
          source_id: "fictional-1",
          manufacturer: "Northvale",
          mpn: "000-CAT.1",
          name: "Fictional memory module",
          description: "Memory module",
          category: "memory",
          specs: { capacity: 32 },
        },
      ]),
    ),
  });
  await page
    .getByRole("button", { name: "Preview catalog import", exact: true })
    .click();
  await expect(page.getByLabel("Catalog import preview")).toContainText(
    "canonical_products",
  );
  await page
    .getByRole("button", { name: "Confirm catalog import", exact: true })
    .click();
  await expect(page.getByLabel("Catalog indexing status")).toContainText(
    "published",
    { timeout: 90000 },
  );
  await page
    .getByLabel("Approved catalog match line")
    .selectOption({ label: "Memory module · 000-CAT.1" });
  await page
    .getByRole("button", { name: "Find matching products", exact: true })
    .click();
  await expect(page.getByLabel("Catalog matching results")).toContainText(
    "Fictional memory module",
    { timeout: 30000 },
  );
  await page
    .getByLabel("Catalog review note")
    .fill("Selected exact reviewed identifier");
  await page
    .getByRole("button", { name: "Select product", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Product review saved" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: `${process.env.RFQ_SCREENSHOT_DIR ?? "../../.local/rfq/phase2/screenshots"}/catalog-match.png`,
    fullPage: true,
  });
  await page.reload();
  await page
    .getByRole("button", {
      name: /Approved synthetic catalog request approved/,
    })
    .click();
  await page
    .getByLabel("Approved catalog match line")
    .selectOption({ label: "Memory module · 000-CAT.1" });
  await expect(page.getByLabel("Catalog search history")).toBeVisible();
  const history = page.getByLabel("Catalog search history");
  const value = await history.locator("option").nth(1).getAttribute("value");
  await history.selectOption(value!);
  await expect(page.getByLabel("Catalog saved reviews")).toContainText(
    "select",
  );
  await page
    .getByLabel("Catalog scope")
    .selectOption({ label: "Fictional memory catalog · published" });
  await page
    .getByRole("button", { name: "Find matching products", exact: true })
    .click();
  await expect(page.getByLabel("Catalog matching results")).toContainText(
    "Fictional memory module",
  );
  await page
    .getByLabel("Catalog review note")
    .fill("Rejected after synthetic comparison");
  await page
    .getByRole("button", { name: "Reject candidate", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Product review saved" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Find matching products", exact: true })
    .click();
  await expect(page.getByLabel("Catalog matching results")).toContainText(
    "Fictional memory module",
  );
  await page
    .getByLabel("Catalog review note")
    .fill("Explicit synthetic no-match decision");
  await page
    .getByRole("button", { name: "Record no valid match", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "No-match decision saved" }),
  ).toBeVisible();
});
