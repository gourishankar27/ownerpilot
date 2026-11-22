import { test, expect, type Page } from "@playwright/test";
import { signupSynthetic } from "./rfq-account";
import { Pool } from "pg";

const origin = new URL(process.env.RFQ_WEB_URL ?? "http://localhost:3033")
  .origin;
async function prepare(page: Page, match = true) {
  const id = await signupSynthetic(page, "phase3");
  const workspaceResponse = await page.request.post("/api/workspaces", {
    data: { name: "Phase 3 fictional quote lab", slug: `phase3-${id}` },
  });
  expect(workspaceResponse.ok()).toBeTruthy();
  const { workspace } = await workspaceResponse.json();
  const headers = { "x-workspace-id": workspace.id, origin };
  async function post(path: string, data: Record<string, unknown>) {
    const response = await page.request.post(`/api/procurement/${path}`, {
      headers,
      data,
    });
    expect(response.ok(), await response.text()).toBeTruthy();
    return response.json();
  }
  async function get(path: string) {
    const response = await page.request.get(`/api/procurement/${path}`, {
      headers,
    });
    expect(response.ok(), await response.text()).toBeTruthy();
    return response.json();
  }
  const rfq = await post("rfqs", { title: "Phase 3 synthetic quote request" });
  const path = `rfqs/${rfq.id}`;
  const upload = await page.request.post(`/api/procurement/${path}/documents`, {
    headers,
    multipart: {
      revision: "0",
      file: {
        name: "synthetic.csv",
        mimeType: "text/csv",
        buffer: Buffer.from(
          `Manufacturer,MPN,Description,Qty,UOM\nNorthvale,000-P3.UI,Fictional device ${id},2,EA\n`,
        ),
      },
    },
  });
  expect(upload.ok()).toBeTruthy();
  const job = await post(`${path}/process`, {
    revision: 1,
    mode: "deterministic",
  });
  await expect
    .poll(async () => (await get(`rfq-jobs/${job.id}`)).state, {
      timeout: 60000,
    })
    .toBe("awaiting_review");
  const detail = await get(path);
  const line = detail.items[0].id;
  const reviewed = await page.request.patch(
    `/api/procurement/${path}/line-items/${line}`,
    {
      headers,
      data: {
        revision: detail.revision,
        fields: {},
        review_status: "reviewed",
        reason: "Explicit synthetic source review",
      },
    },
  );
  expect(reviewed.ok()).toBeTruthy();
  await post(`${path}/approve`, { revision: (await reviewed.json()).revision });
  const approved = await get(path);
  if (match) {
    const catalog = await post("catalogs", {
      name: "Phase 3 fictional catalog",
      license: "CC0 fictional",
    });
    const previewResponse = await page.request.post(
      `/api/procurement/catalogs/${catalog.id}/imports/preview`,
      {
        headers,
        multipart: {
          file: {
            name: "catalog.json",
            mimeType: "application/json",
            buffer: Buffer.from(
              JSON.stringify([
                {
                  source_id: "SYN-UI-1",
                  manufacturer: "Northvale",
                  mpn: "000-P3.UI",
                  name: "Fictional device",
                  category: "memory",
                  specs: { capacity: 32 },
                },
              ]),
            ),
          },
        },
      },
    );
    expect(previewResponse.ok()).toBeTruthy();
    const preview = await previewResponse.json();
    await post(`catalogs/${catalog.id}/imports/confirm`, {
      version_id: preview.id,
      fingerprint: preview.fingerprint,
    });
    await expect
      .poll(
        async () => (await get(`catalog-import-jobs/${preview.id}`)).state,
        { timeout: 120000 },
      )
      .toBe("published");
    const search = await post(`${path}/line-items/${line}/matches`, {
      revision: approved.revision,
      versions: [preview.id],
    });
    await post(`catalog-match-runs/${search.id}/review`, {
      decision: "select",
      product_id: search.candidates[0].id,
      note: "Reviewed synthetic exact identity",
    });
  }
  await page.goto("/procurement");
  await page
    .getByRole("button", { name: /Phase 3 synthetic quote request approved/ })
    .click();
  await expect(
    page.getByRole("heading", { name: "Research & internal quotations" }),
  ).toBeVisible();
  return { workspace, rfq: approved, line, post, get, headers };
}

async function resolve(page: Page) {
  const select = page.getByLabel("Final reviewed product", { exact: true });
  await select.selectOption({ index: 1 });
  await page
    .getByLabel("Selection resolution reason")
    .fill("Resolved authoritative exact product after source review");
  await page
    .getByRole("button", { name: "Record authorized resolution" })
    .click();
  await expect(page.getByText(/2 EA · resolved/)).toBeVisible();
}

