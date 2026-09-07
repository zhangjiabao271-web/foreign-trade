import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "../..");
const python =
  process.platform === "win32"
    ? ".\\.venv\\Scripts\\python.exe"
    : "./.venv/bin/python";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  use: {
    baseURL: "http://127.0.0.1:3100",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    ...devices["Desktop Chrome"],
  },
  webServer: [
    {
      command: `${python} apps/api/scripts/run_e2e_server.py`,
      cwd: root,
      url: "http://127.0.0.1:8010/health/live",
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `${python} apps/api/scripts/run_e2e_web.py`,
      cwd: root,
      env: {
        INTERNAL_API_BASE_URL: "http://127.0.0.1:8010",
        E2E_AUTH_MODE: "bearer",
      },
      url: "http://127.0.0.1:3100/api/health",
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
