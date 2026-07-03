import { chromium } from 'playwright';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

(async () => {
  console.log('Starting modified PRISMA diagram test...');
  
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();
  
  try {
    // Navigate to the test HTML file
    const testFilePath = path.join(__dirname, 'test-prisma-diagram.html');
    await page.goto(`file://${testFilePath}`);
    console.log('Navigated to test diagram page');
    
    // Wait for diagram to be generated
    await page.waitForTimeout(3000);
    
    // Take screenshot of the canvas
    const canvas = page.locator('#prisma-canvas');
    await canvas.screenshot({ 
      path: 'test-results/modified-prisma-diagram.png',
      timeout: 10000 
    });
    console.log('Modified diagram screenshot saved');
    
    // Take full page screenshot for comparison
    await page.screenshot({ 
      path: 'test-results/modified-diagram-full-page.png',
      fullPage: true 
    });
    console.log('Full page screenshot saved');
    
    // Test export functionality
    await page.click('button:has-text("Export as PNG")');
    console.log('Export button clicked');
    
    await page.waitForTimeout(1000);
    
    // Get canvas dimensions for validation
    const canvasElement = await canvas.elementHandle();
    const boundingBox = await canvasElement.boundingBox();
    
    console.log('Canvas dimensions:', {
      width: boundingBox.width,
      height: boundingBox.height
    });
    
    // Verify canvas content
    const canvasContent = await page.evaluate(() => {
      const canvas = document.getElementById('prisma-canvas');
      return canvas.toDataURL();
    });
    
    console.log('Canvas content captured successfully:', canvasContent.length > 0);
    
  } catch (error) {
    console.error('Error during test:', error);
    await page.screenshot({ path: 'test-results/modified-test-error.png', fullPage: true });
  }
  
  await browser.close();
  console.log('Modified diagram test completed');
})();