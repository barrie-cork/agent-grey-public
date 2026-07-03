import { Page, Locator, expect } from '@playwright/test';

/**
 * Search Strategy Page Object
 *
 * Encapsulates the PIC framework form for defining search strategy.
 * Uses tag-input pattern (type + Enter to add keywords).
 */
export class SearchStrategyPage {
  readonly page: Page;

  // PIC form inputs (tag-input pattern: type text then press Enter)
  readonly populationInput: Locator;
  readonly interestInput: Locator;
  readonly contextInput: Locator;
  readonly populationContainer: Locator;
  readonly interestContainer: Locator;
  readonly contextContainer: Locator;

  // Action buttons
  readonly saveStrategyButton: Locator;
  readonly executeSearchButton: Locator;
  readonly cancelButton: Locator;

  // Progress sidebar
  readonly strategyProgressBody: Locator;
  readonly progressItems: Locator;

  // Query preview
  readonly queryPreview: Locator;
  readonly queryItems: Locator;

  // Strategy completion status
  readonly completionStatus: Locator;

  // Filters
  readonly guidelinesFilterCheckbox: Locator;

  // Form
  readonly strategyForm: Locator;

  constructor(page: Page) {
    this.page = page;

    // PIC tag inputs
    this.populationInput = page.locator('[data-testid="population-input"]');
    this.interestInput = page.locator('[data-testid="interest-input"]');
    this.contextInput = page.locator('[data-testid="context-input"]');
    this.populationContainer = page.locator('[data-testid="population-input-container"]');
    this.interestContainer = page.locator('[data-testid="interest-input-container"]');
    this.contextContainer = page.locator('[data-testid="context-input-container"]');

    // Action buttons
    this.saveStrategyButton = page.locator('[data-testid="save-strategy-btn"]');
    this.executeSearchButton = page.locator('[data-testid="execute-search-btn"]');
    this.cancelButton = page.locator('a:has-text("Cancel")');

    // Progress sidebar
    this.strategyProgressBody = page.locator('#strategy-progress-body');
    this.progressItems = page.locator('.strategy-progress-item');

    // Query preview
    this.queryPreview = page.locator('#query-preview');
    this.queryItems = page.locator('.query-item');

    // Completion status badge
    this.completionStatus = page.locator('[data-completion-status]');

    // Filters
    this.guidelinesFilterCheckbox = page.locator('#id_include_guidelines_filter');

    // Form
    this.strategyForm = page.locator('#strategy-form');
  }

  async goto(sessionId: string): Promise<void> {
    await this.page.goto(`/search-strategy/session/${sessionId}/`);
    await this.page.waitForLoadState('networkidle');
  }

  async expectOnStrategyPage(): Promise<void> {
    await expect(this.page).toHaveURL(/\/search-strategy\/session\/[a-f0-9-]+\//);
    await expect(this.populationInput).toBeVisible();
  }

  async addPopulationTerm(term: string): Promise<void> {
    await this.populationInput.fill(term);
    await this.populationInput.press('Enter');
    await this.page.waitForLoadState('networkidle');
  }

  async addInterestTerm(term: string): Promise<void> {
    await this.interestInput.fill(term);
    await this.interestInput.press('Enter');
    await this.page.waitForLoadState('networkidle');
  }

  async addContextTerm(term: string): Promise<void> {
    await this.contextInput.fill(term);
    await this.contextInput.press('Enter');
    await this.page.waitForLoadState('networkidle');
  }

  async fillPICForm(population: string[], interest: string[], context: string[]): Promise<void> {
    for (const term of population) {
      await this.addPopulationTerm(term);
    }
    for (const term of interest) {
      await this.addInterestTerm(term);
    }
    for (const term of context) {
      await this.addContextTerm(term);
    }
  }

  async saveStrategy(): Promise<void> {
    await this.saveStrategyButton.click();
    await this.page.waitForLoadState('networkidle');
  }

  async executeSearch(): Promise<void> {
    await this.executeSearchButton.click();
    await this.page.waitForLoadState('networkidle');
  }

  async expectStrategyComplete(): Promise<void> {
    await expect(this.completionStatus).toContainText('Complete');
  }

  async expectStrategyInProgress(): Promise<void> {
    await expect(this.completionStatus).toContainText('In Progress');
  }

  async expectQueryPreviewVisible(): Promise<void> {
    await expect(this.queryPreview).toBeVisible();
    await expect(this.queryItems.first()).toBeVisible();
  }

  async getQueryCount(): Promise<number> {
    return await this.queryItems.count();
  }

  async getTagCount(field: 'population' | 'interest' | 'context'): Promise<number> {
    return await this.page.locator(`.keyword-tag.${field}`).count();
  }

  async expectProgressItemComplete(index: number): Promise<void> {
    await expect(this.progressItems.nth(index)).toHaveClass(/complete/);
  }

  async toggleGuidelinesFilter(): Promise<void> {
    await this.guidelinesFilterCheckbox.click();
  }

  async getQueryPreviewText(): Promise<string> {
    return await this.queryPreview.innerText();
  }
}
