// Playwright: plays the SPEC's 10-step story in a real browser (npx playwright test).
//
// It builds the UI, then starts `python app.py --port 8650` against a TEMPORARY ledger
// (GUARDIAN_DB) and run-log folder, so the real demo ledger (data/guardian.db) is never touched.
// Set PYTHON to the interpreter with the project's requirements installed (default: python).
// Never calls the AI: the sweeps run without it.
import { defineConfig, devices } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const PORT = Number(process.env.E2E_PORT ?? 8650);
const DATA = process.env.GUARDIAN_E2E_DIR ?? join(tmpdir(), `customer-guardian-e2e-${PORT}`);
mkdirSync(DATA, { recursive: true });
const PYTHON = process.env.PYTHON ?? 'python';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1, // one ledger: the tests run one after the other
  timeout: 180_000,
  expect: { timeout: 15_000 },
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: `npm run build && cd .. && "${PYTHON}" app.py --port ${PORT}`,
    url: `http://127.0.0.1:${PORT}/api/demo/status`,
    reuseExistingServer: false,
    timeout: 180_000,
    stdout: 'pipe',
    env: {
      ...(process.env as Record<string, string>),
      GUARDIAN_DB: join(DATA, 'guardian.db'),
      GUARDIAN_RUNS_DIR: join(DATA, 'runs'),
    },
  },
});
