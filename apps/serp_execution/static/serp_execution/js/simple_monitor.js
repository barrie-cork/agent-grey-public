/**
 * Simple Session Monitor - polling-based session status updates
 * Provides lightweight fallback when SSE is unavailable and powers the
 * execution streaming feed on the session detail page.
 *
 * @typedef {Object} MonitorOptions
 * @property {boolean} [autoRedirect=true] - Whether to automatically redirect on completion
 * @property {number} [pollingInterval=2000] - Polling interval in milliseconds
 * @property {number} [maxRetries=150] - Maximum number of retry attempts
 *
 * @typedef {Object} SessionStatusData
 * @property {string} session_id - UUID of the session
 * @property {string} status - Current session status
 * @property {string} session_status_display - Human-readable status
 * @property {string} status_detail - Detailed status message
 * @property {number} total_queries - Total number of queries
 * @property {number} completed_queries - Number of completed queries
 * @property {number} progress_percentage - Completion percentage (0-100)
 * @property {number} total_raw_results - Total results retrieved
 * @property {QueryStats} query_stats - Detailed query statistics
 * @property {CurrentQuery|null} current_query - Currently executing query details
 * @property {RecentQuery[]} recent_queries - List of recently completed queries
 * @property {string} timestamp - ISO timestamp of this status update
 *
 * @typedef {Object} QueryStats
 * @property {number} total_queries - Total number of queries
 * @property {number} completed_queries - Completed query count
 * @property {number} running_queries - Currently running query count
 * @property {number} failed_queries - Failed query count
 *
 * @typedef {Object} CurrentQuery
 * @property {string} execution_id - UUID of the execution
 * @property {string} query_text - Full query text
 * @property {string} status - Execution status
 * @property {number} current_page - Current pagination page
 * @property {number} total_pages - Total pages available
 * @property {number} results_so_far - Results retrieved so far
 * @property {string} stopped_reason - Reason pagination stopped
 *
 * @typedef {Object} RecentQuery
 * @property {string} query_text - Full query text
 * @property {number} results_count - Total results retrieved
 * @property {number} pages_fetched - Number of pages retrieved
 * @property {string} stopped_reason - Reason pagination stopped
 * @property {string} completed_at - ISO timestamp of completion
 */

class SimpleSessionMonitor {
    // Constants for progress calculation
    static PROGRESS_MIN = 0;
    static PROGRESS_MAX = 100;
    static PERCENTAGE_MULTIPLIER = 100;

    /**
     * Create a new session monitor.
     *
     * @param {string} sessionId - UUID of the session to monitor
     * @param {MonitorOptions} [options={}] - Configuration options
     */
    constructor(sessionId, options = {}) {
        this.sessionId = sessionId;
        this.autoRedirect = options.autoRedirect !== false;
        this.pollingInterval = options.pollingInterval || 2000;
        this.maxRetries = options.maxRetries || 150;  // Increased for long-running searches (5 minutes)
        this.retryCount = 0;
        this.consecutiveErrors = 0;  // Track consecutive errors for circuit breaker

        this.isPolling = false;
        this.currentStatus = null;
        this.lastUpdate = null;
        this.executionStartTime = null;
        this.durationTimer = null;

        // Activity history tracking
        this.activityHistory = [];
        this.lastActivityText = null;
        this.maxHistoryItems = 20;

        this.start();
    }

    start() {
        if (this.isPolling) {
            return;
        }

        this.isPolling = true;
        this.poll();
    }

    stop() {
        this.isPolling = false;
        if (this.pollTimer) {
            clearTimeout(this.pollTimer);
            this.pollTimer = null;
        }
        this.resetExecutionDuration();
    }

