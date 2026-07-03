<template>
  <div>
    <!-- Floating Feedback Button (two-tap FAB) -->
    <button
      @click="handleFabTap"
      @contextmenu.prevent="openTextOnlyModal"
      class="fixed bottom-6 right-6 z-40 inline-flex items-center gap-2 rounded-full px-4 py-2.5 text-sm font-medium shadow-lg transition-all hover:scale-105 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
      :class="isRecording
        ? 'bg-red-500 text-white animate-pulse hover:bg-red-600'
        : 'bg-primary text-primary-foreground hover:bg-primary/90'"
      :aria-label="isRecording ? 'Stop recording' : 'Send feedback'"
      :title="fabTitle"
      data-testid="feedback-button"
      data-no-screenshot
    >
      <!-- Stop icon when recording -->
      <svg v-if="isRecording" class="h-5 w-5" fill="currentColor" viewBox="0 0 24 24">
        <rect x="6" y="6" width="12" height="12" rx="1" />
      </svg>
      <!-- Mic icon when voice supported -->
      <svg v-else-if="voiceSupported" class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-14 0m7 7v4m-4 0h8m-4-16a3 3 0 00-3 3v4a3 3 0 006 0V6a3 3 0 00-3-3z" />
      </svg>
      <!-- Chat icon fallback -->
      <MessageSquarePlus v-else class="h-4 w-4" />
      {{ isRecording ? 'Stop' : 'Feedback' }}
    </button>

    <!-- Recording Indicator -->
    <div
      v-if="isRecording"
      class="fixed bottom-20 right-6 z-50 flex items-center gap-2 bg-white border border-red-200 rounded-full px-4 py-2 shadow-lg"
      data-no-screenshot
    >
      <span class="inline-block w-3 h-3 bg-red-500 rounded-full animate-pulse"></span>
      <span class="text-sm font-medium text-gray-700">
        Recording... {{ recordingTimeDisplay }} / 0:30
      </span>
    </div>

    <!-- Feedback Modal -->
    <Teleport to="body">
      <div
        v-if="isOpen"
        class="fixed inset-0 z-50 flex items-center justify-center"
        data-no-screenshot
      >
        <!-- Backdrop -->
        <div class="absolute inset-0 bg-black/50" @click="closeModal" />

        <!-- Modal Content -->
        <div class="relative w-full max-w-lg mx-4 bg-card border border-border rounded-lg shadow-xl max-h-[90vh] overflow-y-auto">
          <!-- Header -->
          <div class="flex items-center justify-between px-6 py-4 border-b border-border">
            <h3 class="text-lg font-semibold text-foreground">Send Feedback</h3>
            <button
              @click="closeModal"
              class="text-muted-foreground hover:text-foreground focus:outline-none"
              aria-label="Close"
            >
              <X class="h-5 w-5" />
            </button>
          </div>

          <!-- Body -->
          <form @submit.prevent="handleSubmit" class="px-6 py-4 space-y-4">
            <!-- Voice Transcription Display -->
            <div v-if="hasAudio" class="rounded-md bg-blue-50 border border-blue-100 p-3">
              <div class="flex items-center gap-2 mb-1">
                <svg class="w-4 h-4 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-14 0m7 7v4m-4 0h8m-4-16a3 3 0 00-3 3v4a3 3 0 006 0V6a3 3 0 00-3-3z" />
                </svg>
                <span class="text-sm font-medium text-blue-700">Voice Recording</span>
                <span v-if="audioDurationMs" class="text-xs text-gray-500">{{ Math.round(audioDurationMs / 1000) }}s</span>
              </div>
              <p class="text-sm text-gray-700">Voice recording attached. Transcription will be processed after submission.</p>
            </div>

            <!-- Feedback Type -->
            <div>
              <label for="feedback-type" class="block text-sm font-medium text-foreground mb-1">Type <span class="text-destructive">*</span></label>
              <select
                id="feedback-type"
                v-model="feedbackType"
                @change="handleTypeChange"
                class="block w-full rounded-md border-input shadow-sm focus:border-primary focus:ring-ring sm:text-sm"
                required
              >
                <option value="">Please select...</option>
                <option value="bug">Bug Report</option>
                <option value="idea">Feature Idea</option>
                <option value="suggestion">Suggestion</option>
                <option value="general">General Feedback</option>
              </select>
            </div>

            <!-- Severity (shown for bug/idea/suggestion) -->
            <div v-if="showSeverity">
              <label class="block text-sm font-medium text-foreground mb-2">
                {{ feedbackType === 'bug' ? 'How severe?' : 'How important?' }}
                <span class="text-destructive">*</span>
              </label>
              <div class="flex gap-3">
                <label v-for="opt in severityOptions" :key="opt.value" class="flex-1 cursor-pointer">
                  <input type="radio" v-model="severity" :value="opt.value" class="sr-only peer">
                  <div :class="[
                    'text-center px-3 py-2 border rounded-md text-sm transition-colors hover:bg-muted',
                    severity === opt.value ? opt.activeClass : 'border-input'
                  ]">
                    {{ opt.label }}
                  </div>
                </label>
              </div>
            </div>

            <!-- Subject -->
            <div>
              <label for="feedback-subject" class="block text-sm font-medium text-foreground mb-1">Subject <span class="text-muted-foreground text-xs">(optional)</span></label>
              <input
                id="feedback-subject"
                v-model="subject"
                type="text"
                maxlength="200"
                placeholder="Brief summary"
                class="block w-full rounded-md border-input shadow-sm focus:border-primary focus:ring-ring sm:text-sm"
              />
            </div>

            <!-- Message -->
            <div>
              <label for="feedback-message" class="block text-sm font-medium text-foreground mb-1">
                Message
                <span v-if="!hasAudio" class="text-destructive">*</span>
                <span v-else class="text-muted-foreground text-xs">(optional with voice)</span>
              </label>
              <textarea
                id="feedback-message"
                v-model="message"
                rows="4"
                placeholder="Tell us what's on your mind..."
                class="block w-full rounded-md border-input shadow-sm focus:border-primary focus:ring-ring sm:text-sm"
                :required="!hasAudio"
              ></textarea>
            </div>

            <!-- Bug-Specific Fields -->
            <template v-if="feedbackType === 'bug'">
              <div>
                <label for="feedback-expected" class="block text-sm font-medium text-foreground mb-1">Expected Behaviour</label>
                <textarea
                  id="feedback-expected"
                  v-model="expectedBehaviour"
                  rows="2"
                  maxlength="500"
                  placeholder="What did you expect to happen?"
                  class="block w-full rounded-md border-input shadow-sm focus:border-primary focus:ring-ring sm:text-sm"
                ></textarea>
              </div>
              <div>
                <label for="feedback-actual" class="block text-sm font-medium text-foreground mb-1">Actual Behaviour</label>
                <textarea
                  id="feedback-actual"
                  v-model="actualBehaviour"
                  rows="2"
                  maxlength="500"
                  placeholder="What actually happened?"
                  class="block w-full rounded-md border-input shadow-sm focus:border-primary focus:ring-ring sm:text-sm"
                ></textarea>
              </div>
              <div>
                <label for="feedback-frequency" class="block text-sm font-medium text-foreground mb-1">Frequency</label>
                <select
                  id="feedback-frequency"
                  v-model="frequency"
                  class="block w-full rounded-md border-input shadow-sm focus:border-primary focus:ring-ring sm:text-sm"
                >
                  <option value="">Select frequency...</option>
                  <option value="always">Always</option>
                  <option value="sometimes">Sometimes</option>
                  <option value="once">Once</option>
                </select>
              </div>
            </template>

            <!-- Screenshot Preview -->
            <div v-if="screenshotDataUrl" class="relative">
              <label class="block text-sm font-medium text-foreground mb-1">Screenshot</label>
              <div class="relative inline-block">
                <img :src="screenshotDataUrl" class="max-h-32 rounded-md border border-border shadow-sm" alt="Page screenshot">
                <button
                  type="button"
                  @click="clearScreenshot"
                  class="absolute -top-2 -right-2 bg-destructive text-destructive-foreground rounded-full w-5 h-5 flex items-center justify-center text-xs hover:opacity-80"
                  title="Remove screenshot"
                >
                  <X class="w-3 h-3" />
                </button>
              </div>
            </div>

            <!-- Contact Email -->
            <div>
              <label for="feedback-email" class="block text-sm font-medium text-foreground mb-1">
                Contact Email <span class="text-muted-foreground text-xs">(optional)</span>
              </label>
              <input
                id="feedback-email"
                v-model="contactEmail"
                type="email"
                placeholder="your.email@example.com"
                class="block w-full rounded-md border-input shadow-sm focus:border-primary focus:ring-ring sm:text-sm"
              />
            </div>

            <!-- Success Message -->
            <div
              v-if="successMessage"
              class="rounded-md bg-success/10 border border-success/20 p-3 text-sm text-success"
            >
              {{ successMessage }}
            </div>

            <!-- Error Message -->
            <div
              v-if="errorMessage"
              class="rounded-md bg-destructive/10 border border-destructive/20 p-3 text-sm text-destructive"
            >
              {{ errorMessage }}
            </div>
          </form>

          <!-- Footer -->
          <div class="flex justify-end gap-2 px-6 py-4 border-t border-border">
            <button
              type="button"
              @click="closeModal"
              class="inline-flex items-center justify-center rounded-md border border-border bg-card px-4 py-2 text-sm font-medium text-foreground hover:bg-muted focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
            >
              Cancel
            </button>
            <button
              type="button"
              @click="handleSubmit"
              :disabled="isSubmitting || (!message.trim() && !hasAudio)"
              class="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
              data-testid="submit-feedback-btn"
            >
              <Loader2 v-if="isSubmitting" class="h-4 w-4 mr-2 animate-spin" />
              {{ isSubmitting ? 'Sending...' : 'Send Feedback' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { MessageSquarePlus, X, Loader2 } from 'lucide-vue-next';
import apiClient from '../../api/client';

// --- State ---
const isOpen = ref(false);
const feedbackType = ref('');
const subject = ref('');
const message = ref('');
const severity = ref('');
const expectedBehaviour = ref('');
const actualBehaviour = ref('');
const frequency = ref('');
const contactEmail = ref('');
const isSubmitting = ref(false);
const successMessage = ref('');
const errorMessage = ref('');

// Voice
const voiceSupported = ref(false);
const isRecording = ref(false);
const audioBlob = ref<Blob | null>(null);
const audioDurationMs = ref(0);
const voiceRecorder = ref<any>(null);
const recordingElapsedMs = ref(0);
let recordingTimerInterval: ReturnType<typeof setInterval> | null = null;

// Screenshot
const screenshotBlob = ref<Blob | null>(null);
const screenshotDataUrl = ref<string | null>(null);

// --- Computed ---
const hasAudio = computed(() => !!audioBlob.value);
const showSeverity = computed(() => ['bug', 'idea', 'suggestion'].includes(feedbackType.value));

const fabTitle = computed(() => {
  if (isRecording.value) return 'Stop recording';
  if (voiceSupported.value) return 'Tap to record voice feedback';
  return 'Send feedback';
});

const recordingTimeDisplay = computed(() => {
  const seconds = Math.floor(recordingElapsedMs.value / 1000);
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${String(secs).padStart(2, '0')}`;
});

const severityOptions = [
  { value: 'must_have', label: 'Must Have', activeClass: 'border-red-500 bg-red-50 text-red-700' },
  { value: 'should_have', label: 'Should Have', activeClass: 'border-yellow-500 bg-yellow-50 text-yellow-700' },
  { value: 'nice_to_have', label: 'Nice to Have', activeClass: 'border-green-500 bg-green-50 text-green-700' },
];

// --- Lifecycle ---
onMounted(() => {
  // Check voice support - VoiceRecorder is loaded globally from static/js/voice-recorder.js
  voiceSupported.value = !!(
    (window as any).VoiceRecorder &&
    (window as any).VoiceRecorder.isSupported()
  );

  // Preload html2canvas
  if ((window as any).ScreenshotCapture?.isSupported()) {
    (window as any).ScreenshotCapture.preload();
  }
});

onUnmounted(() => {
  stopRecordingTimer();
  if (voiceRecorder.value) {
    voiceRecorder.value.cancel();
  }
});

// --- Methods ---

function resetForm() {
  feedbackType.value = '';
  subject.value = '';
  message.value = '';
  severity.value = '';
  expectedBehaviour.value = '';
  actualBehaviour.value = '';
  frequency.value = '';
  contactEmail.value = '';
  successMessage.value = '';
  errorMessage.value = '';
}

function closeModal() {
  isOpen.value = false;
  clearAudio();
  clearScreenshot();
}

function handleTypeChange() {
  // Reset severity when type changes
  severity.value = '';
}

// --- FAB two-tap logic ---

async function handleFabTap() {
  if (!voiceSupported.value) {
    openTextOnlyModal();
    return;
  }

  if (isRecording.value) {
    await stopRecordingAndOpenModal();
  } else {
    await startVoiceFlow();
  }
}

async function startVoiceFlow() {
  // Capture screenshot BEFORE any UI changes
  await captureScreenshot();

  const VoiceRecorderClass = (window as any).VoiceRecorder;
  if (!VoiceRecorderClass) {
    openTextOnlyModal();
    return;
  }

  voiceRecorder.value = new VoiceRecorderClass({
    maxDurationMs: 30000,
    onStateChange: (state: string) => {
      isRecording.value = state === 'recording';
      if (state === 'completed') {
        onAutoStop();
      }
    },
    onError: () => {
      isRecording.value = false;
      stopRecordingTimer();
      openTextOnlyModal();
    },
  });

  try {
    await voiceRecorder.value.start();
    startRecordingTimer();
  } catch {
    openTextOnlyModal();
  }
}

async function stopRecordingAndOpenModal() {
  stopRecordingTimer();

  if (!voiceRecorder.value) return;

  try {
    const result = await voiceRecorder.value.stop();
    if (result) {
      audioBlob.value = result.blob;
      audioDurationMs.value = result.durationMs;
    }
  } catch {
    // Fall through to open modal without audio
  }

  isRecording.value = false;
  openModalWithVoice();
}

function onAutoStop() {
  stopRecordingTimer();
  if (voiceRecorder.value) {
    audioBlob.value = voiceRecorder.value.getBlob();
    audioDurationMs.value = voiceRecorder.value.durationMs;
  }
  isRecording.value = false;
  openModalWithVoice();
}

function openModalWithVoice() {
  resetForm();
  isOpen.value = true;
}

async function openTextOnlyModal() {
  if (!screenshotBlob.value) {
    await captureScreenshot();
  }
  resetForm();
  isOpen.value = true;
}

// --- Recording timer ---

function startRecordingTimer() {
  stopRecordingTimer();
  recordingElapsedMs.value = 0;
  recordingTimerInterval = setInterval(() => {
    if (voiceRecorder.value) {
      recordingElapsedMs.value = voiceRecorder.value.getElapsedMs();
    }
  }, 500);
}

function stopRecordingTimer() {
  if (recordingTimerInterval) {
    clearInterval(recordingTimerInterval);
    recordingTimerInterval = null;
  }
}

// --- Screenshot ---

async function captureScreenshot() {
  const ScreenshotCaptureClass = (window as any).ScreenshotCapture;
  if (!ScreenshotCaptureClass?.isSupported()) return;

  try {
    const result = await ScreenshotCaptureClass.capture();
    screenshotBlob.value = result.blob;
    screenshotDataUrl.value = result.dataUrl;
  } catch {
    // Silent fail - screenshot is optional
  }
}

function clearScreenshot() {
  screenshotBlob.value = null;
  screenshotDataUrl.value = null;
}

function clearAudio() {
  if (voiceRecorder.value) {
    voiceRecorder.value.cancel();
    voiceRecorder.value = null;
  }
  audioBlob.value = null;
  audioDurationMs.value = 0;
}

// --- Form submission ---

async function handleSubmit() {
  if (isSubmitting.value) return;
  if (!message.value.trim() && !hasAudio.value) return;
  if (!feedbackType.value) {
    errorMessage.value = 'Please select a feedback type.';
    return;
  }

  // Bug type requires severity
  if (feedbackType.value === 'bug' && !severity.value) {
    errorMessage.value = 'Please select a severity level for bug reports.';
    return;
  }

  isSubmitting.value = true;
  errorMessage.value = '';
  successMessage.value = '';

  try {
    const formData = new FormData();
    formData.append('feedback_type', feedbackType.value);
    formData.append('subject', subject.value);
    formData.append('message', message.value);
    formData.append('page_path', window.location.pathname + window.location.search);
    formData.append('page_title', document.title);

    if (severity.value) {
      formData.append('severity', severity.value);
    }
    if (expectedBehaviour.value) {
      formData.append('expected_behaviour', expectedBehaviour.value);
    }
    if (actualBehaviour.value) {
      formData.append('actual_behaviour', actualBehaviour.value);
    }
    if (frequency.value) {
      formData.append('frequency', frequency.value);
    }
    if (contactEmail.value) {
      formData.append('contact_email', contactEmail.value);
    }

    // Audio file
    if (audioBlob.value) {
      formData.append('audio_file', audioBlob.value, 'voice-feedback.webm');
      formData.append('audio_duration_ms', String(audioDurationMs.value));
    }

    // Screenshot
    if (screenshotBlob.value) {
      formData.append('screenshot', screenshotBlob.value, 'screenshot.png');
    }

    // Interaction context from global ContextTracker
    const tracker = (window as any).contextTracker;
    if (tracker) {
      formData.append('interaction_context', JSON.stringify(tracker.getContext()));
    }

    // Technical info
    formData.append('screen_resolution', `${screen.width}x${screen.height}`);
    formData.append('viewport_size', `${window.innerWidth}x${window.innerHeight}`);
    formData.append('user_agent', navigator.userAgent);

    await apiClient.post('/feedback/submit/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });

    successMessage.value = 'Thank you for your feedback!';
    setTimeout(() => {
      closeModal();
      resetForm();
    }, 1500);
  } catch {
    errorMessage.value = 'Failed to send feedback. Please try again.';
  } finally {
    isSubmitting.value = false;
  }
}
</script>
