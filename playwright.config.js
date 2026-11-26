import {defineConfig, devices} from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 45_000,
  expect: {timeout: 8_000},
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: 'http://127.0.0.1:8000',
    ...devices['Desktop Chrome'],
    ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ?
      {launchOptions: {executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
                       args: ['--no-sandbox', '--disable-setuid-sandbox']}} : {}),
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'CHESS_LOW_RAM=1 python server.py',
    url: 'http://127.0.0.1:8000/api/state',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
