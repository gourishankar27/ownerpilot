import { test, expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { Pool } from "pg";
import { signupSynthetic } from "./rfq-account";

// The sources and completed results were produced by real Ollama/tool execution.
// Only tests explicitly labelled UI fixture override the run response.
async function openNativeHistory(
  page: Page,
  fixture?: "partial" | "staged" | "legacy",
) {
  if (
    !process.env.DATABASE_URL?.includes(
      "ownerpilot_rfq_phase3_demo_phase31_validation",
    )
  )
    throw new Error(
      "Requires isolated Phase 3.1 validation database and native development results",
    );
  const state = JSON.parse(
    readFileSync(
      resolve("../../.local/rfq/phase3_1/evaluation-state.json"),
      "utf8",
    ),
  );
  const measured = JSON.parse(
    readFileSync(
      resolve(
        "../../docs/rfq/phase3_1/results/evaluation/dev-contract6/dev-02-citation_repair.json",
      ),
      "utf8",
    ),
  );
  await signupSynthetic(page, "citations");
  const session = await (
    await page.request.get("/api/auth/get-session")
  ).json();
  const pool = new Pool({ connectionString: process.env.DATABASE_URL });
  try {
    await pool.query(
      "insert into workspace_members(workspace_id,user_id,role) values($1,$2,'reviewer')",
      [state.workspace, session.user.id],
    );
  } finally {
    await pool.end();
  }
  if (fixture) {
    await page.route(
      `**/api/procurement/agent-runs/${measured.run_id}`,
      async (route) => {
        const actual = await (await route.fetch()).json();
        if (fixture === "legacy") {
          actual.metadata.claim_schema = undefined;
          actual.metadata.prompt_version = "procurement-native/5";
          actual.result = {
            claims: [
              {
                receipt_id: "explicit-legacy-ui-fixture",
                pointer: "/data/price",
                value: "10",
              },
            ],
            limitations: ["Explicit legacy UI fixture"],
          };
        } else {
          actual.state = fixture === "staged" ? "verifying" : "needs_attention";
          actual.repair_attempts = 1;
          actual.diagnostics = { recovered: true, stage: "citation_repair" };
          actual.result.partial = fixture === "partial";
          actual.result.complete = fixture === "staged";
          actual.result.invalid_citations = [
            { code: "incorrect_claim_association" },
          ];
        }
        await route.fulfill({ json: actual });
      },
    );
  }
  await page.goto("/procurement");
  await expect(page.getByLabel("Workspace")).toContainText(
    "Phase 3.1 independent synthetic research study",
  );
  await page.getByLabel("Workspace").selectOption(state.workspace);
  await page
    .getByLabel("Search RFQs")
    .fill("Independent synthetic study dev-02");
  await page
    .getByRole("button", { name: /Independent synthetic study dev-02/ })
    .click();
  const research = page.getByLabel("Local agent research", { exact: true });
  await research
    .getByRole("button", { name: new RegExp(measured.run_id.slice(0, 8)) })
    .click();
  return research;
}

test("real native history shows backend materialized unknowns, provenance and quote follow-up", async ({
  page,
}) => {
  const research = await openNativeHistory(page);
  await expect(research).toContainText("Citation-only research");
  await expect(research).toContainText("Research complete and published");
  await expect(research).toContainText("Quote inputs require human follow-up");
  await research.getByText(/Line .*coverage complete/).click();
  await expect(research).toContainText("Unknown price");
  await research.getByText("Source and entity associations").first().click();
  await expect(research).toContainText("source_fingerprint");
  await research.screenshot({
    path: "../../docs/rfq/phase3_1/screenshots/native-missing-price.png",
  });
  await page.reload();
  await page
    .getByLabel("Search RFQs")
    .fill("Independent synthetic study dev-02");
  await page
    .getByRole("button", { name: /Independent synthetic study dev-02/ })
    .click();
  await expect(
    page.getByLabel("Local agent research", { exact: true }),
  ).toContainText("complete");
});

for (const fixture of ["partial", "staged"] as const) {
  test(`explicit UI fixture: ${fixture} citations cannot display published completion`, async ({
    page,
  }) => {
    const research = await openNativeHistory(page, fixture);
    await expect(research).toContainText(
      "Research incomplete or awaiting publication",
    );
    await expect(research).not.toContainText("Research complete and published");
    await expect(research).toContainText("Citation corrections 1/1");
    await expect(research).toContainText("resumed from durable checkpoints");
    await expect(research.getByRole("alert")).toContainText(
      "incorrect claim association",
    );
    if (fixture === "partial")
      await expect(research).toContainText("partial evidence saved");
    await research.screenshot({
      path: `../../docs/rfq/phase3_1/screenshots/${fixture}-ui-fixture.png`,
    });
  });
}

test("explicit UI fixture: legacy exact-value history remains labelled and readable", async ({
  page,
}) => {
  const research = await openNativeHistory(page, "legacy");
  await expect(research).toContainText(
    "Legacy research · original exact-value verification",
  );
  await expect(research).toContainText("explicit-legacy-ui-fixture");
  await expect(research).not.toContainText("Citation corrections");
});
