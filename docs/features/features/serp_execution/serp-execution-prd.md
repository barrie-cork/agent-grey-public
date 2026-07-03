# SERP Execution: App-Specific Product Requirements Document

**Project Title:** Agent Grey - SERP Execution App
**Version:** 1.0
**Date:** 2025-01-25
**App Path:** `apps/serp_execution/`
**Master PRD:** [docs/PRD.md](../PRD.md)
**Dependencies:** `search_strategy` (SearchQuery), `review_manager` (SearchSession)
**Status:** Production Ready

## 1. Executive Summary

The SERP Execution app manages the automated execution of search queries against external search APIs, primarily Google Search via Serper.dev. It handles background task orchestration, API rate limiting, cost management, and comprehensive error recovery. This app transforms search strategies into actual search results while providing real-time progress monitoring and intelligent error handling.

### Key Responsibilities

- **Query Execution**: Execute search queries via Serper API with rate limiting
- **Background Processing**: Manage Celery tasks for asynchronous execution
- **Progress Tracking**: Real-time monitoring of search execution status
- **Error Recovery**: Intelligent handling of API errors with automatic recovery
- **Cost Management**: Track API usage and credits with budget controls

### Integration Points

- **Triggered by**: `search_strategy` ("Execute Search" action with immediate query handoff)
- **Provides to**: `results_manager` (seamless transition with raw search results)
- **User Experience**: Progress status page with real-time updates and automatic redirection
- **Coordinates with**: Celery/Redis for background processing and status monitoring

## 2. Technical Architecture

### 2.1 Technology Stack

- **Framework**: Django 4.2 with Celery for async tasks
- **Database**: PostgreSQL for execution tracking
- **Message Broker**: Redis for Celery task queue
- **API Client**: Serper.dev Python SDK with requests
- **Frontend**: Django Templates with AJAX updates
- **Testing**: Django TestCase with mocked API calls
- **Monitoring**: Comprehensive logging with error analytics

### 2.2 App Structure

```
apps/serp_execution/
├── __init__.py
├── admin.py              # Django admin configuration
├── apps.py               # App configuration
├── models.py             # SearchExecution, RawSearchResult
├── views.py              # Execution and monitoring views
├── urls.py               # URL patterns
├── tasks.py              # Celery background tasks
├── recovery.py           # Error recovery manager
├── services/
│   ├── __init__.py
│   ├── serper_client.py  # Serper API client
│   ├── query_builder.py  # Query preparation
│   ├── cache_manager.py  # Response caching
│   ├── usage_tracker.py  # API credit tracking
│   └── result_processor.py # Result processing
├── templates/
│   └── serp_execution/
│       ├── execute_confirm.html
│       ├── execution_status.html
│       └── components/
│           ├── query_status.html
│           └── error_recovery.html
├── static/
│   └── serp_execution/
│       ├── css/
│       │   └── execution.css
│       └── js/
│           └── execution_monitor.js
├── tests/
│   ├── test_models.py
│   ├── test_views.py
│   ├── test_tasks.py
│   ├── test_api_client.py
│   ├── test_error_recovery.py
│   └── test_integration.py
├── management/
│   └── commands/
│       └── check_serper_connection.py
└── migrations/
```

### 2.3 Database Models

#### SearchExecution Model