    poll() {
        if (!this.isPolling) {
            return;
        }

        const url = `/execution/api/session/${this.sessionId}/quick-status/`;

        fetch(url, {
            method: 'GET',
            headers: {
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
            }
        })
        .then(response => {
            if (response.ok) {
                this.retryCount = 0;
                this.consecutiveErrors = 0;  // Reset on success
                return response.json();
            }

            // Handle specific HTTP errors
            if (response.status === 503) {
                // Service temporarily unavailable - retry with longer delay
                throw new Error('SERVICE_UNAVAILABLE');
            } else if (response.status === 500) {
                // Server error - may be recoverable
                throw new Error('SERVER_ERROR');
            }

            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        })
        .then(data => {
            // Check if error response from API
            if (data.error) {
                logger.warning(`API returned error: ${data.error}`);
                // If retry_after is specified, respect it
                if (data.retry_after) {
                    this.pollingInterval = data.retry_after * 1000;
                }
                throw new Error(data.error);
            }
            this.handleUpdate(data);
        })
        .catch(error => {
            this.handleError(error);
        });

        if (this.isPolling) {
            this.pollTimer = setTimeout(() => this.poll(), this.pollingInterval);
        }
    }

    handleUpdate(data) {
        const newStatus = data.status;

        this.updateUI(data);

        if (Object.prototype.hasOwnProperty.call(data, 'current_query')) {
            this.updateCurrentQueryDisplay(data.current_query);
        }

        if (Array.isArray(data.recent_queries)) {
            this.updateRecentQueries(data.recent_queries);
        }

        if (newStatus === 'executing' || newStatus === 'processing_results') {
            this.updateExecutionDuration(data);
        } else {
            this.resetExecutionDuration();
        }

        if (this.currentStatus !== newStatus) {
            this.onStatusChange(this.currentStatus, newStatus);
            this.currentStatus = newStatus;
        }

        this.lastUpdate = new Date();
        this.updateLastUpdateTime();
    }

    handleError(error) {
        console.error('SimpleSessionMonitor polling error:', error);

        this.retryCount += 1;
        this.consecutiveErrors += 1;

        // Check for permanent failures
        if (this.retryCount >= this.maxRetries) {
            console.warn('Max retry attempts reached, stopping monitor');
            this.stop();
            this.showError(
                'Connection lost after multiple retries. The session may be stuck. ' +
                'Please refresh the page or contact support if the issue persists.'
            );
            return;
        }

        // Calculate exponential backoff with cap
        let retryDelay = this.pollingInterval;

        if (error.message === 'SERVICE_UNAVAILABLE') {
            // Longer delay for service unavailable
            retryDelay = Math.min(10000, this.pollingInterval * 2);
        } else if (this.consecutiveErrors > 3) {
            // Use exponential backoff after multiple consecutive errors
            retryDelay = Math.min(
                30000,  // Cap at 30 seconds
                this.pollingInterval * Math.pow(1.5, Math.min(this.consecutiveErrors, 10))
            );
        }

        console.log(
            `Retrying in ${retryDelay}ms ` +
            `(attempt ${this.retryCount}/${this.maxRetries}, ` +
            `consecutive errors: ${this.consecutiveErrors})`
        );

        if (this.isPolling) {
            this.pollTimer = setTimeout(() => this.poll(), retryDelay);
        }
    }

