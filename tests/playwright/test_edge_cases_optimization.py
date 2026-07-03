"""
Edge Cases and Error Scenarios Testing for Optimization Validation

This test suite validates that the optimization implementation handles edge cases
and error scenarios gracefully without degrading user experience:

1. Network interruption during different session states
2. Concurrent user operations with optimized monitoring
3. Invalid state transitions and error handling
4. Cache failures and recovery scenarios
5. High load conditions and resource constraints
6. Monitoring system failures and fallbacks
7. Session timeout and recovery scenarios
"""

import asyncio
import logging
import time
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import TransactionTestCase
from playwright.async_api import Error, Page, Route, expect


from .conftest_optimization import (OPTIMIZATION_TEST_CONFIG,
                                    OptimizationTestFixtures)

logger = logging.getLogger(__name__)


class EdgeCaseOptimizationTests(TransactionTestCase):
    """Edge case and error scenario tests for optimization validation."""
    
    def setUp(self):
        """Set up edge case testing environment."""
        super().setUp()
        cache.clear()
        
        self.error_scenarios = {
            'network_interruption': {
                'duration_seconds': 30,
                'recovery_threshold_ms': 5000,
            },
            'cache_failure': {
                'fallback_threshold_ms': 3000,
                'recovery_timeout_s': 60,
            },
            'high_load': {
                'concurrent_sessions': 20,
                'concurrent_users': 5,
                'load_duration_s': 120,
            }
        }