```python
from django.db import models
from django.contrib.auth import get_user_model
from apps.search_strategy.models import SearchQuery
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid

User = get_user_model()

class SearchExecution(models.Model):
    """
    Tracks the execution of a search query including status,
    progress, and API usage metrics.
    """

    # Status choices for execution lifecycle
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('retrying', 'Retrying'),
        ('cancelled', 'Cancelled'),
        ('partial', 'Partial Results')
    ]

    # Primary key and relationships
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    query = models.ForeignKey(
        SearchQuery,
        on_delete=models.CASCADE,
        related_name='executions'
    )
    executed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='search_executions'
    )

    # Execution status and progress
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    progress_percentage = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    status_message = models.TextField(blank=True)

    # Timing information
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    execution_time_seconds = models.FloatField(default=0)

    # API tracking
    api_calls_made = models.IntegerField(default=0)
    api_credits_used = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=0
    )

    # Error handling
    error_count = models.IntegerField(default=0)
    last_error = models.TextField(blank=True)
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=3)

    # Results tracking
    total_results_found = models.IntegerField(default=0)
    results_retrieved = models.IntegerField(default=0)

    # Celery task tracking
    task_id = models.CharField(max_length=255, blank=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'search_executions'
        verbose_name = 'Search Execution'
        verbose_name_plural = 'Search Executions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['query']),
            models.Index(fields=['status']),
            models.Index(fields=['task_id']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"Execution of {self.query} - {self.status}"

    def can_retry(self):
        """Check if execution can be retried."""
        return (
            self.status in ['failed', 'partial'] and
            self.retry_count < self.max_retries
        )

    def calculate_cost(self):
        """Calculate estimated cost based on API pricing."""
        # Serper pricing: $0.001 per search
        return float(self.api_credits_used) * 0.001

    def get_duration(self):
        """Get execution duration in human-readable format."""
        if not self.started_at or not self.completed_at:
            return None
        duration = self.completed_at - self.started_at
        return duration.total_seconds()


class RawSearchResult(models.Model):
    """
    Stores raw search results from the Serper API.
    Includes grey literature specific metadata.
    """

    # Primary key and relationships
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    execution = models.ForeignKey(
        SearchExecution,
        on_delete=models.CASCADE,
        related_name='raw_results'
    )

    # Core result data
    title = models.CharField(max_length=500)
    url = models.URLField(max_length=2048)
    snippet = models.TextField()
    position = models.IntegerField()  # Position in search results

    # Grey literature metadata
    domain = models.CharField(max_length=255)
    file_type = models.CharField(max_length=50, blank=True)
    publication_date = models.DateField(null=True, blank=True)

    # Source tracking
    source_type = models.CharField(
        max_length=50,
        choices=[
            ('web', 'Web Search'),
            ('scholar', 'Google Scholar'),
            ('news', 'News Search'),
            ('images', 'Image Search')
        ],
        default='web'
    )

    # Additional metadata from API
    raw_data = models.JSONField(default=dict)
    # Stores complete API response for future processing

    # Processing flags
    is_processed = models.BooleanField(default=False)
    processing_notes = models.TextField(blank=True)

    # Quality indicators
    relevance_score = models.FloatField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(1)]
    )
    has_full_text = models.BooleanField(default=False)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'raw_search_results'
        verbose_name = 'Raw Search Result'
        verbose_name_plural = 'Raw Search Results'
        ordering = ['execution', 'position']
        unique_together = [['execution', 'url']]  # Prevent duplicates
        indexes = [
            models.Index(fields=['execution']),
            models.Index(fields=['is_processed']),
            models.Index(fields=['domain']),
            models.Index(fields=['file_type']),
        ]

    def __str__(self):
        return f"{self.title[:50]}... (Position {self.position})"

    def extract_metadata(self):
        """Extract additional metadata from raw_data."""
        # Implementation for extracting dates, authors, etc.
        pass


class SearchExecutionManager(models.Manager):
    """Custom manager for SearchExecution model."""

    def active_executions(self):
        """Get currently running executions."""
        return self.filter(status__in=['pending', 'running', 'retrying'])

    def failed_executions(self):
        """Get failed executions that can be retried."""
        return self.filter(status='failed', retry_count__lt=models.F('max_retries'))

    def for_session(self, session):
        """Get all executions for a session."""
        return self.filter(query__strategy__session=session)

    def calculate_session_cost(self, session):
        """Calculate total cost for a session."""
        return self.for_session(session).aggregate(
            total_cost=models.Sum('api_credits_used')
        )['total_cost'] or 0
```

## 3. User Workflow

### Search Execution and Progress Monitoring

The SERP Execution app provides a seamless execution experience with real-time progress monitoring:

1. **Automatic Trigger**: User clicks "Execute Search" in Search Strategy app
2. **Immediate Handoff**: Session transitions to `executing` status and queries are passed to SERP Execution
3. **Progress Status Page**: User is automatically redirected to progress monitoring interface showing:
   - Real-time execution status for each search query
   - Progress indicators and completion percentages
   - Error handling and recovery status
   - API usage and cost tracking
4. **Background Processing**: Celery tasks execute searches asynchronously while user monitors progress
5. **Automatic Transition**: Upon completion, session transitions to `processing_results` and user is redirected to Results Manager

### Status Flow Integration

This app manages the critical `executing` → `processing_results` transition:
- **Entry Point**: Receives validated queries from Search Strategy with session in `executing` status
- **Process**: Executes queries via Serper API with comprehensive error handling and rate limiting
- **Exit Point**: Delivers raw results to Results Manager and transitions session to `processing_results`
- **User Experience**: Continuous progress visibility with automatic workflow progression

## 4. API Endpoints

### Phase 1 - Internal AJAX APIs (Current)

| Endpoint | Method | Purpose | Authentication |
|----------|---------|---------|----------------|
| `/api/execution/status/<execution_id>/` | GET | Get execution status | Login required |
| `/api/execution/progress/<session_id>/` | GET | Get session progress | Login + ownership |
| `/api/execution/retry/<execution_id>/` | POST | Retry failed execution | Login + ownership |
| `/api/execution/cancel/<session_id>/` | POST | Cancel all executions | Login + ownership |