    /**
     * Update the UI with new session status data.
     *
     * Updates all DOM elements that display session progress including status badges,
     * progress bars, query counts, and execution details.
     *
     * @param {SessionStatusData} data - API response data containing session status and progress
     */
    updateUI(data) {
        const statusBadge = document.getElementById('status-badge');
        if (statusBadge) {
            statusBadge.textContent = data.session_status_display || data.status;
            statusBadge.className = `badge badge-${data.status}`;
        }

        const progressBar = document.querySelector('[data-testid="review-progress-bar"] .progress-bar');
        if (progressBar && data.progress_percentage !== undefined) {
            const pct = Math.max(
                SimpleSessionMonitor.PROGRESS_MIN,
                Math.min(SimpleSessionMonitor.PROGRESS_MAX, data.progress_percentage)
            );
            progressBar.style.width = `${pct}%`;
            progressBar.textContent = `${Math.round(pct)}%`;
            progressBar.setAttribute('aria-valuenow', `${pct}`);
        }

        const statusDetail = document.getElementById('status-detail');
        if (statusDetail && data.status_detail) {
            statusDetail.textContent = data.status_detail;
        }

        if (data.processed_count !== undefined) {
            const processedElement = document.getElementById('processed-count');
            if (processedElement) {
                processedElement.textContent = data.processed_count;
            }
        }

        if (data.total_raw_results !== undefined) {
            const totalElement = document.getElementById('total-results');
            if (totalElement) {
                totalElement.textContent = data.total_raw_results;
            }
        }

        // Update execution status page elements
        const queryStats = data.query_stats || {};
        const totalQueries = data.total_queries || queryStats.total_queries || 0;
        const completedQueries = data.completed_queries || queryStats.completed_queries || 0;
        const runningQueries = queryStats.running_queries || 0;
        const failedQueries = queryStats.failed_queries || 0;

        // Update query progress bar and text
        const queryProgressBar = document.getElementById('query-progress-bar');
        const progressText = document.getElementById('progress-text');
        if (queryProgressBar && progressText) {
            const progressPct = totalQueries > 0
                ? (completedQueries / totalQueries) * SimpleSessionMonitor.PERCENTAGE_MULTIPLIER
                : SimpleSessionMonitor.PROGRESS_MIN;
            queryProgressBar.style.width = `${progressPct}%`;
            queryProgressBar.setAttribute('aria-valuenow', `${progressPct}`);
            progressText.textContent = `${completedQueries}/${totalQueries} queries`;
        }

        // Update individual stat counters
        const totalQueriesElement = document.getElementById('total-queries');
        if (totalQueriesElement) {
            totalQueriesElement.textContent = totalQueries;
        }

        const completedQueriesElement = document.getElementById('completed-queries');
        if (completedQueriesElement) {
            completedQueriesElement.textContent = completedQueries;
        }

        const runningQueriesElement = document.getElementById('running-queries');
        if (runningQueriesElement) {
            runningQueriesElement.textContent = runningQueries;
        }

        const failedQueriesElement = document.getElementById('failed-queries');
        if (failedQueriesElement) {
            failedQueriesElement.textContent = failedQueries;
        }

        // Update current activity message
        const currentActivityElement = document.getElementById('current-activity');
        if (currentActivityElement && data.status_detail) {
            currentActivityElement.innerHTML = `<i class="fas fa-sync fa-spin"></i> ${data.status_detail}`;

            // Add to activity history if it's a new message
            this.addToActivityHistory(data.status_detail);
        }

        // Update status message
        const statusMessageText = document.getElementById('status-message-text');
        if (statusMessageText && data.status_detail) {
            statusMessageText.textContent = data.status_detail;
        }
    }

