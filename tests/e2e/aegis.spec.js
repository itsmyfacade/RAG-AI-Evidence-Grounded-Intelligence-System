const { test, expect } = require("@playwright/test");

test.describe("AEGIS hosted-lite investigation workbench", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/demo/");
    await expect(page.getByText("Service ready", { exact: true })).toBeVisible();
    await expect(page.getByLabel("Scenario selection")).toHaveValue(/SCN-/);
  });

  test("loads, searches scenarios, investigates SCN-005, and exposes evidence and execution", async ({ page }) => {
    await page.getByRole("button", { name: "Scenarios" }).click();
    await expect(page.getByRole("heading", { name: "Scenario explorer" })).toBeVisible();
    await page.locator("#catalog-filter").fill("SCN-005");
    await expect(page.locator(".scenario-card")).toHaveCount(1);
    await expect(page.locator(".scenario-card")).toContainText("SCN-005");
    await page.locator(".scenario-card").getByRole("button", { name: /Investigate/ }).click();

    await expect(page.getByRole("heading", { name: "Incident investigation" })).toBeVisible();
    await expect(page.getByLabel("Scenario selection")).toHaveValue("SCN-005");
    await expect(page.getByLabel("Investigation question")).not.toHaveValue("");
    const investigation = page.waitForResponse(
      (response) => response.url().endsWith("/investigate") && response.request().method() === "POST",
    );
    await page.getByRole("button", { name: /Run investigation/i }).click();
    expect((await investigation).status()).toBe(200);

    await expect(page.getByRole("heading", { name: "Evidence-backed assessment" })).toBeVisible();
    await expect(page.getByText("Plausible hypothesis")).toBeVisible();
    await expect(page.getByText("Evidence explorer")).toBeVisible();
    const evidenceGroup = page.locator("details.evidence-group").filter({ hasText: "Document" }).first();
    await expect(evidenceGroup).toBeVisible();
    await evidenceGroup.locator(":scope > summary").click();
    await expect(evidenceGroup).toHaveAttribute("open", "");

    await page.getByRole("button", { name: "Execution trace", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Workflow timeline" })).toBeVisible();
    const executionTrace = page.locator("#execution-view-trace");
    for (const stage of ["Supervisor", "Document research", "Operations analysis", "Investigation synthesis", "Evidence verification"]) {
      await expect(executionTrace.getByText(stage, { exact: true })).toBeVisible();
    }
    await page.getByRole("button", { name: "Investigate workspace" }).click();
    await expect(page.getByRole("heading", { name: "Evidence-backed assessment" })).toBeVisible();
  });

  test("scenario changes invalidate a completed report and keyboard navigation works", async ({ page }) => {
    await page.getByRole("button", { name: "Scenarios" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { name: "Scenario explorer" })).toBeVisible();
    await page.getByRole("button", { name: "Investigate workspace" }).click();
    await page.getByLabel("Scenario selection").selectOption("SCN-005");
    const investigation = page.waitForResponse(
      (response) => response.url().endsWith("/investigate") && response.request().method() === "POST",
    );
    await page.getByRole("button", { name: /Run investigation/i }).click();
    expect((await investigation).status()).toBe(200);
    await expect(page.getByRole("heading", { name: "Evidence-backed assessment" })).toBeVisible();

    await page.getByLabel("Scenario selection").selectOption("SCN-006");
    await expect(page.getByRole("heading", { name: "Evidence-backed assessment" })).toBeHidden();
    await expect(page.locator("#action-readiness")).toHaveText("Ready to investigate");
  });

  for (const width of [1440, 1024, 900]) {
    test(`does not overflow horizontally at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.reload();
      await expect(page.getByText("Service ready", { exact: true })).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
      expect(overflow).toBe(false);
    });
  }
});
