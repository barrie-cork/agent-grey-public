/**
 * SSE Client for Real-Time Session Status Updates
 *
 * Replaces polling with Server-Sent Events for instant updates.
 * Implements automatic reconnection with exponential backoff and
 * graceful fallback to polling when SSE is unavailable.
 *
 * Usage:
 *   const monitor = new SessionMonitor(sessionId);
 *   monitor.onStatusUpdate = (data) => { ... };
 *   monitor.connect();
 */

class SessionMonitor {
    constructor(sessionId) {
        this.sessionId = sessionId;
        this.eventSource = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;  // Start with 1 second
        this.isConnected = false;
        this.pollingFallbackActive = false;
        this.pollingIntervalId = null;

        // Callbacks
        this.onStatusUpdate = null;
        this.onConnected = null;
        this.onComplete = null;
        this.onError = null;
        this.onDisconnect = null;
    }

    /**
     * Connect to SSE endpoint.
     */
    connect() {
        // Check browser support
        if (typeof EventSource === 'undefined') {
            console.warn('[SSE] EventSource not supported, falling back to polling');
            this.fallbackToPolling();
            return;
        }

        const url = `/sessions/${this.sessionId}/stream/`;

        try {
            this.eventSource = new EventSource(url);
            this.setupEventHandlers();
            console.log(`[SSE] Connecting to ${url}`);
        } catch (error) {
            console.error('[SSE] Connection error:', error);
            if (this.onError) {
                this.onError(error);
            }
            this.scheduleReconnect();
        }
    }

    /**
     * Setup EventSource event handlers.
     */
    setupEventHandlers() {
        // Handle all SSE messages
        this.eventSource.addEventListener('message', (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleEvent(data);
            } catch (error) {
                console.error('[SSE] Parse error:', error);
            }
        });

        // Handle connection open
        this.eventSource.addEventListener('open', () => {
            console.log('[SSE] Connection opened');
            this.isConnected = true;
            this.reconnectAttempts = 0;
            this.reconnectDelay = 1000;
            this.updateConnectionStatus('connected');
        });

