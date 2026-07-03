/**
 * Simplified Session Monitor using Server-Sent Events
 * Replaces 1763-line execution_monitor.js with clean implementation
 * Version: 2.0
 */

class SessionMonitor {
    // Class constants for configuration
    static DEFAULT_RECONNECT_ATTEMPTS = 5;
    static DEFAULT_RECONNECT_DELAY = 3000;
    static DEFAULT_REDIRECT_DELAY = 3000;

    constructor(sessionId, options = {}) {
        // Core configuration
        this.sessionId = sessionId;
        this.options = {
            autoRedirect: true,
            redirectDelay: SessionMonitor.DEFAULT_REDIRECT_DELAY,
            reconnectAttempts: SessionMonitor.DEFAULT_RECONNECT_ATTEMPTS,
            reconnectDelay: SessionMonitor.DEFAULT_RECONNECT_DELAY,
            debugMode: false,
            ...options
        };

        // State management
        this.eventSource = null;
        this.state = {
            status: 'unknown',
            processedCount: 0,
            totalCount: 0,
            currentStep: '',
            currentQuery: null,
            queries: new Map(),
            lastUpdate: null,
            connectionStatus: 'disconnected',
            errors: []
        };

        // UI element cache
        this.elements = {};

        // Reconnection tracking
        this.reconnectAttempts = 0;
        this.reconnectTimer = null;
        this.redirectTimer = null;

        // Initialize
        this.init();
    }

    init() {
        this.cacheElements();
        this.connect();
        this.setupCleanupHandlers();

        // Start polling as backup (will be cancelled if SSE works)
        this.pollTimer = null;
        this.startPollingFallback();
    }

    setupCleanupHandlers() {
        // Ensure cleanup when page unloads
        window.addEventListener('beforeunload', () => {
            if (this.eventSource) {
                this.eventSource.close();
                this.eventSource = null;
            }
        });

        // Also handle page visibility changes for mobile/tabs
        document.addEventListener('visibilitychange', () => {
            if (document.hidden && this.eventSource) {
                // Page is being hidden, close connection
                if (this.options.debugMode) {
                    console.log('[SessionMonitor] Page hidden, closing SSE connection');
                }
                this.eventSource.close();
                this.eventSource = null;
                this.updateConnectionStatus('paused');
            } else if (!document.hidden && !this.eventSource) {
                // Page is visible again, reconnect if needed
                if (this.state.connectionStatus === 'paused') {
                    if (this.options.debugMode) {
                        console.log('[SessionMonitor] Page visible, reconnecting SSE');
                    }
                    this.connect();
                }
            }
        });
    }

    connect() {
        const url = `/core/sse/session/${this.sessionId}/events/`;

        if (this.options.debugMode) {
            console.log(`[SessionMonitor] Connecting to SSE: ${url}`);
        }

        try {
            this.eventSource = new EventSource(url);
            this.setupConnectionHandlers();
            this.registerEventHandlers();
        } catch (error) {
            console.error('[SessionMonitor] Failed to create EventSource:', error);
            this.handleConnectionError();
        }
    }

    setupConnectionHandlers() {
        this.eventSource.onopen = () => {
            console.log('[SessionMonitor] SSE connection established');
            this.updateConnectionStatus('connected');
            this.reconnectAttempts = 0;

            // Cancel reconnect timer
            if (this.reconnectTimer) {
                clearTimeout(this.reconnectTimer);
                this.reconnectTimer = null;
            }

            // Cancel polling since SSE is working
            if (this.pollTimer) {
                clearInterval(this.pollTimer);
                this.pollTimer = null;
                console.log('[SessionMonitor] Cancelled polling - SSE is active');
            }
        };

        this.eventSource.onerror = (error) => {
            console.error('[SessionMonitor] SSE connection error:', error);
            this.updateConnectionStatus('error');

            if (this.eventSource.readyState === EventSource.CLOSED) {
                this.handleConnectionError();
            }
        };
    }

