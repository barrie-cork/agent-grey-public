/**
 * ScreenshotCapture - html2canvas wrapper for feedback screenshots
 * Lazily loads html2canvas from CDN on first use
 */
class ScreenshotCapture {
    static _html2canvasLoaded = false;
    static _loadPromise = null;
    static CDN_URL = 'https://html2canvas.hertzen.com/dist/html2canvas.min.js';

    /**
     * Lazily load html2canvas from CDN
     */
    static _loadHtml2Canvas() {
        if (window.html2canvas) {
            ScreenshotCapture._html2canvasLoaded = true;
            return Promise.resolve();
        }

        if (ScreenshotCapture._loadPromise) {
            return ScreenshotCapture._loadPromise;
        }

        ScreenshotCapture._loadPromise = new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = ScreenshotCapture.CDN_URL;
            script.async = true;
            script.onload = () => {
                ScreenshotCapture._html2canvasLoaded = true;
                resolve();
            };
            script.onerror = () => {
                ScreenshotCapture._loadPromise = null;
                reject(new Error('Failed to load html2canvas'));
            };
            document.head.appendChild(script);
        });

        return ScreenshotCapture._loadPromise;
    }

    /**
     * Capture the current page as a screenshot
     * @param {Object} options - Capture options
     * @returns {Promise<{blob: Blob, dataUrl: string}>}
     */
    static async capture(options = {}) {
        await ScreenshotCapture._loadHtml2Canvas();

        const canvas = await window.html2canvas(document.body, {
            ignoreElements: (element) => {
                // Exclude feedback UI elements from screenshot
                if (element.hasAttribute('data-no-screenshot')) return true;
                if (element.id === 'feedbackBtn') return true;
                if (element.id === 'feedbackModal') return true;
                if (element.id === 'feedbackToast') return true;
                if (element.id === 'feedbackRecordingIndicator') return true;
                if (element.classList && element.classList.contains('no-screenshot')) return true;
                return false;
            },
            scale: 1,
            useCORS: true,
            logging: false,
            backgroundColor: '#ffffff',
            ...options,
        });

        return new Promise((resolve, reject) => {
            canvas.toBlob(
                (blob) => {
                    if (!blob) {
                        reject(new Error('Failed to create screenshot blob'));
                        return;
                    }
                    const dataUrl = canvas.toDataURL('image/png', 0.8);
                    resolve({ blob, dataUrl });
                },
                'image/png',
                0.8
            );
        });
    }

    /**
     * Pre-load html2canvas (call this early to avoid delay on first capture)
     */
    static preload() {
        ScreenshotCapture._loadHtml2Canvas().catch(() => {
            // Silent fail on preload - will retry on capture
        });
    }

    static isSupported() {
        return typeof document.createElement('canvas').getContext === 'function';
    }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = ScreenshotCapture;
}
