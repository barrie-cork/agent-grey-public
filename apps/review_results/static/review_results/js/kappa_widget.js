/**
 * Cohen's Kappa Widget
 *
 * Displays session-wide inter-rater reliability (Cohen's Kappa) metrics
 * for dual-screening workflows with automatic refresh functionality.
 *
 * Usage:
 *   const widget = new KappaWidget('#kappa-widget', sessionId);
 *   widget.refresh();
 */

class KappaWidget {
    /**
     * @param {string} containerSelector - CSS selector for widget container
     * @param {string} sessionId - UUID of the SearchSession
     */
    constructor(containerSelector, sessionId) {
        this.container = document.querySelector(containerSelector);
        this.sessionId = sessionId;
        this.apiUrl = `/api/sessions/${sessionId}/irr-metrics/`;
        this.calculateUrl = `/api/sessions/${sessionId}/irr-calculate/`;

        // Cochrane threshold for acceptable IRR
        this.COCHRANE_THRESHOLD = 0.70;

        // Polling config
        this.POLL_INTERVAL_MS = 3000;
        this.POLL_MAX_ATTEMPTS = 10;
        this.pollTimer = null;

        // Bind event handlers
        this.bindEvents();

        // Initial load
        this.refresh();
    }

    /**
     * Bind event listeners for widget interactions
     */
    bindEvents() {
        const refreshBtn = document.getElementById('refresh-kappa-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.triggerCalculation();
            });
        }
    }

    /**
     * Trigger IRR calculation via POST, then poll for results
     */
    async triggerCalculation() {
        this.setLoading(true, 'Calculating...');
        this.stopPolling();

        try {
            const csrfToken = this.getCsrfToken();
            const response = await fetch(this.calculateUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': csrfToken
                },
                credentials: 'same-origin'
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            // Start polling for results
            this.startPolling();

        } catch (error) {
            console.error('[Kappa Widget] Trigger error:', error);
            this.renderError(error.message);
            this.setLoading(false);
        }
    }

    /**
     * Start polling for IRR results after triggering calculation
     */
    startPolling() {
        let attempts = 0;

        this.pollTimer = setInterval(async () => {
            attempts++;

            if (attempts > this.POLL_MAX_ATTEMPTS) {
                this.stopPolling();
                this.setLoading(false);
                this.renderNoData('Calculation is taking longer than expected. Try refreshing again.');
                return;
            }

            try {
                const response = await fetch(this.apiUrl, {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    credentials: 'same-origin'
                });

                if (!response.ok) {
                    return; // Keep polling
                }

                const data = await response.json();
                const metrics = data?.session_wide_metrics || data;

                if (metrics && metrics.total_pairs > 0 && metrics.average_kappa != null) {
                    this.stopPolling();
                    this.setLoading(false);
                    this.render(data);
                }
                // Otherwise keep polling
            } catch {
                // Ignore errors during polling, keep trying
            }
        }, this.POLL_INTERVAL_MS);
    }

    /**
     * Stop polling timer
     */
    stopPolling() {
        if (this.pollTimer) {
            clearInterval(this.pollTimer);
            this.pollTimer = null;
        }
    }

    /**
     * Get CSRF token from cookie
     */
    getCsrfToken() {
        const name = 'csrftoken';
        const cookies = document.cookie.split(';');
        for (const cookie of cookies) {
            const trimmed = cookie.trim();
            if (trimmed.startsWith(name + '=')) {
                return trimmed.substring(name.length + 1);
            }
        }
        return '';
    }

    /**
     * Fetch latest IRR metrics from API (GET only, no calculation trigger)
     */
    async refresh() {
        this.setLoading(true);

        try {
            const response = await fetch(this.apiUrl, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                credentials: 'same-origin'
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            this.render(data);

        } catch (error) {
            if (error.message.includes('404')) {
                console.debug('[Kappa Widget] No IRR metrics available yet for this session.');
                this.renderNoData();
            } else {
                console.error('[Kappa Widget] Fetch error:', error);
                this.renderError(error.message);
            }
        } finally {
            this.setLoading(false);
        }
    }

    /**
     * Render IRR metrics in widget
     * @param {Object} data - IRR summary from API
     */
    render(data) {
        // API wraps metrics in session_wide_metrics
        const metrics = data?.session_wide_metrics || data;

        // Handle case where no IRR data exists yet
        if (!metrics || metrics.total_pairs === 0 || metrics.average_kappa == null) {
            this.renderNoData();
            return;
        }

        const {
            average_kappa,
            average_agreement,
            total_pairs,
            pairs_below_threshold,
            meets_cochrane,
            calculated_at
        } = metrics;

        // Format Kappa value (0.00 - 1.00)
        const kappaFormatted = average_kappa.toFixed(3);
        const agreementFormatted = average_agreement.toFixed(1);

        // Determine interpretation and alert class
        const interpretation = this.getInterpretation(average_kappa);
        const alertClass = this.getAlertClass(average_kappa);

        // Build HTML
        const html = `
            <div class="kappa-display">
                <div class="kappa-value-container mb-3">
                    <div class="kappa-label text-muted small">Cohen's Kappa</div>
                    <div id="kappa-value" class="kappa-value ${alertClass}">${kappaFormatted}</div>
                    <div class="kappa-agreement text-muted small">${agreementFormatted}% agreement</div>
                </div>

                <div class="alert alert-${alertClass} mb-3" role="alert">
                    <strong>${interpretation.label}</strong><br>
                    <small>${interpretation.description}</small>
                </div>

                <div class="kappa-details">
                    <div class="row text-center">
                        <div class="col-6">
                            <div class="metric-label small text-muted">Reviewer Pairs</div>
                            <div class="metric-value">${total_pairs}</div>
                        </div>
                        <div class="col-6">
                            <div class="metric-label small text-muted">Below Threshold</div>
                            <div class="metric-value ${pairs_below_threshold > 0 ? 'text-warning' : 'text-success'}">
                                ${pairs_below_threshold}
                            </div>
                        </div>
                    </div>

                    ${meets_cochrane
                        ? '<div class="mt-2 text-success small"><svg class="w-4 h-4 inline-block mr-1" fill="currentColor" viewBox="0 0 24 24"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg> Meets Cochrane standard (≥0.70)</div>'
                        : '<div class="mt-2 text-warning small"><svg class="w-4 h-4 inline-block mr-1" fill="currentColor" viewBox="0 0 24 24"><path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg> Below Cochrane standard</div>'
                    }

                    <div class="mt-2 text-muted small">
                        Last updated: ${this.formatTimestamp(calculated_at)}
                    </div>
                </div>
            </div>
        `;

        this.container.innerHTML = html;
    }

    /**
     * Get interpretation based on Kappa value
     * @param {number} kappa - Cohen's Kappa value
     * @returns {Object} - Interpretation with label and description
     */
    getInterpretation(kappa) {
        if (kappa >= 0.81) {
            return {
                label: 'Almost Perfect Agreement',
                description: 'Reviewers are highly consistent in their decisions.'
            };
        } else if (kappa >= 0.70) {
            return {
                label: 'Substantial Agreement',
                description: 'Meets Cochrane standard for systematic reviews.'
            };
        } else if (kappa >= 0.61) {
            return {
                label: 'Substantial Agreement',
                description: 'Good reliability, slightly below Cochrane threshold.'
            };
        } else if (kappa >= 0.41) {
            return {
                label: 'Moderate Agreement',
                description: 'Consider additional training or clarification of criteria.'
            };
        } else if (kappa >= 0.21) {
            return {
                label: 'Fair Agreement',
                description: 'Low reliability. Review and discuss disagreements.'
            };
        } else {
            return {
                label: 'Slight Agreement',
                description: 'Poor reliability. Criteria clarification needed.'
            };
        }
    }

    /**
     * Get Bootstrap alert class based on Kappa value
     * @param {number} kappa - Cohen's Kappa value
     * @returns {string} - Bootstrap alert class (success/warning/danger)
     */
    getAlertClass(kappa) {
        if (kappa >= this.COCHRANE_THRESHOLD) {
            return 'success';
        } else if (kappa >= 0.40) {
            return 'warning';
        } else {
            return 'danger';
        }
    }

    /**
     * Format ISO timestamp to readable format
     * @param {string} timestamp - ISO 8601 timestamp
     * @returns {string} - Formatted timestamp
     */
    formatTimestamp(timestamp) {
        if (!timestamp) return 'Unknown';

        const date = new Date(timestamp);
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);

        // Show "X minutes ago" for recent updates
        if (diffMins < 60) {
            return diffMins === 0 ? 'Just now' : `${diffMins} min ago`;
        }

        // Otherwise show formatted date/time
        return date.toLocaleString('en-GB', {
            day: '2-digit',
            month: 'short',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    /**
     * Render "no data" state
     * @param {string} [message] - Optional custom message
     */
    renderNoData(message) {
        const html = `
            <div class="text-center py-4">
                <svg class="w-8 h-8 mx-auto text-muted-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                <p class="text-muted-foreground mt-2 mb-0">No IRR data available yet</p>
                <small class="text-muted-foreground">
                    ${message || 'Press Refresh to calculate inter-rater reliability.'}
                </small>
            </div>
        `;
        this.container.innerHTML = html;
    }

    /**
     * Render error state
     * @param {string} message - Error message
     */
    renderError(message) {
        const html = `
            <div class="p-4 rounded-md bg-destructive/10 border border-destructive/20 text-destructive" role="alert">
                <svg class="w-5 h-5 inline-block mr-2" fill="currentColor" viewBox="0 0 24 24"><path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>
                <strong>Error loading IRR data</strong><br>
                <small>${message}</small>
            </div>
        `;
        this.container.innerHTML = html;
    }

    /**
     * Toggle loading state
     * @param {boolean} isLoading - Whether widget is loading
     * @param {string} [loadingText] - Optional loading text
     */
    setLoading(isLoading, loadingText) {
        const refreshBtn = document.getElementById('refresh-kappa-btn');

        if (isLoading) {
            // Show loading spinner in widget
            this.container.innerHTML = `
                <div class="text-center py-4">
                    <svg class="w-8 h-8 mx-auto text-primary animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    <p class="text-muted-foreground mt-2 mb-0">${loadingText || 'Loading IRR metrics...'}</p>
                </div>
            `;

            // Disable refresh button
            if (refreshBtn) {
                refreshBtn.disabled = true;
                refreshBtn.innerHTML = '<svg class="w-4 h-4 mr-1 animate-spin inline-block" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg> ' + (loadingText || 'Loading...');
            }
        } else {
            // Re-enable refresh button
            if (refreshBtn) {
                refreshBtn.disabled = false;
                refreshBtn.innerHTML = '<svg class="w-4 h-4 mr-1 inline-block" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg> Refresh';
            }
        }
    }
}

// Export for use in templates
if (typeof module !== 'undefined' && module.exports) {
    module.exports = KappaWidget;
}
