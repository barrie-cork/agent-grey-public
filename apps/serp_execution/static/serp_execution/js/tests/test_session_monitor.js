/**
 * Unit tests for SessionMonitor
 */

describe('SessionMonitor', () => {
    let monitor;
    let mockEventSource;

    beforeEach(() => {
        // Setup minimal DOM
        document.body.innerHTML = `
            <div id="execution-status" data-session-id="test-123"></div>
            <span id="status-badge" class="badge"></span>
            <div class="progress-bar"></div>
            <span id="progress-text"></span>
            <span id="completed-queries"></span>
            <span id="total-queries"></span>
            <div id="status-message"></div>
            <div id="connection-status"></div>
            <div id="transition-indicator" style="display: none;"></div>
            <div id="error-messages"></div>
            <div id="redirect-countdown" style="display: none;"></div>
            <span id="countdown-seconds"></span>
            <table><tbody id="query-progress-tbody"></tbody></table>
            <div id="current-query-indicator" style="display: none;"></div>
            <span id="current-query-text"></span>
            <span id="current-query-step"></span>
            <input type="checkbox" id="auto-redirect-toggle" checked>
        `;

        // Mock EventSource
        mockEventSource = {
            addEventListener: jest.fn(),
            close: jest.fn(),
            readyState: EventSource.OPEN,
            onopen: null,
            onerror: null,
            onmessage: null
        };

        global.EventSource = jest.fn(() => mockEventSource);
    });

    afterEach(() => {
        if (monitor) {
            monitor.cleanup();
            monitor = null;
        }
        jest.clearAllMocks();
    });

    describe('Initialization', () => {
        test('should initialize with correct session ID', () => {
            monitor = new SessionMonitor('test-123');
            expect(monitor.sessionId).toBe('test-123');
            expect(monitor.state.status).toBe('unknown');
        });

        test('should connect to correct SSE endpoint', () => {
            monitor = new SessionMonitor('test-123');
            expect(global.EventSource).toHaveBeenCalledWith('/core/sse/session/test-123/events/');
        });

        test('should cache DOM elements', () => {
            monitor = new SessionMonitor('test-123');
            expect(monitor.elements.statusBadge).toBeTruthy();
            expect(monitor.elements.progressBar).toBeTruthy();
            expect(monitor.elements.queryTable).toBeTruthy();
        });

        test('should merge custom options', () => {
            monitor = new SessionMonitor('test-123', {
                debugMode: true,
                autoRedirect: false,
                redirectDelay: 5000
            });

            expect(monitor.options.debugMode).toBe(true);
            expect(monitor.options.autoRedirect).toBe(false);
            expect(monitor.options.redirectDelay).toBe(5000);
        });
    });

    describe('Event Handlers', () => {
        beforeEach(() => {
            monitor = new SessionMonitor('test-123');
        });

        test('should handle connected event', () => {
            const data = {
                session_id: 'test-123',
                current_state: 'executing'
            };

            monitor.handleConnected(data);
            expect(monitor.state.status).toBe('executing');

            const badge = document.getElementById('status-badge');
            expect(badge.classList.contains('badge-primary')).toBe(true);
            expect(badge.textContent).toBe('Executing');
        });

        test('should handle state transition', () => {
            const data = {
                old_state: 'executing',
                new_state: 'processing_results',
                metadata: {}
            };

            monitor.handleStateTransition(data);
            expect(monitor.state.status).toBe('processing_results');

            const badge = document.getElementById('status-badge');
            expect(badge.textContent).toBe('Processing');
        });

        test('should handle progress update', () => {
            const data = {
                progress: 50,
                processed_count: 25,
                total_count: 50,
                current_step: 'Processing batch 1'
            };

            monitor.handleProgressUpdate(data);

            expect(monitor.state.progress).toBe(50);
            expect(monitor.state.processedCount).toBe(25);
            expect(monitor.state.totalCount).toBe(50);

            const progressBar = document.querySelector('.progress-bar');
            expect(progressBar.style.width).toBe('50%');

            const processedElement = document.getElementById('completed-queries');
            expect(processedElement.textContent).toBe('25');
        });

        test('should handle query progress', () => {
            const data = {
                query_id: 'query-1',
                query_text: 'Test Query',
                status: 'executing',
                progress: 30,
                results_count: 10
            };

            monitor.handleQueryProgress(data);

            const query = monitor.state.queries.get('query-1');
            expect(query).toBeTruthy();
            expect(query.text).toBe('Test Query');
            expect(query.status).toBe('executing');
            expect(query.progress).toBe(30);
            expect(query.resultsCount).toBe(10);
        });

        test('should handle error event', () => {
            const data = {
                error_message: 'Test error',
                error_type: 'API_ERROR',
                recoverable: true
            };

            monitor.handleError(data);

            expect(monitor.state.errors).toHaveLength(1);
            expect(monitor.state.errors[0].message).toBe('Test error');

            const errorContainer = document.getElementById('error-messages');
            expect(errorContainer.querySelector('.alert')).toBeTruthy();
        });

        test('should handle completed state with auto-redirect', () => {
            jest.useFakeTimers();

            // Mock window.location
            delete window.location;
            window.location = { href: '' };

            monitor.handleCompletedState({});

            expect(monitor.redirectTimer).toBeTruthy();

            const countdown = document.getElementById('redirect-countdown');
            expect(countdown.style.display).toBe('block');

            jest.runAllTimers();
            expect(window.location.href).toBe(`/review-results/overview/test-123/`);

            jest.useRealTimers();
        });

        test('should handle completed state with no results', () => {
            monitor.handleCompletedState({ no_results: true });

            const statusMessage = document.getElementById('status-message');
            expect(statusMessage.innerHTML).toContain('no results');
        });
    });

    describe('UI Updates', () => {
        beforeEach(() => {
            monitor = new SessionMonitor('test-123');
        });

        test('should update status display', () => {
            monitor.updateStatusDisplay('executing');

            const badge = document.getElementById('status-badge');
            expect(badge.classList.contains('badge-primary')).toBe(true);
            expect(badge.textContent).toBe('Executing');
        });

        test('should update progress display', () => {
            monitor.updateProgressDisplay(75, 30, 40);

            const progressBar = document.querySelector('.progress-bar');
            expect(progressBar.style.width).toBe('75%');
            expect(progressBar.getAttribute('aria-valuenow')).toBe('75');

            const completed = document.getElementById('completed-queries');
            const total = document.getElementById('total-queries');
            expect(completed.textContent).toBe('30');
            expect(total.textContent).toBe('40');
        });

        test('should update connection status', () => {
            monitor.updateConnectionStatus('connected');

            const indicator = document.getElementById('connection-status');
            expect(indicator.textContent).toContain('Connected');
        });

        test('should show transition indicator', () => {
            jest.useFakeTimers();

            monitor.showTransitionIndicator();

            const indicator = document.getElementById('transition-indicator');
            expect(indicator.style.display).toBe('inline');

            jest.advanceTimersByTime(2000);
            expect(indicator.style.display).toBe('none');

            jest.useRealTimers();
        });

        test('should update query table', () => {
            monitor.state.queries.set('query-1', {
                text: 'Query 1',
                status: 'completed',
                progress: 100,
                resultsCount: 25
            });

            monitor.state.queries.set('query-2', {
                text: 'Query 2',
                status: 'executing',
                progress: 50,
                resultsCount: 10
            });

            monitor.updateQueryTable();

            const tbody = document.getElementById('query-progress-tbody');
            const rows = tbody.querySelectorAll('tr');

            expect(rows).toHaveLength(2);
            expect(rows[0].innerHTML).toContain('✅');
            expect(rows[0].innerHTML).toContain('Query 1');
            expect(rows[1].innerHTML).toContain('⚡');
            expect(rows[1].innerHTML).toContain('Query 2');
        });
    });

    describe('Connection Management', () => {
        beforeEach(() => {
            monitor = new SessionMonitor('test-123');
        });

        test('should handle connection open', () => {
            mockEventSource.onopen();

            expect(monitor.state.connectionStatus).toBe('connected');
            expect(monitor.reconnectAttempts).toBe(0);
        });

        test('should handle connection error and attempt reconnection', () => {
            jest.useFakeTimers();

            mockEventSource.readyState = EventSource.CLOSED;
            mockEventSource.onerror({ type: 'error' });

            expect(monitor.state.connectionStatus).toBe('error');
            expect(monitor.reconnectTimer).toBeTruthy();

            jest.advanceTimersByTime(3000);
            expect(global.EventSource).toHaveBeenCalledTimes(2);

            jest.useRealTimers();
        });

        test('should stop reconnecting after max attempts', () => {
            monitor.options.reconnectAttempts = 2;
            monitor.reconnectAttempts = 2;

            monitor.handleConnectionError();

            expect(monitor.reconnectAttempts).toBe(3);
            expect(monitor.reconnectTimer).toBeNull();
            expect(monitor.state.connectionStatus).toBe('failed');
        });
    });

    describe('Cleanup', () => {
        beforeEach(() => {
            monitor = new SessionMonitor('test-123');
        });

        test('should close EventSource on cleanup', () => {
            monitor.cleanup();

            expect(mockEventSource.close).toHaveBeenCalled();
            expect(monitor.eventSource).toBeNull();
        });

        test('should clear timers on cleanup', () => {
            jest.useFakeTimers();

            monitor.reconnectTimer = setTimeout(() => {}, 1000);
            monitor.redirectTimer = setTimeout(() => {}, 1000);

            monitor.cleanup();

            expect(monitor.reconnectTimer).toBeNull();
            expect(monitor.redirectTimer).toBeNull();

            jest.useRealTimers();
        });

        test('should reset state on cleanup', () => {
            monitor.state.status = 'executing';
            monitor.state.progress = 50;
            monitor.state.queries.set('test', {});

            monitor.cleanup();

            expect(monitor.state.status).toBe('unknown');
            expect(monitor.state.progress).toBe(0);
            expect(monitor.state.queries.size).toBe(0);
        });
    });

    describe('Auto-redirect', () => {
        beforeEach(() => {
            monitor = new SessionMonitor('test-123');
        });

        test('should schedule redirect with countdown', () => {
            jest.useFakeTimers();

            monitor.scheduleRedirect('/test-url', 3000);

            const countdown = document.getElementById('redirect-countdown');
            expect(countdown.style.display).toBe('block');

            const seconds = document.getElementById('countdown-seconds');
            expect(seconds.textContent).toBe('3');

            jest.advanceTimersByTime(1000);
            expect(seconds.textContent).toBe('2');

            jest.useRealTimers();
        });

        test('should cancel redirect', () => {
            jest.useFakeTimers();

            monitor.scheduleRedirect('/test-url', 3000);
            expect(monitor.redirectTimer).toBeTruthy();

            monitor.cancelRedirect();

            expect(monitor.redirectTimer).toBeNull();

            const countdown = document.getElementById('redirect-countdown');
            expect(countdown.style.display).toBe('none');

            jest.useRealTimers();
        });
    });
});

// Test for auto-initialization
describe('Auto-initialization', () => {
    test('should auto-initialize on DOM ready', () => {
        document.body.innerHTML = `
            <div id="execution-status"
                 data-session-id="auto-test-123"
                 data-debug-mode="true"
                 data-auto-redirect="false">
            </div>
        `;

        // Mock SessionMonitor constructor
        const originalSessionMonitor = window.SessionMonitor;
        window.SessionMonitor = jest.fn();

        // Trigger DOMContentLoaded
        const event = new Event('DOMContentLoaded');
        document.dispatchEvent(event);

        expect(window.SessionMonitor).toHaveBeenCalledWith('auto-test-123', {
            debugMode: true,
            autoRedirect: false
        });

        // Restore
        window.SessionMonitor = originalSessionMonitor;
    });
});
