// The SPEC's "one customer, start to finish" story, played in one browser tab like a person would:
// no AI (sweeps run without it), staff click Approve / Execute themselves, and the call code is read
// from the customer's phone view. The Home guide must tick all 10 steps.
import { Locator, Page, expect, test } from '@playwright/test';

const HERO = 'cust_af4200';

async function go(page: Page, label: 'Home' | 'Ledger (C)' | 'Policy (D)' | 'Actions (E)') {
  await page.getByRole('navigation', { name: 'Pages' }).getByRole('link', { name: label }).click();
}

async function expectSteps(page: Page, done: number[]) {
  await go(page, 'Home');
  for (let n = 1; n <= 10; n++) {
    await expect(page.getByTestId(`story-step-${n}`)).toHaveAttribute('data-done', String(done.includes(n)));
  }
}

async function loadStage(page: Page, stage: 'start' | 'full') {
  await go(page, 'Home');
  await page.getByTestId('stage-select').selectOption(stage);
  await page.getByRole('button', { name: 'Load demo data' }).click();
  await expect(page.getByText(`Loaded stage '${stage}'`)).toBeVisible();
}

async function sweepWithoutAI(page: Page) {
  await go(page, 'Policy (D)');
  const button = page.getByRole('button', { name: 'Run sweep without the AI' });
  await button.click();
  await expect(button).toBeEnabled({ timeout: 60_000 });
  await expect(page.getByTestId('run-log')).toContainText('COMPLETED');
}

/** The pending card for hero's recommendation of a kind (e.g. "Quiet Help Push"). */
function heroCard(page: Page, kind: string): Locator {
  return page.locator('[data-testid^="rec-"]').filter({ hasText: kind }).filter({ hasText: HERO });
}

async function approveAndExecute(page: Page, kind: string) {
  await go(page, 'Actions (E)');
  await page.getByRole('tab', { name: 'Approval Queue' }).click();
  await page.getByTestId('staff-select').selectOption('staff_19c');
  const card = heroCard(page, kind);
  await expect(card).toHaveCount(1);
  const recId = (await card.getAttribute('data-testid'))!.replace('rec-', '');
  await card.getByRole('button', { name: 'Approve' }).click();
  await expect(page.getByText(`${recId}: APPROVED — saved in ledger`)).toBeVisible();
  // Approved cards move to "Approved — Awaiting Execution"; a person carries each one out.
  await page.getByTestId(`rec-${recId}`).getByRole('button', { name: 'Execute' }).click();
  await expect(page.getByText(`${recId}: carried out`)).toBeVisible();
  return recId;
}

test('the 10-step story plays in one tab and the Home guide ticks all 10', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('data-brand', 'wbc');

  // Steps 1-2: A scores hero 63 HIGH; C's Quiet Help rule lists hero.
  await loadStage(page, 'start');
  await expectSteps(page, [1, 2]);
  await expect(page.getByTestId('story-next')).toContainText('Policy');

  // Step 3: D's sweep recommends a Quiet Help push (no AI).
  await sweepWithoutAI(page);
  await expect(page.getByTestId('recommendations')).toContainText('QUIET_HELP_PUSH');
  await expectSteps(page, [1, 2, 3]);

  // Steps 4-5: a person approves it, then E carries it out (push notification).
  await approveAndExecute(page, 'Quiet Help Push');
  await expectSteps(page, [1, 2, 3, 4, 5]);

  // Steps 6-7: hero submits the hardship form (stand-in for Node B's form): 75 HIGH, case open.
  await page.getByRole('button', { name: 'Simulate: hero submits hardship form' }).click();
  await expectSteps(page, [1, 2, 3, 4, 5, 6, 7]);
  await go(page, 'Ledger (C)');
  await expect(page.getByTestId('combined-score')).toContainText('75 HIGH');
  await expect(page.getByTestId('open-case')).toContainText('due 01 Dec');

  // Step 8: the next sweep recommends BOOK_MEETING; a person approves; E books the call.
  await sweepWithoutAI(page);
  await approveAndExecute(page, 'Book Meeting');
  await expectSteps(page, [1, 2, 3, 4, 5, 6, 7, 8]);

  // The customer's phone: the lock screen says nothing; the call code is inside the app.
  await go(page, 'Actions (E)');
  await page.getByRole('tab', { name: 'Customer Experience' }).click();
  await page.getByTestId('customer-select').selectOption(HERO);
  await expect(page.getByTestId('lock-screen')).toContainText('You have a new message from Westpac');
  const code = (await page.getByTestId('call-code').textContent())!.trim();
  expect(code).toMatch(/^[A-Z2-7]{6}$/);

  // Step 9: collections tries to send a default notice -> BLOCKED (P2).
  await go(page, 'Policy (D)');
  const check = page.getByRole('form', { name: 'Check an action' });
  await check.getByLabel('Customer').selectOption(HERO);
  await check.getByLabel('Action').selectOption('SEND_DEFAULT_NOTICE');
  await check.getByRole('button', { name: 'Check with D' }).click();
  await expect(page.getByTestId('decision')).toContainText('BLOCK (P2)');
  await expectSteps(page, [1, 2, 3, 4, 5, 6, 7, 8, 9]);

  // Step 10: a scam caller quotes the wrong code -> BLOCKED (P3); the real code is genuine.
  await go(page, 'Actions (E)');
  await page.getByRole('tab', { name: 'Caller verification' }).click();
  await page.getByTestId('customer-select').selectOption(HERO);
  const verify = page.getByRole('form', { name: 'Caller verification' });
  const wrong = code === 'K7P4QX' ? 'ZZZZZZ' : 'K7P4QX';
  await verify.getByLabel('Code provided by caller').fill(wrong);
  await verify.getByRole('button', { name: 'Verify Caller' }).click();
  await expect(page.getByTestId('verdict')).toContainText('Possible scam (P3)');
  await verify.getByLabel('Code provided by caller').fill(code.toLowerCase());
  await verify.getByRole('button', { name: 'Verify Caller' }).click();
  await expect(page.getByTestId('verdict')).toContainText('Genuine Westpac caller');
  await expect(page.getByTestId('verdict')).not.toContainText(code);

  // Home: all 10 ticked.
  await expectSteps(page, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  await expect(page.getByTestId('story-progress')).toHaveAttribute('data-done-count', '10');
  await expect(page.getByTestId('story-next')).toContainText('All 10 steps done');

  // The call code is only on the phone: never in the ledger view.
  await go(page, 'Ledger (C)');
  await expect(page.getByTestId('ledger-table')).toContainText('code (hidden)');
  await expect(page.getByTestId('ledger-table')).not.toContainText(code);
});

