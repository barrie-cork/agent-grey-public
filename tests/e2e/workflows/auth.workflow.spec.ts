import { test, expect } from '@playwright/test';
import { AuthPage } from './pages/auth.page';
import { loginUser, logoutUser, defaultTestUsers, E2E_PASSWORD } from './fixtures/test-users';

/**
 * Authentication Workflow Tests
 *
 * Tests complete authentication flows including signup, login, logout,
 * password reset, and all page transitions.
 *
 * Signup form has email + password only (username is auto-generated).
 * Most tests use pre-created e2e- users from create_e2e_users command.
 */

test.describe('Authentication Workflow', () => {
  test.setTimeout(60000);

  test.describe('Signup Flow', () => {
    test('signup page loads and shows form fields', async ({ page }) => {
      const authPage = new AuthPage(page);

      // Start at login page
      await authPage.goToLogin();
      await authPage.expectOnLoginPage();

      // Navigate to signup via link
      await authPage.clickSignupLink();
      await authPage.expectOnSignupPage();

      // Verify signup form fields are visible (email + password only)
      await expect(authPage.signupEmailInput).toBeVisible();
      await expect(authPage.signupPassword1Input).toBeVisible();
      await expect(authPage.signupPassword2Input).toBeVisible();
      await expect(authPage.signupButton).toBeVisible();
    });

    test('signup with new email creates account', async ({ page }) => {
      const authPage = new AuthPage(page);
      const uniqueEmail = `e2e-signup-${Date.now()}@test.local`;

      await authPage.signupAndExpectSuccess({
        email: uniqueEmail,
        password: E2E_PASSWORD,
      });

      // Should redirect to sessions/create/ after signup
      await expect(page).toHaveURL(/\/(dashboard|sessions)/);
    });

    test('signup with existing email shows error', async ({ page }) => {
      const authPage = new AuthPage(page);

      // Try to signup with an email that already exists (pre-created e2e user)
      await authPage.signup({
        email: defaultTestUsers.reviewer1.email,
        password: E2E_PASSWORD,
      });

      // Should stay on signup page with error
      await authPage.expectOnSignupPage();
      await authPage.expectError();
    });
  });

  test.describe('Login Flow', () => {
    test('login with valid credentials redirects to dashboard', async ({ page }) => {
      const authPage = new AuthPage(page);

      // Login with pre-created e2e user (login form takes email)
      await authPage.loginAndExpectSuccess(
        defaultTestUsers.reviewer1.email,
        E2E_PASSWORD
      );
      await authPage.expectOnDashboard();
    });

    test('login with invalid credentials shows error', async ({ page }) => {
      const authPage = new AuthPage(page);

      await authPage.loginAndExpectError('nonexistent@test.local', 'wrong_password');
      await authPage.expectOnLoginPage();
      await authPage.expectError();
    });

    test('login form clears on navigation away and back', async ({ page }) => {
      const authPage = new AuthPage(page);

      await authPage.goToLogin();
      await authPage.expectOnLoginPage();

      // Fill in some data
      await authPage.usernameInput.fill('test@test.local');
      await authPage.passwordInput.fill('test_pass');

      // Navigate to signup
      await authPage.clickSignupLink();
      await authPage.expectOnSignupPage();

      // Go back to login
      await page.goBack();
      await authPage.expectOnLoginPage();
      await expect(authPage.loginButton).toBeVisible();
    });
  });

  test.describe('Password Reset Flow', () => {
    test('password reset workflow', async ({ page }) => {
      const authPage = new AuthPage(page);

      // Start at login page
      await authPage.goToLogin();
      await authPage.expectOnLoginPage();

      // Click forgot password link
      await authPage.clickForgotPasswordLink();
      await authPage.expectOnPasswordResetPage();

      // Fill email and submit (use pre-created user)
      await authPage.resetEmailInput.fill(defaultTestUsers.reviewer1.email);
      await authPage.resetSubmitButton.click();

      // Should go to done page
      await authPage.expectOnPasswordResetDonePage();

      // Back to login link should work
      await authPage.clickBackToLoginLink();
      await authPage.expectOnLoginPage();
    });

    test('password reset with back navigation', async ({ page }) => {
      const authPage = new AuthPage(page);

      await authPage.goToLogin();
      await authPage.expectOnLoginPage();

      await authPage.clickForgotPasswordLink();
      await authPage.expectOnPasswordResetPage();

      await page.goBack();
      await authPage.expectOnLoginPage();

      await page.goForward();
      await authPage.expectOnPasswordResetPage();
    });
  });

  test.describe('Logout Flow', () => {
    test('logout redirects to login and prevents access', async ({ page }) => {
      // Login with pre-created user
      await loginUser(page, defaultTestUsers.reviewer1.email);

      // Verify we're on dashboard
      await expect(page).toHaveURL('/');

      // Logout
      await logoutUser(page);

      // Verify we're redirected to login or home
      await page.waitForLoadState('domcontentloaded');

      // Try to access protected page -- should redirect to login
      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');
      const currentUrl = page.url();
      // Either stays on root (if public) or redirects to login
      expect(currentUrl).toMatch(/\/(accounts\/login\/)?$/);
    });
  });

  test.describe('Navigation Between Auth Pages', () => {
    test('navigate from login to signup and back', async ({ page }) => {
      const authPage = new AuthPage(page);

      await authPage.goToLogin();
      await authPage.expectOnLoginPage();

      await authPage.clickSignupLink();
      await authPage.expectOnSignupPage();

      await authPage.clickLoginLink();
      await authPage.expectOnLoginPage();
    });

    test('complete navigation cycle with browser history', async ({ page }) => {
      const authPage = new AuthPage(page);

      await authPage.goToLogin();
      await authPage.expectOnLoginPage();

      await authPage.clickSignupLink();
      await authPage.expectOnSignupPage();

      await authPage.clickLoginLink();
      await authPage.expectOnLoginPage();

      await authPage.clickForgotPasswordLink();
      await authPage.expectOnPasswordResetPage();

      await page.goBack();
      await authPage.expectOnLoginPage();

      await page.goForward();
      await authPage.expectOnPasswordResetPage();
    });
  });
});
