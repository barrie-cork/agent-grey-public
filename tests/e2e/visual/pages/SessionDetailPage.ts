import { Page, Locator } from '@playwright/test';

export class SessionDetailPage {
  readonly page: Page;
  readonly navbar: Locator;
  readonly sessionTitle: Locator;
  readonly statusBadge: Locator;
  readonly workflowSteps: Locator;
  readonly actionButtons: Locator;
  readonly tabNavigation: Locator;
  readonly sessionMetadata: Locator;
  readonly progressIndicator: Locator;

  constructor(page: Page) {
    this.page = page;
    this.navbar = page.locator('nav, [role="navigation"]');
    this.sessionTitle = page.locator('h1, [data-testid="session-title"]');
    this.statusBadge = page.locator('[data-testid="status-badge"], .badge, .status-badge');
    this.workflowSteps = page.locator('[data-testid="workflow-steps"], .workflow-steps, .stepper');
    this.actionButtons = page.locator('[data-testid="action-buttons"], .action-buttons');
    this.tabNavigation = page.locator('[role="tablist"], .nav-tabs, [data-testid="tabs"]');
    this.sessionMetadata = page.locator('[data-testid="session-metadata"], .session-metadata');
    this.progressIndicator = page.locator('[data-testid="progress"], .progress, [role="progressbar"]');
  }

  async goto(sessionId: string): Promise<void> {
    await this.page.goto(`/review-manager/sessions/${sessionId}/`);
    await this.page.waitForLoadState('networkidle');
  }

  async waitForPageReady(): Promise<void> {
    await this.sessionTitle.waitFor({ state: 'visible' });
  }

  async takeScreenshot(name: string): Promise<Buffer> {
    return this.page.screenshot({
      path: `tests/e2e/visual-regression/screenshots/${name}.png`,
      fullPage: true,
      animations: 'disabled',
    });
  }
}
