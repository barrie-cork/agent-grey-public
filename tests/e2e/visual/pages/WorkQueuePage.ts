import { Page, Locator } from '@playwright/test';

export class WorkQueuePage {
  readonly page: Page;
  readonly navbar: Locator;
  readonly workQueue: Locator;
  readonly resultCards: Locator;
  readonly resultTitle: Locator;
  readonly resultUrl: Locator;
  readonly decisionButtons: Locator;
  readonly includeButton: Locator;
  readonly excludeButton: Locator;
  readonly maybeButton: Locator;
  readonly progressBar: Locator;
  readonly queueStats: Locator;
  readonly emptyState: Locator;
  readonly filterControls: Locator;

  constructor(page: Page) {
    this.page = page;
    this.navbar = page.locator('nav, [role="navigation"]');
    this.workQueue = page.locator('[data-testid="work-queue"], .work-queue');
    this.resultCards = page.locator('[data-testid="result-card"], .result-card');
    this.resultTitle = page.locator('[data-testid="result-title"], .result-title');
    this.resultUrl = page.locator('[data-testid="result-url"], .result-url');
    this.decisionButtons = page.locator('[data-testid="decision-buttons"], .decision-buttons');
    this.includeButton = page.locator('[data-testid="include-btn"], button:has-text("Include")');
    this.excludeButton = page.locator('[data-testid="exclude-btn"], button:has-text("Exclude")');
    this.maybeButton = page.locator('[data-testid="maybe-btn"], button:has-text("Maybe")');
    this.progressBar = page.locator('[data-testid="progress-bar"], .progress-bar, [role="progressbar"]');
    this.queueStats = page.locator('[data-testid="queue-stats"], .queue-stats');
    this.emptyState = page.locator('[data-testid="empty-state"], .empty-state');
    this.filterControls = page.locator('[data-testid="filters"], .filter-controls');
  }

  async goto(): Promise<void> {
    await this.page.goto('/work-queue/');
    await this.page.waitForLoadState('networkidle');
  }

  async gotoWithSession(sessionId: string): Promise<void> {
    await this.page.goto(`/work-queue/${sessionId}/`);
    await this.page.waitForLoadState('networkidle');
  }

  async waitForPageReady(): Promise<void> {
    // Wait for Vue SPA to mount
    await this.page.waitForTimeout(2000);
    // Wait for either work queue or empty state
    await Promise.race([
      this.workQueue.waitFor({ state: 'visible', timeout: 10000 }),
      this.emptyState.waitFor({ state: 'visible', timeout: 10000 }),
    ]).catch(() => {});
  }

  async getResultCount(): Promise<number> {
    return this.resultCards.count();
  }

  async takeScreenshot(name: string): Promise<Buffer> {
    return this.page.screenshot({
      path: `tests/e2e/visual-regression/screenshots/${name}.png`,
      fullPage: true,
      animations: 'disabled',
    });
  }
}
