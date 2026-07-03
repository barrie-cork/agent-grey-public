import { Page, expect } from '@playwright/test';

/**
 * Navigation Helpers
 *
 * Utilities for testing page transitions, browser history, and breadcrumbs.
 */

/**
 * Go back in browser history and verify the URL
 */
export async function goBackAndVerify(page: Page, expectedUrl: RegExp): Promise<void> {
  await page.goBack();
  await expect(page).toHaveURL(expectedUrl);
}

/**
 * Go forward in browser history and verify the URL
 */
export async function goForwardAndVerify(page: Page, expectedUrl: RegExp): Promise<void> {
  await page.goForward();
  await expect(page).toHaveURL(expectedUrl);
}

/**
 * Click a breadcrumb link and verify navigation
 */
export async function clickBreadcrumbAndVerify(
  page: Page,
  text: string,
  expectedUrl: RegExp
): Promise<void> {
  await page.click(`[data-testid="breadcrumb"]:has-text("${text}"), nav a:has-text("${text}")`);
  await expect(page).toHaveURL(expectedUrl);
}

/**
 * Navigate to a URL and wait for load
 */
export async function navigateAndWait(page: Page, url: string): Promise<void> {
  await page.goto(url);
  await page.waitForLoadState('networkidle');
}

/**
 * Test browser back/forward navigation cycle
 */
export async function testBackForwardCycle(
  page: Page,
  startUrl: RegExp,
  targetUrl: RegExp
): Promise<void> {
  // Verify we're at target
  await expect(page).toHaveURL(targetUrl);

  // Go back
  await page.goBack();
  await expect(page).toHaveURL(startUrl);

  // Go forward
  await page.goForward();
  await expect(page).toHaveURL(targetUrl);
}

/**
 * Wait for page navigation to complete
 */
export async function waitForNavigation(
  page: Page,
  expectedUrl: RegExp,
  timeout: number = 15000
): Promise<void> {
  await page.waitForURL(expectedUrl, { timeout });
}

/**
 * Click a link and wait for navigation
 */
export async function clickAndNavigate(
  page: Page,
  selector: string,
  expectedUrl: RegExp
): Promise<void> {
  await page.click(selector);
  await page.waitForURL(expectedUrl, { timeout: 15000 });
}

/**
 * Verify current URL matches expected pattern
 */
export async function verifyUrl(page: Page, expectedUrl: RegExp): Promise<void> {
  await expect(page).toHaveURL(expectedUrl);
}

/**
 * Navigate to URL and verify it loaded
 */
export async function gotoAndVerify(page: Page, url: string, expectedContent?: string): Promise<void> {
  await page.goto(url);
  await page.waitForLoadState('networkidle');
  
  if (expectedContent) {
    await expect(page.locator('body')).toContainText(expectedContent);
  }
}
