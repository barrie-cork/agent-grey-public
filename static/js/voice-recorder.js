/**
 * VoiceRecorder - MediaRecorder API wrapper for voice-first feedback
 * State machine: idle -> recording -> processing -> completed/error
 */
class VoiceRecorder {
    constructor(options = {}) {
        this.maxDurationMs = options.maxDurationMs || 30000;
        this.mediaRecorder = null;
        this.mediaStream = null;
        this.audioChunks = [];
        this.startTime = null;
        this.durationMs = 0;
        this.state = 'idle';
        this.onStateChange = options.onStateChange || (() => {});
        this.onError = options.onError || (() => {});
        this.autoStopTimer = null;
        this._stopPromiseResolve = null;
    }

    _setState(newState) {
        this.state = newState;
        this.onStateChange(newState);
    }

    async checkPermission() {
        if (!VoiceRecorder.isSupported()) {
            return 'unsupported';
        }
        try {
            const result = await navigator.permissions.query({ name: 'microphone' });
            return result.state; // 'granted', 'denied', 'prompt'
        } catch {
            // permissions.query not supported for microphone in some browsers
            return 'prompt';
        }
    }

    async start() {
        if (this.state === 'recording') return;

        try {
            this.audioChunks = [];
            this.durationMs = 0;

            this.mediaStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                },
            });

            // Determine best MIME type
            const mimeType = this._selectMimeType();

            const recorderOptions = {};
            if (mimeType) {
                recorderOptions.mimeType = mimeType;
            }

            this.mediaRecorder = new MediaRecorder(this.mediaStream, recorderOptions);

            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                }
            };

            this.mediaRecorder.onstop = () => {
                this.durationMs = Date.now() - this.startTime;
                this._releaseStream();

                if (this._stopPromiseResolve) {
                    const blob = this.getBlob();
                    this._stopPromiseResolve({ blob, durationMs: this.durationMs });
                    this._stopPromiseResolve = null;
                }
            };

            this.mediaRecorder.onerror = (event) => {
                this._setState('error');
                this.onError(event.error || new Error('Recording failed'));
                this._releaseStream();
            };

            this.startTime = Date.now();
            this.mediaRecorder.start(1000); // Collect data every second
            this._setState('recording');

            // Auto-stop after max duration
            this.autoStopTimer = setTimeout(() => {
                if (this.state === 'recording') {
                    this.stop();
                }
            }, this.maxDurationMs);

        } catch (err) {
            this._setState('error');
            this.onError(err);
            this._releaseStream();
            throw err;
        }
    }

    stop() {
        if (this.state !== 'recording' || !this.mediaRecorder) {
            return Promise.resolve(null);
        }

        if (this.autoStopTimer) {
            clearTimeout(this.autoStopTimer);
            this.autoStopTimer = null;
        }

        this._setState('processing');

        return new Promise((resolve) => {
            this._stopPromiseResolve = resolve;
            this.mediaRecorder.stop();
        }).then((result) => {
            this._setState('completed');
            return result;
        });
    }

    cancel() {
        if (this.autoStopTimer) {
            clearTimeout(this.autoStopTimer);
            this.autoStopTimer = null;
        }

        if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
            this._stopPromiseResolve = null;
            this.mediaRecorder.stop();
        }

        this._releaseStream();
        this.audioChunks = [];
        this.durationMs = 0;
        this._setState('idle');
    }

    getBlob() {
        if (this.audioChunks.length === 0) return null;
        const mimeType = this.mediaRecorder?.mimeType || 'audio/webm';
        return new Blob(this.audioChunks, { type: mimeType });
    }

    getElapsedMs() {
        if (this.state === 'recording' && this.startTime) {
            return Date.now() - this.startTime;
        }
        return this.durationMs;
    }

    _selectMimeType() {
        const preferred = [
            'audio/webm;codecs=opus',
            'audio/webm',
            'audio/ogg;codecs=opus',
            'audio/mp4',
        ];
        for (const type of preferred) {
            if (MediaRecorder.isTypeSupported(type)) {
                return type;
            }
        }
        return ''; // Let browser choose default
    }

    _releaseStream() {
        if (this.mediaStream) {
            this.mediaStream.getTracks().forEach(track => track.stop());
            this.mediaStream = null;
        }
    }

    static isSupported() {
        return !!(
            navigator.mediaDevices &&
            navigator.mediaDevices.getUserMedia &&
            window.MediaRecorder
        );
    }
}

// Export for both module and global contexts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = VoiceRecorder;
}
