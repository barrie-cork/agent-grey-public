import { Page, Locator } from '@playwright/test';

export class DashboardPage {
  readonly page: Page;
  readonly navbar: Locator;
  readonly sessionCards: Locator;
  readonly createSessionButton: Locator;
  readonly statusBadges: Locator;
  readonly filterControls: Locator;
  readonly heading: Locator;
  readonly userMenu: Locator;
  readonly emptyState: Locator;

  constructor(page: Page) {
    this.page = page;
    this.navbar = page.locator('nav, [role="navigation"]');
    this.sessionCards = page.locator('[data-testid="session-card"], .session-card, .card');
    this.createSessionButton = page.locator('[data-testid="create-session"], a[href*="create"]');
    this.statusBadges = page.locator('[data-testid="status-badge"], .badge, .status-badge');
    this.filterControls = page.locator('[data-testid="filters"], .filter-controls, [data-testid="filter"]');
    this.heading = page.locator('h1');
    this.userMenu = page.locator('[data-testid="user-menu"], .user-menu, .dropdown');
    this.emptyState = page.locator('[data-testid="empty-state"], .empty-state');
  }

  async goto(): Promise<void> {
    await this.page.goto('/review-manager/dashboard/');
    await this.page.waitForLoadState('networkidle');
  }

  async waitForPageReady(): Promise<void> {
    await this.navbar.waitFor({ state: 'visible' });
  }

  async getSessionCount(): Promise<number> {
    return this.sessionCards.count();
  }

  async takeScreenshot(name: string): Promise<Buffer> {
    return this.page.screenshot({
      path: `tests/e2e/visual-regression/screenshots/${name}.png`,
      fullPage: true,
      animations: 'disabled',
    });
  }
}