    registerEventHandlers() {
        // Connection event
        this.eventSource.addEventListener('connected', (e) => {
            const data = JSON.parse(e.data);
            this.handleConnected(data);
        });

        // State transitions
        this.eventSource.addEventListener('state_transition', (e) => {
            const data = JSON.parse(e.data);
            this.handleStateTransition(data);
        });

        // Query progress events (real-time execution tracking)
        this.eventSource.addEventListener('query_progress', (e) => {
            const data = JSON.parse(e.data);
            this.handleQueryProgress(data);
        });

        // Progress updates
        this.eventSource.addEventListener('progress_update', (e) => {
            const data = JSON.parse(e.data);
            this.handleProgressUpdate(data);
        });

        // Query-level updates
        this.eventSource.addEventListener('query_progress', (e) => {
            const data = JSON.parse(e.data);
            this.handleQueryProgress(data);
        });

        // Errors
        this.eventSource.addEventListener('error', (e) => {
            const data = JSON.parse(e.data);
            this.handleError(data);
        });

        // Generic message handler
        this.eventSource.onmessage = (e) => {
            if (this.options.debugMode) {
                console.log('[SessionMonitor] Generic message:', e.data);
            }
        };
    }

    cacheElements() {
        this.elements = {
            // Status elements
            statusBadge: document.querySelector('#status-badge'),
            statusMessage: document.querySelector('#status-message'),
            transitionIndicator: document.querySelector('#transition-indicator'),

            // Count elements
            processedCount: document.querySelector('#completed-queries'),
            totalCount: document.querySelector('#total-queries'),

            // Query progress
            queryTable: document.querySelector('#query-progress-tbody'),
            currentQueryIndicator: document.querySelector('#current-query-indicator'),
            currentQueryText: document.querySelector('#current-query-text'),
            currentQueryStep: document.querySelector('#current-query-step'),

            // Connection status
            connectionIndicator: document.querySelector('#connection-status'),

            // Other elements
            errorContainer: document.querySelector('#error-messages'),
            redirectCountdown: document.querySelector('#redirect-countdown'),
            countdownSeconds: document.querySelector('#countdown-seconds'),
            elapsedTime: document.querySelector('#elapsed-time'),

            // Stats cards
            totalResults: document.querySelector('#total-results'),
            runningQueries: document.querySelector('#running-queries'),
            failedQueries: document.querySelector('#failed-queries')
        };
    }

    // Event Handlers
    handleConnected(data) {
        this.state.status = data.current_state;
        this.updateStatusDisplay(data.current_state);
    }

    handleStateTransition(data) {
        const { old_state, new_state, metadata } = data;

        console.log(`[SessionMonitor] State: ${old_state} → ${new_state}`);

        this.state.status = new_state;
        this.state.lastUpdate = new Date();

        this.updateStatusDisplay(new_state);
        this.showTransitionIndicator();

        switch (new_state) {
            case 'executing':
                this.updateStatusMessage('Search execution in progress...', 'info');
                break;
            case 'processing_results':
                this.updateStatusMessage('Processing search results...', 'info');
                break;
            case 'ready_for_review':
                console.log('[SessionMonitor] Session ready for review - triggering redirect');
                this.handleCompletedState(metadata);
                break;
            case 'failed':
                this.updateStatusMessage('Search execution failed', 'danger');
                break;
        }
    }

    handleProgressUpdate(data) {
        const { processed_count, total_count, current_step, query_stats } = data;

        this.state.processedCount = processed_count || 0;
        this.state.totalCount = total_count || 0;
        this.state.currentStep = current_step || '';

        // Use query statistics if available, otherwise fall back to result counts
        if (query_stats) {
            this.updateCountDisplay(
                query_stats.completed_queries || 0,
                query_stats.total_queries || 0,
                query_stats.running_queries || 0,
                query_stats.failed_queries || 0
            );
        } else {
            // Fallback for backward compatibility
            this.updateCountDisplay(processed_count, total_count, 0, 0);
        }

        if (current_step) {
            this.updateCurrentStep(current_step);
        }
    }

