import { Page, Locator } from '@playwright/test';

export class LoginPage {
  readonly page: Page;
  readonly usernameInput: Locator;
  readonly passwordInput: Locator;
  readonly submitButton: Locator;
  readonly errorMessage: Locator;
  readonly logo: Locator;
  readonly heading: Locator;
  readonly signupLink: Locator;
  readonly forgotPasswordLink: Locator;

  constructor(page: Page) {
    this.page = page;
    this.usernameInput = page.locator('[data-testid="email"]').or(page.locator('#id_email'));
    this.passwordInput = page.locator('[data-testid="password"]').or(page.locator('#id_password'));
    this.submitButton = page.locator('[data-testid="login-btn"]');
    this.errorMessage = page.locator('.alert-danger, [role="alert"], .errorlist');
    this.logo = page.locator('[data-testid="logo"], .navbar-brand img, .logo');
    this.heading = page.locator('h1');
    this.signupLink = page.locator('a[href*="signup"], a[href*="register"]');
    this.forgotPasswordLink = page.locator('a[href*="password-reset"], a[href*="forgot"]');
  }

  async goto(): Promise<void> {
    await this.page.goto('/accounts/login/');
    await this.page.waitForLoadState('networkidle');
  }

  async waitForPageReady(): Promise<void> {
    await this.submitButton.waitFor({ state: 'visible' });
  }

  async login(username: string, password: string): Promise<void> {
    await this.usernameInput.fill(username);
    await this.passwordInput.fill(password);
    await this.submitButton.click();
  }

  async takeScreenshot(name: string): Promise<Buffer> {
    return this.page.screenshot({
      path: `tests/e2e/visual-regression/screenshots/${name}.png`,
      fullPage: true,
      animations: 'disabled',
    });
  }
}
