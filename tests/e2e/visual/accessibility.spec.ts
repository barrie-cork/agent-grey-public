import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { testUsers } from '../fixtures/auth';

const publicPages = [
  { name: 'Login', url: '/accounts/login/' },
  { name: 'Signup', url: '/accounts/signup/' },
  { name: 'Password Reset', url: '/accounts/password-reset/' },
];

const authenticatedPages = [
  { name: 'Dashboard', url: '/review-manager/dashboard/' },
  { name: 'Profile', url: '/accounts/profile/' },
  { name: 'Reporting Dashboard', url: '/reporting/dashboard/' },
  { name: 'Feedback List', url: '/feedback/' },
  { name: 'Feedback Form', url: '/feedback/submit/' },
  { name: 'Session Create', url: '/review-manager/sessions/create/' },
];

const vueSpaPages = [
  { name: 'Conflict List', url: '/conflicts/' },
  { name: 'Team Dashboard', url: '/team-dashboard/' },
  { name: 'Work Queue', url: '/work-queue/' },
  { name: 'Screening', url: '/screening/' },
];

test.describe('Accessibility Audit - WCAG 2.1 AA', () => {
  test.describe('Public Pages', () => {
    for (const pageConfig of publicPages) {
      test(`${pageConfig.name} has no critical accessibility violations`, async ({ page }) => {
        await page.goto(pageConfig.url);
        await page.waitForLoadState('networkidle');

        const accessibilityScanResults = await new AxeBuilder({ page })
          .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
          .analyze();

        // Log violations for debugging
        if (accessibilityScanResults.violations.length > 0) {
          console.log(`\nAccessibility violations on ${pageConfig.name}:`);
          for (const violation of accessibilityScanResults.violations) {
            console.log(`  - ${violation.id}: ${violation.description}`);
            console.log(`    Impact: ${violation.impact}`);
            console.log(`    Affected nodes: ${violation.nodes.length}`);
          }
        }

        // Filter to only critical and serious violations
        const criticalViolations = accessibilityScanResults.violations.filter(
          (v) => v.impact === 'critical' || v.impact === 'serious'
        );

        expect(criticalViolations).toEqual([]);
      });
    }
  });

  test.describe('Authenticated Pages', () => {
    test.beforeEach(async ({ page }) => {
      await page.goto('/accounts/login/');
      await page.waitForLoadState('networkidle');
      await page.fill('[data-testid="email"], #id_email', testUsers.reviewer1.email);
      await page.fill('[data-testid="password"], #id_password', testUsers.reviewer1.password);
      await page.click('[data-testid="login-btn"], button[type="submit"]');
      await page.waitForURL(/\/$|dashboard|sessions/, { timeout: 15000 });
    });

    for (const pageConfig of authenticatedPages) {
      test(`${pageConfig.name} has no critical accessibility violations`, async ({ page }) => {
        await page.goto(pageConfig.url);
        await page.waitForLoadState('networkidle');
        await page.waitForTimeout(1000);

        const accessibilityScanResults = await new AxeBuilder({ page })
          .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
          .exclude('.third-party-widget')
          .analyze();

        // Log violations for debugging
        if (accessibilityScanResults.violations.length > 0) {
          console.log(`\nAccessibility violations on ${pageConfig.name}:`);
          for (const violation of accessibilityScanResults.violations) {
            console.log(`  - ${violation.id}: ${violation.description}`);
            console.log(`    Impact: ${violation.impact}`);
            console.log(`    Affected nodes: ${violation.nodes.length}`);
          }
        }

        // Filter to only critical and serious violations
        const criticalViolations = accessibilityScanResults.violations.filter(
          (v) => v.impact === 'critical' || v.impact === 'serious'
        );

        expect(criticalViolations).toEqual([]);
      });
    }
  });

  test.describe('Vue SPA Pages', () => {
    test.beforeEach(async ({ page }) => {
      await page.goto('/accounts/login/');
      await page.waitForLoadState('networkidle');
      await page.fill('[data-testid="email"], #id_email', testUsers.reviewer1.email);
      await page.fill('[data-testid="password"], #id_password', testUsers.reviewer1.password);
      await page.click('[data-testid="login-btn"], button[type="submit"]');
      await page.waitForURL(/\/$|dashboard|sessions/, { timeout: 15000 });
    });

    for (const pageConfig of vueSpaPages) {
      test(`${pageConfig.name} has no critical accessibility violations`, async ({ page }) => {
        await page.goto(pageConfig.url);
        await page.waitForLoadState('networkidle');
        // Wait for Vue SPA to mount
        await page.waitForTimeout(3000);

        const accessibilityScanResults = await new AxeBuilder({ page })
          .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
          .exclude('.third-party-widget')
          .analyze();

        // Log violations for debugging
        if (accessibilityScanResults.violations.length > 0) {
          console.log(`\nAccessibility violations on ${pageConfig.name}:`);
          for (const violation of accessibilityScanResults.violations) {
            console.log(`  - ${violation.id}: ${violation.description}`);
            console.log(`    Impact: ${violation.impact}`);
            console.log(`    Affected nodes: ${violation.nodes.length}`);
          }
        }

        // Filter to only critical and serious violations
        const criticalViolations = accessibilityScanResults.violations.filter(
          (v) => v.impact === 'critical' || v.impact === 'serious'
        );

        expect(criticalViolations).toEqual([]);
      });
    }
  });

  test.describe('Colour Contrast Verification', () => {
    test('Login page meets colour contrast requirements', async ({ page }) => {
      await page.goto('/accounts/login/');
      await page.waitForLoadState('networkidle');

      const accessibilityScanResults = await new AxeBuilder({ page })
        .withTags(['cat.color'])
        .analyze();

      // Log contrast issues for debugging
      if (accessibilityScanResults.violations.length > 0) {
        console.log('\nColour contrast issues on Login page:');
        for (const violation of accessibilityScanResults.violations) {
          console.log(`  - ${violation.id}: ${violation.description}`);
          for (const node of violation.nodes) {
            console.log(`    Element: ${node.html.substring(0, 100)}...`);
          }
        }
      }

      expect(accessibilityScanResults.violations).toEqual([]);
    });

    test('Dashboard meets colour contrast requirements', async ({ page }) => {
      // Login first
      await page.goto('/accounts/login/');
      await page.waitForLoadState('networkidle');
      await page.fill('[data-testid="email"], #id_email', testUsers.reviewer1.email);
      await page.fill('[data-testid="password"], #id_password', testUsers.reviewer1.password);
      await page.click('[data-testid="login-btn"], button[type="submit"]');
      await page.waitForURL(/\/$|dashboard|sessions/, { timeout: 15000 });

      await page.goto('/review-manager/dashboard/');
      await page.waitForLoadState('networkidle');

      const accessibilityScanResults = await new AxeBuilder({ page })
        .withTags(['cat.color'])
        .analyze();

      // Log contrast issues for debugging
      if (accessibilityScanResults.violations.length > 0) {
        console.log('\nColour contrast issues on Dashboard:');
        for (const violation of accessibilityScanResults.violations) {
          console.log(`  - ${violation.id}: ${violation.description}`);
          for (const node of violation.nodes) {
            console.log(`    Element: ${node.html.substring(0, 100)}...`);
          }
        }
      }

      expect(accessibilityScanResults.violations).toEqual([]);
    });
  });

  test.describe('Keyboard Navigation', () => {
    test('Login form is keyboard navigable', async ({ page }) => {
      await page.goto('/accounts/login/');
      await page.waitForLoadState('networkidle');

      // Tab through form elements
      await page.keyboard.press('Tab');
      const firstFocusedElement = await page.evaluate(() => document.activeElement?.tagName);
      expect(firstFocusedElement).toBeTruthy();

      // Verify email input can be focused
      const emailInput = page.locator('[data-testid="email"], #id_email');
      await emailInput.focus();
      await expect(emailInput).toBeFocused();

      // Tab to password
      await page.keyboard.press('Tab');
      const passwordInput = page.locator('[data-testid="password"], #id_password');
      await expect(passwordInput).toBeFocused();

      // Tab to submit button
      await page.keyboard.press('Tab');
      const submitButton = page.locator('[data-testid="login-btn"], button[type="submit"]');
      await expect(submitButton).toBeFocused();
    });
  });
});
