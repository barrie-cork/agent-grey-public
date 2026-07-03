/**
 * Lighthouse Performance Audit Automation
 *
 * Runs Lighthouse audits on all critical pages to validate:
 * - Performance score ≥90
 * - Accessibility score ≥95
 * - Best Practices score ≥90
 *
 * Generates HTML reports and validates against thresholds.
 *
 * Usage:
 *   node scripts/lighthouse_audit.js
 *
 * Requirements:
 *   npm install lighthouse chrome-launcher
 *
 * Based on:
 * - Google Lighthouse documentation
 * - Agent Grey performance targets from CLAUDE.md
 */

const lighthouse = require('lighthouse');
const chromeLauncher = require('chrome-launcher');
const fs = require('fs');
const path = require('path');

// ============================================================================
// CONFIGURATION
// ============================================================================

const BASE_URL = process.env.BASE_URL || 'http://localhost:8000';
const OUTPUT_DIR = process.env.OUTPUT_DIR || './lighthouse-reports';

// Performance thresholds (0-100 scale)
const THRESHOLDS = {
  performance: 90,
  accessibility: 95,
  bestPractices: 90,
  seo: 80  // Optional
};

// Pages to audit
const PAGES = [
  {
    url: `${BASE_URL}/work-queue`,
    name: 'Work Queue',
    description: 'Main work queue page for claiming results'
  },
  {
    url: `${BASE_URL}/conflicts`,
    name: 'Conflicts List',
    description: 'List of conflicts requiring resolution'
  },
  {
    url: `${BASE_URL}/dashboard/team`,
    name: 'Team Dashboard',
    description: 'Team dashboard with IRR metrics'
  },
  {
    url: `${BASE_URL}/sessions`,
    name: 'Sessions List',
    description: 'List of review sessions'
  }
];

// Lighthouse configuration
const LIGHTHOUSE_CONFIG = {
  logLevel: 'info',
  output: 'html',
  onlyCategories: ['performance', 'accessibility', 'best-practices', 'seo'],
  throttling: {
    // Simulate 3G connection (realistic mobile)
    rttMs: 150,
    throughputKbps: 1638.4,
    cpuSlowdownMultiplier: 4
  },
  screenEmulation: {
    // Desktop viewport
    mobile: false,
    width: 1350,
    height: 940,
    deviceScaleFactor: 1
  }
};

// ============================================================================
// LIGHTHOUSE AUDIT FUNCTIONS
// ============================================================================

/**
 * Run Lighthouse audit on a single page.
 *
 * @param {string} url - URL to audit
 * @param {Object} options - Lighthouse options
 * @param {number} port - Chrome port
 * @returns {Promise<Object>} Audit results
 */
async function runLighthouseAudit(url, options, port) {
  console.log(`\n🔍 Auditing: ${url}`);

  try {
    const runnerResult = await lighthouse(url, { ...options, port });

    return {
      success: true,
      lhr: runnerResult.lhr,
      report: runnerResult.report
    };
  } catch (error) {
    console.error(`❌ Audit failed for ${url}:`, error.message);
    return {
      success: false,
      error: error.message
    };
  }
}

/**
 * Extract scores from Lighthouse result.
 *
 * @param {Object} lhr - Lighthouse result object
 * @returns {Object} Scores
 */
function extractScores(lhr) {
  return {
    performance: Math.round(lhr.categories.performance.score * 100),
    accessibility: Math.round(lhr.categories.accessibility.score * 100),
    bestPractices: Math.round(lhr.categories['best-practices'].score * 100),
    seo: Math.round(lhr.categories.seo.score * 100)
  };
}

/**
 * Validate scores against thresholds.
 *
 * @param {Object} scores - Scores object
 * @param {Object} thresholds - Threshold object
 * @returns {Object} Validation result
 */
function validateScores(scores, thresholds) {
  const failures = [];

  if (scores.performance < thresholds.performance) {
    failures.push({
      metric: 'Performance',
      score: scores.performance,
      threshold: thresholds.performance
    });
  }

  if (scores.accessibility < thresholds.accessibility) {
    failures.push({
      metric: 'Accessibility',
      score: scores.accessibility,
      threshold: thresholds.accessibility
    });
  }

  if (scores.bestPractices < thresholds.bestPractices) {
    failures.push({
      metric: 'Best Practices',
      score: scores.bestPractices,
      threshold: thresholds.bestPractices
    });
  }

  if (scores.seo < thresholds.seo) {
    failures.push({
      metric: 'SEO',
      score: scores.seo,
      threshold: thresholds.seo
    });
  }

  return {
    passed: failures.length === 0,
    failures
  };
}

