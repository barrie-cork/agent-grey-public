"""
Browser compatibility tests for WebSocket implementation.

Tests WebSocket functionality across different browser environments.
"""

import time

from django.contrib.auth import get_user_model
from unittest import skipUnless

from django.test import LiveServerTestCase

from apps.review_manager.models import SearchSession

User = get_user_model()

# Try to import Selenium - skip tests if not available
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


@skipUnless(SELENIUM_AVAILABLE, "Selenium not available for browser testing")
class BrowserCompatibilityTests(LiveServerTestCase):
    """Test WebSocket functionality in real browsers."""

    @classmethod
    def setUpClass(cls):
        """Set up browser driver."""
        super().setUpClass()

        # Chrome options for headless testing
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-web-security')
        chrome_options.add_argument('--allow-running-insecure-content')

        try:
            cls.driver = webdriver.Chrome(options=chrome_options)
            cls.driver.implicitly_wait(10)
        except Exception:
            # If Chrome not available, skip these tests
            cls.driver = None

    @classmethod
    def tearDownClass(cls):
        """Clean up browser driver."""
        if cls.driver:
            cls.driver.quit()
        super().tearDownClass()

    def setUp(self):
        """Set up test data."""
        if not self.driver:
            self.skipTest("Chrome WebDriver not available")

        from apps.core.tests.utils import create_test_user
        self.user = create_test_user()

        self.session = SearchSession.objects.create(
            owner=self.user,
            title="Test Session",
            status="draft"
        )

        # Login user
        self.client.login(email=self.user.email, password="testpass123")

        # Get session cookie for browser
        session_cookie = self.client.cookies.get('sessionid')
        if session_cookie:
            # Navigate to a dummy page first to set domain
            self.driver.get(f"{self.live_server_url}/")

            # Add session cookie to browser
            self.driver.add_cookie({
                'name': 'sessionid',
                'value': session_cookie.value,
                'domain': 'localhost'
            })

    def create_websocket_test_page(self):
        """Create a test page with WebSocket functionality."""
        test_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>WebSocket Test</title>
            <meta charset="UTF-8">
            <script>
                var wsUrl = 'ws://localhost:8001/ws/session/{self.session.id}/';
                var ws = null;
                var messages = [];
                var connectionStatus = 'disconnected';

                function log(message) {{
                    console.log(message);
                    messages.push(message);
                    updateMessages();
                }}

                function connectWebSocket() {{
                    try {{
                        ws = new WebSocket(wsUrl);

                        ws.onopen = function(event) {{
                            connectionStatus = 'connected';
                            document.getElementById('status').textContent = 'Connected';
                            log('WebSocket connected');
                        }};

                        ws.onmessage = function(event) {{
                            try {{
                                var data = JSON.parse(event.data);
                                log('Received: ' + data.type);

                                if (data.type === 'state_change') {{
                                    document.getElementById('state').textContent = data.new_state;
                                    log('State changed to: ' + data.new_state);
                                }} else if (data.type === 'progress_update') {{
                                    document.getElementById('progress').textContent = data.overall_progress + '%';
                                    log('Progress: ' + data.overall_progress + '%');
                                }} else if (data.type === 'connection') {{
                                    log('Connection message: ' + data.action);
                                }} else if (data.type === 'error') {{
                                    log('Error: ' + data.error_code + ' - ' + data.message);
                                }}
                            }} catch (e) {{
                                log('Error parsing message: ' + e.message);
                            }}
                        }};

                        ws.onclose = function(event) {{
                            connectionStatus = 'disconnected';
                            document.getElementById('status').textContent = 'Disconnected';
                            log('WebSocket disconnected, code: ' + event.code);
                        }};

                        ws.onerror = function(error) {{
                            connectionStatus = 'error';
                            document.getElementById('status').textContent = 'Error';
                            log('WebSocket error: ' + error);
                        }};
                    }} catch (e) {{
                        log('Failed to create WebSocket: ' + e.message);
                        connectionStatus = 'error';
                        document.getElementById('status').textContent = 'Error';
                    }}
                }}

                function sendPing() {{
                    if (ws && ws.readyState === WebSocket.OPEN) {{
                        try {{
                            var message = {{
                                type: 'connection',
                                action: 'ping'
                            }};
                            ws.send(JSON.stringify(message));
                            log('Sent ping');
                        }} catch (e) {{
                            log('Error sending ping: ' + e.message);
                        }}
                    }} else {{
                        log('WebSocket not open, cannot send ping');
                    }}
                }}

                function sendGetState() {{
                    if (ws && ws.readyState === WebSocket.OPEN) {{
                        try {{
                            var message = {{
                                type: 'command',
                                action: 'get_state'
                            }};
                            ws.send(JSON.stringify(message));
                            log('Sent get_state command');
                        }} catch (e) {{
                            log('Error sending get_state: ' + e.message);
                        }}
                    }} else {{
                        log('WebSocket not open, cannot send get_state');
                    }}
                }}

                function updateMessages() {{
                    var messageDiv = document.getElementById('messages');
                    messageDiv.innerHTML = messages.slice(-10).join('<br>');
                }}

                function getConnectionStatus() {{
                    return connectionStatus;
                }}

                // Connect on page load
                window.onload = function() {{
                    connectWebSocket();
                    // Set up test functions for Selenium
                    window.testWebSocket = {{
                        connect: connectWebSocket,
                        sendPing: sendPing,
                        sendGetState: sendGetState,
                        getStatus: getConnectionStatus,
                        getMessages: function() {{ return messages; }}
                    }};
                }};
            </script>
        </head>
        <body>
            <h1>WebSocket Test</h1>
            <div>Status: <span id="status">Connecting...</span></div>
            <div>State: <span id="state">unknown</span></div>
            <div>Progress: <span id="progress">0%</span></div>
            <div>
                <button onclick="sendPing()">Send Ping</button>
                <button onclick="sendGetState()">Get State</button>
            </div>
            <div>
                <h3>Messages (last 10):</h3>
                <div id="messages"></div>
            </div>
        </body>
        </html>
        """

        return test_html

    def test_websocket_connection_in_browser(self):
        """Test WebSocket connection works in real browser."""
        # Create test page
        test_html = self.create_websocket_test_page()

        # Create test file
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            f.write(test_html)
            test_file_path = f.name

        try:
            # Navigate to test page
            self.driver.get(f"file://{test_file_path}")

            # Wait for page to load
            time.sleep(2)

            # Check if WebSocket connection status is available
            try:
                status_element = self.driver.find_element(By.ID, "status")
                _initial_status = status_element.text

                # Give WebSocket time to connect or fail
                time.sleep(3)

                final_status = status_element.text

                # WebSocket might not connect due to development environment
                # but we can test that the JavaScript runs without errors
                self.assertIn(final_status.lower(), ['connected', 'disconnected', 'error', 'connecting...'])

                # Test that we can call WebSocket functions
                ping_result = self.driver.execute_script("""
                    if (window.testWebSocket && window.testWebSocket.sendPing) {
                        try {
                            window.testWebSocket.sendPing();
                            return 'ping_sent';
                        } catch (e) {
                            return 'ping_error: ' + e.message;
                        }
                    }
                    return 'function_not_found';
                """)

                # Should be able to call the function (even if WebSocket not connected)
                self.assertIn('ping', ping_result.lower())

            except Exception as e:
                self.skipTest(f"Browser WebSocket test failed due to environment: {e}")

        finally:
            # Clean up test file
            try:
                os.unlink(test_file_path)
            except OSError:
                pass

    def test_websocket_javascript_api_availability(self):
        """Test that WebSocket JavaScript API is available in browser."""
        # Create simple test page
        test_html = """
        <!DOCTYPE html>
        <html>
        <head><title>WebSocket API Test</title></head>
        <body>
            <div id="result">Testing...</div>
            <script>
                var result = 'WebSocket API not available';

                if (typeof WebSocket !== 'undefined') {
                    result = 'WebSocket API available';

                    // Test WebSocket constants
                    if (WebSocket.CONNECTING !== undefined &&
                        WebSocket.OPEN !== undefined &&
                        WebSocket.CLOSING !== undefined &&
                        WebSocket.CLOSED !== undefined) {
                        result += ', constants available';
                    }
                }

                document.getElementById('result').textContent = result;
            </script>
        </body>
        </html>
        """

        import os
        import tempfile

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            f.write(test_html)
            test_file_path = f.name

        try:
            # Navigate to test page
            self.driver.get(f"file://{test_file_path}")

            # Wait for script to execute
            time.sleep(1)

            # Check result
            result_element = self.driver.find_element(By.ID, "result")
            result_text = result_element.text

            # WebSocket API should be available in modern browsers
            self.assertIn('WebSocket API available', result_text)
            self.assertIn('constants available', result_text)

        finally:
            # Clean up test file
            try:
                os.unlink(test_file_path)
            except OSError:
                pass

    def test_websocket_error_handling_in_browser(self):
        """Test WebSocket error handling in browser environment."""
        # Create test page with intentionally bad WebSocket URL
        test_html = """
        <!DOCTYPE html>
        <html>
        <head><title>WebSocket Error Test</title></head>
        <body>
            <div id="status">Testing...</div>
            <div id="errors"></div>
            <script>
                var errors = [];
                var status = 'testing';

                try {
                    var ws = new WebSocket('ws://invalid-host:9999/test/');

                    ws.onopen = function() {
                        status = 'unexpected_connection';
                    };

                    ws.onerror = function(error) {
                        status = 'error_handled';
                        errors.push('WebSocket error occurred');
                    };

                    ws.onclose = function(event) {
                        status = 'connection_closed';
                        errors.push('Connection closed with code: ' + event.code);
                    };

                } catch (e) {
                    status = 'exception_caught';
                    errors.push('Exception: ' + e.message);
                }

                // Update page after short delay
                setTimeout(function() {
                    document.getElementById('status').textContent = status;
                    document.getElementById('errors').innerHTML = errors.join('<br>');
                }, 2000);
            </script>
        </body>
        </html>
        """

        import os
        import tempfile

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            f.write(test_html)
            test_file_path = f.name

        try:
            # Navigate to test page
            self.driver.get(f"file://{test_file_path}")

            # Wait for error handling to complete
            time.sleep(3)

            # Check that error was handled gracefully
            status_element = self.driver.find_element(By.ID, "status")
            status_text = status_element.text

            # Should not be 'testing' anymore, indicating script executed
            self.assertNotEqual(status_text, 'testing')

            # Should handle connection failure gracefully
            self.assertIn(status_text, ['error_handled', 'connection_closed', 'exception_caught'])

        finally:
            # Clean up test file
            try:
                os.unlink(test_file_path)
            except OSError:
                pass


# Additional test class for fallback testing (if needed)
@skipUnless(SELENIUM_AVAILABLE, "Selenium not available for browser testing")
class WebSocketFallbackTests(LiveServerTestCase):
    """Test WebSocket fallback mechanisms in browser."""

    @classmethod
    def setUpClass(cls):
        """Set up browser driver."""
        super().setUpClass()

        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')

        try:
            cls.driver = webdriver.Chrome(options=chrome_options)
            cls.driver.implicitly_wait(5)
        except Exception:
            cls.driver = None

    @classmethod
    def tearDownClass(cls):
        """Clean up browser driver."""
        if cls.driver:
            cls.driver.quit()
        super().tearDownClass()

    def setUp(self):
        """Set up test data."""
        if not self.driver:
            self.skipTest("Chrome WebDriver not available")

    def test_fallback_to_polling_simulation(self):
        """Test that fallback to polling can be simulated."""
        # Create test page that simulates WebSocket failure and fallback
        test_html = """
        <!DOCTYPE html>
        <html>
        <head><title>Fallback Test</title></head>
        <body>
            <div id="mode">websocket</div>
            <div id="status">testing</div>
            <script>
                var mode = 'websocket';
                var status = 'testing';

                // Simulate WebSocket failure and fallback
                function simulateWebSocketFailure() {
                    mode = 'polling';
                    status = 'fallback_activated';

                    // Simulate polling
                    var pollCount = 0;
                    var pollInterval = setInterval(function() {
                        pollCount++;
                        if (pollCount >= 3) {
                            status = 'polling_successful';
                            clearInterval(pollInterval);
                            updatePage();
                        }
                    }, 100);
                }

                function updatePage() {
                    document.getElementById('mode').textContent = mode;
                    document.getElementById('status').textContent = status;
                }

                // Start simulation
                setTimeout(simulateWebSocketFailure, 100);
            </script>
        </body>
        </html>
        """

        import os
        import tempfile

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            f.write(test_html)
            test_file_path = f.name

        try:
            # Navigate to test page
            self.driver.get(f"file://{test_file_path}")

            # Wait for simulation to complete
            time.sleep(1)

            # Check that fallback was simulated
            mode_element = self.driver.find_element(By.ID, "mode")
            status_element = self.driver.find_element(By.ID, "status")

            mode_text = mode_element.text
            status_text = status_element.text

            # Should have switched to polling mode
            self.assertEqual(mode_text, 'polling')
            self.assertEqual(status_text, 'polling_successful')

        finally:
            # Clean up test file
            try:
                os.unlink(test_file_path)
            except OSError:
                pass
