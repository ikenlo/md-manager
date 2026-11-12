import { defineConfig, devices } from '@playwright/test';

/**
 * E2E: власні порти (не заважають `npm run dev` на 5173/8000).
 * Бекенд — e2e/backend.py: чиста тимчасова БД, демо-дані, MOCK_META і MOCK_OLLAMA.
 *
 *   npm run test:e2e
 *
 * Перший раз на новому ПК: `npx playwright install chromium`.
 * Python береться з E2E_PYTHON (типово `python`) — у ньому мають бути залежності бекенда.
 */
const API_PORT = Number(process.env.E2E_API_PORT ?? 8765);
const WEB_PORT = Number(process.env.E2E_WEB_PORT ?? 5199);
const PYTHON = process.env.E2E_PYTHON ?? 'python';


export default defineConfig({
  testDir: './e2e',
  // тести ділять одну БД — по черзі
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  expect: { timeout: 8_000 },
  retries: process.env.CI ? 1 : 0,
  reporter: [['list']],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: 'off',
    screenshot: 'only-on-failure',
    ...devices['Desktop Chrome'],
    viewport: { width: 1440, height: 900 },
  },
  webServer: [
    {
      command: `${PYTHON} e2e/backend.py`,
      url: `http://localhost:${API_PORT}/api/health`,
      env: { E2E_API_PORT: String(API_PORT) },
      reuseExistingServer: false,
      timeout: 60_000,
      // логи бекенда (планувальник кожні 2 с) — лише з E2E_VERBOSE=1
      stdout: 'ignore',
      stderr: process.env.E2E_VERBOSE ? 'pipe' : 'ignore',
    },
    {
      command: `npx vite --port ${WEB_PORT} --strictPort`,
      url: `http://localhost:${WEB_PORT}`,
      env: { MDS_API_TARGET: `http://localhost:${API_PORT}` },
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