/**
 * Save Lighthouse report to file.
 *
 * @param {string} report - HTML report
 * @param {string} filename - Output filename
 */
function saveReport(report, filename) {
  // Create output directory if it doesn't exist
  if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  }

  const filepath = path.join(OUTPUT_DIR, filename);
  fs.writeFileSync(filepath, report);

  console.log(`✅ Report saved: ${filepath}`);
}

/**
 * Extract key metrics from Lighthouse result.
 *
 * @param {Object} lhr - Lighthouse result object
 * @returns {Object} Key metrics
 */
function extractKeyMetrics(lhr) {
  const audits = lhr.audits;

  return {
    // Performance metrics
    firstContentfulPaint: audits['first-contentful-paint']?.displayValue || 'N/A',
    speedIndex: audits['speed-index']?.displayValue || 'N/A',
    largestContentfulPaint: audits['largest-contentful-paint']?.displayValue || 'N/A',
    timeToInteractive: audits['interactive']?.displayValue || 'N/A',
    totalBlockingTime: audits['total-blocking-time']?.displayValue || 'N/A',
    cumulativeLayoutShift: audits['cumulative-layout-shift']?.displayValue || 'N/A',

    // Accessibility issues
    accessibilityIssues: audits['accessibility']?.details?.items?.length || 0,

    // Best practices issues
    bestPracticesIssues: lhr.categories['best-practices']?.auditRefs?.filter(
      ref => lhr.audits[ref.id]?.score < 1
    ).length || 0
  };
}

/**
 * Print audit summary.
 *
 * @param {Object} result - Audit result
 * @param {string} pageName - Page name
 */
function printAuditSummary(result, pageName) {
  console.log(`\n${'='.repeat(80)}`);
  console.log(`AUDIT SUMMARY: ${pageName}`);
  console.log('='.repeat(80));

  if (!result.success) {
    console.log(`❌ Audit failed: ${result.error}`);
    return;
  }

  const scores = extractScores(result.lhr);
  const validation = validateScores(scores, THRESHOLDS);
  const metrics = extractKeyMetrics(result.lhr);

  // Print scores
  console.log('\nSCORES:');
  console.log(`  Performance:    ${scores.performance}/100 ${scores.performance >= THRESHOLDS.performance ? '✅' : '❌'}`);
  console.log(`  Accessibility:  ${scores.accessibility}/100 ${scores.accessibility >= THRESHOLDS.accessibility ? '✅' : '❌'}`);
  console.log(`  Best Practices: ${scores.bestPractices}/100 ${scores.bestPractices >= THRESHOLDS.bestPractices ? '✅' : '❌'}`);
  console.log(`  SEO:            ${scores.seo}/100 ${scores.seo >= THRESHOLDS.seo ? '✅' : '❌'}`);

  // Print key metrics
  console.log('\nKEY METRICS:');
  console.log(`  First Contentful Paint:     ${metrics.firstContentfulPaint}`);
  console.log(`  Speed Index:                ${metrics.speedIndex}`);
  console.log(`  Largest Contentful Paint:   ${metrics.largestContentfulPaint}`);
  console.log(`  Time to Interactive:        ${metrics.timeToInteractive}`);
  console.log(`  Total Blocking Time:        ${metrics.totalBlockingTime}`);
  console.log(`  Cumulative Layout Shift:    ${metrics.cumulativeLayoutShift}`);

  // Print validation result
  console.log('\nVALIDATION:');
  if (validation.passed) {
    console.log('  ✅ ALL THRESHOLDS MET');
  } else {
    console.log('  ❌ SOME THRESHOLDS NOT MET:');
    validation.failures.forEach(failure => {
      console.log(`     - ${failure.metric}: ${failure.score}/100 (threshold: ${failure.threshold})`);
    });
  }

  console.log('='.repeat(80) + '\n');
}

// ============================================================================
// MAIN EXECUTION
// ============================================================================

/**
 * Run Lighthouse audits on all pages.
 *
 * @returns {Promise<Object>} Complete audit results
 */