async function attest(page: Page, expired = false) {
  await page.getByText(/Attest commercial offer for/).click();
  await page
    .getByLabel("Supplier", { exact: true })
    .fill("Fictional UI Supply");
  await page.getByLabel("Supplier price", { exact: true }).fill("10");
  await page.getByLabel("Offer currency").selectOption("USD");
  await page.getByLabel("Price basis").selectOption("each");
  await page.getByLabel("Units per pack").fill("1");
  await page.getByLabel("Minimum units to purchase").fill("1");
  await page.getByLabel("Availability statement").selectOption("available");
  const today = new Date();
  const observed = new Date(today.getTime() - 86400000 * 2)
    .toISOString()
    .slice(0, 10);
  const validity = new Date(today.getTime() + 86400000 * (expired ? -1 : 30))
    .toISOString()
    .slice(0, 10);
  await page.getByLabel("Source observed on").fill(observed);
  await page.getByLabel("Offer valid until", { exact: true }).fill(validity);
  await page
    .getByLabel("Commercial source reference")
    .fill("Fictional dated supplier note UI-001");
  await page
    .getByLabel("Offer attestation reason")
    .fill("Reviewed synthetic commercial source");
  await page.getByRole("button", { name: "Record user attestation" }).click();
  await expect(
    page.getByText("User-attested commercial offer recorded."),
  ).toBeVisible();
}

async function policy(page: Page) {
  await page.getByLabel("Pricing rate (0.20 = 20%)").fill("0.20");
  await page.getByLabel("Shipping amount").fill("5");
  await page.getByLabel("Tax rate (0 = reviewed zero)").fill("0.10");
  await page
    .getByLabel("Tax basis", { exact: true })
    .selectOption("subtotal_plus_shipping");
  await page
    .getByLabel("Quote valid until", { exact: true })
    .fill(new Date(Date.now() + 86400000 * 7).toISOString().slice(0, 10));
  await page
    .getByLabel("Pack / MOQ surplus policy")
    .selectOption("allocate_purchase_cost");
  await page.getByLabel(/Quote offer ·/).selectOption({ index: 1 });
  await page
    .getByLabel("Quote change / review reason")
    .fill("All synthetic commercial facts explicitly reviewed");
}