    updateCurrentQueryDisplay(queryData) {
        const section = document.getElementById('current-query-section');
        if (!section) {
            return;
        }

        if (!queryData) {
            section.style.display = 'none';
            const resultsElement = document.getElementById('results-so-far');
            if (resultsElement) {
                resultsElement.textContent = '0';
            }
            const paginationStatus = document.getElementById('pagination-status');
            if (paginationStatus) {
                paginationStatus.textContent = 'Waiting for next query...';
            }
            const progressBar = document.getElementById('page-progress-bar');
            if (progressBar) {
                progressBar.style.width = '0%';
                progressBar.setAttribute('aria-valuenow', '0');
            }
            return;
        }

        section.style.display = 'block';

        const queryTextElement = document.getElementById('current-query-text');
        if (queryTextElement) {
            queryTextElement.title = queryData.query_text || '';
            this.highlightQueryComponents(queryTextElement, queryData.query_text || '');
        }

        const pageBadge = document.getElementById('query-page-badge');
        if (pageBadge) {
            const currentPage = queryData.current_page || 1;
            const totalPages = queryData.total_pages || null;
            pageBadge.textContent = totalPages ? `Page ${currentPage} of ${totalPages}` : `Page ${currentPage}`;

            const ratio = totalPages ? currentPage / totalPages : 0;
            if (ratio < 0.3) {
                pageBadge.className = 'badge bg-info';
            } else if (ratio < 0.7) {
                pageBadge.className = 'badge bg-primary';
            } else {
                pageBadge.className = 'badge bg-success';
            }
        }

        const resultsElement = document.getElementById('results-so-far');
        if (resultsElement && queryData.results_so_far !== undefined) {
            const previous = parseInt(resultsElement.textContent, 10) || 0;
            const nextValue = queryData.results_so_far || 0;
            if (nextValue > previous) {
                this.animateNumberUpdate(resultsElement, previous, nextValue);
            } else {
                resultsElement.textContent = `${nextValue}`;
            }
        }

        const paginationStatus = document.getElementById('pagination-status');
        if (paginationStatus) {
            const currentPage = queryData.current_page || 0;
            const totalPages = queryData.total_pages || 0;
            const stoppedReason = queryData.stopped_reason;

            if (totalPages && currentPage < totalPages) {
                paginationStatus.innerHTML = '<svg class="w-4 h-4 inline-block mr-1 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg> Fetching next page...';
            } else if (stoppedReason) {
                paginationStatus.innerHTML = `<svg class="w-4 h-4 inline-block mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg> ${this.escapeHtml(this.formatStopReason(stoppedReason))}`;
            } else {
                paginationStatus.innerHTML = '<svg class="w-4 h-4 inline-block mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg> Processing results...';
            }
        }

        const progressBar = document.getElementById('page-progress-bar');
        if (progressBar) {
            const currentPage = queryData.current_page || 0;
            const totalPages = queryData.total_pages || 0;
            const pct = totalPages ? Math.min(100, (currentPage / totalPages) * 100) : 0;
            progressBar.style.width = `${pct}%`;
            progressBar.setAttribute('aria-valuenow', `${pct}`);
        }
    }

    updateRecentQueries(recentQueries) {
        const listContainer = document.getElementById('completed-queries-list');
        if (!listContainer) {
            return;
        }

        if (!recentQueries.length) {
            listContainer.innerHTML = '<p class="text-muted-foreground small mb-0"><svg class="w-4 h-4 inline-block mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg> No completed queries yet.</p>';
            return;
        }

        const html = recentQueries.map(query => {
            const preview = this.truncateQuery(query.query_text || '', 120);
            const stopReason = this.formatStopReason(query.stopped_reason);
            const timeAgo = this.formatTimeAgo(query.completed_at);

            const badges = [
                `<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-success text-white"><svg class="w-3 h-3 mr-1 inline-block" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"/></svg> ${query.results_count || 0} results</span>`,
                `<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-secondary text-secondary-foreground"><svg class="w-3 h-3 mr-1 inline-block" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"/></svg> ${query.pages_fetched || 0} pages</span>`
            ];

            if (stopReason && stopReason !== 'Limit reached') {
                badges.push(`
                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-warning text-gray-900" title="${this.escapeHtml(stopReason)}">
                        <svg class="w-3 h-3 mr-1 inline-block" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg> ${this.escapeHtml(stopReason)}
                    </span>
                `);
            }

            return `
                <div class="timeline-item fade-in">
                    <div class="timeline-marker bg-success">
                        <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
                    </div>
                    <div class="timeline-content">
                        <div class="d-flex justify-content-between align-items-start mb-2">
                            <code class="query-preview text-dark small" title="${this.escapeHtml(query.query_text || '')}">${this.escapeHtml(preview)}</code>
                            <span class="text-muted small">${timeAgo}</span>
                        </div>
                        <div class="d-flex flex-wrap gap-2">
                            ${badges.join('')}
                        </div>
                    </div>
                </div>
            `;
        }).join('');

        listContainer.innerHTML = html;
    }