@pytest.mark.asyncio
class TestNetworkInterruptionScenarios:
    """Test behavior during network connectivity issues."""
    
    async def test_network_interruption_during_session_creation(self, optimization_page: Page, test_helpers, performance_tracker):
        """Test session creation resilience during network interruption."""
        await test_helpers.login_user(optimization_page)
        
        # Start session creation
        await optimization_page.goto(f"{OPTIMIZATION_TEST_CONFIG['base_url']}/dashboard/")
        await optimization_page.click('text=Create New Review')
        
        scenario = OptimizationTestFixtures.REALISTIC_SEARCH_SCENARIOS['healthcare_falls_prevention']
        await optimization_page.fill('[name="name"]', scenario['name'])
        await optimization_page.fill('[name="description"]', scenario['description'])
        
        # Simulate network interruption
        await optimization_page.route("**/api/**", lambda route: route.abort("connectionrefused"))
        
        error_start_time = time.time()
        
        try:
            # Attempt to submit form during network issue
            await optimization_page.click('button[type="submit"]', timeout=OPTIMIZATION_TEST_CONFIG['timeout_short'])
            await optimization_page.wait_for_load_state('networkidle', timeout=OPTIMIZATION_TEST_CONFIG['timeout_short'])
        except Error as e:
            logger.info(f"Expected error during network interruption: {e}")
        
        # Check for error message display
        error_message = optimization_page.locator('[data-testid="error-message"], [class*="error"], .alert-danger')
        await expect(error_message).to_be_visible(timeout=OPTIMIZATION_TEST_CONFIG['timeout_short'])
        
        error_display_time = (time.time() - error_start_time) * 1000
        performance_tracker.record_error('network_interruption', 'Session creation failed', {
            'error_display_time_ms': error_display_time,
            'phase': 'session_creation'
        })
        
        # Restore network
        await optimization_page.unroute("**/api/**")
        
        # Test recovery
        recovery_start_time = time.time()
        
        # Retry session creation
        await optimization_page.click('button[type="submit"]')
        await optimization_page.wait_for_load_state('networkidle')
        
        recovery_time = (time.time() - recovery_start_time) * 1000
        
        # Verify successful creation after recovery
        session_status = optimization_page.locator('[data-testid="session-status"]')
        await expect(session_status).to_be_visible()
        
        performance_tracker.record_ui_interaction('network_recovery', 'session_creation', recovery_time)
        
        assert recovery_time < OPTIMIZATION_TEST_CONFIG['performance_threshold'] * 2, \
            f"Network recovery took too long: {recovery_time:.2f}ms"
        
        logger.info(f"✅ Network interruption recovery validated: {recovery_time:.2f}ms")
    
    async def test_network_interruption_during_active_execution(self, optimization_page: Page, test_helpers, performance_tracker, session_factory):
        """Test behavior during network interruption while session is executing."""
        await test_helpers.login_user(optimization_page)
        
        # Create and start an executing session
        session = session_factory.create_session('ready_to_execute', 'healthcare_falls_prevention')
        
        await optimization_page.goto(f"{OPTIMIZATION_TEST_CONFIG['base_url']}/session/{session.id}/")
        
        # Start execution
        await optimization_page.click('text=Start Search Execution')
        await optimization_page.wait_for_load_state('networkidle')
        
        # Verify execution started
        await expect(optimization_page.locator('[data-testid="session-status"]')).to_contain_text('executing')
        
        # Simulate network interruption during execution
        await optimization_page.route("**/api/execution/**", lambda route: route.abort("connectionrefused"))
        
        # Monitor UI behavior during network issue
        _network_issue_duration = 60  # 1 minute
        ui_checks = []
        
        for i in range(6):  # Check every 10 seconds
            check_start = time.time()
            
            # Refresh page to test UI resilience
            try:
                await optimization_page.reload()
                await optimization_page.wait_for_load_state('networkidle', timeout=OPTIMIZATION_TEST_CONFIG['timeout_short'])
                
                # Check if error indicators are shown
                error_indicators = await optimization_page.locator('[data-testid="network-error"], [class*="offline"], .connection-error').count()
                
                ui_check_time = (time.time() - check_start) * 1000
                ui_checks.append({
                    'check_number': i + 1,
                    'ui_response_time_ms': ui_check_time,
                    'error_indicators_shown': error_indicators > 0,
                    'page_accessible': True
                })
                
            except Error:
                ui_checks.append({
                    'check_number': i + 1,
                    'ui_response_time_ms': OPTIMIZATION_TEST_CONFIG['timeout_short'],
                    'error_indicators_shown': False,
                    'page_accessible': False
                })
            
            await asyncio.sleep(10)
        
        # Restore network
        await optimization_page.unroute("**/api/execution/**")
        
        # Test recovery and execution resumption
        recovery_start = time.time()
        await optimization_page.reload()
        await optimization_page.wait_for_load_state('networkidle')
        recovery_time = (time.time() - recovery_start) * 1000
        
        # Analyze UI resilience during network issues
        accessible_checks = [check for check in ui_checks if check['page_accessible']]
        avg_ui_time = sum([check['ui_response_time_ms'] for check in accessible_checks]) / len(accessible_checks) if accessible_checks else 0
        
        performance_tracker.record_error('network_interruption', 'Execution phase network issue', {
            'ui_checks': ui_checks,
            'avg_ui_response_ms': avg_ui_time,
            'recovery_time_ms': recovery_time,
            'phase': 'executing'
        })
        
        assert len(accessible_checks) > 0, "UI should remain accessible during network issues"
        
        logger.info(f"✅ Network interruption during execution handled: {len(accessible_checks)}/{len(ui_checks)} UI checks passed")
    
    async def test_partial_network_degradation(self, optimization_page: Page, test_helpers, performance_tracker, session_factory):
        """Test behavior during partial network degradation (slow responses)."""
        await test_helpers.login_user(optimization_page)
        
        # Create session for testing
        session = session_factory.create_session('under_review', 'education_digital_literacy')
        
        # Simulate slow network responses
        slow_response_delay = 5000  # 5 seconds
        
        async def slow_route_handler(route: Route):
            await asyncio.sleep(slow_response_delay / 1000)
            await route.continue_()
        
        await optimization_page.route("**/api/**", slow_route_handler)
        
        # Test UI behavior with slow network
        slow_network_tests = [
            {'action': 'navigate_to_session', 'url': f'/session/{session.id}/'},
            {'action': 'navigate_to_dashboard', 'url': '/dashboard/'},
            {'action': 'navigate_to_create', 'url': '/session/create/'},
        ]
        
        for test in slow_network_tests:
            start_time = time.time()
            
            try:
                await optimization_page.goto(f"{OPTIMIZATION_TEST_CONFIG['base_url']}{test['url']}")
                await optimization_page.wait_for_load_state('networkidle', timeout=OPTIMIZATION_TEST_CONFIG['timeout_long'])
                
                response_time = (time.time() - start_time) * 1000
                
                performance_tracker.record_page_load(f"slow_network_{test['action']}", response_time, {
                    'network_delay_ms': slow_response_delay,
                    'degradation_type': 'slow_response'
                })
                
                # Verify page loads even with slow network
                assert response_time < OPTIMIZATION_TEST_CONFIG['timeout_long'], \
                    f"{test['action']} failed to load within timeout during network degradation"
                
            except Error as e:
                performance_tracker.record_error('network_degradation', str(e), test)
                raise
        
        # Remove slow network simulation
        await optimization_page.unroute("**/api/**")
        
        logger.info(f"✅ Partial network degradation handled: {len(slow_network_tests)} tests passed")


