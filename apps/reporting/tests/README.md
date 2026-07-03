# Reporting App Test Suite

This directory contains comprehensive tests for the Django reporting app.

## Test Structure

### Test Modules

1. **test_views.py** - Tests for all view classes
   - Dashboard views
   - Report generation views
   - Download functionality
   - API endpoints
   - Access control

2. **test_forms.py** - Tests for form validation
   - ReportGenerationForm
   - BulkExportForm
   - ReportSchedulingForm
   - Field validation
   - Format compatibility

3. **test_tasks.py** - Tests for Celery background tasks
   - Report generation task
   - Notification tasks
   - Cleanup tasks
   - Error handling
   - Progress tracking

4. **test_services.py** - Tests for service layer
   - PrismaReportingService
   - ExportService
   - PerformanceAnalyticsService
   - SearchResultAnalysisService
   - SearchStrategyReportingService

5. **test_integration.py** - End-to-end integration tests
   - Complete report workflows
   - API integration
   - Access control
   - Cleanup automation

6. **test_models.py** - Tests for model functionality (existing)

7. **test_utils.py** - Shared test utilities
   - Mock classes
   - Test data builders
   - Assertion helpers

## Running Tests

### Run All Tests
```bash
python manage.py test apps.reporting
```

### Run Specific Test Module
```bash
python manage.py test apps.reporting.tests.test_views
python manage.py test apps.reporting.tests.test_forms
python manage.py test apps.reporting.tests.test_tasks
python manage.py test apps.reporting.tests.test_services
python manage.py test apps.reporting.tests.test_integration
```

### Run Specific Test Class
```bash
python manage.py test apps.reporting.tests.test_views.ReportDashboardViewTest
```

### Run Specific Test Method
```bash
python manage.py test apps.reporting.tests.test_views.ReportDashboardViewTest.test_dashboard_context_data
```

### Using the Test Runner Script
```bash
# Run all tests
python apps/reporting/tests/run_tests.py

# Run only view tests
python apps/reporting/tests/run_tests.py --views

# Run with coverage
python apps/reporting/tests/run_tests.py --coverage

# Run in parallel with verbose output
python apps/reporting/tests/run_tests.py --parallel --verbose
```

## Test Coverage

The test suite aims for >90% coverage across all modules:

- **Views**: 95%+ coverage
- **Forms**: 100% coverage
- **Tasks**: 90%+ coverage
- **Services**: 95%+ coverage
- **Integration**: Key workflows covered

### Generate Coverage Report
```bash
coverage run --source='apps.reporting' manage.py test apps.reporting
coverage report -m
coverage html  # Creates htmlcov/index.html
```

## Mock Dependencies

The tests mock external dependencies to ensure fast, reliable testing:

### Mocked Services
- **WeasyPrint**: PDF generation (MockWeasyPrint in test_utils)
- **python-docx**: Word document generation (MockDocument)
- **File Storage**: Django's default_storage
- **Celery Tasks**: Background task execution
- **Email**: Notification sending

### Test Data Builder

Use the `TestDataBuilder` class for creating comprehensive test data:

```python
from apps.reporting.tests.test_utils import TestDataBuilder

builder = TestDataBuilder(user=self.user)
data = builder.build_complete_dataset()
```

## Common Test Patterns

### Testing Views
```python
class MyViewTest(BaseReportingTestCase):
    def test_view_requires_authentication(self):
        self.client.logout()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_view_validates_ownership(self):
        # Test with other user's data
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
```

### Testing Forms
```python
def test_form_validation(self):
    form_data = {...}
    form = MyForm(data=form_data)
    self.assertFalse(form.is_valid())
    self.assertIn("field_name", form.errors)
```

### Testing Tasks
```python
@patch("apps.reporting.tasks.some_service")
def test_task_execution(self, mock_service):
    mock_service.return_value = expected_data
    result = my_task(param)
    self.assertEqual(result["status"], "completed")
```

### Testing Services
```python
def test_service_method(self):
    service = MyService()
    result = service.process_data(self.session.id)
    self.assertIn("expected_key", result)
```

## Test Database

Tests use a separate test database that is created and destroyed for each test run. To keep the test database between runs (faster for development):

```bash
python manage.py test apps.reporting --keepdb
```

## Debugging Tests

### Run with PDB
```python
import pdb; pdb.set_trace()
```

### Print SQL Queries
```python
from django.db import connection
print(connection.queries)
```

### Verbose Output
```bash
python manage.py test apps.reporting --verbosity=2
```

## Best Practices

1. **Isolation**: Each test should be independent
2. **Mocking**: Mock external dependencies
3. **Fixtures**: Use setUp() for common test data
4. **Assertions**: Use specific assertions (assertEqual, assertIn, etc.)
5. **Coverage**: Aim for >90% coverage
6. **Performance**: Keep tests fast (<1s per test)
7. **Documentation**: Document complex test scenarios

## Troubleshooting

### Import Errors
Ensure you're in the project root and the virtual environment is activated.

### Database Errors
Try running with `--keepdb` or check database permissions.

### Mock Errors
Verify mock paths match the actual import paths in the code.

### Slow Tests
Use `--parallel` to run tests in parallel, or focus on specific test modules.
