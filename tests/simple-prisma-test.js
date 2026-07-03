import { chromium } from 'playwright';

(async () => {
  console.log('Starting PRISMA diagram capture...');
  
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();
  
  try {
    // Navigate to the Django app
    await page.goto('http://localhost:8000/');
    console.log('Navigated to Django app');
    
    // Login
    const loginFormExists = await page.locator('input[name="username"]').count() > 0;
    
    if (loginFormExists) {
      await page.fill('input[name="username"]', 'testuser');
      await page.fill('input[name="password"]', 'testpassword123');
      await page.click('button[type="submit"]');
      
      // Wait for redirect
      await page.waitForTimeout(3000);
      console.log('Attempted login');
    }
    
    // Take a screenshot of current page
    await page.screenshot({ path: 'test-results/current-page.png', fullPage: true });
    console.log('Screenshot saved to test-results/current-page.png');
    
    // Look for session links - try different selectors
    let sessionLinks = page.locator('a[href*="/session/"]');
    let sessionCount = await sessionLinks.count();
    
    // If no direct session links, look for the session title or button
    if (sessionCount === 0) {
      sessionLinks = page.locator('text="Validation Test Session", .session-title, h3:has-text("Validation"), button:has-text("Define Strategy")');
      sessionCount = await sessionLinks.count();
    }
    
    console.log(`Found ${sessionCount} session elements`);
    
    if (sessionCount > 0) {
      // Click on the session or its "Define Strategy" button
      const sessionElement = sessionLinks.first();
      await sessionElement.click();
      await page.waitForTimeout(3000);
      
      // Take screenshot of session page
      await page.screenshot({ path: 'test-results/session-page.png', fullPage: true });
      console.log('Session page screenshot saved');
      
      // Look for PRISMA or reporting elements
      const prismaElements = await page.locator('*').evaluateAll(elements => {
        return elements.filter(el => {
          const text = el.textContent?.toLowerCase() || '';
          return text.includes('prisma') || text.includes('flow') || text.includes('report');
        }).map(el => ({
          tag: el.tagName,
          text: el.textContent?.substring(0, 100),
          href: el.getAttribute('href')
        }));
      });
      
      console.log('Found PRISMA-related elements:', prismaElements);
      
      // Look for reporting or PRISMA navigation
      const reportLinks = page.locator('a:has-text("Report"), a:has-text("PRISMA"), button:has-text("Report"), nav a:contains("Report")');
      const reportCount = await reportLinks.count();
      
      console.log(`Found ${reportCount} report links`);
      
      if (reportCount > 0) {
        await reportLinks.first().click();
        await page.waitForTimeout(2000);
        await page.screenshot({ path: 'test-results/report-page.png', fullPage: true });
        console.log('Report page screenshot saved');
      }
      
      // Try to access PRISMA flow API directly
      const currentUrl = page.url();
      const sessionId = currentUrl.match(/session\/([a-f0-9-]+)/)?.[1];
      
      if (sessionId) {
        console.log('Session ID:', sessionId);
        
        try {
          await page.goto(`http://localhost:8000/reporting/api/session/${sessionId}/prisma/flow/`);
          await page.waitForTimeout(2000);
          
          const apiContent = await page.textContent('body');
          console.log('PRISMA API Response:', apiContent.substring(0, 500));
          
          // Take screenshot of API response
          await page.screenshot({ path: 'test-results/prisma-api-response.png' });
          
          // Try to load the HTML template version
          await page.goto(`http://localhost:8000/reporting/sessions/${sessionId}/`);
          await page.waitForTimeout(2000);
          await page.screenshot({ path: 'test-results/reporting-dashboard.png', fullPage: true });
          console.log('Reporting dashboard screenshot saved');
          
        } catch (error) {
          console.log('Error accessing PRISMA API:', error.message);
        }
      }
    } else {
      console.log('No sessions found, taking current page screenshot');
      await page.screenshot({ path: 'test-results/no-sessions.png', fullPage: true });
    }
    
  } catch (error) {
    console.error('Error during test:', error);
    await page.screenshot({ path: 'test-results/error-state.png', fullPage: true });
  }
  
  await browser.close();
  console.log('Test completed');
})();