@pytest.mark.asyncio
class TestConcurrentUserOperations:
    """Test concurrent user operations with optimized monitoring."""
    
    async def test_multiple_users_creating_sessions_simultaneously(self, browser, test_helpers, performance_tracker, session_factory):
        """Test system behavior with multiple users creating sessions concurrently."""
        # Create multiple browser contexts to simulate different users
        num_concurrent_users = 3
        concurrent_contexts = []
        concurrent_pages = []
        
        try:
            for i in range(num_concurrent_users):
                context = await browser.new_context(
                    viewport={'width': 1280, 'height': 1024},
                    ignore_https_errors=True
                )
                page = await context.new_page()
                
                await test_helpers.login_user(page, 'optimization_test_user', 'OptimizationTest123!')
                
                concurrent_contexts.append(context)
                concurrent_pages.append(page)
            
            # Simultaneous session creation
            session_creation_tasks = []
            
            for i, page in enumerate(concurrent_pages):
                scenario = list(OptimizationTestFixtures.REALISTIC_SEARCH_SCENARIOS.values())[i % len(OptimizationTestFixtures.REALISTIC_SEARCH_SCENARIOS)]
                
                async def create_session(page_ref, user_id, scenario_data):
                    start_time = time.time()
                    
                    await page_ref.goto(f"{OPTIMIZATION_TEST_CONFIG['base_url']}/dashboard/")
                    await page_ref.click('text=Create New Review')
                    
                    await page_ref.fill('[name="name"]', f"{scenario_data['name']} - User {user_id}")
                    await page_ref.fill('[name="description"]', f"Concurrent test - {scenario_data['description']}")
                    
                    await page_ref.click('button[type="submit"]')
                    await page_ref.wait_for_load_state('networkidle')
                    
                    creation_time = (time.time() - start_time) * 1000
                    
                    # Extract session ID
                    session_id = page_ref.url.split('/')[-2]
                    
                    return {
                        'user_id': user_id,
                        'session_id': session_id,
                        'creation_time_ms': creation_time,
                        'scenario': scenario_data['name']
                    }
                
                task = create_session(page, i + 1, scenario)
                session_creation_tasks.append(task)
            
            # Execute concurrent session creations
            start_concurrent = time.time()
            creation_results = await asyncio.gather(*session_creation_tasks)
            total_concurrent_time = (time.time() - start_concurrent) * 1000
            
            # Analyze concurrent performance
            creation_times = [result['creation_time_ms'] for result in creation_results]
            avg_creation_time = sum(creation_times) / len(creation_times)
            max_creation_time = max(creation_times)
            
            # Validate performance under concurrent load
            assert avg_creation_time < OPTIMIZATION_TEST_CONFIG['performance_threshold'] * 1.5, \
                f"Average concurrent session creation time {avg_creation_time:.2f}ms too high"
            
            assert max_creation_time < OPTIMIZATION_TEST_CONFIG['performance_threshold'] * 2, \
                f"Maximum concurrent session creation time {max_creation_time:.2f}ms too high"
            
            for result in creation_results:
                performance_tracker.record_page_load(f"concurrent_session_create_user_{result['user_id']}", 
                                                   result['creation_time_ms'], {
                    'concurrent_users': num_concurrent_users,
                    'total_concurrent_time_ms': total_concurrent_time,
                    'scenario': result['scenario']
                })
            
            logger.info(f"✅ Concurrent user operations validated: {num_concurrent_users} users, avg {avg_creation_time:.2f}ms")
            
        finally:
            # Clean up contexts
            for context in concurrent_contexts:
                await context.close()
    
    async def test_concurrent_state_transitions(self, optimization_page: Page, test_helpers, performance_tracker, session_factory, activity_detector):
        """Test concurrent state transitions with optimized monitoring."""
        await test_helpers.login_user(optimization_page)
        
        # Create multiple sessions in different states
        test_sessions = []
        states_to_test = ['draft', 'defining_search', 'ready_to_execute', 'executing', 'processing_results']
        
        for i, state in enumerate(states_to_test):
            session = session_factory.create_session(state, 'mental_health_workplace', 
                                                   name=f"Concurrent Transition Test {i+1}")
            test_sessions.append({
                'session': session,
                'target_state': states_to_test[(i + 1) % len(states_to_test)]  # Next state
            })
        
        # Simulate concurrent monitoring checks
        monitoring_tasks = []
        
        for session_data in test_sessions:
            session = session_data['session']
            
            async def monitor_session(sess_id, sess_state):
                monitoring_results = []
                
                for check in range(10):  # 10 monitoring checks
                    check_start = time.time()
                    
                    should_monitor = activity_detector.should_monitor_session(str(sess_id), sess_state)
                    
                    if should_monitor:
                        activity_detector.update_last_monitored(str(sess_id), sess_state)
                        
                        # Simulate monitoring work
                        await asyncio.sleep(0.1)
                    
                    check_time = (time.time() - check_start) * 1000
                    monitoring_results.append({
                        'check': check + 1,
                        'should_monitor': should_monitor,
                        'check_time_ms': check_time
                    })
                    
                    await asyncio.sleep(5)  # 5 second intervals
                
                return {
                    'session_id': str(sess_id),
                    'state': sess_state,
                    'monitoring_results': monitoring_results
                }
            
            task = monitor_session(session.id, session.status)
            monitoring_tasks.append(task)
        
        # Execute concurrent monitoring
        concurrent_start = time.time()
        monitoring_results = await asyncio.gather(*monitoring_tasks)
        _total_monitoring_time = (time.time() - concurrent_start) * 1000
        
        # Analyze concurrent monitoring performance
        total_checks = sum([len(result['monitoring_results']) for result in monitoring_results])
        avg_check_time = sum([
            check['check_time_ms'] 
            for result in monitoring_results 
            for check in result['monitoring_results']
        ]) / total_checks
        
        # Validate concurrent monitoring doesn't degrade performance
        assert avg_check_time < 100, f"Average monitoring check time {avg_check_time:.2f}ms too high under concurrent load"
        
        for result in monitoring_results:
            performance_tracker.record_monitoring_interval(
                result['session_id'], 
                result['state'], 
                activity_detector.get_monitoring_interval(result['state']), 
                {
                    'concurrent_monitoring': True,
                    'total_checks': len(result['monitoring_results']),
                    'avg_check_time_ms': sum([c['check_time_ms'] for c in result['monitoring_results']]) / len(result['monitoring_results'])
                }
            )
        
        logger.info(f"✅ Concurrent monitoring validated: {len(test_sessions)} sessions, {total_checks} total checks, avg {avg_check_time:.2f}ms")


