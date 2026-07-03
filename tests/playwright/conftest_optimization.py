"""
Enhanced Playwright Configuration for Optimization Testing

This module provides comprehensive test fixtures and configuration for validating
the task optimization implementation from an end-user perspective.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pytest
import pytest_asyncio
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone
from playwright.async_api import Browser, BrowserContext, Page, Playwright

from apps.core.services.session_activity_detector import \
    SimpleSessionActivityDetector
from apps.review_manager.models import SearchSession, SessionActivity
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.models import SearchExecution

# Test configuration constants
OPTIMIZATION_TEST_CONFIG = {
    'base_url': 'http://localhost:8000',
    'api_base_url': 'http://localhost:8000/api',
    'timeout_short': 5000,      # 5 seconds
    'timeout_medium': 15000,    # 15 seconds  
    'timeout_long': 30000,      # 30 seconds
    'timeout_execution': 180000, # 3 minutes for search execution
    'performance_threshold': 2000,  # 2 seconds for page loads
    'monitor_tolerance': 10,    # 10% tolerance for monitoring intervals
    'screenshots_dir': Path(__file__).parent / 'screenshots' / 'optimization',
    'videos_dir': Path(__file__).parent / 'videos' / 'optimization',
    'reports_dir': Path(__file__).parent / 'reports' / 'optimization',
}

# Ensure directories exist
for dir_path in [OPTIMIZATION_TEST_CONFIG['screenshots_dir'], 
                OPTIMIZATION_TEST_CONFIG['videos_dir'],
                OPTIMIZATION_TEST_CONFIG['reports_dir']]:
    dir_path.mkdir(parents=True, exist_ok=True)


class OptimizationTestFixtures:
    """Test data and fixtures for optimization validation."""
    
    REALISTIC_SEARCH_SCENARIOS = {
        'healthcare_falls_prevention': {
            'name': 'Falls Prevention in Elderly Care Settings',
            'description': 'Systematic review of falls prevention interventions in residential care',
            'population': 'elderly residents,older adults,seniors,geriatric patients,nursing home residents',
            'interest': 'falls prevention,fall prevention,balance training,exercise intervention,mobility training,strength training',
            'context': 'nursing homes,residential care,aged care facilities,long-term care,assisted living',
            'guidelines_filter': True,
            'expected_results': 25,
            'estimated_execution_time': 120,  # seconds
        },
        'education_digital_literacy': {
            'name': 'Digital Literacy in Higher Education Post-COVID',
            'description': 'Review of digital literacy programs in universities after COVID-19',
            'population': 'university students,college students,undergraduate students,postgraduate students',
            'interest': 'digital literacy,online learning,e-learning,digital skills,technology integration,remote learning',
            'context': 'higher education,universities,colleges,post-secondary,distance learning,online education',
            'guidelines_filter': False,
            'expected_results': 35,
            'estimated_execution_time': 150,  # seconds
        },
        'mental_health_workplace': {
            'name': 'Workplace Mental Health Interventions',
            'description': 'Interventions for mental health support in workplace settings',
            'population': 'employees,workers,healthcare workers,essential workers,office workers',
            'interest': 'mental health intervention,psychological support,stress management,burnout prevention,wellbeing program',
            'context': 'workplace,occupational setting,employment,work environment,organizational',
            'guidelines_filter': True,
            'expected_results': 30,
            'estimated_execution_time': 140,  # seconds
        }
    }
    
    MONITORING_INTERVAL_SCENARIOS = {
        'active_states': {
            'executing': {
                'interval': 60,
                'description': 'Active search execution requiring frequent monitoring',
                'test_duration': 300,  # 5 minutes
            },
            'processing_results': {
                'interval': 60,
                'description': 'Active result processing requiring frequent monitoring',
                'test_duration': 180,  # 3 minutes
            }
        },
        'review_states': {
            'ready_for_review': {
                'interval': 600,
                'description': 'Waiting for user review - reduced monitoring',
                'test_duration': 1200,  # 20 minutes
            },
            'under_review': {
                'interval': 600,
                'description': 'Manual review in progress - reduced monitoring',
                'test_duration': 1800,  # 30 minutes
            }
        },
        'dormant_states': {
            'completed': {
                'interval': 3600,
                'description': 'Completed session - minimal monitoring',
                'test_duration': 3600,  # 1 hour
            },
            'archived': {
                'interval': 3600,
                'description': 'Archived session - minimal monitoring',
                'test_duration': 3600,  # 1 hour
            }
        }
    }


@pytest.fixture(scope="session")
def optimization_test_config():
    """Provide test configuration for optimization tests."""
    return OPTIMIZATION_TEST_CONFIG


@pytest.fixture(scope="session")  
def test_scenarios():
    """Provide realistic test scenarios."""
    return OptimizationTestFixtures.REALISTIC_SEARCH_SCENARIOS


@pytest.fixture(scope="session")
def monitoring_scenarios():
    """Provide monitoring interval test scenarios."""
    return OptimizationTestFixtures.MONITORING_INTERVAL_SCENARIOS


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """Set up test database with optimizations-specific data."""
    with django_db_blocker.unblock():
        call_command('migrate', verbosity=0, interactive=False)
        
        # Create test users with different roles
        User = get_user_model()
        
        # Main test user
        test_user, created = User.objects.get_or_create(
            username='optimization_test_user',
            defaults={
                'email': 'optimization@test.com',
                'first_name': 'Optimization',
                'last_name': 'Tester',
            }
        )
        if created:
            test_user.set_password('OptimizationTest123!')
            test_user.save()
        
        # Admin test user
        admin_user, created = User.objects.get_or_create(
            username='optimization_admin',
            defaults={
                'email': 'admin@optimization.test.com',
                'first_name': 'Admin',
                'last_name': 'Optimizer',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        if created:
            admin_user.set_password('AdminOptimize123!')
            admin_user.save()


@pytest.fixture
def test_user(db):
    """Create or get the main test user."""
    User = get_user_model()
    user, created = User.objects.get_or_create(
        username='optimization_test_user',
        defaults={
            'email': 'optimization@test.com',
            'first_name': 'Optimization',
            'last_name': 'Tester',
        }
    )
    if created:
        user.set_password('OptimizationTest123!')
        user.save()
    return user


@pytest.fixture
def admin_user(db):
    """Create or get the admin test user."""
    User = get_user_model()
    user, created = User.objects.get_or_create(
        username='optimization_admin',
        defaults={
            'email': 'admin@optimization.test.com',
            'first_name': 'Admin',
            'last_name': 'Optimizer',
            'is_staff': True,
            'is_superuser': True,
        }
    )
    if created:
        user.set_password('AdminOptimize123!')
        user.save()
    return user


@pytest.fixture
def activity_detector():
    """Provide an instance of SimpleSessionActivityDetector."""
    return SimpleSessionActivityDetector()


@pytest.fixture
def clean_cache():
    """Clear cache before and after each test."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def performance_tracker():
    """Track performance metrics during tests."""
    class PerformanceTracker:
        def __init__(self):
            self.metrics = {
                'page_loads': [],
                'state_transitions': [],
                'api_calls': [],
                'ui_interactions': [],
                'monitoring_intervals': [],
                'errors': []
            }
        
        def record_page_load(self, page_name: str, duration_ms: float, additional_data: Dict = None):
            """Record page load performance."""
            entry = {
                'page': page_name,
                'duration_ms': duration_ms,
                'timestamp': datetime.now().isoformat(),
                'additional_data': additional_data or {}
            }
            self.metrics['page_loads'].append(entry)
        
        def record_state_transition(self, from_state: str, to_state: str, duration_ms: float, automatic: bool = False):
            """Record state transition performance."""
            entry = {
                'from_state': from_state,
                'to_state': to_state,
                'duration_ms': duration_ms,
                'automatic': automatic,
                'timestamp': datetime.now().isoformat()
            }
            self.metrics['state_transitions'].append(entry)
        
        def record_api_call(self, endpoint: str, method: str, duration_ms: float, status_code: int):
            """Record API call performance."""
            entry = {
                'endpoint': endpoint,
                'method': method,
                'duration_ms': duration_ms,
                'status_code': status_code,
                'timestamp': datetime.now().isoformat()
            }
            self.metrics['api_calls'].append(entry)
        
        def record_ui_interaction(self, action: str, element: str, duration_ms: float):
            """Record UI interaction performance."""
            entry = {
                'action': action,
                'element': element,
                'duration_ms': duration_ms,
                'timestamp': datetime.now().isoformat()
            }
            self.metrics['ui_interactions'].append(entry)
        
        def record_monitoring_interval(self, session_id: str, state: str, expected_interval: int, actual_behavior: Dict):
            """Record monitoring interval behavior."""
            entry = {
                'session_id': session_id,
                'state': state,
                'expected_interval': expected_interval,
                'actual_behavior': actual_behavior,
                'timestamp': datetime.now().isoformat()
            }
            self.metrics['monitoring_intervals'].append(entry)
        
        def record_error(self, error_type: str, error_message: str, context: Dict = None):
            """Record error for analysis."""
            entry = {
                'error_type': error_type,
                'error_message': error_message,
                'context': context or {},
                'timestamp': datetime.now().isoformat()
            }
            self.metrics['errors'].append(entry)
        
        def get_summary(self) -> Dict[str, Any]:
            """Get performance summary."""
            summary = {}
            
            # Page load statistics
            page_loads = self.metrics['page_loads']
            if page_loads:
                durations = [p['duration_ms'] for p in page_loads]
                summary['page_loads'] = {
                    'count': len(durations),
                    'avg_ms': sum(durations) / len(durations),
                    'min_ms': min(durations),
                    'max_ms': max(durations),
                    'threshold_violations': len([d for d in durations if d > OPTIMIZATION_TEST_CONFIG['performance_threshold']])
                }
            
            # State transition statistics
            transitions = self.metrics['state_transitions']
            if transitions:
                durations = [t['duration_ms'] for t in transitions]
                automatic_count = len([t for t in transitions if t['automatic']])
                summary['state_transitions'] = {
                    'count': len(transitions),
                    'automatic_count': automatic_count,
                    'manual_count': len(transitions) - automatic_count,
                    'avg_ms': sum(durations) / len(durations),
                    'max_ms': max(durations)
                }
            
            # Error statistics
            summary['errors'] = {
                'count': len(self.metrics['errors']),
                'types': list(set([e['error_type'] for e in self.metrics['errors']]))
            }
            
            return summary
        
        def export_to_file(self, filepath: Path):
            """Export metrics to JSON file."""
            with open(filepath, 'w') as f:
                json.dump(self.metrics, f, indent=2)
    
    return PerformanceTracker()


