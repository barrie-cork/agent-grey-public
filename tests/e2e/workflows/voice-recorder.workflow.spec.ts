import { test, expect } from '@playwright/test';
import { loginUser } from './fixtures/test-users';

/**
 * Voice Recorder Widget Tests
 *
 * Tests the feedback FAB voice recording flow. Uses mocked MediaRecorder
 * API since Playwright doesn't have real microphone access.
 *
 * Fixes #144: Recording indicator should disappear after stop is pressed.
 */

const MOCK_MEDIA_RECORDER_SCRIPT = `
  // Mock MediaRecorder and getUserMedia for voice recorder tests
  window.__mockMediaRecorder = {
    state: 'inactive',
    _onstop: null,
    _ondataavailable: null,
  };

  class MockMediaRecorder {
    constructor(stream, options) {
      this.stream = stream;
      this.state = 'inactive';
      this.mimeType = 'audio/webm';
      this.ondataavailable = null;
      this.onstop = null;
      this.onerror = null;
      window.__mockMediaRecorder._instance = this;
    }

    start(timeslice) {
      this.state = 'recording';
      window.__mockMediaRecorder.state = 'recording';
      // Emit a small data chunk
      setTimeout(() => {
        if (this.ondataavailable) {
          this.ondataavailable({ data: new Blob(['mock-audio'], { type: 'audio/webm' }) });
        }
      }, 100);
    }

    stop() {
      this.state = 'inactive';
      window.__mockMediaRecorder.state = 'inactive';
      // Fire onstop asynchronously (like real MediaRecorder)
      setTimeout(() => {
        if (this.onstop) {
          this.onstop();
        }
      }, 50);
    }

    static isTypeSupported(type) {
      return type === 'audio/webm' || type === 'audio/webm;codecs=opus';
    }
  }

  window.MediaRecorder = MockMediaRecorder;

  // Mock getUserMedia
  if (!navigator.mediaDevices) {
    navigator.mediaDevices = {};
  }
  navigator.mediaDevices.getUserMedia = async function(constraints) {
    return {
      getTracks: () => [{ stop: () => {} }],
    };
  };
`;

test.describe('Voice Recorder Widget', () => {
  test.setTimeout(30000);

  test.beforeEach(async ({ page }) => {
    // Inject mock MediaRecorder before page loads
    await page.addInitScript(MOCK_MEDIA_RECORDER_SCRIPT);
  });

  test('recording indicator disappears after stop is pressed (#144)', async ({ page }) => {
    await loginUser(page, 'e2e-owner@test.local');
    await page.goto('/', { waitUntil: 'domcontentloaded' });

    const feedbackBtn = page.locator('[data-testid="open-feedback-btn"]');
    await expect(feedbackBtn).toBeVisible();

    // First tap: starts voice recording
    await feedbackBtn.click();

    // Recording indicator should appear
    const recordingIndicator = page.locator('#feedbackRecordingIndicator');
    await expect(recordingIndicator).toBeVisible({ timeout: 5000 });
    await expect(recordingIndicator).toContainText('Recording');

    // FAB should show stop state
    await expect(feedbackBtn).toContainText('Stop');

    // Second tap: stop recording
    await feedbackBtn.click();

    // Recording indicator should disappear
    await expect(recordingIndicator).toBeHidden({ timeout: 5000 });

    // Modal should open with voice recording context
    const feedbackModal = page.locator('[data-testid="feedback-modal"]');
    await expect(feedbackModal).toBeVisible({ timeout: 5000 });

    // FAB should return to default state (not showing "Stop")
    await expect(feedbackBtn).not.toContainText('Stop');
  });

  test('FAB resets to default state after modal close', async ({ page }) => {
    await loginUser(page, 'e2e-owner@test.local');
    await page.goto('/', { waitUntil: 'domcontentloaded' });

    const feedbackBtn = page.locator('[data-testid="open-feedback-btn"]');
    await expect(feedbackBtn).toBeVisible();

    // Start and stop recording
    await feedbackBtn.click();
    const recordingIndicator = page.locator('#feedbackRecordingIndicator');
    await expect(recordingIndicator).toBeVisible({ timeout: 5000 });

    await feedbackBtn.click();
    await expect(recordingIndicator).toBeHidden({ timeout: 5000 });

    // Modal should be visible
    const feedbackModal = page.locator('[data-testid="feedback-modal"]');
    await expect(feedbackModal).toBeVisible({ timeout: 5000 });

    // Close modal via cancel button
    const cancelBtn = page.locator('[data-testid="cancel-feedback-btn"]');
    await cancelBtn.click();
    await expect(feedbackModal).toBeHidden({ timeout: 5000 });

    // FAB should show mic/feedback state, not stop
    await expect(feedbackBtn).toContainText('Feedback');
    await expect(feedbackBtn).not.toContainText('Stop');
  });
});