    truncateQuery(query, maxLength) {
        if (!query) {
            return '';
        }
        return query.length > maxLength ? query.substring(0, maxLength) + '...' : query;
    }

    highlightQueryComponents(element, fullQuery) {
        if (!element) {
            return;
        }

        const escaped = this.escapeHtml(fullQuery || '');
        const highlighted = escaped
            .replace(/(site:[^\s]+)/gi, '<span class="query-operator">$1</span>')
            .replace(/(filetype:[^\s]+)/gi, '<span class="query-filetype">$1</span>');

        element.innerHTML = highlighted || 'Waiting for query to start...';
    }

    formatStopReason(reason) {
        if (!reason) {
            return '';
        }

        const map = {
            'limit_reached': 'Limit reached',
            'no_more_results': 'No more results',
            'api_limit': 'API limit reached',
            'rate_limit': 'Rate limited',
            'error': 'Stopped due to error',
        };

        return map[reason] || reason;
    }

    formatTimeAgo(timestamp) {
        if (!timestamp) {
            return 'Just now';
        }

        const completed = new Date(timestamp);
        if (Number.isNaN(completed.getTime())) {
            return 'Just now';
        }

        const diffSeconds = Math.floor((Date.now() - completed.getTime()) / 1000);
        if (diffSeconds < 5) {
            return 'Just now';
        }
        if (diffSeconds < 60) {
            return `${diffSeconds}s ago`;
        }
        if (diffSeconds < 3600) {
            const minutes = Math.floor(diffSeconds / 60);
            return `${minutes}m ago`;
        }
        const hours = Math.floor(diffSeconds / 3600);
        return `${hours}h ago`;
    }

    animateNumberUpdate(element, from, to) {
        const duration = 400;
        const step = 40;
        const steps = Math.max(1, Math.floor(duration / step));
        const delta = (to - from) / steps;
        let current = from;

        const timer = setInterval(() => {
            current += delta;
            if ((delta >= 0 && current >= to) || (delta < 0 && current <= to)) {
                element.textContent = `${to}`;
                element.classList.add('highlight-update');
                setTimeout(() => element.classList.remove('highlight-update'), 300);
                clearInterval(timer);
            } else {
                element.textContent = `${Math.round(current)}`;
            }
        }, step);
    }

    updateExecutionDuration(data) {
        const durationElement = document.getElementById('execution-duration');
        if (!durationElement) {
            return;
        }

        if (!this.executionStartTime) {
            const metadata = (data && data.metadata) || {};
            const startTimestamp = metadata.execution_started_at;
            this.executionStartTime = startTimestamp ? new Date(startTimestamp) : new Date();
        }

        if (this.durationTimer) {
            return;
        }

        this.durationTimer = setInterval(() => {
            if (!this.executionStartTime) {
                return;
            }
            const elapsed = Math.max(0, Math.floor((Date.now() - this.executionStartTime.getTime()) / 1000));
            const minutes = Math.floor(elapsed / 60);
            const seconds = elapsed % 60;
            durationElement.textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;
        }, 1000);
    }

    resetExecutionDuration() {
        if (this.durationTimer) {
            clearInterval(this.durationTimer);
            this.durationTimer = null;
        }
        this.executionStartTime = null;

        const durationElement = document.getElementById('execution-duration');
        if (durationElement) {
            durationElement.textContent = '0:00';
        }
    }

    updateLastUpdateTime() {
        const element = document.getElementById('last-update-time');
        if (element) {
            element.textContent = new Date().toLocaleTimeString();
        }
    }

    escapeHtml(value) {
        if (value === undefined || value === null) {
            return '';
        }
        const div = document.createElement('div');
        div.textContent = value;
        return div.innerHTML;
    }