@pytest_asyncio.fixture
async def browser_with_optimization_config(playwright: Playwright):
    """Create browser with optimization-specific configuration."""
    browser = await playwright.chromium.launch(
        headless=False,  # Set to True for CI/CD
        slow_mo=100,     # Slow down actions for better observation
        args=[
            '--disable-web-security',
            '--disable-features=TranslateUI',
            '--disable-ipc-flooding-protection',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding',
        ]
    )
    yield browser
    await browser.close()


@pytest_asyncio.fixture
async def optimization_context(browser_with_optimization_config: Browser):
    """Create browser context optimized for testing."""
    context = await browser_with_optimization_config.new_context(
        viewport={'width': 1280, 'height': 1024},
        ignore_https_errors=True,
        record_video_dir=str(OPTIMIZATION_TEST_CONFIG['videos_dir']),
        record_video_size={'width': 1280, 'height': 1024},
    )
    
    # Enable console logging
    context.on('console', lambda msg: print(f"Browser console [{msg.type}]: {msg.text}"))
    
    yield context
    await context.close()


@pytest_asyncio.fixture
async def optimization_page(optimization_context: BrowserContext, performance_tracker):
    """Create page with optimization testing setup."""
    page = await optimization_context.new_page()
    
    # Add performance monitoring script
    await page.add_init_script("""
        // Performance monitoring setup
        window.optimizationTestData = {
            pageLoadStart: Date.now(),
            apiCalls: [],
            userInteractions: [],
            errors: []
        };
        
        // Monitor fetch requests
        const originalFetch = window.fetch;
        window.fetch = function(...args) {
            const start = Date.now();
            const url = args[0];
            const options = args[1] || {};
            
            return originalFetch.apply(this, args)
                .then(response => {
                    const end = Date.now();
                    window.optimizationTestData.apiCalls.push({
                        url: url,
                        method: options.method || 'GET',
                        duration: end - start,
                        status: response.status,
                        timestamp: end
                    });
                    return response;
                })
                .catch(error => {
                    const end = Date.now();
                    window.optimizationTestData.errors.push({
                        type: 'fetch_error',
                        message: error.message,
                        url: url,
                        timestamp: end
                    });
                    throw error;
                });
        };
        
        // Monitor user interactions
        ['click', 'submit', 'change'].forEach(eventType => {
            document.addEventListener(eventType, function(event) {
                window.optimizationTestData.userInteractions.push({
                    type: eventType,
                    target: event.target.tagName + (event.target.id ? '#' + event.target.id : ''),
                    timestamp: Date.now()
                });
            });
        });
        
        // Monitor page load completion
        window.addEventListener('load', function() {
            window.optimizationTestData.pageLoadComplete = Date.now();
        });
    """)
    
    # Set up error handling
    page.on('pageerror', lambda error: performance_tracker.record_error('page_error', str(error)))
    page.on('requestfailed', lambda request: performance_tracker.record_error('request_failed', f"{request.method} {request.url}"))
    
    yield page