test("real Phase 3 reviewed offers quote changes approval history and native research", async ({
  page,
}) => {
  test.setTimeout(240000);
  const shot =
    process.env.RFQ_SCREENSHOT_DIR ?? "../../docs/rfq/phase3/screenshots";
  await prepare(page);
  await resolve(page);
  await attest(page);
  await page.getByRole("button", { name: "Compare attested offers" }).click();
  await expect(
    page.getByText(
      "Attested price comparison · same currency and purchasing basis only",
    ),
  ).toBeVisible();
  await page
    .getByLabel("Procurement research and quotes", { exact: true })
    .locator("article")
    .first()
    .screenshot({ path: `${shot}/supplier-comparison.png` });
  await policy(page);
  await page
    .getByRole("button", { name: "Save & calculate internal draft" })
    .click();
  await expect(page.getByText("31.90 USD", { exact: true })).toBeVisible();
  await page.getByLabel(/I reviewed product suitability/).check();
  await page
    .getByRole("button", { name: "Submit for internal review" })
    .click();
  await expect(
    page.getByRole("button", { name: "Request changes", exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Internal quote builder", { exact: true })
    .screenshot({ path: `${shot}/human-review.png` });
  await page
    .getByRole("button", { name: "Request changes", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Save & calculate internal draft" }),
  ).toBeVisible();
  await page.getByLabel("Shipping amount").fill("0");
  await page
    .getByRole("button", { name: "Save & calculate internal draft" })
    .click();
  await expect(page.getByText("26.40 USD", { exact: true })).toBeVisible();
  await page.getByLabel(/I reviewed product suitability/).check();
  await page
    .getByRole("button", { name: "Submit for internal review" })
    .click();
  await expect(
    page.getByRole("button", { name: "Approve internally", exact: true }),
  ).toBeVisible();
  await page.getByLabel(/I reviewed product suitability/).check();
  await page
    .getByRole("button", { name: "Approve internally", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Create new draft version" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "View quote history" }).click();
  await expect(
    page.getByText("Persisted revisions and audit evidence"),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Start local research", exact: true })
    .click();
  await expect(page.getByText(/1\. get_approved_rfq/)).toBeVisible({
    timeout: 120000,
  });
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: /Research (complete|needs attention|failed)/ }),
  ).toBeVisible({ timeout: 120000 });
  await page
    .getByLabel("Local agent research", { exact: true })
    .screenshot({ path: `${shot}/native-research.png` });
  await page
    .getByLabel("Internal quote builder", { exact: true })
    .screenshot({ path: `${shot}/approved-quote.png` });
  await page
    .getByLabel("Internal quote builder", { exact: true })
    .getByText(/calculation & source/)
    .click();
  await page
    .getByLabel("Internal quote builder", { exact: true })
    .screenshot({ path: `${shot}/calculation-breakdown.png` });
  await page
    .getByRole("button", { name: "View quote audit", exact: true })
    .click();
  await page
    .getByLabel("Internal quote builder", { exact: true })
    .screenshot({ path: `${shot}/audit-history.png` });
  await page
    .getByLabel("Procurement research and quotes", { exact: true })
    .screenshot({ path: `${shot}/research-workspace.png` });
  await page.reload();
  await page
    .getByRole("button", { name: /Phase 3 synthetic quote request approved/ })
    .click();
  await page
    .getByRole("button", { name: /approved internal · 26.40 USD/ })
    .click();
  await expect(
    page.getByRole("button", { name: "Create new draft version" }),
  ).toBeVisible();
  await expect(page.getByLabel("Shipping amount")).toBeDisabled();
  await page.setViewportSize({ width: 390, height: 844 });
  const overflow = await page.evaluate(() =>
    [...document.querySelectorAll("body *")]
      .filter(
        (element) => element.getBoundingClientRect().right > innerWidth + 1,
      )
      .slice(0, 12)
      .map((element) => ({
        tag: element.tagName,
        classes: element.className,
        text: element.textContent?.slice(0, 80),
        width: element.getBoundingClientRect().width,
        right: element.getBoundingClientRect().right,
      })),
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    JSON.stringify(overflow),
  ).toBeTruthy();
  await page
    .getByLabel("Internal quote builder", { exact: true })
    .screenshot({ path: `${shot}/mobile-quote.png` });
});

test("real expired attestation stays incomplete and cannot enter review", async ({
  page,
}) => {
  test.setTimeout(180000);
  await prepare(page);
  await resolve(page);
  await attest(page, true);
  await policy(page);
  await page
    .getByRole("button", { name: "Save & calculate internal draft" })
    .click();
  await expect(
    page.getByText("Total unresolved USD", { exact: true }),
  ).toBeVisible();
  await page.getByLabel(/I reviewed product suitability/).check();
  await expect(
    page.getByRole("button", { name: "Submit for internal review" }),
  ).toBeDisabled();
});

test("real no-selection quote stays incomplete and unavailable agent error is visible", async ({
  page,
}) => {
  test.setTimeout(120000);
  await prepare(page, false);
  await page
    .getByLabel("Quote change / review reason")
    .fill("Preserve no-match line for human investigation");
  await page
    .getByRole("button", { name: "Save & calculate internal draft" })
    .click();
  await expect(
    page.getByText("Total unresolved USD", { exact: true }),
  ).toBeVisible();
  await page.route("**/api/procurement/rfqs/*/research", (route) =>
    route.request().method() === "POST"
      ? route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({
            detail:
              "Explicit UI outage fixture: local native-tool model unavailable",
          }),
        })
      : route.continue(),
  );
  await page
    .getByRole("button", { name: "Start local research", exact: true })
    .click();
  await expect(
    page.getByText(
      "Explicit UI outage fixture: local native-tool model unavailable",
    ),
  ).toBeVisible();
});

test("real signed browser proxy rejects editor quote approval", async ({
  page,
}) => {
  test.setTimeout(120000);
  if (!process.env.DATABASE_URL?.includes("ownerpilot_rfq_phase3_demo"))
    throw new Error("Role probe requires the isolated Phase 3 demo database");
  const context = await prepare(page);
  await resolve(page);
  await attest(page);
  await policy(page);
  await page
    .getByRole("button", { name: "Save & calculate internal draft" })
    .click();
  await expect(page.getByText("31.90 USD", { exact: true })).toBeVisible();
  await page.getByLabel(/I reviewed product suitability/).check();
  await page
    .getByRole("button", { name: "Submit for internal review" })
    .click();
  await expect(
    page.getByRole("button", { name: "Approve internally", exact: true }),
  ).toBeVisible();
  const session = await (
    await page.request.get("/api/auth/get-session")
  ).json();
  const pool = new Pool({ connectionString: process.env.DATABASE_URL });
  try {
    await pool.query(
      "update workspace_members set role='editor' where workspace_id=$1 and user_id=$2",
      [context.workspace.id, session.user.id],
    );
    await page.getByLabel(/I reviewed product suitability/).check();
    await page
      .getByRole("button", { name: "Approve internally", exact: true })
      .click();
    await expect(
      page.getByText(
        "Owner, admin or reviewer role is required for approval.",
        { exact: true },
      ),
    ).toBeVisible();
  } finally {
    await pool.query(
      "update workspace_members set role='owner' where workspace_id=$1 and user_id=$2",
      [context.workspace.id, session.user.id],
    );
    await pool.end();
  }
});