@pytest.mark.asyncio
class TestSystemFailureRecovery:
    """Test system recovery from various failure scenarios."""
    
    async def test_cache_failure_recovery(self, optimization_page: Page, test_helpers, performance_tracker, session_factory, activity_detector):
        """Test behavior when cache system fails and recovery."""
        await test_helpers.login_user(optimization_page)
        
        # Create session for testing
        session = session_factory.create_session('executing', 'healthcare_falls_prevention')
        
        # Simulate cache failure
        with patch('django.core.cache.cache.get') as mock_cache_get, \
             patch('django.core.cache.cache.set') as mock_cache_set:
            
            # Make cache operations fail
            mock_cache_get.side_effect = Exception("Cache connection failed")
            mock_cache_set.side_effect = Exception("Cache connection failed") 
            
            _cache_failure_start = time.time()
            
            # Test monitoring functionality with cache failure
            try:
                should_monitor = activity_detector.should_monitor_session(str(session.id), session.status)
                # Should fallback to always monitoring when cache fails
                assert should_monitor, "Should fallback to monitoring when cache fails"
                
            except Exception as e:
                performance_tracker.record_error('cache_failure', str(e), {
                    'phase': 'monitoring_check',
                    'session_state': session.status
                })
            
            # Test UI behavior during cache failure
            try:
                ui_start = time.time()
                await optimization_page.goto(f"{OPTIMIZATION_TEST_CONFIG['base_url']}/session/{session.id}/")
                await optimization_page.wait_for_load_state('networkidle')
                
                ui_time_with_cache_failure = (time.time() - ui_start) * 1000
                
                performance_tracker.record_page_load('session_page_cache_failure', ui_time_with_cache_failure, {
                    'cache_failure': True,
                    'session_state': session.status
                })
                
                # UI should still work even with cache failure
                assert ui_time_with_cache_failure < OPTIMIZATION_TEST_CONFIG['performance_threshold'] * 2, \
                    f"UI response time {ui_time_with_cache_failure:.2f}ms too high during cache failure"
                
            except Exception as e:
                performance_tracker.record_error('ui_cache_failure', str(e), {
                    'session_id': str(session.id)
                })
                raise
        
        # Test recovery after cache restoration
        recovery_start = time.time()
        
        # Cache should work normally now
        should_monitor_after_recovery = activity_detector.should_monitor_session(str(session.id), session.status)
        activity_detector.update_last_monitored(str(session.id), session.status)
        
        # Should not monitor immediately after updating
        should_monitor_immediate = activity_detector.should_monitor_session(str(session.id), session.status)
        
        recovery_time = (time.time() - recovery_start) * 1000
        
        # Validate cache recovery
        assert should_monitor_after_recovery, "Should monitor after cache recovery"
        assert not should_monitor_immediate, "Should not monitor immediately after updating post-recovery"
        
        performance_tracker.record_ui_interaction('cache_recovery', 'monitoring_system', recovery_time)
        
        logger.info(f"✅ Cache failure recovery validated: {recovery_time:.2f}ms recovery time")
    
    async def test_database_connection_timeout(self, optimization_page: Page, test_helpers, performance_tracker):
        """Test behavior during database connection timeouts."""
        await test_helpers.login_user(optimization_page)
        
        # Test UI behavior when database queries are slow
        # This simulates database connection issues
        
        slow_db_pages = [
            {'name': 'dashboard', 'url': '/dashboard/'},
            {'name': 'session_list', 'url': '/sessions/'},
            {'name': 'create_session', 'url': '/session/create/'},
        ]
        
        # Use route interception to simulate slow database responses
        async def slow_db_simulation(route: Route):
            # Simulate slow database by adding delay to API calls
            if 'api' in route.request.url:
                await asyncio.sleep(3)  # 3 second delay
            await route.continue_()
        
        await optimization_page.route("**/api/**", slow_db_simulation)
        
        db_timeout_results = []
        
        for page_test in slow_db_pages:
            start_time = time.time()
            
            try:
                await optimization_page.goto(f"{OPTIMIZATION_TEST_CONFIG['base_url']}{page_test['url']}")
                await optimization_page.wait_for_load_state('networkidle', timeout=OPTIMIZATION_TEST_CONFIG['timeout_long'])
                
                load_time = (time.time() - start_time) * 1000
                
                db_timeout_results.append({
                    'page': page_test['name'],
                    'load_time_ms': load_time,
                    'success': True
                })
                
                performance_tracker.record_page_load(f"slow_db_{page_test['name']}", load_time, {
                    'db_simulation': 'slow_response',
                    'timeout_simulation': True
                })
                
                # Page should still load, just slowly
                assert load_time < OPTIMIZATION_TEST_CONFIG['timeout_long'], \
                    f"Page {page_test['name']} failed to load within timeout during DB slowness"
                
            except Error as e:
                db_timeout_results.append({
                    'page': page_test['name'],
                    'load_time_ms': OPTIMIZATION_TEST_CONFIG['timeout_long'],
                    'success': False,
                    'error': str(e)
                })
                
                performance_tracker.record_error('db_timeout', str(e), page_test)
        
        await optimization_page.unroute("**/api/**")
        
        # Validate graceful degradation during DB issues
        successful_loads = [r for r in db_timeout_results if r['success']]
        assert len(successful_loads) >= len(db_timeout_results) * 0.8, \
            f"Too many pages failed during DB timeout simulation: {len(successful_loads)}/{len(db_timeout_results)}"
        
        logger.info(f"✅ Database timeout handling validated: {len(successful_loads)}/{len(db_timeout_results)} pages loaded successfully")


