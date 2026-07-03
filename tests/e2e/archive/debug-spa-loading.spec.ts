import { test } from '@playwright/test';

const testUsers = {
  reviewer1: {
    username: 'reviewer1',
    email: 'reviewer1@test.com',
    password: 'testpass123'
  }
};

test('Check SPA loading', async ({ page }) => {
  // Enable console logging
  page.on('console', msg => {
    const type = msg.type();
    console.log(`BROWSER [${type}]:`, msg.text());
  });
  page.on('pageerror', error => console.error('PAGE ERROR:', error.message));
  page.on('requestfailed', request => {
    const failure = request.failure();
    console.error('REQUEST FAILED:', request.url(), failure ? failure.errorText : '');
  });

  // Login
  await page.goto('http://localhost:8000/accounts/login/');
  await page.fill('[data-testid="email"]', testUsers.reviewer1.email);
  await page.fill('[data-testid="password"]', testUsers.reviewer1.password);
  await page.click('[data-testid="login-btn"]');
  await page.waitForURL('/');

  // Navigate to screening
  await page.goto('http://localhost:8000/screening/');

  // Wait a bit
  await page.waitForTimeout(3000);

  // Get page HTML
  const html = await page.content();
  console.log('\n=== PAGE HTML ===');
  console.log(html.substring(0, 2000));

  // Check app element
  const appInfo = await page.evaluate(() => {
    const app = document.querySelector('#app');
    return {
      exists: !!app,
      visible: app ? window.getComputedStyle(app).display !== 'none' : false,
      innerHTML: app ? app.innerHTML.substring(0, 500) : 'N/A',
      childCount: app ? app.childNodes.length : 0
    };
  });
  console.log('\n=== APP ELEMENT INFO ===');
  console.log(JSON.stringify(appInfo, null, 2));
});
