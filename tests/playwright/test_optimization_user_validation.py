"""
Comprehensive User Testing Suite for Task Optimization Validation

This test suite validates the task optimization implementation from an end-user perspective,
ensuring that the optimizations (Phase 1: CELERY_BEAT_SCHEDULE optimization and 
Phase 2: SimpleSessionActivityDetector) improve system efficiency without degrading 
user experience.

Key Areas Tested:
1. Core User Journey Tests (9-state workflow)
2. Performance Impact Testing (optimization benefits)
3. UI Responsiveness During Different States
4. Background Processing Validation
5. Edge Case & Error Scenarios
6. User Experience Validation

Optimizations Under Test:
- CELERY_BEAT_SCHEDULE: 15+ tasks → 9 tasks with frequency reductions
- unified_session_monitor: 30s → 120s (2 minutes)
- Activity-based monitoring intervals:
  * Active states (executing, processing_results): 60s
  * Review states (under_review, ready_for_review): 600s
  * Dormant states (completed, archived): 3600s
"""

import asyncio
import logging
import time
from typing import Any, Dict, List

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.db import transaction
from django.test import TransactionTestCase
from playwright.async_api import Error, Page, expect

from apps.core.services.session_activity_detector import \
    SimpleSessionActivityDetector
from apps.review_manager.models import SearchSession

logger = logging.getLogger(__name__)

# Test configuration
TEST_CONFIG = {
    'base_url': 'http://localhost:8000',
    'timeout_short': 5000,      # 5 seconds
    'timeout_medium': 15000,    # 15 seconds
    'timeout_long': 30000,      # 30 seconds
    'performance_threshold': 2000,  # 2 seconds for page loads
    'monitor_interval_tolerance': 10,  # 10% tolerance for timing
}

# Test data for realistic scenarios
TEST_SCENARIOS = {
    'healthcare_review': {
        'name': 'Healthcare Interventions Review',
        'population': 'elderly patients,seniors,geriatric patients',
        'interest': 'fall prevention,balance training,exercise therapy',
        'context': 'home care,community settings,nursing homes',
        'guidelines_filter': True,
    },
    'education_review': {
        'name': 'Educational Technology Review',
        'population': 'university students,college students',
        'interest': 'online learning,digital literacy,e-learning',
        'context': 'higher education,distance learning,remote education',
        'guidelines_filter': False,
    }
}


class OptimizationUserValidationTests(TransactionTestCase):
    """Main test class for optimization user validation."""
    
    def setUp(self):
        """Set up test environment before each test."""
        super().setUp()
        
        # Create test user
        from apps.core.tests.utils import create_test_user
        self.user = create_test_user()
        
        # Clear cache for clean state
        cache.clear()
        
        # Initialize activity detector
        self.detector = SimpleSessionActivityDetector()
        
        # Performance tracking
        self.performance_metrics = {
            'page_loads': [],
            'state_transitions': [],
            'monitoring_intervals': [],
            'ui_response_times': []
        }
        
    def tearDown(self):
        """Clean up after each test."""
        super().tearDown()
        cache.clear()


