// The live story in two windows: Jane in the customer app, the hardship team in the Westpac
// dashboard. The sweeps run by themselves (app.py --live, AI off); people only approve.
import { Browser, Page, expect, test } from '@playwright/test';

const HERO = 'cust_af4200';
const JANE = '100200301';
const ALEX_TOKEN = 'cust_6543f0'; // quiet_struggler: HIGH from transactions alone, never contacted the bank
const ALEX = '100200309';

async function windowFor(browser: Browser, url: string, width: number): Promise<Page> {
  const context = await browser.newContext({ viewport: { width, height: 900 } }); // separate sign-ins
  const page = await context.newPage();
  await page.goto(url);
  return page;
}

async function tab(page: Page, name: string) {
  await page.getByRole('tab', { name: new RegExp(`^${name}`) }).click();
}

async function approveCard(westpac: Page, kind: string, token = HERO): Promise<string> {
  await tab(westpac, 'Approvals');
  const card = westpac.locator('[data-testid^="approval-"]').filter({ hasText: kind }).filter({ hasText: token });
  await expect(card).toHaveCount(1, { timeout: 60_000 }); // the automatic sweep recommends it
  const recId = (await card.getAttribute('data-testid'))!.replace('approval-', '');
  await card.getByRole('button', { name: 'Approve' }).click();
  await expect(westpac.getByText(`${recId} approved by staff_19c`)).toBeVisible();
  return recId;
}

async function customerTab(jane: Page, name: string) {
  await jane.getByRole('navigation', { name: 'App' }).getByRole('link', { name }).click();
}