@pytest.fixture
def session_factory(test_user, activity_detector):
    """Factory for creating test sessions in various states."""
    class SessionFactory:
        def __init__(self, user, detector):
            self.user = user
            self.detector = detector
        
        def create_session(self, state: str, scenario_name: str = 'healthcare_falls_prevention', **kwargs) -> SearchSession:
            """Create a session in a specific state."""
            scenario = OptimizationTestFixtures.REALISTIC_SEARCH_SCENARIOS[scenario_name]
            
            with transaction.atomic():
                session = SearchSession.objects.create(
                    name=kwargs.get('name', scenario['name']),
                    description=kwargs.get('description', scenario['description']),
                    status=state,
                    created_by=self.user,
                    **kwargs
                )
                
                # Create associated search strategy if needed
                if state not in ['draft']:
                    search_strategy = SearchStrategy.objects.create(
                        session=session,
                        population_terms=scenario['population'],
                        interest_terms=scenario['interest'],
                        context_terms=scenario['context'],
                        use_guidelines_filter=scenario['guidelines_filter'],
                        created_by=self.user
                    )
                    
                    # Create search queries
                    queries = search_strategy.generate_queries()
                    for query_data in queries[:3]:  # Limit for testing
                        SearchQuery.objects.create(
                            session=session,
                            strategy=search_strategy,
                            query_string=query_data['query'],
                            query_type=query_data.get('type', 'general'),
                            file_types=query_data.get('file_types', ['pdf', 'doc'])
                        )
                
                # Create session activity
                SessionActivity.objects.create(
                    session=session,
                    activity_type='state_change',
                    details={'new_state': state, 'reason': 'test_setup'},
                    created_by=self.user
                )
                
                return session
        
        def create_sessions_in_all_states(self) -> Dict[str, SearchSession]:
            """Create sessions in all possible states for testing."""
            sessions = {}
            states = ['draft', 'defining_search', 'ready_to_execute', 'executing', 
                     'processing_results', 'ready_for_review', 'under_review', 'completed', 'archived']
            
            scenarios = list(OptimizationTestFixtures.REALISTIC_SEARCH_SCENARIOS.keys())
            
            for i, state in enumerate(states):
                scenario_name = scenarios[i % len(scenarios)]
                session = self.create_session(state, scenario_name, name=f"Test Session - {state.title()}")
                sessions[state] = session
            
            return sessions
        
        def simulate_active_execution(self, session: SearchSession) -> List[SearchExecution]:
            """Simulate active executions for testing monitoring."""
            executions = []
            queries = SearchQuery.objects.filter(session=session)
            
            for query in queries:
                execution = SearchExecution.objects.create(
                    query=query,
                    status='running',
                    started_at=timezone.now(),
                    api_endpoint='serper',
                    request_data={'query': query.query_string}
                )
                executions.append(execution)
            
            return executions
    
    return SessionFactory(test_user, activity_detector)


