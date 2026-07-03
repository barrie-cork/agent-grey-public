import { Page, Locator, expect } from '@playwright/test';

/**
 * Organisation Page Object
 *
 * Encapsulates organisation dashboard, user invitation, and
 * invitation acceptance pages.
 *
 * NOTE: Organisation templates may not exist yet. Selectors are based
 * on the view definitions and expected data-testid conventions.
 * Update selectors once templates are built.
 */
export class OrganisationPage {
  readonly page: Page;

  // Dashboard elements
  readonly heading: Locator;
  readonly memberList: Locator;
  readonly memberRows: Locator;
  readonly metricsSection: Locator;

  // Invite form
  readonly inviteEmailInput: Locator;
  readonly inviteRoleSelect: Locator;
  readonly inviteNameInput: Locator;
  readonly inviteSubmitButton: Locator;

  // Invitation acceptance
  readonly acceptInvitationButton: Locator;
  readonly declineInvitationButton: Locator;

  // Feedback / messages
  readonly successMessage: Locator;
  readonly errorMessage: Locator;

  constructor(page: Page) {
    this.page = page;

    // Dashboard
    this.heading = page.locator('h1');
    this.memberList = page.locator('[data-testid="member-list"], .member-list');
    this.memberRows = page.locator('[data-testid="member-row"], .member-row');
    this.metricsSection = page.locator('[data-testid="org-metrics"], .metrics-section');

    // Invite form
    this.inviteEmailInput = page.locator('[data-testid="input-invite-email"], #id_email, input[name="email"]');
    this.inviteRoleSelect = page.locator('[data-testid="select-invite-role"], #id_role, select[name="role"]');
    this.inviteNameInput = page.locator('[data-testid="input-invite-name"], #id_name, input[name="name"]');
    this.inviteSubmitButton = page.locator('[data-testid="submit-invite-btn"], button:has-text("Invite"), button[type="submit"]');

    // Invitation acceptance
    this.acceptInvitationButton = page.locator('[data-testid="accept-invitation-btn"], button:has-text("Accept")');
    this.declineInvitationButton = page.locator('[data-testid="decline-invitation-btn"], button:has-text("Decline"), a:has-text("Decline")');

    // Messages
    this.successMessage = page.locator('[data-testid="success-message"], .alert-success, [role="alert"]:has-text("success")');
    this.errorMessage = page.locator('[data-testid="error-message"], .alert-danger, [role="alert"]:has-text("error")');
  }

  async gotoDashboard(orgId: string): Promise<void> {
    await this.page.goto(`/organisation/${orgId}/dashboard/`);
    await this.page.waitForLoadState('networkidle');
  }

  async gotoInvite(orgId: string): Promise<void> {
    await this.page.goto(`/organisation/${orgId}/invite/`);
    await this.page.waitForLoadState('networkidle');
  }

  async gotoAcceptInvitation(token: string): Promise<void> {
    await this.page.goto(`/organisation/invitation/${token}/`);
    await this.page.waitForLoadState('networkidle');
  }

  async expectOnDashboard(): Promise<void> {
    await expect(this.page).toHaveURL(/\/organisation\/[a-f0-9-]+\/dashboard\//);
  }

  async inviteUser(email: string, role?: string, name?: string): Promise<void> {
    await this.inviteEmailInput.fill(email);
    if (role && await this.inviteRoleSelect.isVisible()) {
      await this.inviteRoleSelect.selectOption(role);
    }
    if (name && await this.inviteNameInput.isVisible()) {
      await this.inviteNameInput.fill(name);
    }
    await this.inviteSubmitButton.click();
    await this.page.waitForLoadState('networkidle');
  }

  async acceptInvitation(): Promise<void> {
    await this.acceptInvitationButton.click();
    await this.page.waitForLoadState('networkidle');
  }

  async declineInvitation(): Promise<void> {
    await this.declineInvitationButton.click();
    await this.page.waitForLoadState('networkidle');
  }

  async expectMemberVisible(nameOrEmail: string): Promise<void> {
    await expect(this.page.locator(`text=${nameOrEmail}`)).toBeVisible();
  }

  async getMemberCount(): Promise<number> {
    return await this.memberRows.count();
  }

  async expectSuccess(): Promise<void> {
    await expect(this.successMessage).toBeVisible();
  }

  async expectError(): Promise<void> {
    await expect(this.errorMessage).toBeVisible();
  }

  async getMetrics(): Promise<Record<string, string>> {
    const metrics: Record<string, string> = {};
    if (await this.metricsSection.isVisible()) {
      const text = await this.metricsSection.textContent() || '';
      metrics['raw'] = text;
    }
    return metrics;
  }
}
