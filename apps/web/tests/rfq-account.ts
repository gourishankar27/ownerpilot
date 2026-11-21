import { expect, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";

// Respect the real Better Auth limit during repeated local suites. Never bypass it.
export async function signupSynthetic(page: Page, prefix = "rfq") {
  const id = randomUUID();
  const options = {
    data: {
      name: "Synthetic RFQ Reviewer",
      email: `${prefix}-${id}@example.test`,
      password: `Rfq-${randomUUID()}!`,
    },
    headers: {
      origin: new URL(process.env.RFQ_WEB_URL ?? "http://localhost:3000")
        .origin,
    },
  };
  let signup = await page.request.post("/api/auth/sign-up/email", options);
  if (signup.status() === 429) {
    const seconds = Number(signup.headers()["x-retry-after"]);
    expect(
      Number.isFinite(seconds) && seconds >= 0 && seconds <= 65,
    ).toBeTruthy();
    await new Promise((resolve) => setTimeout(resolve, (seconds + 1) * 1000));
    signup = await page.request.post("/api/auth/sign-up/email", options);
  }
  expect(signup.ok(), await signup.text()).toBeTruthy();
  return id;
}
