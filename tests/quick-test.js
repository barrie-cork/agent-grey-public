import { test, expect } from '@playwright/test';

test.describe('Quick Agent Grey Validation', () => {
  
  test('should validate Agent Grey system is operational', async ({ page }) => {
    console.log('Testing Agent Grey system connectivity...');
    
    // Test 1: Homepage loads and redirects to login
    await page.goto('http://localhost:8000/');
    await page.waitForTimeout(2000);
    
    console.log('Current URL:', page.url());
    console.log('Page title:', await page.title());
    
    // Should redirect to login or show login page
    expect(page.url()).toMatch(/login|auth/);
    
    // Test 2: Login page has required elements
    const usernameField = page.locator('input[name="username"]');
    const passwordField = page.locator('input[name="password"]');
    const submitButton = page.locator('button[type="submit"], input[type="submit"]');
    
    await expect(usernameField).toBeVisible();
    await expect(passwordField).toBeVisible();
    await expect(submitButton).toBeVisible();
    console.log('✓ Login form elements present');
    
    // Test 3: Successful login
    await usernameField.fill('testuser');
    await passwordField.fill('testpassword123');
    await submitButton.click();
    
    // Wait for redirect
    await page.waitForTimeout(3000);
    
    console.log('After login URL:', page.url());
    
    // Should be on dashboard or similar
    expect(page.url()).toMatch(/dashboard|home/);
    console.log('✓ Login successful');
    
    // Test 4: Dashboard performance
    const startTime = Date.now();
    await page.waitForLoadState('networkidle');
    const loadTime = Date.now() - startTime;
    
    console.log(`Dashboard load time: ${loadTime}ms`);
    expect(loadTime).toBeLessThan(5000);
    console.log('✓ Dashboard loads within acceptable time');
    
    // Test 5: Key UI elements present
    const welcomeElement = page.locator('text=Welcome, text=Dashboard, h1, h2');
    await expect(welcomeElement.first()).toBeVisible({ timeout: 3000 });
    console.log('✓ Dashboard UI elements present');
    
    // Test 6: Navigation responsiveness
    const navigationStart = Date.now();
    const navElements = page.locator('nav, .navbar, .navigation');
    if (await navElements.count() > 0) {
      await navElements.first().hover();
    }
    const navTime = Date.now() - navigationStart;
    
    console.log(`Navigation response time: ${navTime}ms`);
    expect(navTime).toBeLessThan(500);
    console.log('✓ Navigation is responsive');
    
    // Test 7: Test session creation flow
    const createButton = page.locator('a:has-text("Create"), button:has-text("Create"), a:has-text("New Session")');
    if (await createButton.count() > 0) {
      await createButton.first().click();
      await page.waitForTimeout(2000);
      
      console.log('Session creation URL:', page.url());
      expect(page.url()).toMatch(/session.*create|new/);
      console.log('✓ Session creation accessible');
      
      // Quick form test
      const titleField = page.locator('input[name="title"], input[name="name"]');
      if (await titleField.count() > 0) {
        await titleField.fill('Test Performance Session');
        console.log('✓ Session form functional');
      }
    }
    
    console.log('=== Agent Grey System Validation Complete ===');
  });
  
});