    handleQueryProgress(data) {
        // Enhanced query progress handler for real-time execution visibility
        const {
            query_index,
            total_queries,
            query_text,
            status,
            results_count = 0,
            target_domain = null,
            progress_percent = 0
        } = data;

        // Update current activity display based on status
        if (status === 'starting') {
            const domainText = target_domain ? ` (${target_domain})` : '';
            this.updateCurrentActivity(
                `🔍 Executing query ${query_index}/${total_queries}${domainText}: ${query_text.substring(0, 60)}...`
            );
            this.updateStatusMessage(`Processing query ${query_index} of ${total_queries}`, 'info');

            // Update counters: completed = query_index - 1 (haven't finished current yet)
            this.updateCountDisplay(
                query_index - 1,  // completed
                total_queries,    // total
                1,                // running (current query)
                0                 // failed
            );
        } else if (status === 'completed') {
            this.updateCurrentActivity(
                `✅ Completed query ${query_index}/${total_queries} (${results_count} results)`
            );

            // Update counters: completed = query_index (just finished current)
            this.updateCountDisplay(
                query_index,      // completed
                total_queries,    // total
                0,                // running
                0                 // failed (TODO: track failures separately)
            );
        } else if (status === 'failed') {
            this.updateCurrentActivity(
                `❌ Query ${query_index}/${total_queries} failed`
            );
            this.displayError(`Query ${query_index} execution failed`, 'warning');
        }

        // Update progress bar if method exists
        if (typeof this.updateProgressBar === 'function') {
            this.updateProgressBar(query_index, total_queries, status);
        }

        // Store query info in state (keep existing functionality for legacy compatibility)
        const query_id = `query_${query_index}`;
        if (this.state.queries) {
            // Implement cleanup for old queries to prevent memory leak
            if (this.state.queries.size > 100) {
                const oldestQueries = Array.from(this.state.queries.keys()).slice(0, 50);
                oldestQueries.forEach(id => this.state.queries.delete(id));
            }

            this.state.queries.set(query_id, {
                id: query_id,
                index: query_index,
                text: query_text,
                status: status,
                resultsCount: results_count,
                targetDomain: target_domain,
                lastUpdate: new Date()
            });

            // Update query table if it exists
            if (typeof this.updateQueryTable === 'function') {
                this.updateQueryTable();
            }
        }
    }

    handleError(data) {
        const { error_message, error_type, recoverable } = data;

        this.state.errors.push({
            message: error_message,
            type: error_type,
            recoverable: recoverable,
            timestamp: new Date()
        });

        this.displayError(error_message, recoverable ? 'warning' : 'danger');
    }

    handleCompletedState(metadata) {
        console.log('[SessionMonitor] Processing completed, metadata:', metadata);

        if (metadata && metadata.no_results) {
            this.updateStatusMessage('Search completed with no results', 'warning');
            return;
        }

        this.updateStatusMessage('Processing complete! Ready for review.', 'success');

        const autoRedirectToggle = document.querySelector('#auto-redirect-toggle');
        console.log('[SessionMonitor] Auto-redirect toggle checked:', autoRedirectToggle?.checked);
        console.log('[SessionMonitor] Auto-redirect option:', this.options.autoRedirect);

        if (autoRedirectToggle && autoRedirectToggle.checked && this.options.autoRedirect) {
            // Get review URL from metadata or build it
            const redirectUrl = metadata?.review_url || `/review-results/overview/${this.sessionId}/`;
            console.log('[SessionMonitor] Scheduling redirect to:', redirectUrl);
            this.scheduleRedirect(redirectUrl, this.options.redirectDelay);
        } else {
            console.log('[SessionMonitor] Auto-redirect disabled or conditions not met');
        }
    }

    // UI Update Methods
    updateStatusDisplay(status) {
        if (!this.elements.statusBadge) return;

        const statusConfig = {
            'draft': { class: 'badge-secondary', text: 'Draft' },
            'defining_search': { class: 'badge-info', text: 'Defining Search' },
            'ready_to_execute': { class: 'badge-warning', text: 'Starting Execution...' },
            'executing': { class: 'badge-primary', text: 'Executing' },
            'processing_results': { class: 'badge-primary', text: 'Processing' },
            'ready_for_review': { class: 'badge-success', text: 'Ready for Review' },
            'under_review': { class: 'badge-info', text: 'Under Review' },
            'completed': { class: 'badge-success', text: 'Completed' },
            'failed': { class: 'badge-danger', text: 'Failed' },
            'archived': { class: 'badge-dark', text: 'Archived' }
        };

        const config = statusConfig[status] || statusConfig['draft'];
        this.elements.statusBadge.className = `badge ${config.class}`;
        this.elements.statusBadge.textContent = config.text;
    }

