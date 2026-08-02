import { defineConfig, devices } from '@playwright/test';

/**
 * playwright.config.ts
 * @see https://playwright.dev/docs/test-configuration
 */
export default defineConfig({
  testDir:    './e2e',
  fullyParallel: false,  // Keep false until DB isolation is set up
  forbidOnly: !!process.env.CI,
  retries:    process.env.CI ? 2 : 0,
  workers:    process.env.CI ? 1 : undefined,
  reporter:   [['html'], ['list']],

  use: {
    baseURL:           process.env.APP_URL ?? 'http://localhost:8000',
    trace:             'on-first-retry',
    screenshot:        'only-on-failure',
    video:             'retain-on-failure',
    actionTimeout:     15_000,
    navigationTimeout: 30_000,
  },

  projects: [
    {
      name:    'chromium',
      use:     { ...devices['Desktop Chrome'] },
    },
    {
      name:    'Mobile Safari',
      use:     { ...devices['iPhone 14'] },
    },
  ],

  // Spin up the Laravel dev server if not already running
  // webServer: {
  //   command:            'php artisan serve',
  //   url:                'http://localhost:8000',
  //   reuseExistingServer: !process.env.CI,
  // },
});
