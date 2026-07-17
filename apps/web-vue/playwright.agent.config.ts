import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  testMatch: ['agent-creative-flow.spec.ts', 'agent-workspace.spec.ts'],
  timeout: 50 * 60 * 1000,
  expect: {
    timeout: 120 * 1000,
  },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: process.env.E2E_WEB_URL || process.env.PW_BASE_URL || 'http://127.0.0.1:3010',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})