async function auditAllPages() {
  console.log('\n' + '='.repeat(80));
  console.log('LIGHTHOUSE PERFORMANCE AUDIT');
  console.log('='.repeat(80));
  console.log(`\nBase URL: ${BASE_URL}`);
  console.log(`Output Directory: ${OUTPUT_DIR}`);
  console.log(`Pages to Audit: ${PAGES.length}`);
  console.log('\nThresholds:');
  console.log(`  Performance:    ≥${THRESHOLDS.performance}`);
  console.log(`  Accessibility:  ≥${THRESHOLDS.accessibility}`);
  console.log(`  Best Practices: ≥${THRESHOLDS.bestPractices}`);
  console.log(`  SEO:            ≥${THRESHOLDS.seo}`);

  // Launch Chrome
  console.log('\n🚀 Launching Chrome...');
  const chrome = await chromeLauncher.launch({
    chromeFlags: ['--headless', '--disable-gpu', '--no-sandbox']
  });

  console.log(`✅ Chrome launched on port ${chrome.port}`);

  const results = [];
  let allPassed = true;

  try {
    // Audit each page
    for (const page of PAGES) {
      const result = await runLighthouseAudit(
        page.url,
        { ...LIGHTHOUSE_CONFIG, port: chrome.port },
        chrome.port
      );

      if (result.success) {
        // Save report
        const filename = `lighthouse-${page.name.toLowerCase().replace(/\s+/g, '-')}.html`;
        saveReport(result.report, filename);

        // Print summary
        printAuditSummary(result, page.name);

        // Check if passed
        const scores = extractScores(result.lhr);
        const validation = validateScores(scores, THRESHOLDS);

        if (!validation.passed) {
          allPassed = false;
        }

        results.push({
          page: page.name,
          url: page.url,
          scores,
          validation,
          reportFile: filename
        });
      } else {
        allPassed = false;
        results.push({
          page: page.name,
          url: page.url,
          error: result.error
        });
      }
    }
  } finally {
    // Kill Chrome
    await chrome.kill();
    console.log('✅ Chrome closed');
  }

  // Print final summary
  printFinalSummary(results, allPassed);

  return {
    allPassed,
    results,
    timestamp: new Date().toISOString()
  };
}

/**
 * Print final summary of all audits.
 *
 * @param {Array} results - Array of audit results
 * @param {boolean} allPassed - Whether all audits passed
 */
function printFinalSummary(results, allPassed) {
  console.log('\n' + '='.repeat(80));
  console.log('FINAL SUMMARY');
  console.log('='.repeat(80));

  console.log(`\n${'Page'.padEnd(30)} ${'Perf'.padEnd(6)} ${'A11y'.padEnd(6)} ${'BP'.padEnd(6)} ${'SEO'.padEnd(6)} ${'Status'.padEnd(10)}`);
  console.log('-'.repeat(80));

  results.forEach(result => {
    if (result.error) {
      console.log(`${ result.page.padEnd(30)} ${'N/A'.padEnd(6)} ${'N/A'.padEnd(6)} ${'N/A'.padEnd(6)} ${'N/A'.padEnd(6)} ${'❌ ERROR'.padEnd(10)}`);
    } else {
      const status = result.validation.passed ? '✅ PASS' : '❌ FAIL';
      console.log(
        `${result.page.padEnd(30)} ` +
        `${result.scores.performance.toString().padEnd(6)} ` +
        `${result.scores.accessibility.toString().padEnd(6)} ` +
        `${result.scores.bestPractices.toString().padEnd(6)} ` +
        `${result.scores.seo.toString().padEnd(6)} ` +
        `${status.padEnd(10)}`
      );
    }
  });

  console.log('-'.repeat(80));
  console.log(`\nOVERALL: ${allPassed ? '✅ ALL PASSED' : '❌ SOME FAILED'}`);
  console.log('='.repeat(80) + '\n');
}

// ============================================================================
// CLI EXECUTION
// ============================================================================

// Run audits if executed directly
if (require.main === module) {
  auditAllPages()
    .then(result => {
      // Exit with appropriate code
      process.exit(result.allPassed ? 0 : 1);
    })
    .catch(error => {
      console.error('\n❌ FATAL ERROR:', error);
      process.exit(1);
    });
}

// Export for programmatic usage
module.exports = {
  auditAllPages,
  runLighthouseAudit,
  extractScores,
  validateScores,
  THRESHOLDS,
  PAGES
};
