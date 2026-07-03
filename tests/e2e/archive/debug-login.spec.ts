import { test, expect } from '@playwright/test';

test('DEBUG: Simple login test', async ({ page }) => {
  console.log('=== Step 1: Navigate to login page ===');
  await page.goto('http://localhost:8000/accounts/login/');

  console.log('=== Step 2: Wait for form ===');
  await page.waitForSelector('[data-testid="email"]');
  await page.waitForSelector('[data-testid="password"]');

  console.log('=== Step 3: Fill email ===');
  await page.fill('[data-testid="email"]', 'reviewer1@test.com');

  console.log('=== Step 4: Fill password ===');
  await page.fill('[data-testid="password"]', 'testpass123');

  console.log('=== Step 5: Verify fields before submit ===');
  const email = await page.inputValue('[data-testid="email"]');
  const password = await page.inputValue('[data-testid="password"]');
  console.log(`  Email: ${email}`);
  console.log(`  Password length: ${password.length}`);
  console.log(`  Password value: ${password}`);  // Temporarily log actual password for debug

  console.log('=== Step 6: Take screenshot before submit ===');
  await page.screenshot({ path: 'debug-before-submit.png' });

  console.log('=== Step 7: Click login button ===');
  await page.click('[data-testid="login-btn"]');

  console.log('=== Step 8: Wait a moment ===');
  await page.waitForTimeout(2000);

  console.log('=== Step 9: Check current URL ===');
  const currentUrl = page.url();
  console.log(`  Current URL: ${currentUrl}`);

  console.log('=== Step 10: Take screenshot after submit ===');
  await page.screenshot({ path: 'debug-after-submit.png' });

  console.log('=== Step 11: Check for error messages ===');
  const pageContent = await page.content();
  if (pageContent.includes('Invalid login credentials')) {
    console.log('  ❌ ERROR: Invalid login credentials message found');
  } else {
    console.log('  ✅ No error message found');
  }

  console.log('=== Step 12: Check cookies ===');
  const cookies = await page.context().cookies();
  console.log(`  Cookies count: ${cookies.length}`);
  cookies.forEach(cookie => {
    console.log(`  - ${cookie.name}: ${cookie.value.substring(0, 20)}...`);
  });

  console.log('=== TEST COMPLETE ===');
});
