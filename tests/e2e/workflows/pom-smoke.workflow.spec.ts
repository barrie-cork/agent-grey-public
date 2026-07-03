import { test, expect } from '@playwright/test';
import { SearchStrategyPage } from './pages/search-strategy.page';
import { SearchExecutionPage } from './pages/search-execution.page';
import { ReportingPage } from './pages/reporting.page';
import { OrganisationPage } from './pages/organisation.page';
import { FeedbackPage } from './pages/feedback.page';

/**
 * POM Smoke Test -- validates that all new Page Object Models
 * can be instantiated and their key locators are defined.
 * This is the Phase 2 validation gate.
 */
test.describe('Phase 2: Page Object Model Smoke Tests', () => {
  test('SearchStrategyPage can be instantiated', async ({ page }) => {
    const strategyPage = new SearchStrategyPage(page);
    expect(strategyPage.populationInput).toBeDefined();
    expect(strategyPage.interestInput).toBeDefined();
    expect(strategyPage.contextInput).toBeDefined();
    expect(strategyPage.saveStrategyButton).toBeDefined();
    expect(strategyPage.executeSearchButton).toBeDefined();
  });

  test('SearchExecutionPage can be instantiated', async ({ page }) => {
    const executionPage = new SearchExecutionPage(page);
    expect(executionPage.executionStatus).toBeDefined();
    expect(executionPage.progressBar).toBeDefined();
    expect(executionPage.retryButton).toBeDefined();
  });

  test('ReportingPage can be instantiated', async ({ page }) => {
    const reportingPage = new ReportingPage(page);
    expect(reportingPage.prismaFlow).toBeDefined();
    expect(reportingPage.generateReportForm).toBeDefined();
    expect(reportingPage.reportRows).toBeDefined();
    expect(reportingPage.downloadReportButton).toBeDefined();
  });

  test('OrganisationPage can be instantiated', async ({ page }) => {
    const orgPage = new OrganisationPage(page);
    expect(orgPage.memberList).toBeDefined();
    expect(orgPage.inviteEmailInput).toBeDefined();
    expect(orgPage.acceptInvitationButton).toBeDefined();
  });

  test('FeedbackPage can be instantiated', async ({ page }) => {
    const feedbackPage = new FeedbackPage(page);
    expect(feedbackPage.feedbackModal).toBeDefined();
    expect(feedbackPage.feedbackTypeSelect).toBeDefined();
    expect(feedbackPage.submitButton).toBeDefined();
    expect(feedbackPage.feedbackRows).toBeDefined();
  });
});