test('Jane and the hardship team, live: Quiet Help, the form, a booked call, P2 and P3', async ({ browser }) => {
  // The demo starts from the walkthrough's reset (the live apps have no demo buttons).
  const walkthrough = await windowFor(browser, '/', 1280);
  await walkthrough.getByRole('button', { name: 'Reset demo (real pipeline)' }).click();
  await expect(walkthrough.getByText('Demo reset: A and B scored everyone')).toBeVisible({ timeout: 60_000 });
  await walkthrough.close();

  const westpac = await windowFor(browser, '/westpac/', 1280);
  await westpac.getByTestId('sign-in-staff').selectOption('staff_19c');
  await westpac.getByRole('button', { name: 'Sign in' }).click();
  await expect(westpac.getByTestId('live-bar')).toContainText('Automatic sweeps on');
  await expect(westpac.getByTestId('live-bar')).toContainText('AI off');

  // 1. Jane signs in and sees her accounts.
  const jane = await windowFor(browser, '/customer/', 390);
  await jane.getByTestId('sign-in-customer').selectOption(JANE);
  await jane.getByRole('button', { name: 'Sign in' }).click();
  await expect(jane.getByTestId('greeting')).toContainText('Jane');
  await expect(jane.getByTestId('account-TRANSACTION')).toContainText('Everyday account');
  await expect(jane.locator('body')).not.toContainText(HERO); // never her token, score or band
  await expect(jane.locator('body')).not.toContainText('HIGH');

  // 2. The automatic sweep puts hero on Quiet Help and recommends a push: it's in Approvals.
  await expect(westpac.getByTestId('sweep-status')).toContainText('COMPLETED', { timeout: 60_000 });
  await expect(westpac.getByTestId('quiet-help')).toContainText(HERO);

  // 3. Staff approve; the next sweep carries it out by itself; Jane's Messages shows the offer.
  //    Jane reached out first (her callback request), so it's the support offer.
  await tab(westpac, 'Approvals');
  const janeCard = westpac
    .locator('[data-testid^="approval-"]')
    .filter({ hasText: 'Quiet Help Push' })
    .filter({ hasText: HERO });
  await expect(janeCard.getByTestId('message-choice')).toContainText('Support offer', { timeout: 60_000 });
  await expect(janeCard.getByTestId('message-choice')).toContainText('callback request on 7 Nov');
  await approveCard(westpac, 'Quiet Help Push');
  await customerTab(jane, 'Messages');
  await expect(jane.getByTestId('message-QUIET_HELP')).toContainText("We're here if you need a hand", { timeout: 60_000 });
  await expect(jane.getByTestId('lock-screen')).toContainText('You have a new message from Westpac');
  await expect(jane.getByTestId('message-new')).toHaveCount(1); // labelled New while you're looking...
  await expect(jane.getByTestId('message-count')).toHaveCount(0); // ...and the unread badge has gone

  // 4. Jane taps "Apply for hardship help" and submits the form; Westpac sees it with an assessment.
  await jane.getByRole('button', { name: 'Apply for hardship help' }).click();
  const form = jane.getByRole('form', { name: 'Apply for hardship help' });
  await form.getByLabel("Tell us what's happening").fill(
    "It's Jane Citizen, 0491 570 156. I lost my job and can't afford my home loan repayments.",
  );
  await form.getByRole('button', { name: 'Submit my request' }).click();
  await expect(jane.getByTestId('help-result')).toContainText("we've received your hardship request");
  await tab(westpac, 'New contacts');
  const intake = westpac.getByTestId('intake').first();
  await expect(intake).toContainText(HERO);
  await expect(intake).toContainText('JOB_LOSS');
  await expect(intake.getByTestId('assessment')).toContainText('Promises owed', { timeout: 60_000 });
  await expect(intake).not.toContainText('Jane'); // sanitized on arrival
  await customerTab(jane, 'Our promises');
  await expect(jane.getByTestId('promise').filter({ hasText: 'hardship request' })).toHaveCount(1);

  // 5. The next sweep recommends BOOK_MEETING; staff approve; Jane sees her call code.
  await approveCard(westpac, 'Book Meeting');
  await customerTab(jane, 'Messages');
  await expect(jane.getByTestId('message-MEETING')).toContainText('Your call with a hardship specialist', { timeout: 60_000 });
  const code = (await jane.getByTestId('call-code').textContent())!.trim();
  // Jane acted on the Quiet Help offer, so it's tucked away under Earlier messages.
  await expect(jane.getByTestId('message-QUIET_HELP')).toHaveCount(0);
  await expect(jane.getByTestId('earlier-messages')).toContainText('earlier messages (1)');
  expect(code).toMatch(/^[A-Z2-7]{6}$/);

  // 6. On Westpac's Check an action, a default notice for hero is BLOCKED (P2).
  await tab(westpac, 'Check an action');
  const check = westpac.getByRole('form', { name: 'Check an action' });
  await check.getByLabel('Customer', { exact: true }).selectOption(HERO);
  await check.getByLabel('Action', { exact: true }).selectOption('SEND_DEFAULT_NOTICE');
  await check.getByRole('button', { name: 'Check with Node D' }).click();
  await expect(westpac.getByTestId('decision')).toContainText('BLOCK (P2)');

  // 7. A caller says a wrong code ("Hang up"), then the right one ("matches").
  await customerTab(jane, 'Is this Westpac?');
  const caller = jane.getByRole('form', { name: 'Check a caller' });
  await caller.getByLabel('The code the caller says').fill(code === 'K7P4QX' ? 'ZZZZZZ' : 'K7P4QX');
  await caller.getByRole('button', { name: 'Check' }).click();
  await expect(jane.getByTestId('call-verdict')).toContainText("Hang up: this isn't Westpac");
  await caller.getByLabel('The code the caller says').fill(code);
  await caller.getByRole('button', { name: 'Check' }).click();
  await expect(jane.getByTestId('call-verdict')).toContainText('This matches your call code');
  await expect(jane.locator('body')).not.toContainText('P3');
  // ...and the hardship team sees that someone tried (B4), without the code.
  await tab(westpac, 'Overview');
  await expect(westpac.getByTestId('scam-alerts')).toContainText(`Possible scam call · ${HERO}`);
  await expect(westpac.getByTestId('scam-alerts')).not.toContainText(code);

  // Plus: no personal information on any Westpac view, and the call code isn't there either.
  for (const name of ['Overview', 'New contacts', 'Approvals', 'Check an action', 'Customers', 'Audit']) {
    await tab(westpac, name);
    await westpac.waitForTimeout(500);
    const text = await westpac.locator('main').innerText();
    for (const value of ['Jane', 'Citizen', '0491', '@example.com', code]) {
      expect(text, `${name} shows ${value}`).not.toContain(value);
    }
  }

  // 8. Alex never contacted the bank: staff see a gentle tip; Alex's app shows a tip, no hardship wording.
  await tab(westpac, 'Approvals');
  const alexCard = westpac
    .locator('[data-testid^="approval-"]')
    .filter({ hasText: 'Quiet Help Push' })
    .filter({ hasText: ALEX_TOKEN });
  await expect(alexCard.getByTestId('message-choice')).toContainText('Gentle tip');
  await expect(alexCard.getByTestId('message-choice')).toContainText('no money-related contact in the last 30 days');
  await approveCard(westpac, 'Quiet Help Push', ALEX_TOKEN);
  await expect(westpac.getByTestId('decided')).toContainText('Gentle tip');
  const alex = await windowFor(browser, '/customer/', 390);
  await alex.getByTestId('sign-in-customer').selectOption(ALEX);
  await alex.getByRole('button', { name: 'Sign in' }).click();
  await customerTab(alex, 'Messages');
  const tip = alex.getByTestId('message-TIP');
  await expect(tip).toContainText('A tip from Westpac: plan ahead with confidence', { timeout: 60_000 });
  await expect(alex.getByRole('button', { name: 'Apply for hardship help' })).toHaveCount(0);
  expect((await tip.innerText()).toLowerCase()).not.toContain('hardship');
  await tip.getByRole('button', { name: 'See money tips' }).click();
  await expect(alex.getByTestId('money-tips')).toContainText('bill reminders');
  await alex.getByTestId('money-tips').getByRole('button', { name: 'Get help' }).click();
  await expect(alex.getByRole('heading', { name: 'Get help' })).toBeVisible();
});