@pytest.fixture
def monitoring_validator(activity_detector):
    """Validate monitoring interval behavior."""
    class MonitoringValidator:
        def __init__(self, detector):
            self.detector = detector
            self.validation_results = []
        
        def validate_interval(self, session_id: str, state: str, expected_interval: int) -> bool:
            """Validate that a session uses the correct monitoring interval."""
            actual_interval = self.detector.get_monitoring_interval(state)
            
            result = {
                'session_id': session_id,
                'state': state,
                'expected_interval': expected_interval,
                'actual_interval': actual_interval,
                'valid': actual_interval == expected_interval,
                'timestamp': datetime.now().isoformat()
            }
            
            self.validation_results.append(result)
            return result['valid']
        
        def validate_should_monitor_logic(self, session_id: str, state: str) -> Dict[str, Any]:
            """Validate should_monitor_session logic."""
            # First call should return True (never monitored)
            initial_check = self.detector.should_monitor_session(session_id, state)
            
            # Update last monitored
            self.detector.update_last_monitored(session_id, state)
            
            # Immediate second call should return False
            immediate_check = self.detector.should_monitor_session(session_id, state)
            
            result = {
                'session_id': session_id,
                'state': state,
                'initial_check': initial_check,
                'immediate_check': immediate_check,
                'logic_valid': initial_check and not immediate_check,
                'timestamp': datetime.now().isoformat()
            }
            
            return result
        
        def get_summary(self) -> Dict[str, Any]:
            """Get validation summary."""
            valid_count = len([r for r in self.validation_results if r['valid']])
            total_count = len(self.validation_results)
            
            return {
                'total_validations': total_count,
                'valid_count': valid_count,
                'invalid_count': total_count - valid_count,
                'success_rate': (valid_count / total_count * 100) if total_count > 0 else 0,
                'results': self.validation_results
            }
    
    return MonitoringValidator(activity_detector)


