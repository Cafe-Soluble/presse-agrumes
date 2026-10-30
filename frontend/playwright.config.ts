import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  use: {
    baseURL: "http://127.0.0.1:8099",
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
  },
  webServer: {
    command: ".venv/bin/python -m presse_agrumes --config tests/playwright.config.toml --strict-port",
    cwd: "..",
    url: "http://127.0.0.1:8099/api/health",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
