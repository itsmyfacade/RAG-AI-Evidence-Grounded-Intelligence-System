const { defineConfig, devices } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [["html", { outputFolder: "playwright-report", open: "never" }], ["list"]],
  use: {
    baseURL: "http://127.0.0.1:8000",
    browserName: "chromium",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "python -m uvicorn src.api:app --host 127.0.0.1 --port 8000",
    url: "http://127.0.0.1:8000/ready",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      AEGIS_DEPLOYMENT_PROFILE: "lite",
      AEGIS_LLM: "local",
      AEGIS_EMBEDDINGS: "local",
      AEGIS_EMBEDDING_LOCAL_FILES_ONLY: "true",
    },
  },
});
