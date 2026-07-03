import { Page, Locator, expect } from '@playwright/test';

/**
 * Review Page Object
 */
export class ReviewPage {
  readonly page: Page;
  readonly resultRows: Locator;
  readonly includeButtons: Locator;
  readonly excludeButtons: Locator;
  readonly maybeButtons: Locator;
  readonly completeButton: Locator;
  readonly progressIndicator: Locator;
  readonly filterPending: Locator;
  readonly filterIncluded: Locator;
  readonly filterExcluded: Locator;

  constructor(page: Page) {
    this.page = page;
    this.resultRows = page.locator('[data-testid="result-row"], .result-row');
    this.includeButtons = page.locator('[data-testid="include-btn"], button:has-text("Include")');
    this.excludeButtons = page.locator('[data-testid="exclude-btn"], button:has-text("Exclude")');
    this.maybeButtons = page.locator('[data-testid="maybe-btn"], button:has-text("Maybe")');
    this.completeButton = page.locator('[data-testid="complete-review-btn"], button:has-text("Complete")');
    this.progressIndicator = page.locator('[data-testid="review-progress"]');
    this.filterPending = page.locator('[data-testid="filter-pending-btn"]');
    this.filterIncluded = page.locator('[data-testid="filter-included-btn"]');
    this.filterExcluded = page.locator('[data-testid="filter-excluded-btn"]');
  }

  async gotoOverview(sessionId: string): Promise<void> {
    await this.page.goto(`/review-results/overview/${sessionId}/`);
    await this.page.waitForLoadState('networkidle');
  }

  async gotoFiltered(sessionId: string): Promise<void> {
    await this.page.goto(`/review-results/filtered/${sessionId}/`);
    await this.page.waitForLoadState('networkidle');
  }

  async gotoDuplicates(sessionId: string): Promise<void> {
    await this.page.goto(`/review-results/duplicates/${sessionId}/`);
    await this.page.waitForLoadState('networkidle');
  }

  async gotoStatistics(sessionId: string): Promise<void> {
    await this.page.goto(`/review-results/statistics/${sessionId}/`);
    await this.page.waitForLoadState('networkidle');
  }

  async gotoComplete(sessionId: string): Promise<void> {
    await this.page.goto(`/review-results/complete/${sessionId}/`);
    await this.page.waitForLoadState('networkidle');
  }

  async gotoMarkComplete(sessionId: string): Promise<void> {
    await this.page.goto(`/review-results/mark-complete/${sessionId}/`);
    await this.page.waitForLoadState('networkidle');
  }

  async expectOnReviewPage(): Promise<void> {
    await expect(this.page).toHaveURL(/\/review-results\//);
  }

  async getResultCount(): Promise<number> {
    return await this.resultRows.count();
  }

  async includeResult(index: number): Promise<void> {
    await this.includeButtons.nth(index).click();
    await this.page.waitForTimeout(500);
  }

  async excludeResult(index: number): Promise<void> {
    await this.excludeButtons.nth(index).click();
    await this.page.waitForTimeout(500);
  }

  async completeReview(): Promise<void> {
    await this.completeButton.click();
    await this.page.waitForLoadState('networkidle');
  }
}
