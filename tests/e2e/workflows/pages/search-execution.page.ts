import { Page, Locator, expect } from '@playwright/test';

/**
 * Search Execution Page Object
 *
 * Encapsulates the execution status monitoring page.
 * Execution is async (Celery) -- tests must poll for completion.
 */
export class SearchExecutionPage {
  readonly page: Page;

  // Status elements
  readonly executionStatus: Locator;
  readonly sessionStatusBadge: Locator;

  // Progress elements
  readonly progressBar: Locator;
  readonly queryProgress: Locator;

  // Execution details
  readonly executionCards: Locator;
  readonly resultCount: Locator;

  // Error recovery
  readonly retryButton: Locator;
  readonly errorMessages: Locator;

  // Stats cards (from components/stats_card.html)
  readonly statsCards: Locator;

  constructor(page: Page) {
    this.page = page;

    // Status
    this.executionStatus = page.locator('[data-testid="execution-status"]');
    this.sessionStatusBadge = page.locator('[data-testid="session-status-badge"]');

    // Progress
    this.progressBar = page.locator('[data-testid="progress-bar"], .progress-bar, [role="progressbar"]');
    this.queryProgress = page.locator('[data-testid="query-progress"]');

    // Execution details
    this.executionCards = page.locator('[data-testid="execution-card"], .execution-card');
    this.resultCount = page.locator('[data-testid="result-count"]');

    // Error recovery
    this.retryButton = page.locator('[data-testid="retry-btn"], button:has-text("Retry")');
    this.errorMessages = page.locator('[data-testid="error-message"], .alert-danger');

    // Stats
    this.statsCards = page.locator('.stats-card, [data-testid="stats-card"]');
  }

  async goto(sessionId: string): Promise<void> {
    await this.page.goto(`/execution/session/${sessionId}/status/`);
    await this.page.waitForLoadState('domcontentloaded');
  }

  async gotoErrorRecovery(executionId: string): Promise<void> {
    await this.page.goto(`/execution/${executionId}/recover/`);
    await this.page.waitForLoadState('networkidle');
  }

  async expectOnStatusPage(): Promise<void> {
    await expect(this.page).toHaveURL(/\/execution\/session\/[a-f0-9-]+\/status\//);
  }

  async waitForExecutionComplete(timeout: number = 120000): Promise<void> {
    // Poll session status API for final state
    const sessionId = this.getSessionIdFromUrl();
    await this.page.waitForFunction(
      async (id) => {
        try {
          const response = await fetch(`/api/session/${id}/status/`);
          const data = await response.json();
          return ['ready_for_review', 'under_review', 'completed'].includes(data.status);
        } catch {
          return false;
        }
      },
      sessionId,
      { timeout, polling: 3000 }
    );
  }

  async pollSessionStatus(sessionId: string, targetStatuses: string[], timeout: number = 120000): Promise<string> {
    const startTime = Date.now();
    while (Date.now() - startTime < timeout) {
      try {
        const response = await this.page.evaluate(async (id) => {
          const resp = await fetch(`/api/session/${id}/status/`);
          return resp.json();
        }, sessionId);
        if (targetStatuses.includes(response.status)) {
          return response.status;
        }
      } catch {
        // Continue polling on error
      }
      await this.page.waitForTimeout(3000);
    }
    throw new Error(`Session did not reach target status within ${timeout}ms`);
  }

  async getProgress(): Promise<string> {
    if (await this.progressBar.isVisible()) {
      return await this.progressBar.textContent() || '0%';
    }
    return '0%';
  }

  async expectErrorVisible(): Promise<void> {
    await expect(this.errorMessages.first()).toBeVisible();
  }

  async retryExecution(): Promise<void> {
    await this.retryButton.click();
    await this.page.waitForLoadState('networkidle');
  }

  private getSessionIdFromUrl(): string {
    const url = this.page.url();
    const match = url.match(/\/session\/([a-f0-9-]+)\//);
    return match ? match[1] : '';
  }
}
