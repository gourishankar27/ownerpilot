import { test, expect, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";

async function account(page: Page) {
  const id = randomUUID();
  const signup = await page.request.post("/api/auth/sign-up/email", {
    data: {
      name: "Synthetic RFQ Reviewer",
      email: `rfq-${id}@example.test`,
      password: `Rfq-${randomUUID()}!`,
    },
    headers: { origin: "http://localhost:3000" },
  });
  expect(signup.ok(), await signup.text()).toBeTruthy();
  const workspace = await page.request.post("/api/workspaces", {
    data: { name: "Synthetic Procurement Lab", slug: `rfq-${id}` },
  });
  expect(workspace.ok(), await workspace.text()).toBeTruthy();
}

test("anonymous Procurement shows a real sign-in error", async ({ page }) => {
  await page.goto("/procurement");
  await expect(
    page.getByRole("alert", { name: "Procurement error" }),
  ).toContainText("Sign in");
  const response = await page.request.get("/api/procurement/rfqs");
  expect(response.status()).toBe(401);
});

test("explicit simulated unavailable-model state explains deterministic operation", async ({
  page,
}) => {
  await account(page);
  await page.route("**/api/procurement/rfq-health", (route) =>
    route.fulfill({
      json: {
        database: true,
        redis: true,
        worker: true,
        model: { available: false, reason: "Local Ollama is unavailable." },
      },
    }),
  );
  await page.goto("/procurement");
  await expect(
    page.getByText(/Model: Local Ollama is unavailable/),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Create RFQ", exact: true }),
  ).toBeEnabled();
});

test("create upload process inspect correct approve and reload persisted RFQ", async ({
  page,
}) => {
  await account(page);
  await page.goto("/procurement");
  await expect(page.getByLabel("Workspace")).toContainText(
    "Synthetic Procurement Lab",
  );
  await page.getByLabel("RFQ title").fill("Synthetic laptop refresh");
  await page.getByRole("button", { name: "Create RFQ", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "Synthetic laptop refresh",
      exact: true,
    }),
  ).toBeVisible();
  await page.getByLabel("RFQ documents").setInputFiles({
    name: "synthetic-rfq.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "Manufacturer,MPN,Description,Qty,UOM\nNimvora,000-LAP.1,Laptop refresh,12,EA\n",
    ),
  });
  await page
    .getByRole("button", { name: "Upload documents", exact: true })
    .click();
  await expect(page.getByText(/synthetic-rfq.csv · uploaded/)).toBeVisible();
  await page.getByLabel("Extraction mode").selectOption("deterministic");
  await page
    .getByRole("button", { name: "Start processing", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Review line", exact: true }),
  ).toBeVisible({ timeout: 60000 });
  await page.getByRole("button", { name: /000-LAP.1/ }).click();
  await expect(
    page.getByRole("complementary", { name: "Source evidence" }),
  ).toContainText("row 2 column B");
  await page.screenshot({
    path: "../../docs/rfq/screenshots/evidence.png",
    fullPage: true,
  });
  await expect(
    page.getByRole("button", { name: "Approve reviewed RFQ", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Review line", exact: true }).click();
  await page.getByLabel("Edit quantity", { exact: true }).fill("15");
  await page
    .getByLabel("Review reason", { exact: true })
    .fill("Synthetic reviewer correction verified in source discussion");
  await page.getByRole("button", { name: "Save review", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Approve reviewed RFQ", exact: true }),
  ).toBeEnabled();
  await page.getByRole("checkbox").check();
  await page
    .getByRole("button", { name: "Approve reviewed RFQ", exact: true })
    .click();
  await expect(
    page.getByText(/Approved by .*This version is locked/),
  ).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: /Synthetic laptop refresh/ }).click();
  await expect(
    page.getByText(/Approved by .*This version is locked/),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /15.*corrected/ }),
  ).toBeVisible();
  await page.screenshot({
    path: "../../docs/rfq/screenshots/approved.png",
    fullPage: true,
  });
});

test("invalid uploads and stale review updates remain visible errors", async ({
  page,
}) => {
  await account(page);
  await page.goto("/procurement");
  await expect(page.getByLabel("Workspace")).toContainText(
    "Synthetic Procurement Lab",
  );
  await page.getByLabel("RFQ title").fill("Synthetic upload checks");
  await page.getByRole("button", { name: "Create RFQ", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Synthetic upload checks" }),
  ).toBeVisible();
  await page.getByLabel("RFQ documents").setInputFiles({
    name: "broken.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("not a PDF"),
  });
  await page
    .getByRole("button", { name: "Upload documents", exact: true })
    .click();
  await expect(
    page.getByRole("alert", { name: "Procurement error" }),
  ).toContainText("Invalid PDF signature");
  await page.getByRole("button", { name: "Edit header", exact: true }).click();
  await page
    .getByLabel("Edit customer name", { exact: true })
    .fill("Old tab customer");
  await page
    .getByLabel("Review reason", { exact: true })
    .fill("stale tab check");
  const workspaces = await (
    await page.request.get("/api/procurement-workspaces")
  ).json();
  const rows = await (
    await page.request.get("/api/procurement/rfqs", {
      headers: { "x-workspace-id": workspaces[0].id },
    })
  ).json();
  const rfq = rows.items[0];
  const result = await page.request.patch(
    `/api/procurement/rfqs/${rfq.id}/header`,
    {
      headers: {
        origin: "http://localhost:3000",
        "x-workspace-id": workspaces[0].id,
      },
      data: {
        revision: rfq.revision,
        fields: { customer_name: "Other tab" },
        reason: "concurrent change",
      },
    },
  );
  expect(result.status()).toBe(200);
  await page.waitForTimeout(4500);
  await page.getByRole("button", { name: "Save review", exact: true }).click();
  await expect(
    page.getByRole("alert", { name: "Procurement error" }),
  ).toContainText("changed");
});