class TestCoreUserJourneyOptimization(OptimizationUserValidationTests):
    """Test the complete literature review workflow with optimizations."""
    
    @pytest.mark.asyncio
    async def test_complete_9_state_workflow_performance(self, page: Page):
        """
        Test the complete 9-state workflow ensuring optimizations don't impact user experience.
        
        States: draft → defining_search → ready_to_execute → executing → 
                processing_results → ready_for_review → under_review → completed → archived
        """
        await self._login_user(page)
        
        # Measure initial page load
        start_time = time.time()
        await page.goto(f"{TEST_CONFIG['base_url']}/dashboard/")
        await page.wait_for_load_state('networkidle')
        initial_load_time = (time.time() - start_time) * 1000
        
        self.performance_metrics['page_loads'].append({
            'page': 'dashboard',
            'time': initial_load_time
        })
        
        # Create new search session (draft state)
        session_data = await self._create_search_session(page)
        session_id = session_data['session_id']
        
        # Test state transitions with performance monitoring
        await self._test_draft_to_defining_search_transition(page, session_id)
        await self._test_defining_search_configuration(page, session_id)
        await self._test_ready_to_execute_validation(page, session_id)
        await self._test_executing_phase_monitoring(page, session_id)
        await self._test_processing_results_phase(page, session_id)
        await self._test_ready_for_review_phase(page, session_id)
        await self._test_under_review_phase(page, session_id)
        await self._test_completion_phase(page, session_id)
        
        # Validate performance metrics
        avg_page_load = sum([m['time'] for m in self.performance_metrics['page_loads']]) / len(self.performance_metrics['page_loads'])
        assert avg_page_load < TEST_CONFIG['performance_threshold'], f"Average page load time {avg_page_load:.2f}ms exceeds threshold"
        
        logger.info(f"Complete workflow test completed. Average page load: {avg_page_load:.2f}ms")
    
    async def _create_search_session(self, page: Page) -> Dict[str, Any]:
        """Create a new search session and return session data."""
        # Navigate to create session
        start_time = time.time()
        await page.click('text=Create New Review')
        await page.wait_for_load_state('networkidle')
        
        # Fill in session details using healthcare scenario
        scenario = TEST_SCENARIOS['healthcare_review']
        await page.fill('[name="name"]', scenario['name'])
        await page.fill('[name="description"]', f"Automated test session: {scenario['name']}")
        
        # Submit form
        await page.click('button[type="submit"]')
        await page.wait_for_load_state('networkidle')
        
        creation_time = (time.time() - start_time) * 1000
        self.performance_metrics['page_loads'].append({
            'page': 'session_creation',
            'time': creation_time
        })
        
        # Extract session ID from URL
        current_url = page.url
        session_id = current_url.split('/')[-2]  # Assumes URL pattern /session/{id}/
        
        return {
            'session_id': session_id,
            'scenario': scenario,
            'creation_time': creation_time
        }
    
    async def _test_draft_to_defining_search_transition(self, page: Page, session_id: str):
        """Test transition from draft to defining_search state."""
        start_time = time.time()
        
        # Should be on session detail page in draft state
        await expect(page.locator('[data-testid="session-status"]')).to_contain_text('draft')
        
        # Click to start defining search
        await page.click('text=Define Search Strategy')
        await page.wait_for_load_state('networkidle')
        
        # Verify state change
        await expect(page.locator('[data-testid="session-status"]')).to_contain_text('defining_search')
        
        transition_time = (time.time() - start_time) * 1000
        self.performance_metrics['state_transitions'].append({
            'from': 'draft',
            'to': 'defining_search',
            'time': transition_time
        })
        
        # Verify monitoring interval for this state (should be 300s for defining_search)
        expected_interval = self.detector.get_monitoring_interval('defining_search')
        assert expected_interval == 300, f"Expected 300s interval for defining_search, got {expected_interval}s"
    
    async def _test_defining_search_configuration(self, page: Page, session_id: str):
        """Test PIC framework configuration with guidelines filter."""
        scenario = TEST_SCENARIOS['healthcare_review']
        
        start_time = time.time()
        
        # Fill in PIC framework
        await page.fill('[name="population"]', scenario['population'])
        await page.fill('[name="interest"]', scenario['interest'])
        await page.fill('[name="context"]', scenario['context'])
        
        # Test guidelines filter toggle
        if scenario['guidelines_filter']:
            await page.check('[name="use_guidelines_filter"]')
        
        # Verify query generation preview updates
        await page.wait_for_selector('[data-testid="query-preview"]', timeout=TEST_CONFIG['timeout_short'])
        
        # Save search strategy
        await page.click('button[type="submit"]')
        await page.wait_for_load_state('networkidle')
        
        config_time = (time.time() - start_time) * 1000
        self.performance_metrics['ui_response_times'].append({
            'action': 'pic_configuration',
            'time': config_time
        })
        
        assert config_time < TEST_CONFIG['performance_threshold'], f"PIC configuration took too long: {config_time:.2f}ms"
    
    async def _test_ready_to_execute_validation(self, page: Page, session_id: str):
        """Test ready_to_execute state and validation."""
        # Should automatically transition to ready_to_execute
        await expect(page.locator('[data-testid="session-status"]')).to_contain_text('ready_to_execute')
        
        # Verify monitoring interval (300s for ready_to_execute)
        expected_interval = self.detector.get_monitoring_interval('ready_to_execute')
        assert expected_interval == 300
        
        # Test validation UI
        await page.click('text=Validate Search Strategy')
        await page.wait_for_selector('[data-testid="validation-results"]', timeout=TEST_CONFIG['timeout_medium'])
        
        # Start execution
        await page.click('text=Start Search Execution')
        await page.wait_for_load_state('networkidle')
    
    async def _test_executing_phase_monitoring(self, page: Page, session_id: str):
        """Test the executing phase with optimized monitoring."""
        # Should be in executing state
        await expect(page.locator('[data-testid="session-status"]')).to_contain_text('executing')
        
        # Verify this is an active state with 60s monitoring interval
        expected_interval = self.detector.get_monitoring_interval('executing')
        assert expected_interval == 60, f"Expected 60s interval for executing state, got {expected_interval}s"
        
        # Test real-time progress updates
        start_time = time.time()
        
        # Monitor progress updates - should see updates within monitoring interval
        progress_updates = 0
        timeout_seconds = 180  # 3 minutes max wait
        
        while time.time() - start_time < timeout_seconds:
            try:
                # Check for progress updates
                progress_element = await page.wait_for_selector(
                    '[data-testid="execution-progress"]', 
                    timeout=5000
                )
                current_progress = await progress_element.inner_text()
                
                if 'completed' in current_progress.lower():
                    break
                    
                progress_updates += 1
                await asyncio.sleep(10)  # Wait 10 seconds between checks
                
            except Exception as e:
                logger.warning(f"Progress check failed: {e}")
                break
        
        # Record monitoring effectiveness
        self.performance_metrics['monitoring_intervals'].append({
            'state': 'executing',
            'expected_interval': 60,
            'progress_updates': progress_updates,
            'total_time': time.time() - start_time
        })
    
    async def _test_processing_results_phase(self, page: Page, session_id: str):
        """Test processing_results phase with active monitoring."""
        # Wait for automatic transition to processing_results
        await expect(page.locator('[data-testid="session-status"]')).to_contain_text('processing_results')
        
        # Verify active monitoring interval (60s)
        expected_interval = self.detector.get_monitoring_interval('processing_results')
        assert expected_interval == 60
        
        # Monitor automatic processing
        start_time = time.time()
        max_wait = 300  # 5 minutes
        
        while time.time() - start_time < max_wait:
            current_status = await page.locator('[data-testid="session-status"]').inner_text()
            if 'ready_for_review' in current_status:
                break
            await asyncio.sleep(15)
        
        processing_time = time.time() - start_time
        self.performance_metrics['state_transitions'].append({
            'from': 'processing_results',
            'to': 'ready_for_review',
            'time': processing_time * 1000,
            'automatic': True
        })
    
    async def _test_ready_for_review_phase(self, page: Page, session_id: str):
        """Test ready_for_review phase with reduced monitoring."""
        await expect(page.locator('[data-testid="session-status"]')).to_contain_text('ready_for_review')
        
        # Verify reduced monitoring interval (600s)
        expected_interval = self.detector.get_monitoring_interval('ready_for_review')
        assert expected_interval == 600
        
        # Test UI remains responsive despite reduced monitoring
        start_time = time.time()
        await page.click('text=Start Review')
        await page.wait_for_load_state('networkidle')
        
        ui_response = (time.time() - start_time) * 1000
        assert ui_response < TEST_CONFIG['performance_threshold']
        
        self.performance_metrics['ui_response_times'].append({
            'action': 'start_review',
            'time': ui_response
        })
    
    async def _test_under_review_phase(self, page: Page, session_id: str):
        """Test under_review phase with manual review interface."""
        await expect(page.locator('[data-testid="session-status"]')).to_contain_text('under_review')
        
        # Verify reduced monitoring interval (600s)
        expected_interval = self.detector.get_monitoring_interval('under_review')
        assert expected_interval == 600
        
        # Test review interface responsiveness
        review_actions = ['include', 'exclude', 'include', 'exclude']
        
        for i, action in enumerate(review_actions):
            start_time = time.time()
            
            # Find result item and make decision
            result_selector = f'[data-testid="result-{i}"]'
            await page.wait_for_selector(result_selector, timeout=TEST_CONFIG['timeout_short'])
            
            button_selector = f'{result_selector} button[data-action="{action}"]'
            await page.click(button_selector)
            
            # Wait for UI update
            await page.wait_for_selector(f'{result_selector}[data-decision="{action}"]', timeout=TEST_CONFIG['timeout_short'])
            
            action_time = (time.time() - start_time) * 1000
            self.performance_metrics['ui_response_times'].append({
                'action': f'review_{action}',
                'time': action_time
            })
        
        # Complete review
        await page.click('text=Complete Review')
        await page.wait_for_load_state('networkidle')
    
    async def _test_completion_phase(self, page: Page, session_id: str):
        """Test completion and archival phases."""
        await expect(page.locator('[data-testid="session-status"]')).to_contain_text('completed')
        
        # Verify dormant monitoring interval (3600s)
        expected_interval = self.detector.get_monitoring_interval('completed')
        assert expected_interval == 3600
        
        # Test report generation
        start_time = time.time()
        await page.click('text=Generate PRISMA Report')
        
        # Wait for download or report display
        await page.wait_for_selector('[data-testid="report-ready"]', timeout=TEST_CONFIG['timeout_long'])
        
        report_time = (time.time() - start_time) * 1000
        self.performance_metrics['ui_response_times'].append({
            'action': 'generate_report',
            'time': report_time
        })
        
        # Test archival
        await page.click('text=Archive Session')
        await page.wait_for_load_state('networkidle')
        await expect(page.locator('[data-testid="session-status"]')).to_contain_text('archived')
        
        # Verify archived state monitoring interval (3600s)
        expected_interval = self.detector.get_monitoring_interval('archived')
        assert expected_interval == 3600
    
    async def _login_user(self, page: Page):
        """Log in test user."""
        await page.goto(f"{TEST_CONFIG['base_url']}/accounts/login/")
        await page.fill('[name="username"]', 'testuser')
        await page.fill('[name="password"]', 'testpass123')
        await page.click('button[type="submit"]')
        await page.wait_for_load_state('networkidle')


