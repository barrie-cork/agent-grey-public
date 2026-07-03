import { Page, Locator, expect } from '@playwright/test';

/**
 * Reporting Page Object
 *
 * Encapsulates reporting dashboard, report generation, report list,
 * and report detail views.
 */
export class ReportingPage {
  readonly page: Page;

  // Dashboard elements
  readonly prismaFlow: Locator;
  readonly totalCount: Locator;
  readonly includedCount: Locator;
  readonly excludedCount: Locator;
  readonly reviewedCount: Locator;
  readonly duplicatesCount: Locator;
  readonly archiveSessionButton: Locator;
  readonly returnToSearchStrategyButton: Locator;

  // Generate report form (dashboard sidebar)
  readonly formatSelect: Locator;
  readonly generateReportButton: Locator;

  // Generate report page (dedicated)
  readonly generateReportForm: Locator;
  readonly formatCardPdf: Locator;
  readonly formatCardCsv: Locator;
  readonly formatCardJson: Locator;
  readonly submitGenerateButton: Locator;
  readonly cancelGenerateButton: Locator;

  // Report list
  readonly reportRows: Locator;
  readonly viewReportLink: Locator;
  readonly downloadReportLink: Locator;
  readonly deleteReportButton: Locator;
  readonly noReportsMessage: Locator;
  readonly filterForm: Locator;
  readonly filterStatusCompleted: Locator;
  readonly filterFormat: Locator;
  readonly submitFilterButton: Locator;

  // Report detail
  readonly reportDetailContainer: Locator;
  readonly reportStatus: Locator;
  readonly downloadReportButton: Locator;
  readonly previewReportLink: Locator;
  readonly generateSimilarButton: Locator;

  // Delete modal
  readonly deleteModal: Locator;
  readonly confirmDeleteButton: Locator;

  constructor(page: Page) {
    this.page = page;

    // Dashboard
    this.prismaFlow = page.locator('[data-testid="prisma-flow"]');
    this.totalCount = page.locator('[data-testid="total-count"]');
    this.includedCount = page.locator('[data-testid="included-count"]');
    this.excludedCount = page.locator('[data-testid="excluded-count"]');
    this.reviewedCount = page.locator('[data-testid="reviewed-count"]');
    this.duplicatesCount = page.locator('[data-testid="duplicates-count"]');
    this.archiveSessionButton = page.locator('[data-testid="archive-session-btn"]');
    this.returnToSearchStrategyButton = page.locator('[data-testid="return-to-search-strategy-btn"]');

    // Dashboard generate form
    this.formatSelect = page.locator('#format');
    this.generateReportButton = page.locator('form[action*="generate_report"] button[type="submit"]');

    // Dedicated generate report page
    this.generateReportForm = page.locator('[data-testid="generate-report-form"]');
    this.formatCardPdf = page.locator('[data-testid="format-card-pdf"]');
    this.formatCardCsv = page.locator('[data-testid="format-card-csv"]');
    this.formatCardJson = page.locator('[data-testid="format-card-json"]');
    this.submitGenerateButton = page.locator('[data-testid="submit-generate-report-btn"]');
    this.cancelGenerateButton = page.locator('[data-testid="cancel-generate-btn"]');

    // Report list
    this.reportRows = page.locator('[data-testid="report-row"]');
    this.viewReportLink = page.locator('[data-testid="view-report-link"]');
    this.downloadReportLink = page.locator('[data-testid="download-report-link"]');
    this.deleteReportButton = page.locator('[data-testid="delete-report-btn"]');
    this.noReportsMessage = page.locator('[data-testid="no-reports-message"]');
    this.filterForm = page.locator('[data-testid="filter-form"]');
    this.filterStatusCompleted = page.locator('[data-testid="filter-status-completed"]');
    this.filterFormat = page.locator('[data-testid="filter-format"]');
    this.submitFilterButton = page.locator('[data-testid="submit-filter-btn"]');

    // Report detail
    this.reportDetailContainer = page.locator('[data-testid="report-detail-container"]');
    this.reportStatus = page.locator('[data-testid="report-status"]');
    this.downloadReportButton = page.locator('[data-testid="download-report-btn"]');
    this.previewReportLink = page.locator('[data-testid="preview-report-link"]');
    this.generateSimilarButton = page.locator('[data-testid="generate-similar-btn"]');

    // Delete modal
    this.deleteModal = page.locator('[data-testid="delete-modal"]');
    this.confirmDeleteButton = page.locator('[data-testid="confirm-delete-btn"]');
  }

  async gotoDashboard(sessionId: string): Promise<void> {
    await this.page.goto(`/reporting/sessions/${sessionId}/`);
    await this.page.waitForLoadState('networkidle');
  }

  async gotoGenerateReport(sessionId: string): Promise<void> {
    await this.page.goto(`/reporting/sessions/${sessionId}/generate/`);
    await this.page.waitForLoadState('networkidle');
  }

  async gotoReportList(): Promise<void> {
    await this.page.goto('/reporting/reports/');
    await this.page.waitForLoadState('networkidle');
  }

  async gotoReportDetail(reportId: string): Promise<void> {
    await this.page.goto(`/reporting/reports/${reportId}/`);
    await this.page.waitForLoadState('networkidle');
  }

  async gotoPrismaChecklist(sessionId: string): Promise<void> {
    await this.page.goto(`/reporting/sessions/${sessionId}/prisma/checklist/`);
    await this.page.waitForLoadState('networkidle');
  }

  async expectOnDashboard(): Promise<void> {
    await expect(this.page).toHaveURL(/\/reporting\/sessions\/[a-f0-9-]+\//);
    await expect(this.prismaFlow).toBeVisible();
  }

  async expectOnGenerateReport(): Promise<void> {
    await expect(this.page).toHaveURL(/\/reporting\/sessions\/[a-f0-9-]+\/generate\//);
    await expect(this.generateReportForm).toBeVisible();
  }

  async expectOnReportList(): Promise<void> {
    await expect(this.page).toHaveURL(/\/reporting\/reports\//);
  }

  async expectOnReportDetail(): Promise<void> {
    await expect(this.page).toHaveURL(/\/reporting\/reports\/[a-f0-9-]+\//);
    await expect(this.reportDetailContainer).toBeVisible();
  }

  async selectFormatAndGenerate(format: 'pdf' | 'csv' | 'json'): Promise<void> {
    const formatCard = format === 'pdf' ? this.formatCardPdf
      : format === 'csv' ? this.formatCardCsv
      : this.formatCardJson;
    await formatCard.click();
    await this.submitGenerateButton.click();
    await this.page.waitForLoadState('networkidle');
  }

  async generateReportFromDashboard(format: string): Promise<void> {
    await this.formatSelect.selectOption(format);
    await this.generateReportButton.click();
    await this.page.waitForLoadState('networkidle');
  }

  async waitForReportReady(timeout: number = 60000): Promise<void> {
    await this.page.waitForSelector('.success-notification, [data-testid="download-report-btn"]', { timeout });
  }

  async downloadReport(): Promise<void> {
    await this.downloadReportButton.click();
  }

  async getReportCount(): Promise<number> {
    return await this.reportRows.count();
  }

  async clickFirstReport(): Promise<void> {
    await this.viewReportLink.first().click();
    await this.page.waitForLoadState('networkidle');
  }

  async expectStatVisible(testId: string): Promise<void> {
    await expect(this.page.locator(`[data-testid="${testId}"]`)).toBeVisible();
  }
}
