# SERP Execution Tests - Core Requirements Edition

Comprehensive test suite for the SERP execution module in Agent Grey Core Requirements Edition, ensuring reliable systematic grey literature search functionality.

## Test Structure

The test suite is organised into the following modules with Core Requirements Edition focus:

### 1. **test_models.py**
Tests for Core Requirements Edition models:
- `SearchExecution` model with enhanced status management and progress tracking
- `RawSearchResult` data storage with metadata enrichment
- Model relationships with search_strategy app integration
- Field validations including UUID primary keys and JSON field constraints
- Progress tracking without percentages (status-based only)

### 2. **test_services.py**
Tests for enhanced service layer components:
- `SerperClient` - Enhanced API integration with circuit breaker protection
- `CacheManager` - Production Redis caching with automatic fallback
- `QueryBuilder` - Advanced PIC framework query construction  
- `ResultProcessor` - Intelligent result normalisation and metadata extraction
- `StatisticsService` - Real-time execution statistics and monitoring

### 3. **test_views.py**
Tests for Core Requirements Edition views with service layer integration:
- `SearchExecutionStatusView` - Real-time monitoring with SSE support
- `ErrorRecoveryView` - Intelligent failure recovery interface with categorised errors
- `TestSessionMonitorView` - Development testing interface
- API endpoints for progress updates and status monitoring
- Enhanced permission checks with session ownership validation

### 4. **test_tasks.py** 
Tests for decomposed Celery task architecture:
- `initiate_search_session_execution_task` - Session orchestration
- `perform_serp_query_task` - Individual query execution with progress tracking
- `monitor_session_completion_task` - Session monitoring and auto-transitions
- `unified_session_monitor` - Unified monitoring with WebSocket notifications
- Task retry logic with intelligent delay calculation

### 5. **test_forms.py**
Tests for Core Requirements Edition forms:
- `ErrorRecoveryForm` with intelligent recovery options
- Form validation with execution context
- Dynamic form field generation based on error categories
- Integration with recovery service layer

### 6. **test_integration.py**
End-to-end integration tests for systematic review workflows:
- Complete 9-state workflow integration from 'executing' to 'ready_for_review'
- Real-time progress tracking with SSE and polling fallback
- Error recovery workflows with categorised error handling
- Circuit breaker protection and graceful degradation
- Redis caching integration with automatic fallback
- Performance testing under concurrent execution scenarios

## Running Tests

### Docker-based Testing (Recommended)
```bash
# Run all SERP execution tests
docker compose exec web python manage.py test apps.serp_execution

# Run with verbose output for debugging
docker compose exec web python manage.py test apps.serp_execution --verbosity=3

# Run specific test categories
docker compose exec web python manage.py test apps.serp_execution.tests.test_models
docker compose exec web python manage.py test apps.serp_execution.tests.test_services  
docker compose exec web python manage.py test apps.serp_execution.tests.test_views
docker compose exec web python manage.py test apps.serp_execution.tests.test_tasks
docker compose exec web python manage.py test apps.serp_execution.tests.test_integration

# Run single test method
docker compose exec web python manage.py test apps.serp_execution.tests.test_models.SearchExecutionModelTests.test_can_retry_logic
```

### Core Requirements Edition Testing
```bash  
# Test API connectivity
docker compose exec web python manage.py test_serper_connection

# Test workflow integration
docker compose exec web python manage.py test_workflow_integration

# Test circuit breaker functionality  
docker compose exec web python manage.py circuit_breaker_control --test

# Monitor queue health during testing
docker compose exec web python manage.py queue_control --status
```

### Run Specific Test Class
```bash
python manage.py test apps.serp_execution.tests.test_services.TestSerperClient
```

### Run Specific Test Method
```bash
python manage.py test apps.serp_execution.tests.test_models.SearchExecutionModelTests.test_can_retry_logic
```

### Using the Test Runner Script
```bash
cd apps/serp_execution/tests

# Run all tests
python run_tests.py

# Run specific test type
python run_tests.py models
python run_tests.py services
python run_tests.py views
python run_tests.py tasks
python run_tests.py integration
python run_tests.py forms

# Run with coverage
python run_tests.py coverage

# Run with options
python run_tests.py all --verbosity=3 --failfast
```

## Test Coverage & Quality Assurance

The Core Requirements Edition test suite maintains >95% code coverage with focus on production reliability:

