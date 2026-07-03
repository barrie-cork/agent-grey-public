import { Page, Locator, expect } from '@playwright/test';

/**
 * SPA Page Object for Vue.js screening interface
 */
export class SPAPage {
  readonly page: Page;

  // Work Queue elements
  readonly workQueue: Locator;
  readonly claimButton: Locator;
  readonly workQueueRows: Locator;
  readonly refreshQueueButton: Locator;
  readonly filterPendingBtn: Locator;
  readonly filterClaimedBtn: Locator;
  readonly filterConflictsBtn: Locator;

  // Screening Decision elements
  readonly screeningDecision: Locator;
  readonly decisionForm: Locator;
  readonly decisionNotes: Locator;
  readonly submitDecision: Locator;
  readonly includeBtn: Locator;
  readonly excludeBtn: Locator;
  readonly maybeBtn: Locator;

  // Conflict elements
  readonly conflictList: Locator;
  readonly conflictItems: Locator;
  readonly resolveConflictBtn: Locator;
  readonly conflictHeader: Locator;
  readonly commentTextarea: Locator;
  readonly postCommentBtn: Locator;

  constructor(page: Page) {
    this.page = page;

    // Work Queue
    this.workQueue = page.locator('[data-testid="work-queue"]');
    this.claimButton = page.locator('[data-testid="claim-button"]');
    this.workQueueRows = page.locator('[data-testid="work-queue-row"]');
    this.refreshQueueButton = page.locator('[data-testid="refresh-queue-btn"]');
    this.filterPendingBtn = page.locator('[data-testid="filter-pending-btn"]');
    this.filterClaimedBtn = page.locator('[data-testid="filter-claimed-btn"]');
    this.filterConflictsBtn = page.locator('[data-testid="filter-conflicts-btn"]');

    // Screening Decision
    this.screeningDecision = page.locator('[data-testid="screening-decision"]');
    this.decisionForm = page.locator('[data-testid="decision-form"]');
    this.decisionNotes = page.locator('[data-testid="decision-notes"]');
    this.submitDecision = page.locator('[data-testid="submit-decision"]');
    this.includeBtn = page.locator('[data-testid="include-btn"]');
    this.excludeBtn = page.locator('[data-testid="exclude-btn"]');
    this.maybeBtn = page.locator('[data-testid="maybe-btn"]');

    // Conflicts
    this.conflictList = page.locator('[data-testid="conflict-list"]');
    this.conflictItems = page.locator('[data-testid="conflict-item"]');
    this.resolveConflictBtn = page.locator('[data-testid="resolve-conflict-btn"]');
    this.conflictHeader = page.locator('[data-testid="conflict-header"]');
    this.commentTextarea = page.locator('[data-testid="comment-textarea"]');
    this.postCommentBtn = page.locator('[data-testid="post-comment-btn"]');
  }

  async waitForVueSPA(timeout: number = 10000): Promise<void> {
    await this.page.waitForSelector('#app', { timeout });
    await this.page.waitForFunction(() => {
      const app = document.querySelector('#app');
      return app && app.childNodes.length > 0;
    }, { timeout });
  }

  async gotoWorkQueue(): Promise<void> {
    await this.page.goto('/screening/work-queue');
    await this.waitForVueSPA();
  }

  async gotoConflicts(): Promise<void> {
    await this.page.goto('/screening/conflicts');
    await this.waitForVueSPA();
  }

  async gotoDashboard(): Promise<void> {
    await this.page.goto('/screening/dashboard');
    await this.waitForVueSPA();
  }

  async expectOnWorkQueue(): Promise<void> {
    await expect(this.page).toHaveURL(/\/screening\/work-queue/);
    await expect(this.workQueue).toBeVisible();
  }

  async expectOnConflicts(): Promise<void> {
    await expect(this.page).toHaveURL(/\/screening\/conflicts/);
  }

  async claimNextResult(): Promise<void> {
    await this.claimButton.first().click();
    await this.page.waitForURL(/\/results\/[a-f0-9-]+\/screen/, { timeout: 10000 });
  }

  async makeDecision(decision: 'include' | 'exclude' | 'maybe', notes?: string): Promise<void> {
    if (notes) {
      await this.decisionNotes.fill(notes);
    }
    
    switch (decision) {
      case 'include':
        await this.includeBtn.click();
        break;
      case 'exclude':
        await this.excludeBtn.click();
        break;
      case 'maybe':
        await this.maybeBtn.click();
        break;
    }
    await this.page.waitForLoadState('networkidle');
  }

  async refreshWorkQueue(): Promise<void> {
    await this.refreshQueueButton.click();
    await this.page.waitForTimeout(500);
  }

  async getConflictCount(): Promise<number> {
    return await this.conflictItems.count();
  }

  async clickConflictItem(index: number = 0): Promise<void> {
    await this.conflictItems.nth(index).click();
    await this.page.waitForURL(/\/conflicts\/[a-f0-9-]+/);
  }

  async postComment(comment: string): Promise<void> {
    await this.commentTextarea.fill(comment);
    await this.postCommentBtn.click();
    await this.page.waitForLoadState('networkidle');
  }
}