    onStatusChange(oldStatus, newStatus) {
        console.log(`Status changed from ${oldStatus} to ${newStatus}`);

        if (this.autoRedirect && this.shouldRedirect(newStatus)) {
            this.scheduleRedirect(newStatus);
        }
    }

    shouldRedirect(status) {
        return status === 'ready_for_review' || status === 'completed';
    }

    scheduleRedirect(status) {
        const delay = 3000;
        this.showRedirectNotification(delay);

        setTimeout(() => {
            if (status === 'ready_for_review') {
                window.location.href = `/review-results/overview/${this.sessionId}/`;
            } else if (status === 'completed') {
                window.location.href = `/sessions/${this.sessionId}/`;
            }
        }, delay);
    }

    showRedirectNotification(delay) {
        let notification = document.getElementById('redirect-notification');
        if (!notification) {
            notification = document.createElement('div');
            notification.id = 'redirect-notification';
            notification.className = 'alert alert-info mt-3';

            const container = document.querySelector('.col-lg-8') || document.body;
            container.appendChild(notification);
        }

        const seconds = Math.ceil(delay / 1000);
        notification.innerHTML = `
            <strong>Processing Complete!</strong>
            Redirecting to review page in <span id="countdown">${seconds}</span> seconds...
            <button type="button" class="btn btn-sm btn-primary ms-2" onclick="window.location.reload()">
                Stay Here
            </button>
        `;

        let remaining = seconds;
        const countdownTimer = setInterval(() => {
            remaining -= 1;
            const countdownElement = document.getElementById('countdown');
            if (countdownElement && remaining > 0) {
                countdownElement.textContent = remaining;
            } else {
                clearInterval(countdownTimer);
            }
        }, 1000);
    }

    showError(message) {
        let errorNotification = document.getElementById('error-notification');
        if (!errorNotification) {
            errorNotification = document.createElement('div');
            errorNotification.id = 'error-notification';
            errorNotification.className = 'alert alert-danger mt-3';

            const container = document.querySelector('.col-lg-8') || document.body;
            container.appendChild(errorNotification);
        }

        errorNotification.innerHTML = `
            <strong>Connection Error:</strong> ${this.escapeHtml(message)}
            <button type="button" class="btn btn-sm btn-outline-danger ms-2" onclick="window.location.reload()">
                Refresh Page
            </button>
        `;
    }

    addToActivityHistory(activityText) {
        // Don't add duplicate consecutive messages
        if (this.lastActivityText === activityText) {
            return;
        }

        this.lastActivityText = activityText;

        // Add to history array (newest first)
        const historyItem = {
            text: activityText,
            timestamp: new Date(),
        };

        this.activityHistory.unshift(historyItem);

        // Limit history size
        if (this.activityHistory.length > this.maxHistoryItems) {
            this.activityHistory = this.activityHistory.slice(0, this.maxHistoryItems);
        }

        // Update display
        this.updateActivityHistoryDisplay();
    }

    updateActivityHistoryDisplay() {
        const historyContainer = document.getElementById('activity-history');
        if (!historyContainer) {
            return;
        }

        // Clear container
        historyContainer.innerHTML = '';

        // Add each history item
        this.activityHistory.forEach((item, index) => {
            const itemElement = document.createElement('div');
            itemElement.className = 'activity-item';

            const timeElement = document.createElement('span');
            timeElement.className = 'activity-time';
            timeElement.textContent = this.formatTimeAgo(item.timestamp.toISOString());

            const textElement = document.createElement('span');
            textElement.className = 'activity-text';
            textElement.textContent = item.text;

            itemElement.appendChild(timeElement);
            itemElement.appendChild(textElement);
            historyContainer.appendChild(itemElement);
        });
    }
}

window.SimpleSessionMonitor = SimpleSessionMonitor;