class TestPerformanceImpactValidation(OptimizationUserValidationTests):
    """Test performance impacts of the optimization implementation."""
    
    @pytest.mark.asyncio
    async def test_unified_monitoring_frequency_optimization(self, page: Page):
        """Test that unified monitoring runs at 120s interval instead of 30s."""
        await self._login_user(page)
        
        # Monitor Celery Beat schedule through admin or API
        await page.goto(f"{TEST_CONFIG['base_url']}/admin/")
        
        # Navigate to Django admin (assuming admin access)
        await page.goto(f"{TEST_CONFIG['base_url']}/admin/django_celery_beat/periodictask/")
        
        # Find unified monitoring task
        unified_task_row = page.locator('tr:has-text("unified-session-monitor")')
        await expect(unified_task_row).to_be_visible()
        
        # Verify interval (should be 120.0 seconds)
        interval_cell = unified_task_row.locator('td:nth-child(4)')  # Adjust based on admin layout
        interval_text = await interval_cell.inner_text()
        
        # The exact format may vary, but should indicate 120 seconds
        assert '120' in interval_text or '2 minute' in interval_text.lower()
        
        logger.info("Verified unified monitoring runs at 120s interval (optimized from 30s)")
    
    @pytest.mark.asyncio
    async def test_activity_based_monitoring_intervals(self, page: Page):
        """Test that different session states use appropriate monitoring intervals."""
        await self._login_user(page)
        
        # Create sessions in different states for testing
        test_sessions = await self._create_test_sessions_in_various_states()
        
        # Test each session's monitoring interval
        for session_data in test_sessions:
            session = session_data['session']
            expected_interval = session_data['expected_interval']
            
            # Verify the activity detector returns correct interval
            actual_interval = self.detector.get_monitoring_interval(session.status)
            assert actual_interval == expected_interval, \
                f"Session {session.id} in state '{session.status}' should have {expected_interval}s interval, got {actual_interval}s"
            
            # Test should_monitor_session logic
            should_monitor = self.detector.should_monitor_session(str(session.id), session.status)
            assert should_monitor, f"New session {session.id} should be monitored initially"
            
            # Update last monitored
            self.detector.update_last_monitored(str(session.id), session.status)
            
            # Should not monitor again immediately
            should_monitor_again = self.detector.should_monitor_session(str(session.id), session.status)
            assert not should_monitor_again, f"Session {session.id} should not be monitored again immediately"
        
        logger.info("Verified activity-based monitoring intervals for all session states")
    
    async def _create_test_sessions_in_various_states(self) -> List[Dict[str, Any]]:
        """Create test sessions in various states for interval testing."""
        sessions = []
        
        state_intervals = {
            'draft': 300,
            'defining_search': 300,
            'ready_to_execute': 300,
            'executing': 60,
            'processing_results': 60,
            'ready_for_review': 600,
            'under_review': 600,
            'completed': 3600,
            'archived': 3600,
        }
        
        with transaction.atomic():
            for status, expected_interval in state_intervals.items():
                session = SearchSession.objects.create(
                    name=f"Test Session - {status}",
                    description=f"Test session in {status} state",
                    status=status,
                    created_by=self.user,
                )
                
                sessions.append({
                    'session': session,
                    'expected_interval': expected_interval
                })
        
        return sessions
    
    @pytest.mark.asyncio 
    async def test_reduced_background_load_impact(self, page: Page):
        """Test that reduced background load doesn't impact UI responsiveness."""
        await self._login_user(page)
        
        # Measure dashboard load times with multiple sessions
        load_times = []
        
        for i in range(5):  # Test 5 page loads
            start_time = time.time()
            await page.goto(f"{TEST_CONFIG['base_url']}/dashboard/")
            await page.wait_for_load_state('networkidle')
            load_time = (time.time() - start_time) * 1000
            load_times.append(load_time)
            
            # Brief pause between loads
            await asyncio.sleep(1)
        
        # Calculate statistics
        avg_load_time = sum(load_times) / len(load_times)
        max_load_time = max(load_times)
        
        # Verify performance is acceptable
        assert avg_load_time < TEST_CONFIG['performance_threshold'], \
            f"Average dashboard load time {avg_load_time:.2f}ms exceeds threshold"
        
        assert max_load_time < TEST_CONFIG['performance_threshold'] * 1.5, \
            f"Max dashboard load time {max_load_time:.2f}ms is too high"
        
        self.performance_metrics['page_loads'].extend([
            {'page': 'dashboard_repeated', 'time': t} for t in load_times
        ])
        
        logger.info(f"Dashboard load times - Avg: {avg_load_time:.2f}ms, Max: {max_load_time:.2f}ms")


