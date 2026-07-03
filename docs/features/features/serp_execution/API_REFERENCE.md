# SERP Execution API Reference

## Table of Contents
1. [Models API](#models-api)
2. [Service Layer API](#service-layer-api)
3. [Task API](#task-api)
4. [Client API](#client-api)
5. [View API](#view-api)
6. [Utility API](#utility-api)

## Models API

### SearchExecution

**Location**: `apps/serp_execution/models.py:11`

#### Fields

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| `id` | UUIDField | Primary key | Auto-generated, unique |
| `query` | ForeignKey | Reference to SearchQuery | CASCADE on delete |
| `initiated_by` | ForeignKey | User who initiated execution | SET_NULL on delete |
| `status` | CharField | Current execution status | Choices: pending, running, completed, failed, cancelled, rate_limited |
| `search_engine` | CharField | Search engine used | Default: 'google' |
| `api_request_id` | CharField | External API tracking ID | Max 255 chars, optional |
| `api_parameters` | JSONField | Parameters sent to API | Default: {} |
| `started_at` | DateTimeField | Execution start time | Nullable |
| `completed_at` | DateTimeField | Execution completion time | Nullable |
| `duration_seconds` | FloatField | Execution duration | Auto-calculated |
| `results_count` | IntegerField | Number of results | Default: 0 |
| `results_offset` | IntegerField | Pagination offset | Default: 0 |
| `api_result_count` | IntegerField | Raw API result count | Nullable |
| `error_message` | TextField | Error details if failed | Optional |
| `retry_count` | IntegerField | Number of retries | Default: 0 |
| `celery_task_id` | CharField | Async task ID | Max 255 chars, optional |
| `created_at` | DateTimeField | Record creation time | Auto-generated |
| `updated_at` | DateTimeField | Last update time | Auto-updated |

#### Methods

```python
def can_retry(self) -> bool:
    """
    Check if execution can be retried.

    Returns:
        bool: True if status is failed/rate_limited and retry_count < 3

    Example:
        if execution.can_retry():
            retry_execution_task.delay(execution.id)
    """

def save(self, *args, **kwargs) -> None:
    """
    Override save to auto-calculate duration.
    Sets duration_seconds when status changes to completed.
    """
```

### RawSearchResult

**Location**: `apps/serp_execution/models.py:128`

#### Fields

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| `id` | UUIDField | Primary key | Auto-generated |
| `execution` | ForeignKey | Parent execution | CASCADE on delete |
| `position` | IntegerField | Result position | 1-based indexing |
| `title` | TextField | Result title | Required |
| `link` | URLField | Result URL | Max 2048 chars |
| `snippet` | TextField | Result description | Optional |
| `display_link` | CharField | Display URL | Max 255 chars |
| `source` | CharField | Source website | Max 255 chars |
| `raw_data` | JSONField | Complete API response | Default: {} |
| `has_pdf` | BooleanField | PDF indicator | Default: False |
| `has_date` | BooleanField | Date detected | Default: False |
| `detected_date` | DateField | Extracted date | Nullable |
| `language_code` | CharField | Language code | Max 10 chars |
| `is_processed` | BooleanField | Processing status | Default: False |
| `processing_error` | TextField | Processing error | Optional |
| `created_at` | DateTimeField | Creation time | Auto-generated |

#### Methods

```python
def get_domain(self) -> str:
    """
    Extract domain from URL.

    Returns:
        str: Domain name (e.g., 'example.com')

    Example:
        domain = result.get_domain()  # 'scholar.google.com'
    """
```

## Service Layer API

### ExecutionOrchestrator

**Location**: `apps/serp_execution/services/execution_orchestrator.py:25`

#### Constructor

```python
def __init__(self, celery_task_id: Optional[str] = None):
    """
    Initialize orchestrator.

    Args:
        celery_task_id: Optional Celery task ID for tracking
    """
```

#### Methods

```python
def execute_session(self, session_id: UUID) -> SessionExecutionResult:
    """
    Execute a search session.

    Args:
        session_id: UUID of the session to execute

    Returns:
        SessionExecutionResult: Execution result with status

    Raises:
        ValidationError: If session cannot be executed
        ExecutionError: If execution fails

    Example:
        orchestrator = ExecutionOrchestrator()
        result = orchestrator.execute_session(session.id)
        if result.success:
            print(f"Executed {result.queries_count} queries")
    """
```

### SerperClient

**Location**: `apps/core/services/serper_client.py:37`

#### Constructor

```python
def __init__(
    self,
    http_client: HTTPClient = None,
    rate_limiter = None
):
    """
    Initialize Serper API client.

    Args:
        http_client: Optional HTTP client instance
        rate_limiter: Optional rate limiter instance

    Raises:
        ValueError: If SERPER_API_KEY not configured
    """
```

#### Methods

```python
def search(
    self,
    query: str,
    num_results: int = 10,
    **kwargs
) -> Tuple[dict, dict]:
    """
    Execute a search query.

    Args:
        query: Search query string
        num_results: Number of results (max 100)
        **kwargs: Additional parameters (date_from, language, etc.)

    Returns:
        Tuple[dict, dict]: (results_data, metadata)

    Raises:
        SerperRateLimitError: Rate limit exceeded
        SerperAuthError: Authentication failed
        SerperQuotaError: Quota exceeded
        SerperAPIError: General API error

    Example:
        client = SerperClient()
        results, meta = client.search(
            "machine learning filetype:pdf",
            num_results=50,
            date_from="2023-01-01"
        )
    """

def safe_search(
    self,
    query: str,
    num_results: int = 10,
    **kwargs
) -> Tuple[dict, dict]:
    """
    Search with graceful fallback.

    Returns empty results instead of raising exceptions.
    Use in tasks for graceful degradation.

    Returns:
        Tuple[dict, dict]: Results or error response with metadata
    """

def check_rate_limits(self) -> dict:
    """
    Check current rate limit status.

    Returns:
        dict: {
            'tokens': int,
            'rate_limit': int,
            'status': str,
            'can_make_request': bool,
            'wait_time': float
        }
    """

def validate_query(self, query: str) -> Tuple[bool, Optional[str]]:
    """
    Validate search query.

    Args:
        query: Query string to validate

    Returns:
        Tuple[bool, Optional[str]]: (is_valid, error_message)
    """

def validate_response_structure(
    self,
    response_data: dict
) -> Tuple[bool, Optional[str], List[str]]:
    """
    Validate API response structure.

    Returns:
        Tuple[bool, Optional[str], List[str]]:
            (is_valid, error_message, warnings)
    """
```

### GlobalRateLimiter

**Location**: `apps/serp_execution/services/rate_limiter.py:15`

#### Constructor

```python
def __init__(self, key_prefix: str = "rate_limit"):
    """
    Initialize rate limiter with Redis backend.

    Args:
        key_prefix: Redis key prefix for namespacing
    """
```

#### Methods

```python
def is_allowed(
    self,
    identifier: str,
    rate: Optional[int] = None,
    burst: Optional[int] = None
) -> Tuple[bool, float]:
    """
    Check if request is allowed.

    Args:
        identifier: Unique identifier (e.g., 'serper_api')
        rate: Requests per minute (default from config)
        burst: Burst capacity (default from config)

    Returns:
        Tuple[bool, float]: (allowed, wait_time_if_denied)

    Example:
        limiter = GlobalRateLimiter()
        allowed, wait = limiter.is_allowed('serper_api')
        if not allowed:
            time.sleep(wait)
    """

def wait_if_needed(
    self,
    identifier: str,
    max_wait: float = 30.0
) -> bool:
    """
    Wait if rate limited.

    Args:
        identifier: Rate limit identifier
        max_wait: Maximum seconds to wait

    Returns:
        bool: True if proceeded, False if timeout
    """

def get_status(self, identifier: str) -> dict:
    """
    Get rate limiter status.

    Returns:
        dict: {
            'tokens': float,
            'rate_limit': int,
            'status': str,
            'last_refill': float
        }
    """
```

## Task API

### Primary Execution Task

**Location**: `apps/serp_execution/tasks.py:56`

```python
@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
)
def initiate_search_session_execution_task(
    self,
    session_id: Union[str, UUID]
) -> dict:
    """
    Initiate search session execution.

    Args:
        session_id: Session UUID (string or UUID object)

    Returns:
        dict: {
            'success': bool,
            'session_id': str,
            'queries_count': int,
            'executions': list,
            'error': Optional[str]
        }

    Raises:
        Retry: On transient errors
        ExecutionError: On permanent failures

    Example:
        result = initiate_search_session_execution_task.delay(
            str(session.id)
        )
        task_id = result.id
    """
```

### Single Query Execution

**Location**: `apps/serp_execution/tasks.py:180`

```python
@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def execute_single_query_task(
    self,
    execution_id: Union[str, UUID]
) -> dict:
    """
    Execute a single search query.

    Args:
        execution_id: SearchExecution UUID

    Returns:
        dict: {
            'success': bool,
            'execution_id': str,
            'results_count': int,
            'error': Optional[str]
        }
    """
```

### Session Monitoring

**Location**: `apps/serp_execution/tasks.py:250`

```python
@shared_task
def monitor_session_execution(session_id: Union[str, UUID]) -> dict:
    """
    Monitor and update session execution status.

    Args:
        session_id: Session UUID

    Returns:
        dict: {
            'session_id': str,
            'status': str,
            'progress': float,  # 0.0 to 1.0
            'completed_queries': int,
            'total_queries': int
        }
    """
```

## Client API

### HTTPClient

**Location**: `apps/serp_execution/services/http_client.py:15`

```python
class HTTPClient:
    """
    HTTP client with retry and timeout handling.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str = None,
        timeout: int = 30,
        max_retries: int = 3
    ):
        """
        Initialize HTTP client.

        Args:
            base_url: Base API URL
            api_key: API authentication key
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
        """

    def post(
        self,
        endpoint: str,
        json_data: dict = None,
        **kwargs
    ) -> requests.Response:
        """
        Make POST request with retry logic.

        Args:
            endpoint: API endpoint path
            json_data: JSON payload
            **kwargs: Additional request parameters

        Returns:
            requests.Response: API response

        Raises:
            requests.exceptions.RequestException: On failure
        """

    def get(
        self,
        endpoint: str,
        params: dict = None,
        **kwargs
    ) -> requests.Response:
        """
        Make GET request with retry logic.
        """
```

## View API

### ExecutionProgressView

**Location**: `apps/serp_execution/views.py:45`

```python
class ExecutionProgressView(LoginRequiredMixin, DetailView):
    """
    Display execution progress with real-time updates.
    """

    model = SearchSession
    template_name = 'serp_execution/progress.html'
    context_object_name = 'session'

    def get_context_data(self, **kwargs) -> dict:
        """
        Get execution progress context.

        Returns:
            dict: {
                'session': SearchSession,
                'executions': QuerySet[SearchExecution],
                'progress': float,
                'estimated_time': int,
                'can_cancel': bool
            }
        """
```

### ExecutionStatusAPI

**Location**: `apps/serp_execution/views.py:120`

```python
class ExecutionStatusAPI(View):
    """
    API endpoint for execution status.
    """

    def get(self, request, session_id: str) -> JsonResponse:
        """
        Get current execution status.

        Returns:
            JsonResponse: {
                'status': str,
                'progress': float,
                'completed_queries': int,
                'total_queries': int,
                'results_count': int,
                'errors': list,
                'next_url': Optional[str]
            }
        """
```

## Utility API

### Circuit Breaker

**Location**: `apps/serp_execution/services/circuit_breaker.py:25`

```python
class DynamicCircuitBreaker:
    """
    Configurable circuit breaker with Redis storage.
    """

    @classmethod
    def create_serper_breaker(cls) -> pybreaker.CircuitBreaker:
        """
        Create circuit breaker for Serper API.

        Configuration from Constance:
        - CIRCUIT_BREAKER_ENABLED
        - CIRCUIT_BREAKER_FAILURE_THRESHOLD
        - CIRCUIT_BREAKER_RECOVERY_TIMEOUT
        - CIRCUIT_BREAKER_EXPECTED_EXCEPTION

        Returns:
            pybreaker.CircuitBreaker: Configured breaker
        """

    @staticmethod
    def reset_breaker(breaker_name: str) -> bool:
        """
        Manually reset circuit breaker.

        Args:
            breaker_name: Name of breaker to reset

        Returns:
            bool: Success status
        """
```

### Query Executor

**Location**: `apps/serp_execution/query_executor.py:15`

```python
class SerpQueryExecutor:
    """
    Execute search queries with result processing.
    """

    def execute_query(
        self,
        execution: SearchExecution
    ) -> Tuple[bool, Optional[str]]:
        """
        Execute a single query.

        Args:
            execution: SearchExecution instance

        Returns:
            Tuple[bool, Optional[str]]: (success, error_message)
        """

    def process_results(
        self,
        execution: SearchExecution,
        api_results: dict
    ) -> int:
        """
        Process and store API results.

        Args:
            execution: SearchExecution instance
            api_results: Raw API response

        Returns:
            int: Number of results processed
        """
```

### Cache Manager

**Location**: `apps/serp_execution/services/cache_manager.py:10`

```python
class SearchCacheManager:
    """
    Cache manager for search results.
    """

    def get_cached_results(
        self,
        query_hash: str
    ) -> Optional[dict]:
        """
        Get cached search results.

        Args:
            query_hash: MD5 hash of query

        Returns:
            Optional[dict]: Cached results or None
        """

    def cache_results(
        self,
        query_hash: str,
        results: dict,
        ttl: int = 3600
    ) -> bool:
        """
        Cache search results.

        Args:
            query_hash: MD5 hash of query
            results: Results to cache
            ttl: Time to live in seconds

        Returns:
            bool: Success status
        """

    @staticmethod
    def generate_query_hash(
        query: str,
        params: dict
    ) -> str:
        """
        Generate hash for query and parameters.

        Returns:
            str: MD5 hash
        """
```

## Error Classes

### Custom Exceptions

**Location**: `apps/core/services/serper_client.py:21`

```python
class SerperAPIError(Exception):
    """Base exception for Serper API errors."""

class SerperRateLimitError(SerperAPIError):
    """Raised when API rate limit is exceeded."""

class SerperAuthError(SerperAPIError):
    """Raised when API authentication fails."""

class SerperQuotaError(SerperAPIError):
    """Raised when API quota is exceeded."""
```

## Response Schemas

### SessionExecutionResult

**Location**: `apps/serp_execution/schemas/task_schemas.py`

```python
class SessionExecutionResult:
    """
    Result of session execution.

    Attributes:
        success: bool
        session_id: UUID
        queries_count: int
        executions: List[dict]
        error: Optional[str]
        error_type: Optional[str]
        duration: Optional[float]
    """
```

### SessionValidationResult

```python
class SessionValidationResult:
    """
    Result of session validation.

    Attributes:
        can_execute: bool
        session_id: UUID
        current_status: str
        error_message: Optional[str]
        warnings: List[str]
    """
```

## Usage Examples

### Basic Search Execution

```python
from apps.core.services.serper_client import SerperClient

# Initialize client
client = SerperClient()

# Execute search
results, metadata = client.search(
    query="artificial intelligence research",
    num_results=50
)

# Process results
for result in results.get('organic', []):
    print(f"{result['position']}: {result['title']}")
    print(f"  URL: {result['link']}")
    print(f"  Snippet: {result['snippet'][:100]}...")
```

### Session Execution

```python
from apps.serp_execution.tasks import initiate_search_session_execution_task

# Launch async execution
task = initiate_search_session_execution_task.delay(
    str(session.id)
)

# Monitor progress
result = task.get(timeout=300)
if result['success']:
    print(f"Executed {result['queries_count']} queries")
else:
    print(f"Execution failed: {result['error']}")
```

### Rate Limit Management

```python
from apps.serp_execution.services.rate_limiter import get_rate_limiter

# Get rate limiter
limiter = get_rate_limiter()

# Check if request allowed
allowed, wait_time = limiter.is_allowed('serper_api')

if not allowed:
    print(f"Rate limited. Wait {wait_time:.2f} seconds")
    time.sleep(wait_time)

# Or use wait helper
if limiter.wait_if_needed('serper_api', max_wait=30):
    # Proceed with request
    pass
else:
    # Timeout waiting for rate limit
    pass
```

### Error Recovery

```python
from apps.core.services.serper_client import (
    SerperClient,
    SerperRateLimitError,
    SerperAuthError
)

client = SerperClient()

try:
    results, meta = client.search(query)
except SerperRateLimitError as e:
    # Handle rate limiting
    logger.warning(f"Rate limited: {e}")
    # Schedule retry
except SerperAuthError as e:
    # Handle auth failure
    logger.error(f"Authentication failed: {e}")
    # Alert admin
except Exception as e:
    # Handle other errors
    logger.error(f"Search failed: {e}")
    # Use fallback
```

## Configuration

### Environment Variables

```bash
# API Configuration
SERPER_API_KEY=your_api_key_here
SERPER_TIMEOUT=30
SERPER_MAX_RETRIES=3

# Rate Limiting
API_RATE_LIMIT_PER_MINUTE=30
API_RATE_LIMIT_BURST=10

# Circuit Breaker
CIRCUIT_BREAKER_ENABLED=True
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=60
```

### Django Settings

```python
# settings/base.py

# SERP Execution Configuration
SERP_EXECUTION_CONFIG = {
    'max_results_per_query': 100,
    'default_language': 'en',
    'default_country': 'us',
    'cache_ttl': 3600,
    'enable_mock_mode': False,
}

# Celery Task Configuration
CELERY_TASK_ROUTES.update({
    'apps.serp_execution.tasks.*': {'queue': 'serp_execution'},
})
```

## Testing

### Mock Client Usage

```python
from apps.serp_execution.services.mock_serper_client import MockSerperClient

# Use mock client in tests
def test_search_execution():
    client = MockSerperClient()
    results, meta = client.search("test query")

    assert len(results['organic']) > 0
    assert meta['credits_used'] == 0  # No real credits used
```

### Test Fixtures

```python
from apps.serp_execution.tests.factories import (
    SearchExecutionFactory,
    RawSearchResultFactory
)

# Create test execution
execution = SearchExecutionFactory(
    status='completed',
    results_count=10
)

# Create test results
results = RawSearchResultFactory.create_batch(
    10,
    execution=execution
)
```

## Performance Considerations

1. **Connection Pooling**: HTTP client uses session for connection reuse
2. **Batch Processing**: Process results in batches of 50
3. **Caching**: Cache duplicate queries for 1 hour
4. **Async Execution**: Use Celery for non-blocking execution
5. **Rate Limiting**: Distributed rate limiting with Redis

## Security Notes

1. **API Key Storage**: Store in environment variables, never in code
2. **Input Validation**: Sanitize all search queries
3. **Error Masking**: Don't expose internal errors to users
4. **Audit Logging**: Log all API calls for compliance
5. **Rate Limiting**: Enforce per-user and global limits