### Phase 2 - REST API (Future)

Full REST API for programmatic access to search execution functionality.

## 5. User Interface

### 4.1 Views

#### ExecuteSearchView
- **Purpose**: Confirm and initiate search execution
- **URL**: `/review/session/{session_id}/execute/`
- **Template**: `serp_execution/execute_confirm.html`
- **Permissions**: Login required, session ownership, strategy_ready status
- **Features**:
  - Query preview with counts
  - Cost estimation display
  - Execution options (parallel/sequential)
  - Warning for large searches

#### SearchExecutionStatusView
- **Purpose**: Monitor execution progress in real-time
- **URL**: `/review/session/{session_id}/execution/status/`
- **Template**: `serp_execution/execution_status.html`
- **Permissions**: Login required, session ownership
- **Features**:
  - Real-time progress updates via AJAX
  - Individual query status tracking
  - Error display with recovery options
  - Cancel/pause functionality

#### ErrorRecoveryView
- **Purpose**: Manage and recover from execution errors
- **URL**: `/review/session/{session_id}/execution/recovery/`
- **Template**: `serp_execution/error_recovery.html`
- **Permissions**: Login required, session ownership
- **Features**:
  - Error classification and analysis
  - One-click recovery actions
  - Bulk retry operations
  - Manual intervention options

### 4.2 URL Configuration

```python
app_name = 'serp_execution'

urlpatterns = [
    # Execution management
    path('session/<uuid:session_id>/execute/',
         views.ExecuteSearchView.as_view(),
         name='execute'),
    path('session/<uuid:session_id>/execution/status/',
         views.SearchExecutionStatusView.as_view(),
         name='status'),
    path('session/<uuid:session_id>/execution/recovery/',
         views.ErrorRecoveryView.as_view(),
         name='recovery'),

    # API endpoints
    path('api/status/<uuid:execution_id>/',
         views.execution_status_api,
         name='api_status'),
    path('api/progress/<uuid:session_id>/',
         views.session_progress_api,
         name='api_progress'),
    path('api/retry/<uuid:execution_id>/',
         views.retry_execution_api,
         name='api_retry'),
]
```

## 6. Business Logic

### 5.1 Services

#### SerperClient Service
```python
class SerperClient:
    """Handles communication with Serper API."""

    def __init__(self):
        self.api_key = settings.SERPER_API_KEY
        self.base_url = "https://api.serper.dev"
        self.timeout = 30
        self.session = self._create_session()

    def search(self, query, num_results=10, **kwargs):
        """Execute a search query."""
        # Implementation with rate limiting and error handling
        pass

    def check_rate_limits(self):
        """Check current rate limit status."""
        pass

    def get_usage_stats(self):
        """Get API usage statistics."""
        pass
```

#### QueryBuilder Service
- Prepares queries for API submission
- Handles query length optimization
- Manages special characters and encoding
- Adds search parameters and filters

#### CacheManager Service
- Caches API responses to reduce costs
- Implements TTL-based expiration
- Provides cache invalidation
- Tracks cache hit rates

#### UsageTracker Service
- Monitors API credit usage
- Implements budget controls
- Provides usage analytics
- Alerts on threshold breaches

### 5.2 Background Tasks

#### Celery Tasks (`tasks.py`)
```python
from celery import shared_task
from django.db import transaction

@shared_task(bind=True, max_retries=3)
def initiate_search_session_execution_task(self, session_id):
    """Orchestrate execution of all queries for a session."""
    # Get all queries and create execution records
    # Dispatch individual query tasks
    # Monitor completion
    pass

@shared_task(bind=True, max_retries=3)
def perform_serp_query_task(self, execution_id):
    """Execute a single search query."""
    # Call Serper API
    # Store raw results
    # Update execution status
    # Handle errors with retry
    pass

@shared_task
def monitor_session_completion_task(session_id):
    """Monitor and update session completion status."""
    # Check all executions
    # Update session status
    # Trigger next workflow step
    pass
```

### 5.3 Error Recovery

#### ErrorRecoveryManager
```python
class ErrorRecoveryManager:
    """Intelligent error recovery system."""

    ERROR_STRATEGIES = {
        'rate_limit': 'exponential_backoff',
        'timeout': 'query_modification',
        'invalid_query': 'query_simplification',
        'quota_exceeded': 'partial_results',
        'network_error': 'immediate_retry',
        'auth_error': 'manual_intervention',
        'server_error': 'linear_backoff',
        'unknown': 'adaptive_strategy'
    }

    def classify_error(self, error):
        """Classify error type for appropriate recovery."""
        pass

    def apply_recovery_strategy(self, execution, error_type):
        """Apply recovery strategy based on error type."""
        pass

    def generate_recovery_options(self, session):
        """Generate recovery options for user intervention."""
        pass
```