class TestEdgeCasesAndErrorScenarios(OptimizationUserValidationTests):
    """Test edge cases and error handling with optimizations."""
    
    @pytest.mark.asyncio
    async def test_network_interruption_handling(self, page: Page):
        """Test behavior during network connectivity issues."""
        await self._login_user(page)
        
        # Start a session
        await page.goto(f"{TEST_CONFIG['base_url']}/dashboard/")
        await page.click('text=Create New Review')
        
        # Simulate network interruption by intercepting requests
        await page.route("**/api/**", lambda route: route.abort())
        
        # Try to perform actions that require network
        start_time = time.time()
        try:
            await page.click('button[type="submit"]', timeout=TEST_CONFIG['timeout_short'])
            await page.wait_for_load_state('networkidle', timeout=TEST_CONFIG['timeout_short'])
        except Error:
            pass  # Expected to fail
        
        # Verify error handling UI appears
        error_message = page.locator('[data-testid="error-message"]')
        await expect(error_message).to_be_visible()
        
        # Restore network
        await page.unroute("**/api/**")
        
        # Verify recovery
        await page.reload()
        await page.wait_for_load_state('networkidle')
        
        recovery_time = (time.time() - start_time) * 1000
        self.performance_metrics['ui_response_times'].append({
            'action': 'network_recovery',
            'time': recovery_time
        })
        
        logger.info(f"Network interruption recovery time: {recovery_time:.2f}ms")
    
    @pytest.mark.asyncio
    async def test_concurrent_user_operations(self, page: Page):
        """Test concurrent user operations with optimized monitoring."""
        await self._login_user(page)
        
        # Create multiple sessions to simulate load
        session_ids = []
        
        for i in range(3):
            await page.goto(f"{TEST_CONFIG['base_url']}/dashboard/")
            await page.click('text=Create New Review')
            
            await page.fill('[name="name"]', f"Concurrent Test Session {i+1}")
            await page.fill('[name="description"]', f"Testing concurrent operations {i+1}")
            
            start_time = time.time()
            await page.click('button[type="submit"]')
            await page.wait_for_load_state('networkidle')
            
            # Extract session ID
            current_url = page.url
            session_id = current_url.split('/')[-2]
            session_ids.append(session_id)
            
            creation_time = (time.time() - start_time) * 1000
            self.performance_metrics['ui_response_times'].append({
                'action': f'concurrent_session_create_{i+1}',
                'time': creation_time
            })
        
        # Verify all sessions are accessible
        for session_id in session_ids:
            await page.goto(f"{TEST_CONFIG['base_url']}/session/{session_id}/")
            await expect(page.locator('[data-testid="session-status"]')).to_be_visible()
        
        logger.info(f"Successfully created and accessed {len(session_ids)} concurrent sessions")
    
    @pytest.mark.asyncio
    async def test_session_state_transition_errors(self, page: Page):
        """Test error handling for invalid state transitions."""
        await self._login_user(page)
        
        # Create a session and try invalid transitions
        await page.goto(f"{TEST_CONFIG['base_url']}/dashboard/")
        await page.click('text=Create New Review')
        
        await page.fill('[name="name"]', "State Transition Test")
        await page.click('button[type="submit"]')
        await page.wait_for_load_state('networkidle')
        
        # Should be in draft state - try to jump to invalid state
        # This would typically be done through API manipulation or developer tools
        await page.evaluate("""
            // Simulate direct API call to invalid transition
            fetch('/api/session/invalid-transition/', {
                method: 'POST',
                headers: {'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value},
                body: JSON.stringify({state: 'completed'})
            }).catch(err => console.log('Expected error:', err));
        """)
        
        # Verify error handling in UI
        await page.wait_for_timeout(2000)  # Brief wait for potential error display
        
        # Session should still be in valid state
        await expect(page.locator('[data-testid="session-status"]')).to_contain_text('draft')
        
        logger.info("Verified invalid state transition error handling")


