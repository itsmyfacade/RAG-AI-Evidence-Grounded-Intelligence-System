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
    await expect(page.getByRole("button", { name: "Export review decisions" })).toBeDisabled();
    await expect(page.getByLabel("Import saved decisions")).toBeVisible();
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
    await page.locator("#decision").selectOption("confirmed");
    await page.locator("#review-notes").fill("Source supports the observed behavior.");
    await page.getByRole("button", { name: "Save decision" }).click();
    await expect(page.locator("#reviewed-count")).toHaveText("1");
    await expect(page.locator("#ambiguous-count")).toHaveText("0");
    await expect(page.locator("#review-progress-label")).toHaveText("100%");
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "Export review decisions" }).click();
    expect((await downloadPromise).suggestedFilename()).toBe("aegis-ground-truth-review-decisions.json");
  });

  test("restores matching decisions and rejects a mismatched export", async ({ page }) => {
    await page.goto("/demo/review.html");
    const packet = { dataset_version: "resume-packet", cases: [{ case_id: "RESUME-001", category: "api", split: "validation", answerability: "answerable", difficulty: "introductory", question: "Can this case resume?", expected_evidence: [], potential_distractors: [], review_rationale: "Check persistence." }] };
    await page.locator("#packet-file").setInputFiles({ name: "packet.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(packet)) });
    await page.locator("#decision").selectOption("ambiguous");
    await page.locator("#review-notes").fill("Needs a second look.");
    await expect(page.locator("#storage-status")).toContainText("Saved locally");
    await page.reload();
    await page.locator("#packet-file").setInputFiles({ name: "packet.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(packet)) });
    await expect(page.locator("#reviewed-count")).toHaveText("1");
    await expect(page.locator("#ambiguous-count")).toHaveText("1");
    await expect(page.locator("#review-notes")).toHaveValue("Needs a second look.");
    const mismatch = { schema_version: "aegis-phase4-review-decisions-v1", packet_fingerprint: "sha256-not-this-packet", decisions: { "RESUME-001": { decision: "confirmed", notes: "wrong", reviewed_at: new Date().toISOString() } } };
    await page.locator("#decisions-file").setInputFiles({ name: "wrong.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(mismatch)) });
    await expect(page.locator("#review-status")).toContainText("different review packet");
    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "Reset saved decisions" }).click();
  });

  test("reports browser storage failures without hiding the export path", async ({ page }) => {
    await page.addInitScript(() => {
      Object.defineProperty(window, "localStorage", { configurable: true, get: () => ({ getItem: () => { throw new Error("storage blocked"); }, setItem: () => { throw new Error("storage blocked"); }, removeItem: () => { throw new Error("storage blocked"); } }) });
    });
    await page.goto("/demo/review.html");
    await expect(page.locator("#storage-status")).toContainText("Browser storage is unavailable");
    const packet = { dataset_version: "storage-failure-packet", cases: [{ case_id: "STORAGE-001", category: "api", split: "validation", answerability: "answerable", difficulty: "introductory", question: "Can export recover this work?", expected_evidence: [], potential_distractors: [], review_rationale: "Check export fallback." }] };
    await page.locator("#packet-file").setInputFiles({ name: "packet.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(packet)) });
    await page.locator("#decision").selectOption("confirmed");
    await expect(page.locator("#storage-status")).toContainText("Could not save locally");
    await expect(page.getByRole("button", { name: "Export review decisions" })).toBeEnabled();
  });

  test("reviews captured model output without exposing expected labels", async ({ page }) => {
    await page.goto("/demo/model-review.html");
    const packet = {
      schema_version: "aegis-phase3-model-output-review-packet-v1",
      source_run_id: "test-run",
      blinded: true,
      cases: [{
        case_id: "RET-001",
        question: "What did AEGIS observe?",
        output_status: "completed",
        actual_output: { answer: "Actual captured answer", findings: [], retrieved_evidence: [{ rank: 1, evidence_id: "DOC-001", excerpt: "Observed evidence." }], citations: ["DOC-001"], abstention: { status: "not_abstained" } },
        run_metadata: { provider: "local", model: "deterministic-local", retrieval_mode: "lexical", latency_ms: 2 },
      }],
    };
    await page.locator("#model-packet-file").setInputFiles({ name: "model-output.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(packet)) });
    await expect(page.locator("#model-total")).toHaveText("1");
    await expect(page.getByText("Actual captured answer", { exact: true })).toBeVisible();
    await expect(page.getByText("Expected evidence", { exact: true })).toHaveCount(0);
    await page.locator("#model-overall-decision").selectOption("supported_correct");
    await page.locator("#model-review-notes").fill("The captured evidence supports the observed statement.");
    await expect(page.locator("#model-overall-decision")).toHaveValue("supported_correct");
    await expect(page.locator("#model-review-notes")).toHaveValue("The captured evidence supports the observed statement.");
    await page.getByRole("button", { name: "Save decision locally" }).click();
    await expect(page.locator("#model-reviewed-count")).toHaveText("1");
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "Export model-review decisions" }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe("aegis-model-output-review-decisions.json");
    const stream = await download.createReadStream();
    const chunks = [];
    for await (const chunk of stream) chunks.push(chunk);
    const exported = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    expect(exported.schema_version).toBe("aegis-phase3-model-output-decisions-v3");
    expect(exported.fingerprint_contract).toBe("aegis-phase3-fingerprint-v3");
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
