"""
Performance-Focused Optimization Testing Suite

This test suite focuses specifically on measuring and validating the performance
improvements from the task optimization implementation:

1. CELERY_BEAT_SCHEDULE optimization (15+ tasks → 9 tasks)
2. Unified monitoring frequency (30s → 120s)
3. Activity-based monitoring intervals by session state
4. System load reduction and UI responsiveness

Performance Metrics Tracked:
- Page load times across different system states
- API response times during various session states  
- Background task execution frequency and efficiency
- UI responsiveness during high-load scenarios
- Memory and CPU usage patterns (where measurable)
"""

import asyncio
import logging
import time

import pytest
from django.core.cache import cache
from django.test import TransactionTestCase
from playwright.async_api import Page, expect


from .conftest_optimization import (OPTIMIZATION_TEST_CONFIG)

logger = logging.getLogger(__name__)


class PerformanceOptimizationTests(TransactionTestCase):
    """Performance-focused tests for optimization validation."""
    
    def setUp(self):
        """Set up performance testing environment."""
        super().setUp()
        cache.clear()
        
        self.performance_baselines = {
            'dashboard_load_ms': 2000,      # 2 second baseline
            'session_create_ms': 3000,      # 3 second baseline
            'state_transition_ms': 1500,    # 1.5 second baseline
            'api_response_ms': 1000,        # 1 second baseline
        }
        
        self.optimization_targets = {
            'monitoring_frequency_reduction': 4.0,  # 30s → 120s = 4x reduction
            'background_task_reduction': 1.67,     # 15 tasks → 9 tasks = 1.67x reduction
            'dormant_session_interval': 3600,      # 1 hour for dormant states
            'active_session_interval': 60,         # 1 minute for active states
        }


@pytest.mark.asyncio
class TestCeleryOptimizationPerformance:
    """Test Celery Beat schedule optimization performance impact."""
    
    async def test_unified_monitoring_frequency_validation(self, optimization_page: Page, test_helpers, performance_tracker):
        """Validate that unified monitoring runs at optimized 120s interval."""
        await test_helpers.login_user(optimization_page)
        
        # Access admin interface to validate Celery Beat configuration
        await optimization_page.goto(f"{OPTIMIZATION_TEST_CONFIG['base_url']}/admin/")
        
        # Navigate to periodic tasks
        await optimization_page.click('text=Periodic tasks')
        
        # Find unified monitoring task
        unified_task_selector = 'tr:has-text("unified-session-monitor")'
        await optimization_page.wait_for_selector(unified_task_selector)
        
        # Extract interval information
        task_row = optimization_page.locator(unified_task_selector)
        interval_text = await task_row.locator('td').nth(3).inner_text()  # Adjust based on admin layout
        
        # Verify optimization - should be 120.0 seconds
        assert '120' in interval_text or '2 minute' in interval_text.lower(), \
            f"Unified monitoring should run at 120s interval, found: {interval_text}"
        
        performance_tracker.record_monitoring_interval('unified-session-monitor', 'N/A', 120, {
            'configured_interval': interval_text,
            'validation_passed': '120' in interval_text
        })
        
        logger.info(f"✅ Unified monitoring frequency validated: {interval_text}")
    
    async def test_task_count_reduction_validation(self, optimization_page: Page, test_helpers, performance_tracker):
        """Validate that total Celery Beat tasks have been reduced from 15+ to 9."""
        await test_helpers.login_user(optimization_page)
        
        await optimization_page.goto(f"{OPTIMIZATION_TEST_CONFIG['base_url']}/admin/django_celery_beat/periodictask/")
        
        # Count total periodic tasks
        task_rows = await optimization_page.locator('tbody tr').count()
        
        # Should be around 9 tasks (allowing for some flexibility)
        assert task_rows <= 12, f"Expected ≤12 periodic tasks after optimization, found {task_rows}"
        assert task_rows >= 8, f"Expected ≥8 periodic tasks after optimization, found {task_rows}"
        
        # Verify key optimized tasks exist
        expected_tasks = [
            'unified-session-monitor',
            'monitor-workflow-health', 
            'update-session-statistics',
            'cleanup-old-sessions',
            'comprehensive-recovery',
            'warm-active-caches',
            'collect-performance-metrics',
            'cleanup-orphaned-processing',
            'optimize-database-connections'
        ]
        
        for task_name in expected_tasks:
            task_selector = f'tr:has-text("{task_name}")'
            await expect(optimization_page.locator(task_selector)).to_be_visible()
        
        performance_tracker.record_api_call('/admin/periodic-tasks', 'GET', 0, 200)  # Placeholder timing
        
        logger.info(f"✅ Task count reduction validated: {task_rows} periodic tasks found")
    
    async def test_monitoring_frequency_impact_on_ui(self, optimization_page: Page, test_helpers, performance_tracker, session_factory):
        """Test that reduced monitoring frequency doesn't impact UI responsiveness."""
        await test_helpers.login_user(optimization_page)
        
        # Create sessions in various states to generate monitoring load
        _sessions = session_factory.create_sessions_in_all_states()
        
        # Measure dashboard performance with active monitoring
        dashboard_load_times = []
        
        for i in range(10):  # 10 measurements over time
            start_time = time.time()
            
            await optimization_page.goto(f"{OPTIMIZATION_TEST_CONFIG['base_url']}/dashboard/")
            await optimization_page.wait_for_load_state('networkidle')
            
            load_time = (time.time() - start_time) * 1000
            dashboard_load_times.append(load_time)
            
            performance_tracker.record_page_load(f'dashboard_with_monitoring_{i+1}', load_time)
            
            # Wait 30 seconds between measurements to observe monitoring impact
            await asyncio.sleep(30)
        
        # Calculate statistics
        avg_load_time = sum(dashboard_load_times) / len(dashboard_load_times)
        max_load_time = max(dashboard_load_times)
        min_load_time = min(dashboard_load_times)
        
        # Validate performance remains acceptable
        assert avg_load_time < OPTIMIZATION_TEST_CONFIG['performance_threshold'], \
            f"Average dashboard load {avg_load_time:.2f}ms exceeds threshold with active monitoring"
        
        # Verify consistency (max shouldn't be more than 2x avg)
        assert max_load_time < avg_load_time * 2, \
            f"Load time inconsistency detected: max {max_load_time:.2f}ms vs avg {avg_load_time:.2f}ms"
        
        logger.info(f"✅ UI responsiveness maintained with optimized monitoring: avg {avg_load_time:.2f}ms, range {min_load_time:.2f}-{max_load_time:.2f}ms")