        // Handle connection errors
        this.eventSource.addEventListener('error', (error) => {
            console.error('[SSE] Connection error:', error);
            this.isConnected = false;
            this.updateConnectionStatus('disconnected');

            // EventSource automatically reconnects, but we'll handle manual reconnect
            if (this.eventSource.readyState === EventSource.CLOSED) {
                this.scheduleReconnect();
            }
        });
    }

    /**
     * Handle different SSE event types.
     */
    handleEvent(data) {
        switch (data.type) {
            case 'connected':
                console.log('[SSE] Connected to session:', data.session_id);
                if (this.onConnected) {
                    this.onConnected(data);
                }
                break;

            case 'status_update':
                console.log('[SSE] Status update:', data.status, `(${data.progress}%)`);
                this.updateSessionUI(data);
                if (this.onStatusUpdate) {
                    this.onStatusUpdate(data);
                }
                break;

            case 'complete':
                console.log('[SSE] Session complete:', data.final_status);
                this.disconnect();
                if (this.onComplete) {
                    this.onComplete(data);
                }
                break;

            case 'error':
                console.error('[SSE] Server error:', data.message);
                this.disconnect();
                if (this.onError) {
                    this.onError(data.message);
                }
                this.fallbackToPolling();
                break;

            default:
                console.warn('[SSE] Unknown event type:', data.type);
        }
    }

    /**
     * Update session UI elements.
     */
    updateSessionUI(data) {
        // Update status badge
        const statusBadge = document.getElementById('session-status');
        if (statusBadge) {
            statusBadge.textContent = data.status;
            statusBadge.className = `badge bg-${this.getStatusClass(data.status)} fs-6`;
        }

        // Update progress bar
        const progressBar = document.getElementById('session-progress-bar');
        if (progressBar) {
            progressBar.style.width = `${data.progress}%`;
            progressBar.setAttribute('aria-valuenow', data.progress);
        }

        // Update results count
        const resultsCount = document.getElementById('results-count');
        if (resultsCount) {
            resultsCount.textContent = `${data.reviewed_results || 0} / ${data.total_results || 0}`;
        }

        // Update timestamp
        const timestamp = document.getElementById('last-updated');
        if (timestamp) {
            const date = new Date(data.timestamp);
            timestamp.textContent = `Last updated: ${date.toLocaleTimeString()}`;
        }
    }

    /**
     * Update connection status indicator.
     */
    updateConnectionStatus(status) {
        const indicator = document.getElementById('connection-status');
        if (indicator) {
            const statusConfig = {
                'connected': { text: 'Connected', class: 'text-success', icon: '●' },
                'disconnected': { text: 'Disconnected', class: 'text-danger', icon: '○' },
                'reconnecting': { text: 'Reconnecting...', class: 'text-warning', icon: '◔' }
            };

            const config = statusConfig[status] || statusConfig['disconnected'];
            indicator.innerHTML = `<span class="${config.class}">${config.icon} ${config.text}</span>`;
        }
    }

    /**
     * Get Bootstrap badge class for session status.
     */
    getStatusClass(status) {
        const statusMap = {
            'draft': 'secondary',
            'defining_search': 'info',
            'ready_to_execute': 'primary',
            'executing': 'warning',
            'processing_results': 'warning',
            'ready_for_review': 'success',
            'under_review': 'info',
            'completed': 'success',
            'archived': 'secondary',
            'failed': 'danger'
        };
        return statusMap[status] || 'secondary';
    }

    /**
     * Schedule reconnection attempt with exponential backoff.
     */
    scheduleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('[SSE] Max reconnect attempts reached, falling back to polling');
            this.fallbackToPolling();
            return;
        }

        this.reconnectAttempts++;
        this.updateConnectionStatus('reconnecting');

        console.log(`[SSE] Reconnecting in ${this.reconnectDelay}ms (attempt ${this.reconnectAttempts})`);

        setTimeout(() => {
            this.disconnect();
            this.connect();
        }, this.reconnectDelay);

        // Exponential backoff
        this.reconnectDelay = Math.min(this.reconnectDelay * 2, 30000);  // Max 30 seconds
    }

    /**
     * Disconnect from SSE endpoint.
     */
    disconnect() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
            this.isConnected = false;
            console.log('[SSE] Disconnected');

            if (this.onDisconnect) {
                this.onDisconnect();
            }
        }

        // Stop polling if active
        if (this.pollingIntervalId) {
            clearInterval(this.pollingIntervalId);
            this.pollingIntervalId = null;
            this.pollingFallbackActive = false;
        }
    }

    /**
     * Fallback to polling if SSE not available or failed.
     */
    fallbackToPolling() {
        if (this.pollingFallbackActive) {
            return;  // Already polling
        }

        console.log('[SSE] Falling back to polling');
        this.pollingFallbackActive = true;
        this.updateConnectionStatus('disconnected');

        // Start simple polling (500ms interval)
        const pollInterval = 500;

        const poll = async () => {
            try {
                const response = await fetch(`/api/session/${this.sessionId}/status/`);
                if (response.ok) {
                    const data = await response.json();
                    this.updateSessionUI({
                        type: 'status_update',
                        status: data.status,
                        progress: data.progress_percent,
                        total_results: data.stats.total_results,
                        reviewed_results: data.stats.retrieved_count,
                        timestamp: data.last_updated
                    });

                    // Notify status update callback
                    if (this.onStatusUpdate) {
                        this.onStatusUpdate({
                            status: data.status,
                            progress: data.progress_percent
                        });
                    }

                    // Stop polling if terminal state
                    if (['completed', 'archived', 'failed'].includes(data.status)) {
                        this.disconnect();
                        if (this.onComplete) {
                            this.onComplete({ final_status: data.status });
                        }
                        return;
                    }
                }
            } catch (error) {
                console.error('[Polling] Error:', error);
            }
        };

        // Start polling
        this.pollingIntervalId = setInterval(poll, pollInterval);
        poll();  // Immediate first poll
    }
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = SessionMonitor;
}
