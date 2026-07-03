/**
 * Feedback System JavaScript
 * Voice-first two-tap FAB: tap to record, tap to stop and open modal
 * Uses vanilla JS for modal and toast (no Bootstrap dependencies)
 */

(function() {
    'use strict';

    /**
     * VanillaModal - Simple modal implementation without Bootstrap
     * Supports static backdrop, keyboard dismissal, and focus trapping
     */
    class VanillaModal {
        constructor(element, options = {}) {
            this.element = element;
            this.options = {
                backdrop: options.backdrop || true,
                keyboard: options.keyboard !== false,
                ...options
            };
            this.isOpen = false;
            this.previousActiveElement = null;

            this._bindEvents();
        }

        _bindEvents() {
            const backdrop = this.element.querySelector('[data-modal-backdrop]');
            if (backdrop && this.options.backdrop !== 'static') {
                backdrop.addEventListener('click', () => this.hide());
            }

            const closeButtons = this.element.querySelectorAll('[data-modal-close]');
            closeButtons.forEach(btn => {
                btn.addEventListener('click', () => this.hide());
            });

            this.element.addEventListener('keydown', (e) => this._handleKeydown(e));
        }

        _handleKeydown(e) {
            if (!this.isOpen) return;

            if (e.key === 'Escape' && this.options.keyboard) {
                e.preventDefault();
                this.hide();
                return;
            }

            if (e.key === 'Tab') {
                this._handleTabKey(e);
            }
        }

        _handleTabKey(e) {
            const focusable = this.element.querySelectorAll(
                'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
            );
            const focusableArray = Array.from(focusable);

            if (focusableArray.length === 0) return;

            const firstFocusable = focusableArray[0];
            const lastFocusable = focusableArray[focusableArray.length - 1];

            if (e.shiftKey) {
                if (document.activeElement === firstFocusable) {
                    e.preventDefault();
                    lastFocusable.focus();
                }
            } else {
                if (document.activeElement === lastFocusable) {
                    e.preventDefault();
                    firstFocusable.focus();
                }
            }
        }

        show() {
            if (this.isOpen) return;

            this.previousActiveElement = document.activeElement;

            this.element.classList.remove('hidden');
            this.element.setAttribute('aria-hidden', 'false');
            this.isOpen = true;

            document.body.style.overflow = 'hidden';

            requestAnimationFrame(() => {
                const firstFocusable = this.element.querySelector(
                    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
                );
                if (firstFocusable) {
                    firstFocusable.focus();
                }
            });

            this.element.dispatchEvent(new CustomEvent('modal:shown'));
        }

        hide() {
            if (!this.isOpen) return;

            this.element.classList.add('hidden');
            this.element.setAttribute('aria-hidden', 'true');
            this.isOpen = false;

            document.body.style.overflow = '';

            if (this.previousActiveElement) {
                this.previousActiveElement.focus();
            }

            this.element.dispatchEvent(new CustomEvent('modal:hidden'));
        }
    }

    /**
     * VanillaToast - Simple toast notification without Bootstrap
     */
    class VanillaToast {
        constructor(element, options = {}) {
            this.element = element;
            this.options = {
                autohide: options.autohide !== false,
                delay: options.delay || 5000,
                ...options
            };
            this.hideTimeout = null;

            this._bindEvents();
        }

        _bindEvents() {
            const closeButton = this.element.querySelector('[data-toast-close]');
            if (closeButton) {
                closeButton.addEventListener('click', () => this.hide());
            }
        }

        show() {
            if (this.hideTimeout) {
                clearTimeout(this.hideTimeout);
            }

            this.element.classList.remove('hidden');
            this.element.setAttribute('aria-live', 'assertive');
            this.element.setAttribute('aria-atomic', 'true');

            if (this.options.autohide) {
                this.hideTimeout = setTimeout(() => this.hide(), this.options.delay);
            }

            this.element.dispatchEvent(new CustomEvent('toast:shown'));
        }

        hide() {
            if (this.hideTimeout) {
                clearTimeout(this.hideTimeout);
                this.hideTimeout = null;
            }

            this.element.classList.add('hidden');
            this.element.removeAttribute('aria-live');
            this.element.removeAttribute('aria-atomic');

            this.element.dispatchEvent(new CustomEvent('toast:hidden'));
        }

        setMessage(message) {
            const bodyEl = this.element.querySelector('.toast-body') ||
                          this.element.querySelector('[class*="py-3"]:last-child');
            if (bodyEl) {
                bodyEl.textContent = message;
            }
        }
    }

    // SVG icons used in the FAB
    const ICONS = {
        mic: '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-14 0m7 7v4m-4 0h8m-4-16a3 3 0 00-3 3v4a3 3 0 006 0V6a3 3 0 00-3-3z"></path></svg>',
        stop: '<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="1"></rect></svg>',
        chat: '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"></path></svg>',
    };

    // Global feedback object
    window.FeedbackSystem = {
        modal: null,
        toast: null,
        form: null,
        isSubmitting: false,
        voiceRecorder: null,
        screenshotBlob: null,
        screenshotDataUrl: null,
        audioResult: null,
        recordingTimerInterval: null,
        voiceSupported: false,
        _isStartingRecording: false,
        _manualStop: false,

        init: function() {
            this.voiceSupported = (typeof VoiceRecorder !== 'undefined') && VoiceRecorder.isSupported();
            this.setupElements();
            this.bindEvents();
            this.setupPageContext();
            this._updateFabState();

            // Preload html2canvas
            if (typeof ScreenshotCapture !== 'undefined' && ScreenshotCapture.isSupported()) {
                ScreenshotCapture.preload();
            }
        },

        setupElements: function() {
            const modalEl = document.getElementById('feedbackModal');
            if (modalEl) {
                this.modal = new VanillaModal(modalEl, {
                    backdrop: 'static',
                    keyboard: true
                });

                // Clean up on modal close
                modalEl.addEventListener('modal:hidden', () => {
                    this._clearScreenshot();
                    this._clearAudio();
                });
            }

            const toastEl = document.getElementById('feedbackToast');
            if (toastEl) {
                this.toast = new VanillaToast(toastEl, {
                    autohide: true,
                    delay: 5000
                });
            }

            this.form = document.getElementById('feedbackForm');
        },

        bindEvents: function() {
            const feedbackBtn = document.getElementById('feedbackBtn');
            if (feedbackBtn) {
                feedbackBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    this._handleFabTap();
                });

                // Alt+click or long-press opens text-only modal
                feedbackBtn.addEventListener('contextmenu', (e) => {
                    e.preventDefault();
                    this._openTextOnlyModal();
                });
            }

            if (this.form) {
                this.form.addEventListener('submit', this.handleSubmit.bind(this));
            }

            const messageField = document.getElementById('feedbackMessage');
            if (messageField) {
                messageField.addEventListener('input', this.updateCharacterCount);
            }

            this.setupStarRating();

            const typeField = document.getElementById('feedbackType');
            if (typeField) {
                typeField.addEventListener('change', this.handleTypeChange.bind(this));
            }

            // Screenshot remove button
            const removeScreenshotBtn = document.getElementById('removeScreenshotBtn');
            if (removeScreenshotBtn) {
                removeScreenshotBtn.addEventListener('click', () => this._clearScreenshot());
            }
        },

        // --- FAB two-tap logic ---

        _handleFabTap: function() {
            if (!this.voiceSupported) {
                this._openTextOnlyModal();
                return;
            }

            if (this.voiceRecorder && this.voiceRecorder.state === 'recording') {
                // Second tap: stop recording and open modal
                this._stopRecordingAndOpenModal();
            } else if (!this._isStartingRecording) {
                // First tap: capture screenshot then start recording
                this._startVoiceFlow();
            }
        },

        _startVoiceFlow: async function() {
            this._isStartingRecording = true;

            // Capture screenshot BEFORE any UI changes
            try {
                if (typeof ScreenshotCapture !== 'undefined' && ScreenshotCapture.isSupported()) {
                    const result = await ScreenshotCapture.capture();
                    this.screenshotBlob = result.blob;
                    this.screenshotDataUrl = result.dataUrl;
                }
            } catch (err) {
                console.warn('Screenshot capture failed:', err);
            }

            // Create recorder with state change callback
            this.voiceRecorder = new VoiceRecorder({
                maxDurationMs: 30000,
                onStateChange: (state) => {
                    this._updateFabState();
                    if (state === 'completed' && !this._manualStop) {
                        // Auto-stop triggered (30s limit)
                        this._onRecordingComplete();
                    }
                },
                onError: (err) => {
                    console.error('Voice recording error:', err);
                    this._hideRecordingIndicator();
                    this._updateFabState();
                },
            });

            try {
                await this.voiceRecorder.start();
                this._showRecordingIndicator();
            } catch (err) {
                console.warn('Could not start recording:', err);
                this._hideRecordingIndicator();
                this._openTextOnlyModal();
            } finally {
                this._isStartingRecording = false;
            }
        },

        _stopRecordingAndOpenModal: async function() {
            if (!this.voiceRecorder) return;

            this._manualStop = true;
            this._hideRecordingIndicator();

            try {
                this.audioResult = await this.voiceRecorder.stop();
            } catch (err) {
                console.error('Error stopping recording:', err);
            }

            this._manualStop = false;
            this._openModalWithVoice();
        },

        _onRecordingComplete: function() {
            // Called when auto-stop fires
            this._hideRecordingIndicator();
            if (this.voiceRecorder) {
                this.audioResult = {
                    blob: this.voiceRecorder.getBlob(),
                    durationMs: this.voiceRecorder.durationMs,
                };
            }
            this._openModalWithVoice();
        },

        _openModalWithVoice: function() {
            this.resetForm();
            this.setupPageContext();

            // Show transcription placeholder while we transcribe
            const transcriptionArea = document.getElementById('feedbackTranscription');
            if (transcriptionArea && this.audioResult?.blob) {
                transcriptionArea.closest('.feedback-transcription-section')?.classList.remove('hidden');
                transcriptionArea.textContent = 'Transcribing your voice recording...';
            }

            // Show audio duration
            const durationDisplay = document.getElementById('feedbackAudioDuration');
            if (durationDisplay && this.audioResult?.durationMs) {
                const seconds = Math.round(this.audioResult.durationMs / 1000);
                durationDisplay.textContent = `${seconds}s recorded`;
                durationDisplay.classList.remove('hidden');
            }

            // Show screenshot preview
            this._showScreenshotPreview();

            if (this.modal) {
                this.modal.show();
            }

            this.trackEvent('feedback_modal_opened', { mode: 'voice' });

            // Immediately transcribe the audio
            if (this.audioResult?.blob) {
                this._transcribeAudio(this.audioResult.blob);
            }
        },

        _transcribeAudio: function(audioBlob) {
            const formData = new FormData();
            formData.append('audio_file', audioBlob, 'voice-feedback.webm');

            const transcriptionArea = document.getElementById('feedbackTranscription');

            fetch('/feedback/transcribe/', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': this.getCSRFToken(),
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success && data.text) {
                    // Fill the message textarea with transcription
                    const messageField = document.getElementById('feedbackMessage');
                    if (messageField) {
                        messageField.value = data.text;
                        this.updateCharacterCount();
                    }
                    if (transcriptionArea) {
                        transcriptionArea.textContent = data.text;
                    }
                    // Mark as pre-transcribed so submission skips Celery task
                    this._preTranscribed = true;
                } else {
                    // Fallback: keep the recording, transcription will happen after submission
                    if (transcriptionArea) {
                        transcriptionArea.textContent = 'Voice recording attached. Transcription will be processed after submission.';
                    }
                    this._preTranscribed = false;
                }
            })
            .catch(() => {
                // Fallback on network error
                if (transcriptionArea) {
                    transcriptionArea.textContent = 'Voice recording attached. Transcription will be processed after submission.';
                }
                this._preTranscribed = false;
            });
        },

        _openTextOnlyModal: function() {
            // Capture screenshot before opening
            if (typeof ScreenshotCapture !== 'undefined' && ScreenshotCapture.isSupported() && !this.screenshotBlob) {
                ScreenshotCapture.capture().then((result) => {
                    this.screenshotBlob = result.blob;
                    this.screenshotDataUrl = result.dataUrl;
                    this._showScreenshotPreview();
                }).catch(() => {});
            }

            this.resetForm();
            this.setupPageContext();
            this._showScreenshotPreview();

            if (this.modal) {
                this.modal.show();
            }

            setTimeout(() => {
                const firstField = document.getElementById('feedbackType');
                if (firstField) firstField.focus();
            }, 100);

            this.trackEvent('feedback_modal_opened', { mode: 'text' });
        },

        // --- Recording indicator ---

        _showRecordingIndicator: function() {
            let indicator = document.getElementById('feedbackRecordingIndicator');
            if (!indicator) {
                indicator = document.createElement('div');
                indicator.id = 'feedbackRecordingIndicator';
                indicator.setAttribute('data-no-screenshot', '');
                indicator.className = 'fixed bottom-20 right-6 z-50 hidden items-center gap-2 bg-white border border-red-200 rounded-full px-4 py-2 shadow-lg';
                indicator.innerHTML = `
                    <span class="inline-block w-3 h-3 bg-red-500 rounded-full animate-pulse"></span>
                    <span class="text-sm font-medium text-gray-700">Recording... <span id="feedbackRecordingTimer">0:00</span> / 0:30</span>
                `;
                document.body.appendChild(indicator);
            } else {
                // Reset timer text when reusing existing indicator
                const timerEl = document.getElementById('feedbackRecordingTimer');
                if (timerEl) {
                    timerEl.textContent = '0:00';
                }
            }
            // Toggle flex/hidden (Tailwind: flex overrides hidden in source order)
            indicator.classList.remove('hidden');
            indicator.classList.add('flex');

            // Start timer
            this._startRecordingTimer();
        },

        _hideRecordingIndicator: function() {
            this._stopRecordingTimer();
            const indicator = document.getElementById('feedbackRecordingIndicator');
            if (indicator) {
                indicator.classList.add('hidden');
                indicator.classList.remove('flex');
            }
        },

        _startRecordingTimer: function() {
            this._stopRecordingTimer();
            this.recordingTimerInterval = setInterval(() => {
                if (!this.voiceRecorder || this.voiceRecorder.state !== 'recording') {
                    this._stopRecordingTimer();
                    return;
                }
                const elapsed = this.voiceRecorder.getElapsedMs();
                const seconds = Math.floor(elapsed / 1000);
                const mins = Math.floor(seconds / 60);
                const secs = seconds % 60;
                const timerEl = document.getElementById('feedbackRecordingTimer');
                if (timerEl) {
                    timerEl.textContent = `${mins}:${String(secs).padStart(2, '0')}`;
                }
            }, 500);
        },

        _stopRecordingTimer: function() {
            if (this.recordingTimerInterval) {
                clearInterval(this.recordingTimerInterval);
                this.recordingTimerInterval = null;
            }
        },

        // --- FAB state management ---

        _updateFabState: function() {
            const feedbackBtn = document.getElementById('feedbackBtn');
            if (!feedbackBtn) return;

            const isRecording = this.voiceRecorder && this.voiceRecorder.state === 'recording';

            if (!this.voiceSupported) {
                // Text-only mode: show chat icon
                feedbackBtn.innerHTML = ICONS.chat + '<span class="feedback-btn-text">Feedback</span>';
                feedbackBtn.classList.remove('feedback-float-btn--recording');
                feedbackBtn.title = 'Share your feedback';
            } else if (isRecording) {
                // Recording state: show stop icon with pulsing red
                feedbackBtn.innerHTML = ICONS.stop + '<span class="feedback-btn-text">Stop</span>';
                feedbackBtn.classList.add('feedback-float-btn--recording');
                feedbackBtn.title = 'Stop recording';
            } else {
                // Idle state: show mic icon
                feedbackBtn.innerHTML = ICONS.mic + '<span class="feedback-btn-text">Feedback</span>';
                feedbackBtn.classList.remove('feedback-float-btn--recording');
                feedbackBtn.title = 'Tap to record voice feedback';
            }
        },

        // --- Screenshot ---

        _showScreenshotPreview: function() {
            const previewContainer = document.getElementById('screenshotPreviewContainer');
            const previewImg = document.getElementById('screenshotPreviewImg');
            if (previewContainer && previewImg && this.screenshotDataUrl) {
                previewImg.src = this.screenshotDataUrl;
                previewContainer.classList.remove('hidden');
            }
        },

        _clearScreenshot: function() {
            this.screenshotBlob = null;
            this.screenshotDataUrl = null;
            const previewContainer = document.getElementById('screenshotPreviewContainer');
            if (previewContainer) {
                previewContainer.classList.add('hidden');
            }
        },

        _clearAudio: function() {
            if (this.voiceRecorder) {
                this.voiceRecorder.cancel();
                this.voiceRecorder = null;
            }
            this.audioResult = null;
            this._preTranscribed = false;
            this._hideRecordingIndicator();
            this._updateFabState();

            const transcriptionSection = document.querySelector('.feedback-transcription-section');
            if (transcriptionSection) {
                transcriptionSection.classList.add('hidden');
            }
            const durationDisplay = document.getElementById('feedbackAudioDuration');
            if (durationDisplay) {
                durationDisplay.classList.add('hidden');
            }
        },

        // --- Page context ---

        setupPageContext: function() {
            const currentPath = window.location.pathname + window.location.search;
            const currentTitle = document.title;

            const pathField = document.getElementById('feedbackPagePath');
            const titleField = document.getElementById('feedbackPageTitle');
            const displayField = document.getElementById('currentPageDisplay');

            if (pathField) pathField.value = currentPath;
            if (titleField) titleField.value = currentTitle;
            if (displayField) {
                displayField.textContent = currentTitle + ' (' + currentPath + ')';
            }
        },

        // --- Form ---

        resetForm: function() {
            if (this.form) {
                this.form.reset();
                this.clearMessages();
                this.updateCharacterCount();
                this.resetSubmitButton();
            }

            // Reset bug-specific fields visibility
            const bugFields = document.getElementById('bugSpecificFields');
            if (bugFields) bugFields.classList.add('hidden');

            // Reset severity section
            const severitySection = document.getElementById('severitySection');
            if (severitySection) severitySection.classList.add('hidden');
        },

        handleSubmit: function(event) {
            event.preventDefault();

            if (this.isSubmitting) return;

            if (!this.validateForm()) {
                return;
            }

            this.submitFeedback();
        },

        validateForm: function() {
            const type = document.getElementById('feedbackType').value;
            const message = document.getElementById('feedbackMessage').value.trim();
            const hasAudio = !!(this.audioResult && this.audioResult.blob);

            this.clearMessages();

            let isValid = true;
            let errors = [];

            if (!type) {
                errors.push('Please select a feedback type.');
                isValid = false;
            }

            // Message is optional if voice recording is present
            if (!hasAudio && (!message || message.length < 10)) {
                errors.push('Please provide a detailed message (at least 10 characters), or use voice recording.');
                isValid = false;
            }

            if (message.length > 2000) {
                errors.push('Message is too long. Please keep it under 2000 characters.');
                isValid = false;
            }

            // Bug type requires severity
            if (type === 'bug') {
                const severity = document.querySelector('input[name="severity"]:checked');
                if (!severity) {
                    errors.push('Please select a severity level for bug reports.');
                    isValid = false;
                }
            }

            if (!isValid) {
                this.showMessage(errors.join(' '), 'danger');
            }

            return isValid;
        },

        submitFeedback: function() {
            this.isSubmitting = true;
            this.setSubmitButtonLoading(true);

            const formData = new FormData(this.form);

            // Add technical information
            this.addTechnicalInfo(formData);

            // Add audio file if present
            if (this.audioResult && this.audioResult.blob) {
                formData.append('audio_file', this.audioResult.blob, 'voice-feedback.webm');
                formData.append('audio_duration_ms', String(this.audioResult.durationMs || 0));
                if (this._preTranscribed) {
                    formData.append('pre_transcribed', 'true');
                }
            }

            // Add screenshot if present
            if (this.screenshotBlob) {
                formData.append('screenshot', this.screenshotBlob, 'screenshot.png');
            }

            // Add interaction context from ContextTracker
            if (window.contextTracker) {
                formData.append('interaction_context', JSON.stringify(window.contextTracker.getContext()));
            }

            const csrfToken = this.getCSRFToken();

            fetch('/feedback/submit/', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': csrfToken,
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(response => response.json())
            .then(data => {
                this.handleSubmissionResponse(data);
            })
            .catch(error => {
                console.error('Feedback submission error:', error);
                this.showMessage('An error occurred while submitting your feedback. Please try again.', 'danger');
            })
            .finally(() => {
                this.isSubmitting = false;
                this.setSubmitButtonLoading(false);
            });
        },

        addTechnicalInfo: function(formData) {
            formData.append('screen_resolution', `${screen.width}x${screen.height}`);
            formData.append('viewport_size', `${window.innerWidth}x${window.innerHeight}`);
            formData.append('user_agent', navigator.userAgent);
            formData.append('timestamp', new Date().toISOString());
        },

        handleSubmissionResponse: function(data) {
            if (data.success) {
                this.showMessage(data.message, 'success');
                this.trackEvent('feedback_submitted', {
                    feedback_id: data.feedback_id,
                    type: document.getElementById('feedbackType').value,
                    has_audio: !!(this.audioResult && this.audioResult.blob),
                    has_screenshot: !!this.screenshotBlob,
                });

                setTimeout(() => {
                    if (this.modal) {
                        this.modal.hide();
                    }
                    this.showToast('Thank you for your feedback!');
                }, 2000);

            } else {
                let errorMessage = data.message || 'Please correct the errors and try again.';

                if (data.errors) {
                    const errorMessages = [];
                    for (const field in data.errors) {
                        errorMessages.push(...data.errors[field]);
                    }
                    if (errorMessages.length > 0) {
                        errorMessage = errorMessages.join(' ');
                    }
                }

                this.showMessage(errorMessage, 'danger');
            }
        },

        // --- UI helpers ---

        showMessage: function(message, type) {
            const container = document.getElementById('feedbackMessages');
            if (!container) return;

            const typeClasses = {
                'danger': 'bg-red-50 border-red-200 text-red-800',
                'success': 'bg-green-50 border-green-200 text-green-800',
                'warning': 'bg-yellow-50 border-yellow-200 text-yellow-800',
                'info': 'bg-blue-50 border-blue-200 text-blue-800'
            };

            const classes = typeClasses[type] || typeClasses['info'];

            container.innerHTML = `
                <div class="rounded-lg border p-4 ${classes}" role="alert">
                    <div class="flex items-start">
                        <div class="flex-1">${message}</div>
                        <button type="button" class="ml-3 text-current opacity-50 hover:opacity-100" onclick="this.parentElement.parentElement.remove()">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                            </svg>
                        </button>
                    </div>
                </div>
            `;
            container.classList.remove('hidden');
        },

        clearMessages: function() {
            const container = document.getElementById('feedbackMessages');
            if (container) {
                container.innerHTML = '';
                container.classList.add('hidden');
            }
        },

        showToast: function(message) {
            if (this.toast) {
                this.toast.setMessage(message);
                this.toast.show();
            }
        },

        updateCharacterCount: function() {
            const messageField = document.getElementById('feedbackMessage');
            const countEl = document.getElementById('messageCharCount');

            if (messageField && countEl) {
                const count = messageField.value.length;
                countEl.textContent = count;

                countEl.classList.remove('text-red-500', 'text-yellow-500', 'text-blue-500');
                if (count > 1800) {
                    countEl.classList.add('text-red-500');
                } else if (count > 1500) {
                    countEl.classList.add('text-yellow-500');
                } else {
                    countEl.classList.add('text-blue-500');
                }
            }
        },

        setupStarRating: function() {
            const starInputs = document.querySelectorAll('.star-rating input[type="radio"]');
            starInputs.forEach(input => {
                input.addEventListener('change', function() {
                    const rating = this.value;
                    const ratingText = document.querySelector('.rating-text small');
                    if (ratingText) {
                        const labels = {
                            '1': 'Poor experience',
                            '2': 'Fair experience',
                            '3': 'Good experience',
                            '4': 'Very good experience',
                            '5': 'Excellent experience'
                        };
                        ratingText.textContent = labels[rating] || 'Click stars to rate your experience';
                    }
                });
            });
        },

        handleTypeChange: function(event) {
            const type = event.target.value;
            const messageField = document.getElementById('feedbackMessage');
            const subjectField = document.getElementById('feedbackSubject');

            const placeholders = {
                'bug': 'Please describe the bug you encountered. What did you expect to happen vs. what actually happened?',
                'idea': 'Please describe your feature idea. How would this help you?',
                'suggestion': 'Please tell us what could be improved and how it would make your experience better.',
                'general': 'Please share your feedback with us.'
            };

            if (messageField && placeholders[type]) {
                messageField.placeholder = placeholders[type];
            }

            const autoSubjects = {
                'bug': 'Bug Report: ',
                'idea': 'Feature Idea: ',
                'suggestion': 'Improvement Suggestion: '
            };

            if (subjectField && autoSubjects[type] && !subjectField.value) {
                subjectField.value = autoSubjects[type];
                setTimeout(() => subjectField.focus(), 100);
            }

            // Toggle bug-specific fields
            const bugFields = document.getElementById('bugSpecificFields');
            if (bugFields) {
                bugFields.classList.toggle('hidden', type !== 'bug');
            }

            // Toggle severity section (shown for bug, idea, suggestion - not general)
            const severitySection = document.getElementById('severitySection');
            if (severitySection) {
                severitySection.classList.toggle('hidden', type === 'general' || type === '');
            }

            // Update severity label
            const severityLabel = document.getElementById('severityLabel');
            if (severityLabel) {
                severityLabel.textContent = type === 'bug' ? 'How severe?' : 'How important?';
            }
        },

        setSubmitButtonLoading: function(loading) {
            const btn = document.getElementById('submitFeedbackBtn');
            if (!btn) return;

            const submitText = btn.querySelector('.submit-text');
            const loadingText = btn.querySelector('.loading-text');

            if (loading) {
                if (submitText) submitText.classList.add('hidden');
                if (loadingText) loadingText.classList.remove('hidden');
                btn.disabled = true;
            } else {
                if (submitText) submitText.classList.remove('hidden');
                if (loadingText) loadingText.classList.add('hidden');
                btn.disabled = false;
            }
        },

        resetSubmitButton: function() {
            this.setSubmitButtonLoading(false);
        },

        getCSRFToken: function() {
            const cookieValue = document.cookie
                .split('; ')
                .find(row => row.startsWith('csrftoken='))
                ?.split('=')[1];

            return cookieValue || '';
        },

        trackEvent: function(eventName, eventData = {}) {
            if (typeof gtag !== 'undefined') {
                gtag('event', eventName, eventData);
            }

            console.log('Feedback Event:', eventName, eventData);
        }
    };

    // Initialize when DOM is ready
    document.addEventListener('DOMContentLoaded', function() {
        if (document.getElementById('feedbackBtn')) {
            window.FeedbackSystem.init();
        }
    });

    // Quick feedback functions
    window.quickFeedback = function(type, rating) {
        const data = {
            feedback_type: type,
            rating: rating,
            page_path: window.location.pathname + window.location.search,
            page_title: document.title
        };

        fetch('/feedback/quick/', {
            method: 'POST',
            body: JSON.stringify(data),
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': window.FeedbackSystem.getCSRFToken(),
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                window.FeedbackSystem.showToast(data.message);
            }
        })
        .catch(error => {
            console.error('Quick feedback error:', error);
        });
    };

})();