    updateCountDisplay(completed = 0, total = 0, running = 0, failed = 0) {
        // Update query count displays with proper statistics
        if (this.elements.processedCount) {
            this.elements.processedCount.textContent = completed;
        }

        if (this.elements.totalCount) {
            this.elements.totalCount.textContent = total;
        }

        if (this.elements.runningQueries) {
            this.elements.runningQueries.textContent = running;
        }

        if (this.elements.failedQueries) {
            this.elements.failedQueries.textContent = failed;
        }
    }

    updateCurrentQueryDisplay(queryText, status) {
        if (this.elements.currentQueryIndicator) {
            this.elements.currentQueryIndicator.style.display = 'block';
        }

        if (this.elements.currentQueryText) {
            this.elements.currentQueryText.textContent = queryText;
        }

        if (this.elements.currentQueryStep) {
            this.elements.currentQueryStep.textContent = `Status: ${status}`;
        }
    }

    updateQueryTable() {
        if (!this.elements.queryTable) return;

        this.elements.queryTable.innerHTML = '';

        for (const [, query] of this.state.queries) {
            const row = document.createElement('tr');

            const statusIcon = query.status === 'completed' ? '✅' :
                              query.status === 'executing' ? '⚡' :
                              query.status === 'failed' ? '❌' : '⏱️';

            row.innerHTML = `
                <td>${statusIcon}</td>
                <td>${query.text}</td>
                <td>${query.status}</td>
                <td>${query.resultsCount}</td>
            `;

            this.elements.queryTable.appendChild(row);
        }
    }

    updateStatusMessage(message, type = 'info') {
        if (this.elements.statusMessage) {
            this.elements.statusMessage.className = `alert alert-${type}`;
            this.elements.statusMessage.innerHTML = `<i class="fas fa-info-circle"></i> ${message}`;
        }
    }

    updateConnectionStatus(status) {
        this.state.connectionStatus = status;

        if (this.elements.connectionIndicator) {
            const statusText = status === 'connected' ? '🟢 Connected' :
                              status === 'error' ? '🔴 Disconnected' : '🟡 Connecting';
            this.elements.connectionIndicator.textContent = statusText;
        }
    }

    showTransitionIndicator() {
        if (this.elements.transitionIndicator) {
            this.elements.transitionIndicator.style.display = 'inline';
            setTimeout(() => {
                this.elements.transitionIndicator.style.display = 'none';
            }, 2000);
        }
    }

    displayError(message, type = 'danger') {
        if (this.elements.errorContainer) {
            const alert = document.createElement('div');
            alert.className = `alert alert-${type} alert-dismissible fade show`;
            alert.innerHTML = `
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            `;
            this.elements.errorContainer.appendChild(alert);
        }
    }

    updateCurrentStep(step) {
        if (this.elements.currentQueryStep) {
            this.elements.currentQueryStep.textContent = step;
        }
    }

    updateProgressBar(completed, total, status) {
        // Update visual progress bar for query execution
        const progressBar = document.getElementById('query-progress-bar');
        const progressText = document.getElementById('progress-text');

        if (!progressBar || !progressText) return;

        // Calculate percentage based on status
        let percent = 0;
        if (total > 0) {
            if (status === 'completed') {
                percent = (completed / total) * 100;
            } else if (status === 'starting') {
                // Show progress up to the starting query
                percent = ((completed - 1) / total) * 100;
            }
        }

        // Update progress bar
        progressBar.style.width = `${percent}%`;
        progressBar.setAttribute('aria-valuenow', Math.round(percent));

        // Update text
        if (status === 'completed' && completed === total) {
            progressText.textContent = `${completed}/${total} queries completed ✓`;
            progressBar.classList.remove('progress-bar-animated');
        } else {
            progressText.textContent = `${completed}/${total} queries`;
        }
    }

    // Auto-redirect functionality
    scheduleRedirect(url, delay = 3000) {
        console.log(`[SessionMonitor] Redirecting to ${url} in ${delay}ms`);

        // Small delay to ensure DOM is ready
        setTimeout(() => {
            if (this.elements.redirectCountdown) {
                this.elements.redirectCountdown.style.display = 'block';
            }
        }, 100);

        let remaining = Math.ceil(delay / 1000);
        const updateCountdown = () => {
            if (this.elements.countdownSeconds) {
                this.elements.countdownSeconds.textContent = remaining;
            }
            remaining--;
        };

        updateCountdown();
        const countdownInterval = setInterval(updateCountdown, 1000);

        this.redirectTimer = setTimeout(() => {
            clearInterval(countdownInterval);
            window.location.href = url;
        }, delay);
    }

