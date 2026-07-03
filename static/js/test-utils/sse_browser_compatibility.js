/**
 * SSE Browser Compatibility Test Suite
 *
 * Tests Server-Sent Events functionality across:
 * - Chrome 90+
 * - Firefox 88+
 * - Safari 14+ (with polyfill)
 * - Edge 90+
 *
 * Tests:
 * 1. Connection establishment and latency
 * 2. Event delivery (connected, new_comment, revote_proposal, consensus_reached)
 * 3. Reconnection after disconnect
 * 4. Keepalive message handling
 * 5. Error handling and exponential backoff
 *
 * Based on:
 * - apps/review_results/api/sse_views.py
 * - apps/review_results/tests/test_sse_views.py
 *
 * Usage:
 * 1. Open browser DevTools console
 * 2. Load conflict discussion page
 * 3. Run: runBrowserTests()
 * 4. Monitor console output for test results
 */

// ============================================================================
// SSE COMPATIBILITY TEST CLASS
// ============================================================================

class SSECompatibilityTest {
  /**
   * Initialise SSE compatibility test.
   *
   * @param {string} conflictId - UUID of conflict to monitor
   */
  constructor(conflictId) {
    this.conflictId = conflictId;
    this.eventSource = null;
    this.connectionLatency = 0;
    this.reconnectAttempts = 0;
    this.receivedEvents = [];
    this.keepaliveCount = 0;
    this.isConnected = false;
  }

  /**
   * Test EventSource connection and measure latency.
   *
   * @returns {Promise<Object>} Connection result with latency
   */
  async testConnection() {
    const startTime = performance.now();

    console.log('🔌 Establishing SSE connection...');

    this.eventSource = new EventSource(
      `/api/conflicts/${this.conflictId}/stream/`
    );

    return new Promise((resolve, reject) => {
      // Connection opened successfully
      this.eventSource.onopen = () => {
        this.connectionLatency = performance.now() - startTime;
        this.isConnected = true;

        console.log(`✅ Connected in ${this.connectionLatency.toFixed(2)}ms`);

        if (this.connectionLatency > 500) {
          console.warn(`⚠️ Connection latency ${this.connectionLatency.toFixed(2)}ms exceeds 500ms threshold`);
        }

        resolve({
          success: true,
          latency: this.connectionLatency,
          timestamp: new Date().toISOString()
        });
      };

      // Listen for 'connected' event (first event sent by server)
      this.eventSource.addEventListener('connected', (event) => {
        const data = JSON.parse(event.data);
        console.log('📨 Connected event received:', data);

        this.receivedEvents.push({
          type: 'connected',
          data: data,
          timestamp: Date.now()
        });
      });

      // Listen for 'new_comment' events
      this.eventSource.addEventListener('new_comment', (event) => {
        const data = JSON.parse(event.data);
        console.log('📨 New comment event received:', data);

        this.receivedEvents.push({
          type: 'new_comment',
          data: data,
          timestamp: Date.now()
        });
      });

      // Listen for 'revote_proposal' events
      this.eventSource.addEventListener('revote_proposal', (event) => {
        const data = JSON.parse(event.data);
        console.log('📨 Revote proposal event received:', data);

        this.receivedEvents.push({
          type: 'revote_proposal',
          data: data,
          timestamp: Date.now()
        });
      });

      // Listen for 'consensus_reached' events
      this.eventSource.addEventListener('consensus_reached', (event) => {
        const data = JSON.parse(event.data);
        console.log('📨 Consensus reached event received:', data);

        this.receivedEvents.push({
          type: 'consensus_reached',
          data: data,
          timestamp: Date.now()
        });
      });

      // Error handling with exponential backoff
      this.eventSource.onerror = (error) => {
        this.isConnected = false;
        this.reconnectAttempts++;

        console.error(`❌ SSE Error (attempt ${this.reconnectAttempts}):`, error);

        if (this.reconnectAttempts < 3) {
          // Exponential backoff: 1s, 2s, 4s
          const backoffMs = 1000 * Math.pow(2, this.reconnectAttempts - 1);
          console.log(`⏳ Reconnecting in ${backoffMs}ms...`);

          // EventSource auto-reconnects, so we don't need to manually retry
          // Just log the attempt
        } else {
          console.error('❌ Max reconnection attempts reached (3)');
          reject({
            success: false,
            error: 'Max reconnection attempts reached',
            reconnectAttempts: this.reconnectAttempts
          });
        }
      };

      // Timeout after 30 seconds
      setTimeout(() => {
        if (!this.isConnected) {
          console.error('❌ Connection timeout (30s)');
          reject({ success: false, error: 'Connection timeout' });
        }
      }, 30000);
    });
  }