## 7. Testing Requirements

### 6.1 Unit Tests

#### Model Tests (`test_models.py`)
- SearchExecution creation and validation
- Status transition logic
- Cost calculation accuracy
- Retry eligibility checks
- Manager method functionality

#### Task Tests (`test_tasks.py`)
- Celery task execution with mocks
- Error handling and retry logic
- Progress tracking updates
- Session status transitions
- Rate limiting compliance

#### API Client Tests (`test_api_client.py`)
- Serper API mocking
- Response parsing
- Error handling scenarios
- Rate limit management
- Connection pooling

### 6.2 Integration Tests

#### Workflow Integration (`test_integration.py`)
- Complete execution flow
- Error recovery workflows
- Status update propagation
- Result storage verification
- Session workflow transitions

### 6.3 Error Recovery Tests

#### Recovery Scenarios (`test_error_recovery.py`)
- Rate limit recovery
- Timeout handling
- Network error resilience
- Quota management
- Manual intervention flows

## 8. Performance Optimization

### 7.1 Database Optimization
- Efficient bulk inserts for results
- Optimized status queries
- Connection pooling for API calls
- Indexed fields for common lookups

### 7.2 Background Task Optimization
- Parallel query execution
- Task result caching
- Efficient task routing
- Resource-aware scheduling

### 7.3 API Optimization
- Response caching strategy
- Request batching where possible
- Connection reuse
- Adaptive rate limiting

## 9. Security Considerations

### 8.1 API Security
- Secure API key storage (environment variables)
- Request signing and validation
- SSL/TLS for all API calls
- API key rotation support

### 8.2 Data Security
- Sanitize search queries
- Validate result data
- Secure result storage
- Activity logging for audit

### 8.3 Access Control
- Session ownership validation
- Execution permission checks
- API usage limits per user
- Rate limiting per account

## 10. Phase Implementation

### Phase 1 - Current Implementation ✅
- Complete model architecture
- Serper API integration
- Celery task orchestration
- Real-time progress monitoring
- Basic error handling and retry
- Cost tracking and estimation
- Comprehensive error recovery system

### Phase 2 - Future Enhancements
- Advanced query optimization
- Multi-API support (Bing, DuckDuckGo)
- Scheduled execution
- Batch execution management
- Advanced analytics dashboard
- Machine learning for result ranking
- Export to citation managers

## 11. Development Checklist

### Initial Setup ✅
- [x] Create app structure
- [x] Configure Celery tasks
- [x] Set up API credentials
- [x] Create URL routing

### Models & Database ✅
- [x] Implement SearchExecution model
- [x] Implement RawSearchResult model
- [x] Create custom managers
- [x] Run migrations

### API Integration ✅
- [x] Implement SerperClient
- [x] Add rate limiting
- [x] Create caching layer
- [x] Test API connection

### Background Tasks ✅
- [x] Configure Celery routing
- [x] Implement task orchestration
- [x] Add retry logic
- [x] Create monitoring tasks

### User Interface ✅
- [x] Create execution views
- [x] Build status monitoring
- [x] Add AJAX updates
- [x] Implement error recovery UI

### Error Handling ✅
- [x] Implement recovery manager
- [x] Create recovery strategies
- [x] Add user interventions
- [x] Test all scenarios

### Testing ✅
- [x] Unit tests for all components
- [x] Integration tests
- [x] Error scenario tests
- [x] Performance tests

## 12. Success Metrics

### Functional Metrics
- All queries execute successfully
- Real-time progress updates working
- Error recovery rate >85%
- Cost tracking accurate to $0.001

### Performance Metrics
- Query execution <5 seconds average
- Status updates <100ms latency
- Parallel execution efficiency >80%
- Cache hit rate >30%

### Reliability Metrics
- Automatic recovery success >85%
- Zero data loss on errors
- 99.9% task completion rate
- <1% duplicate results

### User Experience Metrics
- Clear progress indication
- Intuitive error messages
- One-click recovery actions
- Accurate cost estimates

## 13. References

- Master PRD: [docs/PRD.md](../PRD.md)
- Search Strategy PRD: [docs/search-strategy/search-strategy-prd.md](../search-strategy/search-strategy-prd.md)
- Implementation Tasks: [docs/serp_execute.md/tasks-serp-execution.md](../serp_execute.md/tasks-serp-execution.md)
- Serper API Documentation: https://serper.dev/docs
- Celery Best Practices Documentation
- Django Celery Integration Guide