    cancelRedirect() {
        if (this.redirectTimer) {
            clearTimeout(this.redirectTimer);
            this.redirectTimer = null;
        }

        if (this.elements.redirectCountdown) {
            this.elements.redirectCountdown.style.display = 'none';
        }
    }

    // Connection management with exponential backoff
    handleConnectionError() {
        this.reconnectAttempts++;

        if (this.reconnectAttempts <= this.options.reconnectAttempts) {
            // Exponential backoff: 3s, 6s, 12s, 24s, 48s
            const backoffDelay = Math.min(
                this.options.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
                30000  // Max 30 seconds
            );

            console.log(`[SessionMonitor] Reconnecting in ${backoffDelay}ms... (${this.reconnectAttempts}/${this.options.reconnectAttempts})`);

            this.reconnectTimer = setTimeout(() => {
                this.connect();
            }, backoffDelay);
        } else {
            console.error('[SessionMonitor] Max reconnection attempts reached, falling back to polling');
            this.updateConnectionStatus('polling');
            this.startPollingFallback();
        }
    }

    // Polling fallback for when SSE fails
    startPollingFallback() {
        // Don't start polling if SSE is connected
        if (this.state.connectionStatus === 'connected') {
            return;
        }

        // Avoid duplicate polling
        if (this.pollTimer) {
            return;
        }

        console.log('[SessionMonitor] Starting polling fallback');

        // Poll every 5 seconds
        this.pollTimer = setInterval(() => {
            this.fetchSessionStatus();
        }, 5000);

        // Do immediate poll
        this.fetchSessionStatus();
    }

    async fetchSessionStatus() {
        try {
            const response = await fetch(`/execution/api/session/${this.sessionId}/quick-status/`, {
                credentials: 'same-origin',
                headers: {
                    'Accept': 'application/json',
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();

            // Update state if changed
            if (data.status !== this.state.status) {
                console.log(`[SessionMonitor] Polling detected state change: ${this.state.status} → ${data.status}`);
                this.handleStateTransition({
                    old_state: this.state.status,
                    new_state: data.status,
                    metadata: data.metadata || {}
                });
            }

            // Update counts
            if (data.processed_count !== undefined || data.total_count !== undefined || data.query_stats) {
                this.handleProgressUpdate({
                    processed_count: data.processed_count || 0,
                    total_count: data.total_count || 0,
                    current_step: data.current_step || '',
                    query_stats: data.query_stats || null
                });
            }

            // Stop polling if session is complete
            if (['ready_for_review', 'completed', 'archived', 'failed'].includes(data.status)) {
                console.log('[SessionMonitor] Session complete, stopping polling');
                if (this.pollTimer) {
                    clearInterval(this.pollTimer);
                    this.pollTimer = null;
                }
            }

        } catch (error) {
            console.error('[SessionMonitor] Polling error:', error);
        }
    }

    // Cleanup
    cleanup() {
        console.log('[SessionMonitor] Cleaning up');

        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }

        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }

        if (this.redirectTimer) {
            clearTimeout(this.redirectTimer);
            this.redirectTimer = null;
        }

        if (this.pollTimer) {
            clearInterval(this.pollTimer);
            this.pollTimer = null;
        }

        this.updateConnectionStatus('disconnected');

        // Ensure complete cleanup by explicitly clearing Map
        if (this.state.queries) {
            this.state.queries.clear();
        }

        this.state = {
            status: 'unknown',
            processedCount: 0,
            totalCount: 0,
            currentStep: '',
            queries: new Map(),
            errors: []
        };
    }
}

// Auto-initialize on DOM ready
document.addEventListener('DOMContentLoaded', function() {
    const container = document.getElementById('execution-status');
    if (container) {
        const sessionId = container.dataset.sessionId;
        const debugMode = container.dataset.debugMode === 'true';
        const autoRedirect = container.dataset.autoRedirect !== 'false';

        if (sessionId) {
            window.sessionMonitor = new SessionMonitor(sessionId, {
                debugMode: debugMode,
                autoRedirect: autoRedirect
            });
        }
    }
});

// Export for testing
if (typeof module !== 'undefined' && module.exports) {
    module.exports = SessionMonitor;
}