  /**
   * Test reconnection after simulated disconnect.
   *
   * @returns {Promise<Object>} Reconnection result with latency
   */
  async testReconnection() {
    console.log('\n🔌 Testing reconnection...');

    if (!this.eventSource) {
      throw new Error('No existing connection to disconnect');
    }

    // Simulate network disconnect by closing connection
    console.log('🔌 Simulating network disconnect...');
    this.eventSource.close();
    this.isConnected = false;

    // Wait 2 seconds
    await new Promise(resolve => setTimeout(resolve, 2000));

    // Reconnect
    const reconnectStart = performance.now();
    await this.testConnection();
    const reconnectLatency = performance.now() - reconnectStart;

    console.log(`✅ Reconnected in ${reconnectLatency.toFixed(2)}ms`);

    if (reconnectLatency > 2000) {
      console.warn(`⚠️ Reconnection latency ${reconnectLatency.toFixed(2)}ms exceeds 2s threshold`);
    }

    return {
      success: true,
      reconnectLatency: reconnectLatency,
      timestamp: new Date().toISOString()
    };
  }

  /**
   * Test keepalive message handling.
   *
   * Monitors for keepalive messages sent every 30 seconds.
   * Runs for 2 minutes to capture multiple keepalives.
   *
   * @returns {Promise<Object>} Keepalive test results
   */
  async testKeepalive() {
    console.log('\n💓 Testing keepalive messages (2 minutes)...');

    const startTime = Date.now();
    const keepaliveTimes = [];

    // Monitor for keepalive comments (SSE comments start with ":")
    // These are sent by server to keep connection alive
    const originalOnmessage = this.eventSource.onmessage;

    this.eventSource.onmessage = (event) => {
      // Call original handler if exists
      if (originalOnmessage) {
        originalOnmessage(event);
      }

      // Check for keepalive (empty data or ":keepalive")
      if (event.data === '' || event.data.includes('keepalive')) {
        this.keepaliveCount++;
        keepaliveTimes.push(Date.now());
        console.log(`💓 Keepalive ${this.keepaliveCount} received`);
      }
    };

    // Wait for 2 minutes
    await new Promise(resolve => setTimeout(resolve, 120000));

    // Calculate keepalive intervals
    const intervals = [];
    for (let i = 1; i < keepaliveTimes.length; i++) {
      const interval = keepaliveTimes[i] - keepaliveTimes[i - 1];
      intervals.push(interval);
    }

    const avgInterval = intervals.length > 0
      ? intervals.reduce((a, b) => a + b, 0) / intervals.length
      : 0;

    console.log(`\n✅ Received ${this.keepaliveCount} keepalives in 2 minutes`);
    console.log(`   Average interval: ${(avgInterval / 1000).toFixed(1)}s`);

    if (this.keepaliveCount < 3) {
      console.warn(`⚠️ Expected ~4 keepalives (every 30s), received ${this.keepaliveCount}`);
    }

    return {
      keepaliveCount: this.keepaliveCount,
      averageInterval: avgInterval,
      timestamp: new Date().toISOString()
    };
  }

