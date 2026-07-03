import { Page, Locator } from '@playwright/test';

export class ConflictResolutionPage {
  readonly page: Page;
  readonly navbar: Locator;
  readonly conflictList: Locator;
  readonly conflictCard: Locator;
  readonly resultTitle: Locator;
  readonly resultUrl: Locator;
  readonly decisionButtons: Locator;
  readonly includeButton: Locator;
  readonly excludeButton: Locator;
  readonly maybeButton: Locator;
  readonly discussionPanel: Locator;
  readonly progressIndicator: Locator;
  readonly emptyState: Locator;

  constructor(page: Page) {
    this.page = page;
    this.navbar = page.locator('nav, [role="navigation"]');
    this.conflictList = page.locator('[data-testid="conflict-list"], .conflict-list');
    this.conflictCard = page.locator('[data-testid="conflict-card"], .conflict-card');
    this.resultTitle = page.locator('[data-testid="result-title"], .result-title');
    this.resultUrl = page.locator('[data-testid="result-url"], .result-url');
    this.decisionButtons = page.locator('[data-testid="decision-buttons"], .decision-buttons');
    this.includeButton = page.locator('[data-testid="include-btn"], button:has-text("Include")');
    this.excludeButton = page.locator('[data-testid="exclude-btn"], button:has-text("Exclude")');
    this.maybeButton = page.locator('[data-testid="maybe-btn"], button:has-text("Maybe")');
    this.discussionPanel = page.locator('[data-testid="discussion"], .discussion-panel');
    this.progressIndicator = page.locator('[data-testid="progress"], .progress, [role="progressbar"]');
    this.emptyState = page.locator('[data-testid="empty-state"], .empty-state');
  }

  async goto(): Promise<void> {
    await this.page.goto('/conflicts/');
    await this.page.waitForLoadState('networkidle');
  }

  async gotoResolve(conflictId: string): Promise<void> {
    await this.page.goto(`/conflicts/${conflictId}/resolve/`);
    await this.page.waitForLoadState('networkidle');
  }

  async waitForPageReady(): Promise<void> {
    // Wait for Vue SPA to mount
    await this.page.waitForTimeout(2000);
    // Wait for either conflict list or empty state
    await Promise.race([
      this.conflictList.waitFor({ state: 'visible', timeout: 10000 }),
      this.emptyState.waitFor({ state: 'visible', timeout: 10000 }),
    ]).catch(() => {});
  }

  async getConflictCount(): Promise<number> {
    return this.conflictCard.count();
  }

  async takeScreenshot(name: string): Promise<Buffer> {
    return this.page.screenshot({
      path: `tests/e2e/visual-regression/screenshots/${name}.png`,
      fullPage: true,
      animations: 'disabled',
    });
  }
}
