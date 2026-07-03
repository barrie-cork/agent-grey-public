import { Page, Locator, expect } from '@playwright/test';

/**
 * Dashboard Page Object
 */
export class DashboardPage {
  readonly page: Page;
  readonly createSessionButton: Locator;
  readonly sessionCards: Locator;
  readonly filterTotal: Locator;
  readonly filterActive: Locator;
  readonly filterCompleted: Locator;
  readonly searchInput: Locator;
  readonly invitationsLink: Locator;
  readonly heading: Locator;

  constructor(page: Page) {
    this.page = page;
    this.createSessionButton = page.locator('[data-testid="create-session-btn"]');
    this.sessionCards = page.locator('[data-testid="session-card"]');
    this.filterTotal = page.locator('[data-testid="filter-total"]');
    this.filterActive = page.locator('[data-testid="filter-active"]');
    this.filterCompleted = page.locator('[data-testid="filter-completed"]');
    this.searchInput = page.locator('[data-testid="input-search-sessions"]');
    this.invitationsLink = page.locator('[data-testid="link-view-invitations"]');
    this.heading = page.locator('h1');
  }

  async goto(): Promise<void> {
    await this.page.goto('/');
    await this.page.waitForLoadState('domcontentloaded');
  }

  async expectOnDashboard(): Promise<void> {
    // Dashboard is at root path (/). Playwright resolves string URLs against baseURL.
    await expect(this.page).toHaveURL('/');
  }

  async expectSessionCount(count: number): Promise<void> {
    await expect(this.sessionCards).toHaveCount(count);
  }

  async expectSessionVisible(title: string): Promise<void> {
    await expect(this.sessionCards.filter({ hasText: title }).first()).toBeVisible();
  }

  async clickCreateSession(): Promise<void> {
    await this.createSessionButton.click();
    await expect(this.page).toHaveURL(/\/sessions\/create\//);
  }

  async clickSessionCard(title: string): Promise<void> {
    const card = this.sessionCards.filter({ hasText: title }).first();
    const actionBtn = card.locator('[data-testid="session-action-btn"]');
    await actionBtn.click();
    await this.page.waitForLoadState('networkidle');
  }

  async getSessionCount(): Promise<number> {
    return await this.sessionCards.count();
  }
}