class OptimizationTestHelpers:
    """Helper functions for optimization testing."""
    
    @staticmethod
    async def login_user(page: Page, username: str = 'optimization_test_user', password: str = 'OptimizationTest123!'):
        """Log in a user for testing."""
        await page.goto(f"{OPTIMIZATION_TEST_CONFIG['base_url']}/accounts/login/")
        await page.fill('[name="username"]', username)
        await page.fill('[name="password"]', password)
        await page.click('button[type="submit"]')
        await page.wait_for_load_state('networkidle')
        
        # Verify login success
        await page.wait_for_selector('[data-testid="user-menu"]', timeout=OPTIMIZATION_TEST_CONFIG['timeout_short'])
    
    @staticmethod
    async def create_session_via_ui(page: Page, scenario: Dict[str, Any], performance_tracker) -> str:
        """Create a session through the UI and return session ID."""
        import time
        
        start_time = time.time()
        
        await page.goto(f"{OPTIMIZATION_TEST_CONFIG['base_url']}/dashboard/")
        await page.click('text=Create New Review')
        
        await page.fill('[name="name"]', scenario['name'])
        await page.fill('[name="description"]', scenario['description'])
        
        await page.click('button[type="submit"]')
        await page.wait_for_load_state('networkidle')
        
        creation_time = (time.time() - start_time) * 1000
        performance_tracker.record_page_load('session_creation', creation_time, {'scenario': scenario['name']})
        
        # Extract session ID from URL
        session_id = page.url.split('/')[-2]
        return session_id
    
    @staticmethod
    async def configure_search_strategy(page: Page, scenario: Dict[str, Any], performance_tracker):
        """Configure search strategy through UI."""
        import time
        
        start_time = time.time()
        
        await page.click('text=Define Search Strategy')
        await page.wait_for_load_state('networkidle')
        
        await page.fill('[name="population"]', scenario['population'])
        await page.fill('[name="interest"]', scenario['interest'])
        await page.fill('[name="context"]', scenario['context'])
        
        if scenario.get('guidelines_filter'):
            await page.check('[name="use_guidelines_filter"]')
        
        await page.click('button[type="submit"]')
        await page.wait_for_load_state('networkidle')
        
        config_time = (time.time() - start_time) * 1000
        performance_tracker.record_ui_interaction('configure_search_strategy', 'form', config_time)
    
    @staticmethod
    async def take_screenshot(page: Page, name: str, context: str = ""):
        """Take a screenshot for documentation."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{name}_{context}_{timestamp}.png" if context else f"{name}_{timestamp}.png"
        filepath = OPTIMIZATION_TEST_CONFIG['screenshots_dir'] / filename
        
        await page.screenshot(path=str(filepath), full_page=True)
        return filepath


@pytest.fixture
def test_helpers():
    """Provide test helper functions."""
    return OptimizationTestHelpers


# Export configuration for easy import
__all__ = [
    'OPTIMIZATION_TEST_CONFIG',
    'OptimizationTestFixtures',
    'OptimizationTestHelpers',
]