```bash
# Generate coverage report
docker compose exec web coverage run --source='apps/serp_execution' manage.py test apps.serp_execution
docker compose exec web coverage report -m

# Generate HTML coverage report
docker compose exec web coverage html
# Open htmlcov/index.html in browser

# Coverage with specific modules
docker compose exec web coverage run --source='apps.serp_execution.services' manage.py test apps.serp_execution.tests.test_services
```

### Quality Gates
- **Code Coverage**: >95% line coverage required
- **Branch Coverage**: >90% branch coverage for critical paths  
- **Integration Coverage**: All 9-state workflow transitions tested
- **Error Path Coverage**: All error categories and recovery paths tested

## Test Data and Fixtures

Tests use Django's TestCase classes which provide:
- Automatic database transaction rollback
- Test isolation
- Factory methods for creating test data

Common test data patterns:
```python
# User creation
user = User.objects.create_user(
    email='test@example.com',
    password='testpass123'
)

# Session with queries
session = SearchSession.objects.create(
    title='Test Session',
    owner=user,
    status='ready_to_execute'
)

query = SearchQuery.objects.create(
    session=session,
    population='developers',
    interest='testing',
    context='python',
    search_engines=['google']
)
```

## Mocking External Services

External API calls are mocked to ensure:
- Tests run without internet connection
- Predictable test results
- No API credit consumption
- Fast test execution

Example mock pattern:
```python
@patch('apps.core.services.serper_client.requests.Session.post')
def test_search_execution(self, mock_post):
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {'organic': [...]}
    mock_post.return_value = mock_response
```

## Testing Best Practices

1. **Test Isolation**: Each test should be independent
2. **Clear Test Names**: Use descriptive test method names
3. **Arrange-Act-Assert**: Follow AAA pattern in tests
4. **Mock External Dependencies**: Don't make real API calls
5. **Test Edge Cases**: Include error scenarios and boundary conditions
6. **Use Factories**: Create reusable test data factories
7. **Transaction Tests**: Use TransactionTestCase for tests requiring transactions

## Common Test Scenarios

### Testing API Integration
- Successful API calls
- Rate limiting
- Authentication errors
- Network failures
- Retry logic

### Testing Async Tasks
- Task execution
- Retry on failure
- Task chaining
- Progress monitoring

### Testing User Workflows
- Search initiation
- Error recovery
- Result viewing
- Permission checks

### Testing Data Processing
- Result normalization
- Duplicate detection
- Metadata extraction
- Batch processing

## Debugging Failed Tests

1. **Increase Verbosity**: `python manage.py test --verbosity=3`
2. **Run Single Test**: Isolate the failing test
3. **Check Test Database**: Use `--keepdb` to inspect test data
4. **Add Debug Prints**: Use `print()` or `pdb` for debugging
5. **Check Mocks**: Ensure mocks match actual implementation

## Core Requirements Edition Testing Best Practices

### Test-Driven Development
1. **Write Tests First**: Follow TDD approach for all new features
2. **Test State Transitions**: Ensure all 9-state workflow transitions are covered
3. **Mock External APIs**: Never make real API calls in tests - use comprehensive mocking
4. **Test Error Scenarios**: Cover all error categories and recovery paths
5. **Performance Testing**: Include tests for concurrent execution scenarios

### Production Testing Patterns
```python
# Example: Testing circuit breaker protection
@patch('apps.core.services.serper_client.requests.Session.post')
def test_circuit_breaker_protection(self, mock_post):
    # Simulate API failures to trigger circuit breaker
    mock_post.side_effect = requests.exceptions.Timeout()
    
    client = SerperClient()
    
    # Should gracefully handle when circuit opens
    result = client.safe_search("test query")
    self.assertIn('error', result)
    self.assertEqual(result['error_type'], 'circuit_breaker_open')

# Example: Testing 9-state workflow integration
def test_execution_to_review_transition(self):
    session = self.create_test_session(status='executing')
    
    # Simulate successful execution completion
    self.complete_all_executions(session)
    
    # Should automatically transition to ready_for_review
    session.refresh_from_db()
    self.assertEqual(session.status, 'ready_for_review')
```

### Continuous Integration Requirements
- **All Tests Pass**: Zero test failures allowed in CI
- **Coverage Gates**: >95% coverage required for merge
- **Performance Benchmarks**: Response time thresholds enforced
- **Security Testing**: API key handling and input validation tests
- **Integration Testing**: End-to-end workflow validation