test('the ledger catches an insider edit, highlights it, and the sweep stops', async ({ page }) => {
  await page.goto('/');
  await loadStage(page, 'start');
  await page.getByRole('button', { name: 'Record checkpoint' }).click();
  await expect(page.getByText('Checkpoint recorded.')).toBeVisible();
  await page.getByRole('button', { name: 'Simulate insider edit' }).click();
  await expect(page.getByText('E-0004 was quietly edited')).toBeVisible();

  await go(page, 'Ledger (C)');
  await expect(page.getByTestId('integrity')).toContainText('LEDGER TAMPERED');
  await expect(page.getByTestId('integrity')).toContainText('E-0004');
  await expect(page.getByText('Checkpoint OK: E-0020')).toBeVisible();
  const bad = page.getByTestId('ledger-table').locator('tr[data-highlighted="true"]');
  await expect(bad).toHaveCount(1);
  await expect(bad).toContainText('E-0004');

  await go(page, 'Home');
  await expect(page.getByTestId('node-C')).toContainText('tampered');

  await go(page, 'Policy (D)');
  await page.getByRole('button', { name: 'Run sweep without the AI' }).click();
  await expect(page.getByTestId('run-log')).toContainText('STOPPED');
  await expect(page.getByTestId('run-summary')).toContainText('LEDGER TAMPERED');
});

/** Tick one item in the open GEL MultiSelect (not the native <select> options elsewhere on the page). */
async function pick(page: Page, text: string) {
  await page.locator('[role="listbox"] [role="option"]').filter({ hasText: new RegExp(`^${text}$`) }).click();
}

test('the full ledger filters by entry type and customer', async ({ page }) => {
  await page.goto('/');
  await loadStage(page, 'full');
  await expectSteps(page, [1, 2, 3, 4, 5, 6, 7, 8]);
  await go(page, 'Ledger (C)');
  const table = page.getByTestId('ledger-table');
  await expect(table.locator('tbody tr')).toHaveCount(40);

  await page.getByRole('combobox', { name: 'Entry types' }).click();
  await pick(page, 'CONTACT_SCHEDULED');
  await page.keyboard.press('Escape');
  await expect(table.locator('tbody tr')).toHaveCount(1);
  await expect(table).toContainText('code (hidden)');

  await page.getByRole('combobox', { name: 'Entry types' }).click();
  await pick(page, 'SCORE');
  await page.keyboard.press('Escape');
  await page.getByRole('combobox', { name: 'Customers' }).click();
  await pick(page, HERO);
  await page.keyboard.press('Escape');
  await expect(table.locator('tbody tr')).toHaveCount(4); // hero's A score, B scores 0 and 50, the booked call
});
