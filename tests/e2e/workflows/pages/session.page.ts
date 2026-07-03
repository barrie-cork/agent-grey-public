import { Page, Locator, expect } from '@playwright/test';

/**
 * Session Page Object
 */
export class SessionPage {
  readonly page: Page;
  readonly statusBadge: Locator;
  readonly titleInput: Locator;
  readonly descriptionInput: Locator;
  readonly createSubmitButton: Locator;
  readonly cancelButton: Locator;
  readonly setupLink: Locator;
  readonly strategyLink: Locator;
  readonly executeButton: Locator;
  readonly reviewLink: Locator;
  readonly minReviewersSelect: Locator;
  readonly setupSubmitButton: Locator;
  readonly organisationSelect: Locator;

  constructor(page: Page) {
    this.page = page;
    this.statusBadge = page.locator('[data-testid="session-status-badge"]');
    this.titleInput = page.locator('[data-testid="input-title"], #id_title');
    this.descriptionInput = page.locator('[data-testid="input-description"], #id_description');
    // Organisation selector is only present when the user belongs to more than
    // one active organisation (Issue #171); single-org users do not see it.
    this.organisationSelect = page.locator('#id_organisation');
    this.createSubmitButton = page.locator('[data-testid="submit-create-session-btn"]');
    this.cancelButton = page.locator('[data-testid="cancel-create-btn"], [data-testid="cancel-edit-btn"]');
    this.setupLink = page.locator('a:has-text("Setup"), a:has-text("Configure")');
    this.strategyLink = page.locator('a:has-text("Search Strategy"), a:has-text("Define Search")');
    this.executeButton = page.locator('[data-testid="execute-search-btn"], button:has-text("Execute")');
    this.reviewLink = page.locator('a:has-text("Review"), a:has-text("Start Review")');
    this.minReviewersSelect = page.locator('[data-testid="select-min-reviewers"], #id_min_reviewers_per_result');
    this.setupSubmitButton = page.locator('[data-testid="submit-setup-btn"]');
  }

  async gotoCreate(): Promise<void> {
    await this.page.goto('/sessions/create/');
    await this.page.waitForLoadState('networkidle');
  }

  async gotoDetail(sessionId: string): Promise<void> {
    await this.page.goto(`/sessions/${sessionId}/`);
    // Session detail has SSE which prevents networkidle; use domcontentloaded
    await this.page.waitForLoadState('domcontentloaded');
  }

  async gotoSetup(sessionId: string): Promise<void> {
    await this.page.goto(`/sessions/${sessionId}/setup/`);
    await this.page.waitForLoadState('networkidle');
  }

  async expectOnCreatePage(): Promise<void> {
    await expect(this.page).toHaveURL(/\/sessions\/create\//);
    await expect(this.titleInput).toBeVisible();
  }

  async expectStatus(statusText: RegExp | string): Promise<void> {
    if (typeof statusText === 'string') {
      await expect(this.statusBadge).toContainText(statusText, { ignoreCase: true });
    } else {
      await expect(this.statusBadge).toHaveText(statusText);
    }
  }

  async fillCreateForm(title: string, description?: string): Promise<void> {
    await this.titleInput.fill(title);
    if (description && await this.descriptionInput.isVisible()) {
      await this.descriptionInput.fill(description);
    }
    // Select the first real organisation if the selector is shown (multi-org
    // users only). Index 1 skips the "Select an organisation" placeholder.
    if (await this.organisationSelect.isVisible().catch(() => false)) {
      await this.organisationSelect.selectOption({ index: 1 });
    }
  }

  async submitCreateForm(): Promise<string> {
    await this.createSubmitButton.click();
    await this.page.waitForURL(/\/sessions\/[a-f0-9-]+\/(setup)?/, { timeout: 15000 });
    const url = this.page.url();
    const match = url.match(/\/sessions\/([a-f0-9-]+)/);
    if (!match) throw new Error(`Could not extract session ID from URL: ${url}`);
    return match[1];
  }

  async createSession(title: string, description?: string): Promise<string> {
    await this.gotoCreate();
    await this.fillCreateForm(title, description);
    return await this.submitCreateForm();
  }

  async cancelCreate(): Promise<void> {
    await this.cancelButton.click();
    await expect(this.page).toHaveURL('/');
  }

  async expectOnSetupPage(): Promise<void> {
    await expect(this.page).toHaveURL(/\/sessions\/[a-f0-9-]+\/setup\//);
  }

  async configureReviewers(minReviewers: number): Promise<void> {
    if (await this.minReviewersSelect.isVisible()) {
      await this.minReviewersSelect.selectOption(String(minReviewers));
    }
  }

  async saveSetup(): Promise<void> {
    if (await this.setupSubmitButton.isVisible()) {
      await this.setupSubmitButton.click();
      await this.page.waitForLoadState('domcontentloaded');
    }
  }

  async getStatus(): Promise<string> {
    return await this.statusBadge.textContent() || '';
  }

  async getSessionId(): Promise<string> {
    const url = this.page.url();
    const match = url.match(/\/sessions\/([a-f0-9-]+)/);
    return match ? match[1] : '';
  }
}
