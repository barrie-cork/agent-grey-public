import { Page, Locator, expect } from '@playwright/test';

/**
 * Feedback Page Object
 *
 * Encapsulates the feedback modal (submit/quick), feedback list (staff),
 * and feedback detail (staff) pages.
 *
 * Feedback submission uses a modal overlay (feedback_modal.html) included
 * in the base template. The list and detail pages are staff-only.
 */
export class FeedbackPage {
  readonly page: Page;

  // Feedback modal elements
  readonly feedbackModal: Locator;
  readonly feedbackTypeSelect: Locator;
  readonly subjectInput: Locator;
  readonly messageInput: Locator;
  readonly submitButton: Locator;
  readonly cancelButton: Locator;
  readonly feedbackToast: Locator;

  // Star rating (radio inputs)
  readonly ratingStar1: Locator;
  readonly ratingStar2: Locator;
  readonly ratingStar3: Locator;
  readonly ratingStar4: Locator;
  readonly ratingStar5: Locator;

  // Feedback list (staff only)
  readonly feedbackRows: Locator;
  readonly viewFeedbackButton: Locator;
  readonly applyFiltersButton: Locator;
  readonly clearFiltersButton: Locator;

  // Feedback detail (staff only)
  readonly updateStatusButton: Locator;
  readonly backToListLink: Locator;
  readonly statusSelect: Locator;

  constructor(page: Page) {
    this.page = page;

    // Modal
    this.feedbackModal = page.locator('[data-testid="feedback-modal"]');
    this.feedbackTypeSelect = page.locator('[data-testid="input-feedback-type"]');
    this.subjectInput = page.locator('[data-testid="input-feedback-subject"]');
    this.messageInput = page.locator('[data-testid="input-feedback-message"]');
    this.submitButton = page.locator('[data-testid="submit-feedback-btn"]');
    this.cancelButton = page.locator('[data-testid="cancel-feedback-btn"]');
    this.feedbackToast = page.locator('[data-testid="feedback-toast"]');

    // Star rating
    this.ratingStar1 = page.locator('#star1');
    this.ratingStar2 = page.locator('#star2');
    this.ratingStar3 = page.locator('#star3');
    this.ratingStar4 = page.locator('#star4');
    this.ratingStar5 = page.locator('#star5');

    // List page
    this.feedbackRows = page.locator('[data-testid="feedback-row"]');
    this.viewFeedbackButton = page.locator('[data-testid="view-feedback-btn"]');
    this.applyFiltersButton = page.locator('[data-testid="apply-filters-btn"]');
    this.clearFiltersButton = page.locator('[data-testid="clear-filters-btn"]');

    // Detail page
    this.updateStatusButton = page.locator('[data-testid="update-status-btn"]');
    this.backToListLink = page.locator('[data-testid="link-back-list"]');
    this.statusSelect = page.locator('#statusSelect');
  }

  async gotoList(): Promise<void> {
    await this.page.goto('/feedback/list/');
    await this.page.waitForLoadState('networkidle');
  }

  async gotoDetail(feedbackId: string): Promise<void> {
    await this.page.goto(`/feedback/detail/${feedbackId}/`);
    await this.page.waitForLoadState('networkidle');
  }

  async expectOnListPage(): Promise<void> {
    await expect(this.page).toHaveURL(/\/feedback\/list\//);
  }

  async expectOnDetailPage(): Promise<void> {
    await expect(this.page).toHaveURL(/\/feedback\/detail\/[a-f0-9-]+\//);
  }

  async openFeedbackModal(): Promise<void> {
    // The feedback modal trigger button may vary by page.
    // Look for a common feedback button in the base template.
    const feedbackTrigger = this.page.locator('button:has-text("Feedback"), [data-testid="open-feedback-btn"], a:has-text("Feedback")');
    if (await feedbackTrigger.isVisible()) {
      await feedbackTrigger.click();
      await expect(this.feedbackModal).toBeVisible();
    }
  }

  async submitFeedback(data: {
    type: string;
    message: string;
    subject?: string;
    rating?: number;
  }): Promise<void> {
    await this.feedbackTypeSelect.selectOption(data.type);
    if (data.subject) {
      await this.subjectInput.fill(data.subject);
    }
    await this.messageInput.fill(data.message);
    if (data.rating) {
      await this.setRating(data.rating);
    }
    await this.submitButton.click();
  }

  async submitQuickFeedback(message: string): Promise<void> {
    // Quick feedback is a simplified submission
    await this.page.goto('/feedback/quick/');
    await this.page.waitForLoadState('networkidle');
    const quickMessageInput = this.page.locator('textarea[name="message"], [data-testid="input-feedback-message"]');
    await quickMessageInput.fill(message);
    const quickSubmitBtn = this.page.locator('button[type="submit"]');
    await quickSubmitBtn.click();
    await this.page.waitForLoadState('networkidle');
  }

  async setRating(stars: number): Promise<void> {
    const ratingInput = this.page.locator(`#star${stars}`);
    await ratingInput.check({ force: true });
  }

  async expectSuccess(): Promise<void> {
    await expect(this.feedbackToast).toBeVisible({ timeout: 10000 });
  }

  async expectModalVisible(): Promise<void> {
    await expect(this.feedbackModal).toBeVisible();
  }

  async expectModalHidden(): Promise<void> {
    await expect(this.feedbackModal).toBeHidden();
  }

  async getFeedbackCount(): Promise<number> {
    return await this.feedbackRows.count();
  }

  async clickFirstFeedback(): Promise<void> {
    await this.viewFeedbackButton.first().click();
    await this.page.waitForLoadState('networkidle');
  }

  async updateStatus(status: string): Promise<void> {
    await this.statusSelect.selectOption(status);
    await this.updateStatusButton.click();
    await this.page.waitForLoadState('networkidle');
  }
}