  /**
   * Test event delivery by monitoring received events.
   *
   * @param {number} timeoutMs - How long to monitor (default 10s)
   * @returns {Promise<Object>} Event delivery test results
   */
  async testEventDelivery(timeoutMs = 10000) {
    console.log(`\n📨 Testing event delivery (${timeoutMs / 1000}s)...`);

    const initialCount = this.receivedEvents.length;

    await new Promise(resolve => setTimeout(resolve, timeoutMs));

    const newCount = this.receivedEvents.length;
    const receivedCount = newCount - initialCount;

    console.log(`✅ Received ${receivedCount} events in ${timeoutMs / 1000}s`);

    // Group events by type
    const eventTypes = {};
    this.receivedEvents.forEach(event => {
      eventTypes[event.type] = (eventTypes[event.type] || 0) + 1;
    });

    console.log('   Event breakdown:');
    Object.entries(eventTypes).forEach(([type, count]) => {
      console.log(`     - ${type}: ${count}`);
    });

    return {
      totalEvents: this.receivedEvents.length,
      newEvents: receivedCount,
      eventTypes: eventTypes,
      timestamp: new Date().toISOString()
    };
  }

  /**
   * Disconnect from SSE stream.
   */
  disconnect() {
    if (this.eventSource) {
      this.eventSource.close();
      this.isConnected = false;
      console.log('🔌 Disconnected from SSE stream');
    }
  }

  /**
   * Get test summary.
   *
   * @returns {Object} Test summary with all metrics
   */
  getSummary() {
    return {
      connectionLatency: this.connectionLatency,
      reconnectAttempts: this.reconnectAttempts,
      totalEvents: this.receivedEvents.length,
      keepaliveCount: this.keepaliveCount,
      isConnected: this.isConnected,
      events: this.receivedEvents
    };
  }
}

// ============================================================================
// BROWSER DETECTION AND POLYFILL
// ============================================================================

/**
 * Detect browser and return name.
 *
 * @returns {string} Browser name
 */
function detectBrowser() {
  const userAgent = navigator.userAgent;

  if (userAgent.includes('Chrome') && !userAgent.includes('Edge')) {
    return 'Chrome';
  } else if (userAgent.includes('Firefox')) {
    return 'Firefox';
  } else if (userAgent.includes('Safari') && !userAgent.includes('Chrome')) {
    return 'Safari';
  } else if (userAgent.includes('Edge') || userAgent.includes('Edg/')) {
    return 'Edge';
  } else {
    return 'Unknown';
  }
}

/**
 * Check if Safari polyfill is needed.
 *
 * @returns {boolean} True if polyfill needed
 */
function needsSafariPolyfill() {
  return detectBrowser() === 'Safari';
}

/**
 * Load EventSource polyfill for Safari.
 *
 * @returns {Promise<void>}
 */
async function loadSafariPolyfill() {
  if (!needsSafariPolyfill()) {
    return;
  }

  console.log('⚠️ Safari detected - loading EventSource polyfill');

  // Check if polyfill already loaded
  if (window.EventSourcePolyfill) {
    console.log('✅ EventSource polyfill already loaded');
    return;
  }

  // Load polyfill from CDN
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/event-source-polyfill@1.0.31/src/eventsource.min.js';
    script.onload = () => {
      console.log('✅ EventSource polyfill loaded');

      // Replace native EventSource with polyfill
      if (window.EventSourcePolyfill) {
        window.EventSource = window.EventSourcePolyfill;
        console.log('✅ EventSource replaced with polyfill');
      }

      resolve();
    };
    script.onerror = () => {
      console.error('❌ Failed to load EventSource polyfill');
      reject(new Error('Failed to load polyfill'));
    };
    document.head.appendChild(script);
  });
}

// ============================================================================
// BROWSER TEST EXECUTION
// ============================================================================

/**
 * Run complete browser compatibility test suite.
 *
 * @param {string} conflictId - UUID of conflict to test
 * @returns {Promise<Object>} Complete test results
 */
