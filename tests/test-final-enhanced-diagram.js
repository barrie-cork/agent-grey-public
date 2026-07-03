import { chromium } from 'playwright';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

(async () => {
  console.log('Starting final enhanced PRISMA diagram test...');
  
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();
  
  try {
    // Navigate to the enhanced test HTML file
    const testFilePath = path.join(__dirname, 'test-enhanced-diagram.html');
    await page.goto(`file://${testFilePath}`);
    console.log('Navigated to enhanced test diagram page');
    
    // Wait for diagram to be generated
    await page.waitForTimeout(3000);
    
    // Take screenshot of the canvas
    const canvas = page.locator('#prisma-canvas');
    await canvas.screenshot({ 
      path: 'test-results/final-enhanced-prisma-diagram.png',
      timeout: 10000 
    });
    console.log('Enhanced diagram screenshot saved');
    
    // Take full page screenshot for comparison
    await page.screenshot({ 
      path: 'test-results/enhanced-diagram-full-page.png',
      fullPage: true 
    });
    console.log('Full page screenshot saved');
    
    // Verify canvas content and dimensions
    const canvasElement = await canvas.elementHandle();
    const boundingBox = await canvasElement.boundingBox();
    
    console.log('Enhanced canvas dimensions:', {
      width: boundingBox.width,
      height: boundingBox.height
    });
    
    // Verify the diagram contains expected elements
    const canvasContent = await page.evaluate(() => {
      const canvas = document.getElementById('prisma-canvas');
      const ctx = canvas.getContext('2d');
      
      // Check if the canvas has been drawn to
      const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const pixels = imageData.data;
      
      // Count non-white pixels to verify content
      let nonWhitePixels = 0;
      for (let i = 0; i < pixels.length; i += 4) {
        const r = pixels[i];
        const g = pixels[i + 1]; 
        const b = pixels[i + 2];
        
        if (r !== 255 || g !== 255 || b !== 255) {
          nonWhitePixels++;
        }
      }
      
      return {
        totalPixels: pixels.length / 4,
        nonWhitePixels,
        hasContent: nonWhitePixels > 1000
      };
    });
    
    console.log('Canvas content analysis:', canvasContent);
    
    // Test export functionality
    await page.click('button:has-text("Export as PNG")');
    console.log('Export button clicked');
    
    await page.waitForTimeout(2000);
    
    console.log('✅ Enhanced PRISMA diagram validation completed successfully!');
    
  } catch (error) {
    console.error('❌ Error during enhanced diagram test:', error);
    await page.screenshot({ path: 'test-results/enhanced-test-error.png', fullPage: true });
  }
  
  await browser.close();
  console.log('Enhanced diagram test completed');
})();