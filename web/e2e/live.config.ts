// Playwright for the live apps: the customer app and the Westpac dashboard side by side, with the
// automatic sweeps on (`app.py --live`) and the AI forced OFF so the run is repeatable.
//
//   npx playwright test -c e2e/live.config.ts        (from web/)
//
// It builds the UI and starts app.py on 127.0.0.1:8661 against a TEMPORARY ledger, clean-data and
// run-log folder, so the demo data is never touched. The walkthrough's specs keep their own config
// (playwright.config.ts) and don't run here.
import { defineConfig, devices } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const WEB = fileURLToPath(new URL('..', import.meta.url));
const ROOT = fileURLToPath(new URL('../..', import.meta.url));
const PORT = Number(process.env.E2E_LIVE_PORT ?? 8661);
const DATA = process.env.GUARDIAN_E2E_DIR ?? join(tmpdir(), `customer-guardian-live-e2e-${PORT}`);
mkdirSync(DATA, { recursive: true });
const PYTHON = process.env.PYTHON ?? 'python';

export default defineConfig({
  testDir: '.',
  testMatch: 'live.story.ts',
  outputDir: join(WEB, 'test-results'),
  fullyParallel: false,
  workers: 1,
  timeout: 240_000,
  expect: { timeout: 30_000 },
  reporter: [['list']],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: `npm run build && "${PYTHON}" "${join(ROOT, 'app.py')}" --live --port ${PORT}`,
    cwd: WEB,
    url: `http://127.0.0.1:${PORT}/api/live/status`,
    reuseExistingServer: false,
    timeout: 180_000,
    stdout: 'pipe',
    env: {
      ...(process.env as Record<string, string>),
      GUARDIAN_DB: join(DATA, 'guardian.db'),
      GUARDIAN_RUNS_DIR: join(DATA, 'runs'),
      GUARDIAN_CLEAN_DIR: join(DATA, 'clean'),
      GUARDIAN_LIVE_AI: '0', // repeatable: the sweeps and intake reviews run without the AI
      GUARDIAN_LIVE_INTERVAL: '2',
    },
  },
});