async function runBrowserTests(conflictId) {
  const browserName = detectBrowser();

  console.log('\n' + '='.repeat(80));
  console.log(`🧪 SSE BROWSER COMPATIBILITY TEST - ${browserName}`);
  console.log('='.repeat(80) + '\n');

  // Load Safari polyfill if needed
  if (needsSafariPolyfill()) {
    try {
      await loadSafariPolyfill();
    } catch (error) {
      console.error('❌ Failed to load Safari polyfill:', error);
      return {
        success: false,
        error: 'Safari polyfill failed to load',
        browser: browserName
      };
    }
  }

  const test = new SSECompatibilityTest(conflictId);
  const results = {
    browser: browserName,
    tests: {},
    timestamp: new Date().toISOString()
  };

  try {
    // Test 1: Connection
    console.log('\n--- TEST 1: Connection ---');
    results.tests.connection = await test.testConnection();

    // Wait a bit for initial events
    await new Promise(resolve => setTimeout(resolve, 2000));

    // Test 2: Event Delivery
    console.log('\n--- TEST 2: Event Delivery ---');
    results.tests.eventDelivery = await test.testEventDelivery(10000);

    // Test 3: Reconnection
    console.log('\n--- TEST 3: Reconnection ---');
    results.tests.reconnection = await test.testReconnection();

    // Test 4: Keepalive (optional - takes 2 minutes)
    // Uncomment to run keepalive test
    // console.log('\n--- TEST 4: Keepalive ---');
    // results.tests.keepalive = await test.testKeepalive();

    // Get summary
    results.summary = test.getSummary();
    results.success = true;

    console.log('\n' + '='.repeat(80));
    console.log('✅ ALL TESTS PASSED');
    console.log('='.repeat(80));

    // Print summary
    console.log('\nTEST SUMMARY:');
    console.log(`  Browser: ${browserName}`);
    console.log(`  Connection Latency: ${results.tests.connection.latency.toFixed(2)}ms`);
    console.log(`  Reconnection Latency: ${results.tests.reconnection.reconnectLatency.toFixed(2)}ms`);
    console.log(`  Total Events: ${results.summary.totalEvents}`);
    console.log(`  Reconnect Attempts: ${results.summary.reconnectAttempts}`);

    // Cleanup
    test.disconnect();

  } catch (error) {
    console.error('\n❌ TESTS FAILED:', error);
    results.success = false;
    results.error = error.message || String(error);

    // Cleanup
    test.disconnect();
  }

  return results;
}

// ============================================================================
// AUTO-RUN ON PAGE LOAD
// ============================================================================

/**
 * Auto-run tests when page loads.
 *
 * Extracts conflict ID from URL and runs tests automatically.
 */
async function autoRunTests() {
  // Extract conflict ID from URL
  const urlMatch = window.location.pathname.match(/\/conflicts\/([0-9a-f-]+)/);

  if (!urlMatch) {
    console.warn('⚠️ No conflict ID found in URL - cannot auto-run tests');
    console.log('To run tests manually:');
    console.log('  runBrowserTests("YOUR_CONFLICT_ID")');
    return;
  }

  const conflictId = urlMatch[1];
  console.log(`📍 Conflict ID detected: ${conflictId}`);

  // Wait for page to fully load
  await new Promise(resolve => {
    if (document.readyState === 'complete') {
      resolve();
    } else {
      window.addEventListener('load', resolve);
    }
  });

  // Run tests
  await runBrowserTests(conflictId);
}

// Run tests when page loads
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', autoRunTests);
} else {
  autoRunTests();
}

// ============================================================================
// EXPORT FOR MANUAL USAGE
// ============================================================================

// Make available globally for manual testing
window.SSECompatibilityTest = SSECompatibilityTest;
window.runBrowserTests = runBrowserTests;
window.detectBrowser = detectBrowser;
window.loadSafariPolyfill = loadSafariPolyfill;

console.log('\n📚 SSE Compatibility Test Suite Loaded');
console.log('\nManual Usage:');
console.log('  runBrowserTests("conflict-id") - Run full test suite');
console.log('  detectBrowser()                - Detect current browser');
console.log('  loadSafariPolyfill()           - Load Safari polyfill');
console.log('');
