const { test, expect } = require("@playwright/test");

test.describe("AEGIS hosted-lite investigation workbench", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/demo/");
    await expect(page.getByText("Service ready", { exact: true })).toBeVisible();
    await expect(page.getByLabel("Scenario selection")).toHaveValue(/SCN-/);
    await expect(page.locator("#sample-count")).toHaveText("20 interactive investigation scenarios");
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

  test("shows provenance dashboard and keeps the review workflow usable on mobile", async ({ page }) => {
    await page.getByRole("button", { name: "Validation dashboard" }).click();
    await expect(page.locator("#workspace-title")).toHaveText("Validation dashboard");
    await expect(page.getByRole("heading", { name: "Validation dashboard", exact: true })).toHaveCount(1);
    await expect(page.getByText(/Artifact phase3-optimized-final-run1-result\.json/)).toBeVisible();
    await expect(page.getByText("Same 1,200-case workload", { exact: true })).toBeVisible();
    await expect(page.getByText("Human review is pending.", { exact: true })).toBeVisible();

    await page.goto("/demo/review.html");
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByRole("heading", { name: "Ground-truth review" })).toBeVisible();
    await expect(page.getByText("One case at a time, with the evidence beside it.", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: /complete review first/i })).toBeDisabled();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    expect(overflow).toBe(false);
  });

  test("records a review decision and exports it as a separate artifact", async ({ page }) => {
    await page.goto("/demo/review.html");
    const packet = {
      dataset_version: "test-packet",
      cases: [{
        case_id: "TEST-001",
        category: "api_authentication",
        split: "validation",
        answerability: "answerable",
        difficulty: "introductory",
        question: "Does the source support the observed request behavior?",
        expected_evidence: [{ document_id: "DOC-001", title: "Test source", excerpt: "The source records the observed behavior." }],
        potential_distractors: [],
        review_rationale: "Confirm the label against the source excerpt.",
      }],
    };
    await page.locator("#packet-file").setInputFiles({ name: "packet.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(packet)) });
    await expect(page.locator("#review-total")).toHaveText("1");
    await expect(page.locator("#pending-count")).toHaveText("1");
    await expect(page.getByRole("button", { name: /complete review first/i })).toBeDisabled();
    await page.locator("#decision").selectOption("confirmed");
    await page.locator("#review-notes").fill("Source supports the observed behavior.");
    await page.getByRole("button", { name: "Save decision" }).click();
    await expect(page.locator("#reviewed-count")).toHaveText("1");
    await expect(page.locator("#review-progress-label")).toHaveText("100%");
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "Export review decisions" }).click();
    expect((await downloadPromise).suggestedFilename()).toBe("aegis-ground-truth-review-decisions.json");
  });

  for (const width of [390, 768, 1024, 1440, 1920]) {
    test(`does not overflow horizontally at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.reload();
      await expect(page.getByText("Service ready", { exact: true })).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
      expect(overflow).toBe(false);
    });
  }
});
