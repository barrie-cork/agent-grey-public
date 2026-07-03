/**
 * Manual E2E driver for the Agent Grey browser extension (source capture).
 *
 * Loads the built extension (`npm run build` first) into a persistent
 * Chromium profile and drives, against the local dev stack:
 *   1. Token issuance via /accounts/extension-tokens/ (logged-in session)
 *   2. Popup settings (base URL + token) and session listing
 *   3. Stream 2: one-click "+ Add this page" incl. duplicate 409 handling
 *   4. Stream 1: start capture -> browse in capture window -> flush -> stop
 *
 * HUMAN-IN-THE-LOOP: Stream 1 needs one human interaction PER RUN. The
 * extension revokes the optional webNavigation permission on every stop (by
 * design), so Chrome re-prompts each run - and the bubble auto-dismisses if
 * the triggering click is automated. The script pauses and tells you when to
 * click "Start capture" + "Allow" yourself.
 *
 * First run passed 9/9 on 2026-07-02 (see PMD / browser-extension memory).
 *
 * Run from this directory:  node ext-e2e.js
 * Env overrides: AG_E2E_BASE, AG_E2E_USER, AG_E2E_PASSWORD, AG_E2E_SESSION
 */
const { chromium } = require('playwright');
const path = require('path');

const EXT_PATH = path.resolve(__dirname, '../.output/chrome-mv3');
const PROFILE = path.join(__dirname, '.profile'); // gitignored
const BASE = process.env.AG_E2E_BASE || 'http://localhost:8000';
const USER = process.env.AG_E2E_USER || 'e2e-owner@test.local';
const PASSWORD = process.env.AG_E2E_PASSWORD || 'TestPass123!';
// Must be a ready_for_review/under_review session OWNED by USER
const SESSION_ID = process.env.AG_E2E_SESSION || '7d44d2a4-85e0-4a35-b415-2e4c65dfde5d';
const RUN_ID = Date.now();