@pytest.mark.asyncio
class TestActivityBasedMonitoringPerformance:
    """Test activity-based monitoring interval performance."""
    
    async def test_active_state_monitoring_performance(self, optimization_page: Page, test_helpers, performance_tracker, session_factory, activity_detector):
        """Test performance of active state monitoring (executing, processing_results)."""
        await test_helpers.login_user(optimization_page)
        
        # Create sessions in active states
        executing_session = session_factory.create_session('executing', 'healthcare_falls_prevention')
        processing_session = session_factory.create_session('processing_results', 'education_digital_literacy')
        
        # Simulate active executions
        session_factory.simulate_active_execution(executing_session)
        session_factory.simulate_active_execution(processing_session)
        
        active_sessions = [executing_session, processing_session]
        monitoring_results = []
        
        # Monitor for 5 minutes (should see multiple monitoring cycles)
        test_duration = 300  # 5 minutes
        start_time = time.time()
        
        while (time.time() - start_time) < test_duration:
            for session in active_sessions:
                # Test monitoring decision
                should_monitor = activity_detector.should_monitor_session(str(session.id), session.status)
                
                monitoring_results.append({
                    'session_id': str(session.id),
                    'state': session.status,
                    'should_monitor': should_monitor,
                    'timestamp': time.time(),
                    'expected_interval': 60  # Active states should be 60s
                })
                
                if should_monitor:
                    activity_detector.update_last_monitored(str(session.id), session.status)
                    
                    # Test UI response during active monitoring
                    ui_start = time.time()
                    await optimization_page.goto(f"{OPTIMIZATION_TEST_CONFIG['base_url']}/session/{session.id}/")
                    await optimization_page.wait_for_load_state('networkidle')
                    ui_time = (time.time() - ui_start) * 1000
                    
                    performance_tracker.record_page_load(f'active_session_{session.status}', ui_time)
            
            await asyncio.sleep(30)  # Check every 30 seconds
        
        # Analyze monitoring frequency
        monitoring_counts = {}
        for result in monitoring_results:
            session_key = f"{result['session_id']}_{result['state']}"
            if session_key not in monitoring_counts:
                monitoring_counts[session_key] = {'monitored': 0, 'skipped': 0}
            
            if result['should_monitor']:
                monitoring_counts[session_key]['monitored'] += 1
            else:
                monitoring_counts[session_key]['skipped'] += 1
        
        # Validate monitoring frequency for active states
        for session_key, counts in monitoring_counts.items():
            total_checks = counts['monitored'] + counts['skipped']
            monitoring_rate = counts['monitored'] / total_checks if total_checks > 0 else 0
            
            # Should monitor approximately every 60 seconds (with 30s checks = ~50% rate)
            assert 0.3 <= monitoring_rate <= 0.7, \
                f"Active session monitoring rate {monitoring_rate:.2%} outside expected range for {session_key}"
        
        logger.info(f"✅ Active state monitoring performance validated: {len(monitoring_results)} checks over {test_duration}s")
    
    async def test_dormant_state_monitoring_efficiency(self, optimization_page: Page, test_helpers, performance_tracker, session_factory, activity_detector):
        """Test efficiency of dormant state monitoring (completed, archived)."""
        await test_helpers.login_user(optimization_page)
        
        # Create sessions in dormant states
        completed_session = session_factory.create_session('completed', 'mental_health_workplace')
        archived_session = session_factory.create_session('archived', 'healthcare_falls_prevention')
        
        dormant_sessions = [completed_session, archived_session]
        
        # Test monitoring behavior over 2 hours (should see minimal monitoring)
        _test_duration = 120  # 2 minutes for testing (simulate longer period)
        monitoring_checks = []
        
        for session in dormant_sessions:
            # Initial check - should monitor
            should_monitor_initial = activity_detector.should_monitor_session(str(session.id), session.status)
            assert should_monitor_initial, f"Initial check should return True for {session.status}"
            
            # Update last monitored
            activity_detector.update_last_monitored(str(session.id), session.status)
            
            # Immediate recheck - should not monitor
            should_monitor_immediate = activity_detector.should_monitor_session(str(session.id), session.status)
            assert not should_monitor_immediate, f"Immediate recheck should return False for {session.status}"
            
            monitoring_checks.append({
                'session_id': str(session.id),
                'state': session.status,
                'expected_interval': 3600,  # 1 hour
                'initial_check': should_monitor_initial,
                'immediate_check': should_monitor_immediate,
                'efficiency_validated': should_monitor_initial and not should_monitor_immediate
            })
        
        # Test UI performance when accessing dormant sessions
        dormant_ui_times = []
        
        for session in dormant_sessions:
            ui_start = time.time()
            await optimization_page.goto(f"{OPTIMIZATION_TEST_CONFIG['base_url']}/session/{session.id}/")
            await optimization_page.wait_for_load_state('networkidle')
            ui_time = (time.time() - ui_start) * 1000
            
            dormant_ui_times.append(ui_time)
            performance_tracker.record_page_load(f'dormant_session_{session.status}', ui_time)
        
        # Validate UI remains responsive for dormant sessions
        avg_dormant_ui_time = sum(dormant_ui_times) / len(dormant_ui_times)
        assert avg_dormant_ui_time < OPTIMIZATION_TEST_CONFIG['performance_threshold'], \
            f"Dormant session UI time {avg_dormant_ui_time:.2f}ms exceeds threshold"
        
        logger.info(f"✅ Dormant state monitoring efficiency validated: avg UI time {avg_dormant_ui_time:.2f}ms")
    
    async def test_review_state_monitoring_balance(self, optimization_page: Page, test_helpers, performance_tracker, session_factory, activity_detector):
        """Test balanced monitoring for review states (ready_for_review, under_review)."""
        await test_helpers.login_user(optimization_page)
        
        # Create sessions in review states
        ready_session = session_factory.create_session('ready_for_review', 'education_digital_literacy')
        under_review_session = session_factory.create_session('under_review', 'mental_health_workplace')
        
        review_sessions = [ready_session, under_review_session]
        
        # Test monitoring intervals (should be 600s = 10 minutes)
        for session in review_sessions:
            expected_interval = activity_detector.get_monitoring_interval(session.status)
            assert expected_interval == 600, \
                f"Review state {session.status} should have 600s interval, got {expected_interval}s"
            
            # Test monitoring logic
            should_monitor = activity_detector.should_monitor_session(str(session.id), session.status)
            assert should_monitor, f"Initial monitoring should be True for {session.status}"
            
            activity_detector.update_last_monitored(str(session.id), session.status)
            
            # Should not monitor again immediately
            should_monitor_again = activity_detector.should_monitor_session(str(session.id), session.status)
            assert not should_monitor_again, f"Immediate recheck should be False for {session.status}"
            
            performance_tracker.record_monitoring_interval(str(session.id), session.status, 600, {
                'initial_check': should_monitor,
                'immediate_recheck': should_monitor_again,
                'interval_validated': True
            })
        
        # Test UI responsiveness during review phase
        review_ui_times = []
        
        for session in review_sessions:
            # Navigate to session
            ui_start = time.time()
            await optimization_page.goto(f"{OPTIMIZATION_TEST_CONFIG['base_url']}/session/{session.id}/")
            await optimization_page.wait_for_load_state('networkidle')
            
            # Simulate review actions
            if session.status == 'under_review':
                # Simulate reviewing results (if UI elements exist)
                try:
                    review_buttons = await optimization_page.locator('[data-action="include"], [data-action="exclude"]').count()
                    if review_buttons > 0:
                        await optimization_page.locator('[data-action="include"]').first.click()
                        await optimization_page.wait_for_load_state('networkidle')
                except Exception:
                    pass  # Review UI might not be fully implemented
            
            ui_time = (time.time() - ui_start) * 1000
            review_ui_times.append(ui_time)
            performance_tracker.record_page_load(f'review_session_{session.status}', ui_time)
        
        avg_review_ui_time = sum(review_ui_times) / len(review_ui_times)
        assert avg_review_ui_time < OPTIMIZATION_TEST_CONFIG['performance_threshold'], \
            f"Review session UI time {avg_review_ui_time:.2f}ms exceeds threshold"
        
        logger.info(f"✅ Review state monitoring balance validated: {len(review_sessions)} sessions, avg UI {avg_review_ui_time:.2f}ms")


