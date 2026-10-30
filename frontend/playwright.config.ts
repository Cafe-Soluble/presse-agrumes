import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  use: {
    baseURL: process.env.PA_URL ?? "http://127.0.0.1:8080",
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
  },
  webServer: process.env.PA_URL
    ? undefined
    : {
        command: "cd .. && .venv/bin/python -m presse_agrumes --port 8080",
        url: "http://127.0.0.1:8080/api/health",
        reuseExistingServer: true,
        timeout: 120_000,
      },
});
