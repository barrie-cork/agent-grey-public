/**
 * ContextTracker - Tracks page visits, clicks, and JS errors throughout a session
 * Persists in sessionStorage for "what happened before this bug" context
 */
class ContextTracker {
    constructor() {
        this.MAX_PAGES = 10;
        this.MAX_CLICKS = 20;
        this.MAX_ERRORS = 5;
        this.STORAGE_KEY = 'ag_context_tracker';

        this.pages = [];
        this.clicks = [];
        this.errors = [];
        this.sessionStart = Date.now();
        this.currentPageEntry = null;

        this._originalPushState = null;
        this._originalReplaceState = null;
    }

    init() {
        this._restoreState();
        this._recordPageVisit(window.location.href, document.title);
        this._monkeyPatchHistory();
        this._bindEventListeners();
    }

    _restoreState() {
        try {
            const stored = sessionStorage.getItem(this.STORAGE_KEY);
            if (stored) {
                const data = JSON.parse(stored);
                this.pages = data.pages || [];
                this.clicks = data.clicks || [];
                this.errors = data.errors || [];
                this.sessionStart = data.sessionStart || Date.now();
            }
        } catch {
            // Corrupted data, start fresh
        }
    }

    _saveState() {
        try {
            sessionStorage.setItem(this.STORAGE_KEY, JSON.stringify({
                pages: this.pages,
                clicks: this.clicks,
                errors: this.errors,
                sessionStart: this.sessionStart,
            }));
        } catch {
            // sessionStorage full or unavailable
        }
    }

    _monkeyPatchHistory() {
        // Patch pushState
        this._originalPushState = history.pushState.bind(history);
        history.pushState = (...args) => {
            this._originalPushState(...args);
            this._recordPageVisit(window.location.href, document.title);
        };

        // Patch replaceState
        this._originalReplaceState = history.replaceState.bind(history);
        history.replaceState = (...args) => {
            this._originalReplaceState(...args);
            this._recordPageVisit(window.location.href, document.title);
        };

        // Listen for back/forward navigation
        window.addEventListener('popstate', () => {
            this._recordPageVisit(window.location.href, document.title);
        });
    }

    _bindEventListeners() {
        // Delegated click listener for interactive elements
        document.addEventListener('click', (event) => {
            this._recordClick(event);
        }, true);

        // JS error tracking
        window.addEventListener('error', (event) => {
            this._recordError({
                message: event.message,
                stack: event.error?.stack || '',
                source: event.filename,
                line: event.lineno,
            });
        });

        window.addEventListener('unhandledrejection', (event) => {
            this._recordError({
                message: String(event.reason?.message || event.reason || 'Unhandled rejection'),
                stack: event.reason?.stack || '',
                source: 'promise',
            });
        });
    }

    _recordPageVisit(url, title) {
        const now = Date.now();

        // Calculate time spent on previous page
        if (this.currentPageEntry) {
            this.currentPageEntry.timeSpentMs = now - this.currentPageEntry.enteredAt;
        }

        // Check if this is the same URL (avoid duplicates from replaceState)
        const lastPage = this.pages[this.pages.length - 1];
        if (lastPage && lastPage.url === url) {
            this.currentPageEntry = lastPage;
            return;
        }

        this.currentPageEntry = {
            url: url,
            title: title,
            enteredAt: now,
            timeSpentMs: 0,
        };

        this.pages.push(this.currentPageEntry);

        // Trim to max
        if (this.pages.length > this.MAX_PAGES) {
            this.pages = this.pages.slice(-this.MAX_PAGES);
        }

        this._saveState();
    }

    _recordClick(event) {
        const target = event.target?.closest(
            'button, a, input, select, textarea, [role="button"], [data-action]'
        );
        if (!target) return;

        // Skip clicks inside feedback UI
        if (target.closest('[data-no-screenshot]') ||
            target.closest('#feedbackModal') ||
            target.closest('#feedbackBtn')) {
            return;
        }

        const text = (target.textContent || '').trim().substring(0, 50);
        const tag = target.tagName.toLowerCase();

        this.clicks.push({
            element: tag,
            id: target.id || undefined,
            text: text || undefined,
            href: target.href || undefined,
            selector: this._buildSelector(target),
            timestamp: Date.now(),
        });

        if (this.clicks.length > this.MAX_CLICKS) {
            this.clicks = this.clicks.slice(-this.MAX_CLICKS);
        }

        this._saveState();
    }

    _recordError(errorInfo) {
        this.errors.push({
            message: (errorInfo.message || '').substring(0, 200),
            stack: (errorInfo.stack || '').substring(0, 500),
            source: errorInfo.source || '',
            timestamp: Date.now(),
        });

        if (this.errors.length > this.MAX_ERRORS) {
            this.errors = this.errors.slice(-this.MAX_ERRORS);
        }

        this._saveState();
    }

    _buildSelector(element) {
        if (element.id) return `#${element.id}`;
        const tag = element.tagName.toLowerCase();
        const cls = element.className && typeof element.className === 'string'
            ? '.' + element.className.trim().split(/\s+/).slice(0, 2).join('.')
            : '';
        return tag + cls;
    }

    getContext() {
        // Update time spent on current page
        if (this.currentPageEntry) {
            this.currentPageEntry.timeSpentMs = Date.now() - this.currentPageEntry.enteredAt;
        }

        return {
            pages_visited: this.pages.map(p => ({
                url: p.url,
                title: p.title,
                enteredAt: p.enteredAt,
                timeSpentMs: p.timeSpentMs,
            })),
            recent_clicks: this.clicks.map(c => ({
                element: c.element,
                id: c.id,
                text: c.text,
                href: c.href,
                selector: c.selector,
                timestamp: c.timestamp,
            })),
            js_errors: this.errors.map(e => ({
                message: e.message,
                stack: e.stack,
                source: e.source,
                timestamp: e.timestamp,
            })),
            current_url: window.location.href,
            current_title: document.title,
            session_duration_ms: Date.now() - this.sessionStart,
        };
    }

    formatAsText() {
        const now = Date.now();
        let text = '';

        if (this.pages.length > 0) {
            text += 'Screen Journey:\n';
            this.pages.forEach((p, i) => {
                const timeSpent = p.timeSpentMs ? Math.round(p.timeSpentMs / 1000) : 0;
                const path = new URL(p.url, window.location.origin).pathname;
                text += `  ${i + 1}. ${path} (${timeSpent}s)\n`;
            });
        }

        if (this.clicks.length > 0) {
            text += '\nRecent Actions:\n';
            this.clicks.slice(-5).forEach((c, i) => {
                const agoMs = now - c.timestamp;
                const agoS = Math.round(agoMs / 1000);
                const label = c.text || c.element;
                text += `  ${i + 1}. Clicked '${label}' (${agoS}s ago)\n`;
            });
        }

        if (this.errors.length > 0) {
            text += '\nJS Errors:\n';
            this.errors.forEach((e, i) => {
                text += `  ${i + 1}. ${e.message}\n`;
            });
        }

        return text;
    }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = ContextTracker;
}