class TestSystemLoadAndScalability(OptimizationUserValidationTests):
    """Test system behavior under load with optimizations."""
    
    @pytest.mark.asyncio
    async def test_multiple_active_sessions_performance(self, page: Page):
        """Test performance with multiple active sessions using optimized monitoring."""
        await self._login_user(page)
        
        # Create multiple sessions in active states
        active_sessions = []
        
        # Create sessions that will be in different active states
        test_scenarios = [
            ('executing', TEST_SCENARIOS['healthcare_review']),
            ('processing_results', TEST_SCENARIOS['education_review']),
            ('executing', TEST_SCENARIOS['healthcare_review']),
        ]
        
        for i, (target_state, scenario) in enumerate(test_scenarios):
            session_start = time.time()
            
            # Create session
            await page.goto(f"{TEST_CONFIG['base_url']}/dashboard/")
            await page.click('text=Create New Review')
            
            await page.fill('[name="name"]', f"{scenario['name']} - Load Test {i+1}")
            await page.click('button[type="submit"]')
            await page.wait_for_load_state('networkidle')
            
            # Configure and advance to target state
            session_id = page.url.split('/')[-2]
            await self._advance_session_to_state(page, session_id, target_state, scenario)
            
            session_time = (time.time() - session_start) * 1000
            active_sessions.append({
                'id': session_id,
                'state': target_state,
                'setup_time': session_time
            })
        
        # Test dashboard performance with multiple active sessions
        dashboard_times = []
        for i in range(5):
            start_time = time.time()
            await page.goto(f"{TEST_CONFIG['base_url']}/dashboard/")
            await page.wait_for_load_state('networkidle')
            dashboard_time = (time.time() - start_time) * 1000
            dashboard_times.append(dashboard_time)
            
            await asyncio.sleep(2)  # Brief pause between loads
        
        avg_dashboard_time = sum(dashboard_times) / len(dashboard_times)
        
        # Verify performance remains acceptable with multiple active sessions
        assert avg_dashboard_time < TEST_CONFIG['performance_threshold'], \
            f"Dashboard performance degraded with active sessions: {avg_dashboard_time:.2f}ms"
        
        self.performance_metrics['page_loads'].extend([
            {'page': 'dashboard_with_active_sessions', 'time': t} for t in dashboard_times
        ])
        
        logger.info(f"Dashboard performance with {len(active_sessions)} active sessions: {avg_dashboard_time:.2f}ms avg")
    
    async def _advance_session_to_state(self, page: Page, session_id: str, target_state: str, scenario: Dict):
        """Advance a session to a specific state for testing."""
        # This is a simplified version - in reality, you'd need to properly
        # configure the search strategy and handle state transitions
        
        if target_state in ['executing', 'processing_results']:
            # Configure search strategy
            await page.click('text=Define Search Strategy')
            await page.wait_for_load_state('networkidle')
            
            await page.fill('[name="population"]', scenario['population'])
            await page.fill('[name="interest"]', scenario['interest'])
            await page.fill('[name="context"]', scenario['context'])
            
            await page.click('button[type="submit"]')
            await page.wait_for_load_state('networkidle')
            
            if target_state in ['executing', 'processing_results']:
                # Start execution
                await page.click('text=Start Search Execution')
                await page.wait_for_load_state('networkidle')
                
                # For processing_results, we'd wait for executing to complete
                # This is simplified for testing purposes


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """Set up test database with required data."""
    with django_db_blocker.unblock():
        # Create any required test data
        call_command('migrate', verbosity=0, interactive=False)


@pytest.fixture
def browser_context_args(browser_context_args):
    """Configure browser context for testing."""
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 720},
        "ignore_https_errors": True,
        "record_video_dir": "tests/playwright/videos/",
        "record_har_path": "tests/playwright/har/test.har",
    }


@pytest.fixture
async def page(browser, browser_context_args):
    """Create a page with proper configuration."""
    context = await browser.new_context(**browser_context_args)
    page = await context.new_page()
    
    # Enable console logging
    page.on("console", lambda msg: logger.info(f"Browser console: {msg.text}"))
    
    # Set up performance monitoring
    await page.add_init_script("""
        window.performanceData = [];
        const originalFetch = window.fetch;
        window.fetch = function(...args) {
            const start = performance.now();
            return originalFetch.apply(this, args).then(response => {
                const end = performance.now();
                window.performanceData.push({
                    url: args[0],
                    duration: end - start,
                    timestamp: Date.now()
                });
                return response;
            });
        };
    """)
    
    yield page
    
    await context.close()


if __name__ == "__main__":
    # Run specific test
    pytest.main([__file__, "-v", "--tb=short"])