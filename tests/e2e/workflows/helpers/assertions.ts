import { Page, Locator, expect } from '@playwright/test';

/**
 * Assertion Helpers
 *
 * Common assertion patterns for workflow tests.
 */

/**
 * Assert element is visible with optional text
 */
export async function assertVisible(
  locator: Locator,
  text?: string
): Promise<void> {
  await expect(locator).toBeVisible();
  if (text) {
    await expect(locator).toContainText(text);
  }
}

/**
 * Assert element is not visible
 */
export async function assertNotVisible(locator: Locator): Promise<void> {
  await expect(locator).not.toBeVisible();
}

/**
 * Assert element has specific text
 */
export async function assertText(locator: Locator, text: string): Promise<void> {
  await expect(locator).toHaveText(text);
}

/**
 * Assert element contains text
 */
export async function assertContainsText(locator: Locator, text: string): Promise<void> {
  await expect(locator).toContainText(text);
}

/**
 * Assert element count
 */
export async function assertCount(locator: Locator, count: number): Promise<void> {
  await expect(locator).toHaveCount(count);
}

/**
 * Assert form field has value
 */
export async function assertFieldValue(locator: Locator, value: string): Promise<void> {
  await expect(locator).toHaveValue(value);
}

/**
 * Assert element is enabled
 */
export async function assertEnabled(locator: Locator): Promise<void> {
  await expect(locator).toBeEnabled();
}

/**
 * Assert element is disabled
 */
export async function assertDisabled(locator: Locator): Promise<void> {
  await expect(locator).toBeDisabled();
}

/**
 * Assert no error messages are visible
 */
export async function assertNoErrors(page: Page): Promise<void> {
  const errorSelectors = [
    '[data-testid="error-message"]',
    '.alert-danger',
    '[role="alert"]:has-text("error")',
    '.error-message',
  ];
  
  for (const selector of errorSelectors) {
    const count = await page.locator(selector).count();
    if (count > 0) {
      const text = await page.locator(selector).first().textContent();
      throw new Error(`Unexpected error visible: ${text}`);
    }
  }
}

/**
 * Assert error message is visible
 */
export async function assertError(page: Page, message?: string): Promise<void> {
  const errorLocator = page.locator('[data-testid="error-message"], .alert-danger, [role="alert"]');
  await expect(errorLocator.first()).toBeVisible();
  
  if (message) {
    await expect(errorLocator.first()).toContainText(message);
  }
}

/**
 * Assert success message is visible
 */
export async function assertSuccess(page: Page, message?: string): Promise<void> {
  const successLocator = page.locator('[data-testid="success-message"], .alert-success');
  await expect(successLocator.first()).toBeVisible();
  
  if (message) {
    await expect(successLocator.first()).toContainText(message);
  }
}

/**
 * Assert page title contains text
 */
export async function assertPageTitle(page: Page, title: string): Promise<void> {
  await expect(page).toHaveTitle(new RegExp(title, 'i'));
}

/**
 * Assert heading text
 */
export async function assertHeading(page: Page, text: string, level: number = 1): Promise<void> {
  await expect(page.locator(`h${level}`).first()).toContainText(text);
}

/**
 * Wait for loading to complete
 */
export async function waitForLoadingComplete(page: Page): Promise<void> {
  const loadingSelectors = [
    '[data-testid="loading"]',
    '.loading',
    '.spinner',
    '[aria-busy="true"]',
  ];
  
  for (const selector of loadingSelectors) {
    const locator = page.locator(selector);
    if (await locator.count() > 0) {
      await expect(locator).not.toBeVisible({ timeout: 30000 });
    }
  }
}
