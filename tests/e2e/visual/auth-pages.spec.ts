import { test, expect } from '@playwright/test';
import { LoginPage } from './pages';

test.describe('Authentication Pages - Visual Regression', () => {
  test.beforeEach(async ({ page }) => {
    // Viewport set in playwright.config.ts (1920x1080)
  });

  test('Login page', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.waitForPageReady();

    await expect(page).toHaveScreenshot('login-desktop.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });

  test('Signup page', async ({ page }) => {
    await page.goto('/accounts/signup/');
    await page.waitForLoadState('networkidle');

    // Wait for form to be visible
    await page.waitForSelector('form', { state: 'visible' });

    await expect(page).toHaveScreenshot('signup-desktop.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });

  test('Password reset page', async ({ page }) => {
    await page.goto('/accounts/password-reset/');
    await page.waitForLoadState('networkidle');

    await expect(page).toHaveScreenshot('password-reset-desktop.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });

  test.skip('Login page with error state', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.waitForPageReady();

    // Fill invalid credentials manually (don't use login method as it expects navigation)
    await loginPage.usernameInput.fill('invalid@example.com');
    await loginPage.passwordInput.fill('wrongpassword');

    // Click and wait for response (invalid login stays on same page)
    await Promise.all([
      page.waitForResponse((response) => response.url().includes('/accounts/login/')),
      loginPage.submitButton.click(),
    ]);

    // Wait for error message to appear
    await page.waitForSelector('.alert-danger, [role="alert"], .errorlist', {
      state: 'visible',
      timeout: 5000,
    }).catch(() => {});

    await expect(page).toHaveScreenshot('login-error-desktop.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });
});