const results = [];
function check(name, ok, detail = '') {
  results.push({ name, ok, detail });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ' -- ' + detail : ''}`);
}

async function main() {
  const context = await chromium.launchPersistentContext(PROFILE, {
    headless: false, // extension popup + permission prompt need a headed browser
    args: [
      `--disable-extensions-except=${EXT_PATH}`,
      `--load-extension=${EXT_PATH}`,
    ],
    viewport: { width: 1280, height: 900 },
  });

  // --- extension id via MV3 service worker ---
  let [sw] = context.serviceWorkers();
  if (!sw) sw = await context.waitForEvent('serviceworker', { timeout: 15000 });
  const extId = new URL(sw.url()).host;
  console.log('extension id:', extId);

  // --- 1. login + issue token through the real endpoint ---
  const page = await context.newPage();
  await page.goto(`${BASE}/accounts/login/`, { waitUntil: 'domcontentloaded' });
  if (page.url().includes('/accounts/login')) {
    await page.fill('[data-testid="email"], #id_username', USER);
    await page.fill('[data-testid="password"], #id_password', PASSWORD);
    await page.click('[data-testid="login-btn"], button[type=submit]');
    await page.waitForURL(`${BASE}/`, { timeout: 15000 });
  }
  await page.goto(`${BASE}/accounts/extension-tokens/`, { waitUntil: 'domcontentloaded' });
  const token = await page.evaluate(async () => {
    const csrf =
      document.querySelector('input[name=csrfmiddlewaretoken]')?.value ||
      document.cookie.match(/csrftoken=([^;]+)/)?.[1];
    const resp = await fetch('/accounts/extension-tokens/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-CSRFToken': csrf,
      },
      body: new URLSearchParams({ action: 'issue', name: 'e2e-playwright' }).toString(),
    });
    return (await resp.json()).token;
  });
  check('token issued with ag_ext_ prefix', typeof token === 'string' && token.startsWith('ag_ext_'), token?.slice(0, 12) + '...');

  // --- 2. configure popup settings, list sessions ---
  // The popup is driven as a regular tab; chrome.* APIs behave the same.
  const popup = await context.newPage();
  await popup.goto(`chrome-extension://${extId}/popup.html`);
  await popup.click('button[title="Settings"]');
  await popup.fill('input[type=url]', BASE);
  await popup.fill('input[type=password]', token);
  await popup.click('button:has-text("Save")');
  await popup.waitForSelector('text=Settings saved.');
  await popup.click('.btn-back');
  await popup.click('button:has-text("Refresh sessions")');
  // <option> in a closed <select> is "hidden" to Playwright - wait attached
  await popup.waitForSelector(`option[value="${SESSION_ID}"]`, { timeout: 10000, state: 'attached' });
  const optionTexts = await popup.$$eval('select option', (els) => els.map((e) => e.textContent.trim()));
  check('sessions listed in popup', optionTexts.length > 1, optionTexts.join(' | '));

  // --- 3. Stream 2: one-click add ---
  const target = await context.newPage();
  const targetUrl = `${BASE}/accounts/login/?e2e_run=${RUN_ID}`;
  await target.goto(targetUrl, { waitUntil: 'domcontentloaded' });
  await target.bringToFront(); // popup queries the active tab

  await popup.selectOption('select', SESSION_ID);
  await popup.click('button:has-text("+ Add this page")');
  await popup.waitForSelector('text=Add page to');
  const prefilledTitle = await popup.inputValue('.field:has-text("Title") input');
  const shownUrl = await popup.textContent('.url');
  check('add form prefilled from live page', !!prefilledTitle, `title="${prefilledTitle}" url=${shownUrl?.trim()}`);
  await popup.click('button:has-text("Add to screening queue")');
  await popup.waitForSelector('text=Page added to screening queue.', { timeout: 10000 });
  check('add-this-page returns success', true);

  // duplicate add -> friendly 409
  await target.bringToFront();
  await popup.click('button:has-text("+ Add this page")');
  await popup.waitForSelector('text=Add page to');
  await popup.click('button:has-text("Add to screening queue")');
  await popup.waitForSelector('text=This page is already in the session.', { timeout: 10000 });
  check('duplicate add shows friendly 409 message', true);
  await popup.click('.btn-back'); // 409 leaves the popup on the add view

  // --- 4. Stream 1: capture ---
  // A real user gesture keeps Chrome's permission bubble stable; automation
  // clicks can auto-dismiss it. Hand this one step to the human.
  await popup.bringToFront();
  console.log('\n>>> YOUR TURN: in the extension popup tab, click "Start capture", then click "Allow" on');
  console.log('>>> the permission prompt. The script resumes when the capture window opens (3 min max).\n');

  // capture window opens with pinned status tab; poll pages only (no page
  // evaluates - they can dismiss the pending permission bubble)
  let statusPage = null;
  for (let i = 0; i < 360 && !statusPage; i++) {
    statusPage = context.pages().find((p) => p.url().includes('status.html')) || null;
    if (!statusPage) await new Promise((r) => setTimeout(r, 500));
  }
  check('capture window opened (status tab)', !!statusPage);
  if (!statusPage) throw new Error('capture window never appeared - permission denied?');

  // browse two pages inside the capture window
  for (const q of ['cap1', 'cap2']) {
    await statusPage.evaluate((u) => window.open(u), `${BASE}/accounts/login/?${q}=${RUN_ID}`);
    await new Promise((r) => setTimeout(r, 1500));
  }
  await new Promise((r) => setTimeout(r, 1500)); // let background persist visits

  const state = await popup.evaluate(
    () => new Promise((res) => chrome.runtime.sendMessage({ type: 'GET_STATE' }, res))
  );
  check('visits queued in capture state', state && state.active && state.pendingVisits.length >= 2, `pending=${state?.pendingVisits?.length} incognito=${state?.capturedIncognito}`);

  const flush = await popup.evaluate(
    () => new Promise((res) => chrome.runtime.sendMessage({ type: 'FLUSH' }, res))
  );
  check('flush ingested visits', !!flush?.result && flush.result.visits_created >= 2, JSON.stringify(flush?.result));

  // stop capture via popup UI
  await popup.reload();
  await popup.waitForSelector('button:has-text("Stop capture")', { timeout: 10000 });
  await popup.click('button:has-text("Stop capture")');
  await popup.waitForSelector('button:has-text("Start capture")', { timeout: 10000 });
  check('stop capture returns popup to idle', true);

  console.log('\nRUN_ID=' + RUN_ID);
  console.log('TARGET_URL=' + targetUrl);
  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
  await context.close();
  process.exit(failed.length ? 1 : 0);
}

main().catch(async (err) => {
  console.error('E2E FAILED:', err.message);
  console.log('RUN_ID=' + RUN_ID);
  const failed = results.filter((r) => !r.ok);
  console.log(`${results.length - failed.length}/${results.length} checks passed before failure`);
  process.exit(1);
});