@pytest.mark.asyncio
class TestSystemLoadOptimization:
    """Test overall system load optimization impact."""
    
    async def test_concurrent_session_performance_with_optimization(self, optimization_page: Page, test_helpers, performance_tracker, session_factory):
        """Test system performance with multiple concurrent sessions using optimized monitoring."""
        await test_helpers.login_user(optimization_page)
        
        # Create sessions across all states to simulate realistic load
        all_state_sessions = session_factory.create_sessions_in_all_states()
        
        # Create additional active sessions to test load
        additional_active = []
        for i in range(5):
            session = session_factory.create_session('executing', 'healthcare_falls_prevention', 
                                                   name=f"Load Test Executing {i+1}")
            session_factory.simulate_active_execution(session)
            additional_active.append(session)
        
        total_sessions = len(all_state_sessions) + len(additional_active)
        
        # Test dashboard performance with high session count
        dashboard_load_times = []
        
        for i in range(10):
            start_time = time.time()
            
            await optimization_page.goto(f"{OPTIMIZATION_TEST_CONFIG['base_url']}/dashboard/")
            await optimization_page.wait_for_load_state('networkidle')
            
            # Verify session count in UI
            session_count_element = optimization_page.locator('[data-testid="session-count"]')
            if await session_count_element.count() > 0:
                displayed_count = await session_count_element.inner_text()
                logger.info(f"Dashboard showing {displayed_count} sessions")
            
            load_time = (time.time() - start_time) * 1000
            dashboard_load_times.append(load_time)
            
            performance_tracker.record_page_load(f'dashboard_high_load_{i+1}', load_time, {
                'total_sessions': total_sessions,
                'active_sessions': len(additional_active)
            })
            
            await asyncio.sleep(5)  # Brief pause between loads
        
        # Analyze performance under load
        avg_load_time = sum(dashboard_load_times) / len(dashboard_load_times)
        max_load_time = max(dashboard_load_times)
        min_load_time = min(dashboard_load_times)
        
        # Performance should remain acceptable even with high session count
        assert avg_load_time < OPTIMIZATION_TEST_CONFIG['performance_threshold'], \
            f"Dashboard performance degraded under load: {avg_load_time:.2f}ms avg with {total_sessions} sessions"
        
        # Consistency check
        load_time_variance = max_load_time - min_load_time
        assert load_time_variance < OPTIMIZATION_TEST_CONFIG['performance_threshold'], \
            f"Load time variance too high: {load_time_variance:.2f}ms with {total_sessions} sessions"
        
        logger.info(f"✅ High load performance validated: {total_sessions} sessions, avg load {avg_load_time:.2f}ms")
    
    async def test_memory_efficiency_with_optimized_monitoring(self, optimization_page: Page, test_helpers, performance_tracker, session_factory):
        """Test that optimized monitoring doesn't cause memory issues."""
        await test_helpers.login_user(optimization_page)
        
        # Create sessions and let them run through monitoring cycles
        sessions = []
        for state in ['executing', 'processing_results', 'ready_for_review', 'under_review', 'completed']:
            for i in range(3):  # 3 sessions per state
                session = session_factory.create_session(state, 'healthcare_falls_prevention',
                                                        name=f"Memory Test {state} {i+1}")
                sessions.append(session)
        
        # Test repeated dashboard access over time (simulating user workflow)
        memory_test_duration = 300  # 5 minutes
        page_loads = 0
        start_time = time.time()
        
        while (time.time() - start_time) < memory_test_duration:
            # Dashboard access
            await optimization_page.goto(f"{OPTIMIZATION_TEST_CONFIG['base_url']}/dashboard/")
            await optimization_page.wait_for_load_state('networkidle')
            
            # Access a few session detail pages
            for session in sessions[:3]:  # Just first 3 to avoid too much load
                await optimization_page.goto(f"{OPTIMIZATION_TEST_CONFIG['base_url']}/session/{session.id}/")
                await optimization_page.wait_for_load_state('networkidle')
            
            page_loads += 4  # Dashboard + 3 session pages
            
            # Check for JavaScript errors or memory warnings
            js_errors = await optimization_page.evaluate("""
                () => {
                    const errors = window.optimizationTestData?.errors || [];
                    return errors.filter(e => e.type === 'memory_warning' || e.message.includes('memory'));
                }
            """)
            
            if js_errors:
                logger.warning(f"Memory-related JavaScript errors detected: {js_errors}")
            
            performance_tracker.record_api_call('memory_test_cycle', 'GET', 0, 200)
            
            await asyncio.sleep(10)  # 10 second intervals
        
        # Validate no significant memory issues detected
        final_js_errors = await optimization_page.evaluate("() => window.optimizationTestData?.errors || []")
        memory_errors = [e for e in final_js_errors if 'memory' in str(e).lower()]
        
        assert len(memory_errors) == 0, f"Memory-related errors detected during optimization test: {memory_errors}"
        
        logger.info(f"✅ Memory efficiency validated: {page_loads} page loads over {memory_test_duration}s with {len(sessions)} sessions")
    
    async def test_background_task_reduction_impact(self, optimization_page: Page, test_helpers, performance_tracker):
        """Test the impact of reduced background task frequency on system performance."""
        await test_helpers.login_user(optimization_page)
        
        # Monitor system responsiveness over time during peak monitoring periods
        # (when unified monitor would be most active)
        
        responsiveness_tests = [
            {'page': 'dashboard', 'url': '/dashboard/'},
            {'page': 'create_session', 'url': '/session/create/'},
            {'page': 'admin_overview', 'url': '/admin/'},
        ]
        
        # Test at different times to capture monitoring cycles
        test_intervals = [0, 60, 120, 180, 240]  # Every minute for 4 minutes
        
        for interval in test_intervals:
            if interval > 0:
                await asyncio.sleep(60)  # Wait 1 minute between tests
            
            for test in responsiveness_tests:
                start_time = time.time()
                
                try:
                    await optimization_page.goto(f"{OPTIMIZATION_TEST_CONFIG['base_url']}{test['url']}")
                    await optimization_page.wait_for_load_state('networkidle', timeout=OPTIMIZATION_TEST_CONFIG['timeout_medium'])
                    
                    load_time = (time.time() - start_time) * 1000
                    
                    performance_tracker.record_page_load(f"{test['page']}_interval_{interval}", load_time, {
                        'test_interval': interval,
                        'monitoring_phase': 'background_optimization_test'
                    })
                    
                    # Verify performance remains consistent
                    assert load_time < OPTIMIZATION_TEST_CONFIG['performance_threshold'], \
                        f"{test['page']} load time {load_time:.2f}ms exceeds threshold at interval {interval}s"
                    
                except Exception as e:
                    performance_tracker.record_error('page_load_error', str(e), {
                        'page': test['page'],
                        'interval': interval
                    })
                    raise
        
        logger.info(f"✅ Background task reduction impact validated across {len(test_intervals) * len(responsiveness_tests)} tests")


# Test data and helper functions
@pytest.fixture
def performance_test_scenarios():
    """Provide performance test scenarios."""
    return {
        'load_testing': {
            'concurrent_sessions': 15,
            'session_states': ['executing', 'processing_results', 'ready_for_review', 'under_review', 'completed'],
            'test_duration_minutes': 10,
        },
        'monitoring_validation': {
            'active_states': ['executing', 'processing_results'],
            'review_states': ['ready_for_review', 'under_review'], 
            'dormant_states': ['completed', 'archived'],
            'test_cycles': 20,
        },
        'ui_responsiveness': {
            'page_load_threshold_ms': 2000,
            'api_response_threshold_ms': 1000,
            'consistency_variance_threshold_ms': 1000,
        }
    }


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "--maxfail=5"])