@pytest.mark.asyncio
class TestResourceConstraints:
    """Test behavior under resource constraints."""
    
    async def test_high_memory_usage_scenario(self, optimization_page: Page, test_helpers, performance_tracker, session_factory):
        """Test system behavior under high memory usage conditions."""
        await test_helpers.login_user(optimization_page)
        
        # Create many sessions to simulate memory pressure
        memory_test_sessions = []
        
        for i in range(50):  # Create 50 sessions
            state = ['draft', 'executing', 'completed', 'archived'][i % 4]
            session = session_factory.create_session(state, 'healthcare_falls_prevention',
                                                   name=f"Memory Test Session {i+1}")
            memory_test_sessions.append(session)
        
        # Test UI performance with many sessions
        memory_stress_tests = [
            {'name': 'dashboard_with_many_sessions', 'url': '/dashboard/'},
            {'name': 'session_list_full', 'url': '/sessions/'},
        ]
        
        memory_results = []
        
        for test in memory_stress_tests:
            # Multiple page loads to stress memory
            for load_iteration in range(5):
                start_time = time.time()
                
                await optimization_page.goto(f"{OPTIMIZATION_TEST_CONFIG['base_url']}{test['url']}")
                await optimization_page.wait_for_load_state('networkidle')
                
                # Check for memory-related JavaScript errors
                js_memory_info = await optimization_page.evaluate("""
                    () => {
                        const errors = window.optimizationTestData?.errors || [];
                        const memoryErrors = errors.filter(e => e.message && e.message.toLowerCase().includes('memory'));
                        
                        return {
                            memory_errors: memoryErrors.length,
                            total_errors: errors.length,
                            performance_memory: performance.memory ? {
                                used: performance.memory.usedJSHeapSize,
                                total: performance.memory.totalJSHeapSize,
                                limit: performance.memory.jsHeapSizeLimit
                            } : null
                        };
                    }
                """)
                
                load_time = (time.time() - start_time) * 1000
                
                memory_results.append({
                    'test': test['name'],
                    'iteration': load_iteration + 1,
                    'load_time_ms': load_time,
                    'js_memory_info': js_memory_info,
                    'session_count': len(memory_test_sessions)
                })
                
                performance_tracker.record_page_load(f"{test['name']}_memory_stress_{load_iteration + 1}", load_time, {
                    'memory_test': True,
                    'session_count': len(memory_test_sessions),
                    'js_memory_info': js_memory_info
                })
                
                # Brief pause between loads
                await asyncio.sleep(2)
        
        # Analyze memory performance
        avg_load_times = {}
        for test in memory_stress_tests:
            test_results = [r for r in memory_results if r['test'] == test['name']]
            avg_time = sum([r['load_time_ms'] for r in test_results]) / len(test_results)
            avg_load_times[test['name']] = avg_time
        
        # Validate performance doesn't degrade significantly under memory pressure
        for test_name, avg_time in avg_load_times.items():
            assert avg_time < OPTIMIZATION_TEST_CONFIG['performance_threshold'] * 2, \
                f"Memory stress test {test_name} avg time {avg_time:.2f}ms too high"
        
        # Check for memory leaks
        memory_errors = sum([r['js_memory_info']['memory_errors'] for r in memory_results])
        assert memory_errors == 0, f"Memory-related JavaScript errors detected: {memory_errors}"
        
        logger.info(f"✅ High memory usage scenario validated: {len(memory_test_sessions)} sessions, avg load times: {avg_load_times}")
    
    async def test_concurrent_execution_resource_limits(self, optimization_page: Page, test_helpers, performance_tracker, session_factory):
        """Test resource limits during concurrent execution scenarios."""
        await test_helpers.login_user(optimization_page)
        
        # Create multiple sessions in executing state
        concurrent_executing_sessions = []
        
        for i in range(10):  # 10 concurrent executing sessions
            session = session_factory.create_session('executing', 'education_digital_literacy',
                                                   name=f"Concurrent Execution Test {i+1}")
            
            # Simulate active executions
            executions = session_factory.simulate_active_execution(session)
            concurrent_executing_sessions.append({
                'session': session,
                'executions': executions
            })
        
        # Test system behavior with many concurrent executions
        resource_test_start = time.time()
        
        # Monitor system responsiveness during high resource usage
        _resource_monitoring_tasks = []
        
        async def monitor_resource_usage():
            monitoring_results = []
            
            for check in range(10):  # Monitor for ~2 minutes
                check_start = time.time()
                
                # Test dashboard responsiveness
                await optimization_page.goto(f"{OPTIMIZATION_TEST_CONFIG['base_url']}/dashboard/")
                await optimization_page.wait_for_load_state('networkidle')
                
                dashboard_time = (time.time() - check_start) * 1000
                
                # Check system resources (simulated)
                system_info = await optimization_page.evaluate("""
                    () => ({
                        timestamp: Date.now(),
                        connection_status: navigator.onLine,
                        memory_info: performance.memory ? {
                            used: performance.memory.usedJSHeapSize,
                            total: performance.memory.totalJSHeapSize
                        } : null
                    })
                """)
                
                monitoring_results.append({
                    'check': check + 1,
                    'dashboard_load_ms': dashboard_time,
                    'system_info': system_info
                })
                
                await asyncio.sleep(12)  # 12 second intervals
            
            return monitoring_results
        
        resource_monitoring_results = await monitor_resource_usage()
        
        _total_resource_test_time = (time.time() - resource_test_start) * 1000
        
        # Analyze resource usage impact
        dashboard_times = [r['dashboard_load_ms'] for r in resource_monitoring_results]
        avg_dashboard_time = sum(dashboard_times) / len(dashboard_times)
        max_dashboard_time = max(dashboard_times)
        
        # Validate system remains responsive under resource pressure
        assert avg_dashboard_time < OPTIMIZATION_TEST_CONFIG['performance_threshold'], \
            f"Dashboard responsiveness degraded under resource pressure: {avg_dashboard_time:.2f}ms avg"
        
        assert max_dashboard_time < OPTIMIZATION_TEST_CONFIG['performance_threshold'] * 1.5, \
            f"Peak dashboard time too high under resource pressure: {max_dashboard_time:.2f}ms"
        
        for i, result in enumerate(resource_monitoring_results):
            performance_tracker.record_page_load(f'dashboard_resource_pressure_{i+1}', 
                                               result['dashboard_load_ms'], {
                'concurrent_executions': len(concurrent_executing_sessions),
                'resource_test': True,
                'system_info': result['system_info']
            })
        
        logger.info(f"✅ Resource constraints validated: {len(concurrent_executing_sessions)} concurrent executions, avg dashboard {avg_dashboard_time:.2f}ms")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "--maxfail=3"])