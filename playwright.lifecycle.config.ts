/**
 * Minimal Playwright config for running the WF2 lifecycle test in isolation.
 * Skips global setup/teardown (which require docker-compose v1).
 * The lifecycle test seeds its own data via beforeAll.
 */
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [['line']],
  timeout: 300000,
  expect: { timeout: 10000 },
  use: {
    baseURL: 'http://localhost:8000',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
