import { test, expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { Pool } from "pg";
import { signupSynthetic } from "./rfq-account";

type Fixture = "partial" | "recovered" | "capacity";

async function openHistory(page: Page, caseId: string, fixture?: Fixture) {
  if (!process.env.DATABASE_URL?.includes("phase31_validation_phase32"))
    throw new Error("Requires isolated Phase 3.2 database");
  const state = JSON.parse(
    readFileSync(
      resolve("../../.local/rfq/phase3_2/evaluation-state.json"),
      "utf8",
    ),
  );
  const measured = JSON.parse(
    readFileSync(
      resolve(
        `../../docs/rfq/phase3_2/results/evaluation/dev-plan7-v2/${caseId}-hybrid.json`,
      ),
      "utf8",
    ),
  );
  await signupSynthetic(page, "coverage32");
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
        if (fixture === "recovered") {
          actual.diagnostics = { recovered: true, stage: "receipt_persisted" };
          actual.attempts = 2;
        } else {
          actual.state = "needs_attention";
          actual.finalization_calls = 0;
          actual.result.complete = false;
          actual.result.partial = true;
          actual.result.invalid_citations = [];
          actual.coverage_state.covered_lines = 0;
          actual.coverage_state.lines = actual.coverage_state.lines.map(
            (line: object) => ({
              ...line,
              source_covered: false,
              offers_inspected: false,
              missing_tools: ["get_supplier_offers"],
            }),
          );
          if (fixture === "capacity") {
            actual.error = "capacity_line_limit";
            actual.coverage_state.total_lines = 13;
            actual.coverage_state.capacity = {
              supported: false,
              maximum_lines: 12,
              continuation_available: false,
              continuation_guidance:
                "Create a separately reviewed scoped RFQ if this approved scope exceeds the envelope",
            };
          }
        }
        await route.fulfill({ json: actual });
      },
    );
  }
  await page.goto("/procurement");
  await page.getByLabel("Workspace").selectOption(state.workspace);
  await page
    .getByLabel("Search RFQs")
    .fill(`Independent synthetic study ${caseId}`);
  await page
    .getByRole("button", {
      name: new RegExp(`Independent synthetic study ${caseId}`),
    })
    .click();
  const research = page.getByLabel("Local agent research", { exact: true });
  await research
    .getByRole("button", { name: new RegExp(measured.run_id.slice(0, 8)) })
    .click();
  return research;
}

for (const [caseId, lines] of [
  ["v3-dev-01", 1],
  ["v3-dev-02", 2],
  ["v3-dev-05", 12],
] as const) {
  test(`real native ${lines}-line history separates source reads from citations`, async ({
    page,
  }) => {
    const research = await openHistory(page, caseId);
    const coverage = research.getByLabel("Coverage-aware planning");
    await expect(coverage).toContainText(
      `Source coverage: ${lines} of ${lines} lines`,
    );
    await expect(coverage).toContainText("Native model-selected tool calls:");
    await expect(coverage).toContainText("Backend scheduled tool calls:");
    await expect(research).toContainText("Research complete and published");
    await coverage
      .getByText("Recorded research activity", { exact: true })
      .click();
    await expect(coverage).toContainText("receipt persisted");
    await coverage
      .getByText(/sources inspected/)
      .first()
      .click();
    await expect(coverage).toContainText("Required citations: verified");
    await research.screenshot({
      path: `../../docs/rfq/phase3_2/screenshots/native-${lines}-line.png`,
    });
  });
}

for (const fixture of ["partial", "recovered", "capacity"] as const) {
  test(`explicit UI fixture: ${fixture} coverage remains honestly labelled`, async ({
    page,
  }) => {
    const research = await openHistory(page, "v3-dev-05", fixture);
    if (fixture === "recovered") {
      await expect(research).toContainText("resumed from durable checkpoints");
      await expect(research).toContainText("Research complete and published");
    } else {
      await expect(research).not.toContainText(
        "Research complete and published",
      );
      await expect(research).toContainText("required reads missing");
      await expect(research).not.toContainText(
        "Citation verification rejected",
      );
    }
    if (fixture === "capacity") {
      await expect(research).toContainText(
        "Research scope exceeds safe capacity",
      );
      await expect(research).toContainText("separately reviewed scoped RFQ");
      await expect(research).toContainText(
        "Automatic continuation: unavailable",
      );
    }
    await research.screenshot({
      path: `../../docs/rfq/phase3_2/screenshots/${fixture}-ui-fixture.png`,
    });
  });
}
