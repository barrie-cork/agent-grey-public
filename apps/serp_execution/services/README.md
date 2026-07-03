# SERP Execution Services - Core Requirements Edition

This directory contains the enhanced service layer for the SERP (Search Engine Results Page) execution functionality in Agent Grey Core Requirements Edition. These services handle the complete pipeline from search query execution through intelligent result processing, following PRISMA-compliant systematic review methodology.

## Overview

The SERP execution services provide a comprehensive system for:

- **Enhanced Search Execution**: Execute grey literature searches via the Serper API with circuit breaker protection
- **Intelligent Result Processing**: Extract, normalise, and deduplicate search results with metadata enrichment  
- **Production Caching**: Redis-based caching with automatic fallback for high-availability deployments
- **Execution Orchestration**: Complete session management with real-time progress tracking
- **PIC Framework Integration**: Advanced query building from Population, Interest, Context terms

## Enhanced Service Architecture

The services follow a production-ready, layered architecture with dependency injection:

```
┌─────────────────────── View Services ──────────────────────┐
│ StatusViewService │ RecoveryViewService │ ExecutionService │
└─────────────┬───────────────────────────────────────┬─────┘
              │                                       │
┌─────────────▼──────────── Core Services ────────────▼─────┐
│ SerperClient ───► QueryBuilder ───► ResultProcessor      │
│      │                                        │          │
│      ▼                                        ▼          │
│ CacheManager ◄──── Circuit Breaker ────► StatisticsServ  │
└─────────────────────────────────────────────────────────┘
              │                                       │
┌─────────────▼──── Infrastructure Services ─────────▼─────┐
│ HTTPClient │ RateLimiter │ SerperValidator │ Processor   │
└─────────────────────────────────────────────────────────┘
```

### Enhanced Data Flow

1. **Strategy Integration**: Services receive SearchQuery objects with PIC framework data
2. **Query Building**: `QueryBuilder` creates optimised search strings with domain filtering
3. **Protected Execution**: `SerperClient` with circuit breaker protection and rate limiting
4. **Intelligent Processing**: `ResultProcessor` extracts metadata and prepares for deduplication
5. **Real-time Updates**: Progress tracking integrated with core.progress.tracker
6. **Error Recovery**: Categorised error handling with intelligent retry strategies

## Service Layer Architecture (Refactored 2025)

As part of the vertical slice architecture refactoring, the SERP execution app now follows a clean service layer pattern:

### API Services (`api_service.py`)
Centralized business logic for all API endpoints:
- **ExecutionAPIService**: Handles execution status queries
- **SessionAPIService**: Manages session progress and cancellation
- **DiagnosticAPIService**: Provides API testing functionality
- **RecoveryAPIService**: Manages retry operations

### View Services (`view_services/`)
Business logic extracted from Django views:
- **ExecutionViewService**: Logic for ExecuteSearchView
- **StatusViewService**: Logic for SearchExecutionStatusView
- **RecoveryViewService**: Error recovery and retry logic

### Statistics Services (`statistics_service.py`)
Calculation and aggregation services:
- **ExecutionStatisticsService**: Enhanced statistics calculations
- **SessionProgressService**: Session progress metrics

This refactoring achieved:
- 60% reduction in views.py size (964 → 382 lines)
- Clean separation of HTTP handling from business logic
- Improved testability with isolated service classes
- Type hints on all service methods
- Pydantic validation for API responses

## Individual Service Documentation

### SerperClient

**Purpose**: Enhanced API client for executing search queries via Serper API with production-ready features.

**Key Methods**:
- `search(query, num_results=10, session=None, **kwargs)` - Execute search with progress tracking
- `safe_search(query, num_results=10, **kwargs)` - Search with circuit breaker fallback
- `validate_query(query)` - Comprehensive query validation
- Enhanced request parameter building with processor integration

**Production Features**:
```python
# Circuit breaker protection
@serper_circuit_breaker
def search(self, query, num_results=10, session=None, **kwargs):
    # Protected API execution with graceful degradation
    
# Integration with core services
client = SerperClient()
client.rate_limiter = get_rate_limiter()  # Dependency injection
client.cache_manager = get_cache_manager()
```

**Enhanced Rate Limiting**:
- Intelligent rate limiting based on API response headers
- Circuit breaker protection preventing cascade failures
- Connection pooling with retry strategies
- Real-time rate limit monitoring

**Comprehensive Error Handling**:
- `SerperRateLimitError` - Rate limit exceeded with retry recommendations
- `SerperAuthError` - Invalid API key with configuration guidance
- `SerperQuotaError` - API quota exhausted with budget suggestions
- `SerperTimeoutError` - Request timeout with retry logic
- `SerperConnectionError` - Network connectivity issues

**Enhanced Usage**:
```python
from apps.core.services.serper_client import SerperClient

# Production usage with session tracking
client = SerperClient()
results, metadata = client.search(
    "diabetes AND mobile health",
    num_results=100,
    session=search_session,  # For progress updates
    location="United Kingdom",
    file_types=["pdf"]
)

# Safe search with circuit breaker fallback
safe_results = client.safe_search(
    "telemedicine AND elderly",
    num_results=50
)
if safe_results.get('error'):
    # Handle graceful degradation
    logger.warning(f"Search fallback: {safe_results['error']}")
```

### QueryBuilder

**Purpose**: Advanced query construction from PIC framework with domain filtering and optimisation.

**Key Methods**:
- `build_query(population, interest, context, file_types=None, domain=None)` - Build optimised search query
- `encode_for_url(query)` - URL encode query string with proper escaping
- `validate_query_components()` - Validate PIC components before building

**Enhanced Features**:
- **Advanced Boolean Logic**: Optimised AND/OR combinations with proper precedence
- **Domain-specific Queries**: Support for targeted domain searches
- **File Type Optimisation**: Enhanced file type filtering with precedence
- **Query Length Optimisation**: Automatic truncation and optimisation for API limits
- **Term Prioritisation**: PIC component prioritisation for optimal results

**Production Usage**:
```python
from .services import QueryBuilder

builder = QueryBuilder()

# General query
general_query = builder.build_query(
    population="elderly patients",
    interest="telemedicine interventions", 
    context="rural healthcare settings",
    file_types=["pdf", "doc"]
)

# Domain-specific query  
domain_query = builder.build_query(
    population="elderly patients",
    interest="telemedicine interventions",
    context="rural healthcare settings",
    domain="nhs.uk",
    file_types=["pdf"]
)
# Result: site:nhs.uk "elderly patients" AND "telemedicine interventions" AND "rural healthcare settings" filetype:pdf
```

### ResultProcessor

**Purpose**: Simple processing of raw search results from Serper API into normalized data.

**Key Methods**:
- `process_search_results(raw_results)` - Process API results
- `extract_metadata(result)` - Extract basic metadata from a result

**Processing Features**:
- **Basic Normalization**: URL, title, and snippet extraction
- **File Type Detection**: Simple file type detection from URLs
- **Domain Extraction**: Extract domain from URLs
- **Metadata Extraction**: Basic result metadata

**Example Processing Flow**:
```python
processor = ResultProcessor()
processed_results = processor.process_search_results(
    raw_results=api_response['organic']
)
```



### CacheManager

**Purpose**: Production-grade caching system with intelligent fallback and cost optimisation.

**Key Methods**:
- `get_search_results(query_params)` - Retrieve cached results with fallback handling
- `set_search_results(query_params, results, custom_ttl=None)` - Cache with dynamic TTL
- `invalidate_search_results(query_params)` - Selective cache invalidation
- `get_cache_statistics()` - Performance monitoring and hit rate analysis

**Advanced Caching Strategy**:
- **Dynamic TTL**: Adaptive cache duration based on query complexity and result quality
- **Intelligent Key Generation**: Normalised MD5 hash keys with collision detection
- **High-Availability Redis**: Production Redis integration with automatic failover
- **Query Similarity Detection**: Avoid duplicate API calls for similar queries

**Production Configuration**:
```python
# Enhanced caching settings
SERP_CACHE_ENABLED = True
SERP_CACHE_TTL = 3600  # Base TTL
SERP_CACHE_MAX_TTL = 86400  # Maximum TTL for high-quality results
REDIS_CONNECTION_POOL_SIZE = 50
CACHE_VERSION_CONTROL = True  # Support for cache versioning
```

**High-Availability Features**:
- **SafeRedisWrapper Integration**: Automatic fallback when Redis unavailable
- **Connection Pool Management**: Optimised Redis connections with health checks
- **Cache Warming**: Pre-population of frequently accessed queries
- **Memory Management**: Intelligent cache eviction with LRU policies
- **Zero-downtime Deployments**: Cache versioning for seamless updates

### ExecutionService

**Purpose**: Basic execution coordination and statistics.

**Key Methods**:
- `get_execution_statistics(session_id)` - Basic session execution stats

**Features**:
- **Basic Statistics**: Total, successful, and failed execution counts
- **Success Rate**: Percentage of successful executions
- **Simple Metrics**: No complex analysis or estimation


## Usage Examples

### Simple Search Execution Flow

```python
from apps.core.services.serper_client import SerperClient
from apps.serp_execution.services import (
    QueryBuilder, ResultProcessor, CacheManager
)

# 1. Build simple query
builder = QueryBuilder()
query = builder.build_query(
    population="diabetes patients",
    interest="mobile health apps",
    context="self-management",
    file_types=["pdf"]
)

# 2. Execute search with caching
client = SerperClient()
results, metadata = client.search(query, num_results=100, use_cache=True)

# 3. Process results
processor = ResultProcessor()
processed_results = processor.process_search_results(
    raw_results=results.get('organic', [])
)

# 4. Extract metadata if needed
for result in processed_results:
    metadata = processor.extract_metadata(result)
    print(f"Domain: {metadata['domain']}, File Type: {metadata['file_type']}")
```

### Basic Query Processing

```python
from apps.core.services.serper_client import SerperClient
from apps.serp_execution.services import QueryBuilder

builder = QueryBuilder()
client = SerperClient()

queries = [
    ("elderly", "telemedicine", "rural areas"),
    ("children", "mental health", "school settings"),
    ("cancer patients", "support groups", "online communities")
]

for population, interest, context in queries:
    query = builder.build_query(population, interest, context)

    # Validate before execution
    is_valid, error = client.validate_query(query)
    if not is_valid:
        print(f"Invalid query: {error}")
        continue

    try:
        results, metadata = client.search(query)
        print(f"Found {len(results.get('organic', []))} results")
    except Exception as e:
        print(f"Search failed: {e}")
```

## Configuration Guide

### Environment Variables

Required environment variables in `.env`:

```bash
# Serper API Configuration
SERPER_API_KEY=your-serper-api-key-here

# Cache Configuration (optional)
SERP_CACHE_ENABLED=True
SERP_CACHE_TTL=3600  # Default TTL in seconds (1 hour)
```

### Django Settings

Add to your Django settings:

```python
# API Configuration
SERPER_API_KEY = config('SERPER_API_KEY', default='')

# Cache Configuration
SERP_CACHE_ENABLED = config('SERP_CACHE_ENABLED', default=True, cast=bool)
SERP_CACHE_TTL = config('SERP_CACHE_TTL', default=3600, cast=int)

# Caching Backend (Redis recommended for production)
# SafeRedisWrapper provides automatic fallback handling
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

# Redis connection automatically handled by SafeRedisWrapper:
# - Detects Redis availability at runtime
# - Falls back to database/memory cache when Redis unavailable
# - Handles connection pooling and error recovery
# - Zero configuration required for deployment flexibility
```

### API Limits and Costs

**Serper API Limits**:
- Rate limit: 300 requests per second
- Cost: $0.001 per search query
- Free tier: 2,500 queries per month

**Built-in Rate Limiting**:
- Automatic rate limiting to respect API limits
- Connection pooling for efficiency
- Retry logic for transient failures

## Error Handling

### Basic Error Recovery

The services include basic error handling with automatic retries:

1. **Built-in Retries**: Automatic retry for network and rate limit errors
2. **Rate Limit Handling**: Respects API rate limits with delays
3. **Connection Pooling**: Reduces connection-related errors
4. **Authentication/Quota Errors**: Clear error messages for manual intervention

### Common Error Scenarios

**Rate Limit Exceeded**:
```python
try:
    results, metadata = client.search(query)
except SerperRateLimitError as e:
    # Automatic retry handled by client
    # Log error and handle gracefully
    logger.error(f"Rate limit exceeded: {e}")
```

**API Authentication**:
```python
try:
    client = SerperClient()
except ValueError as e:
    # Missing or invalid API key
    logger.error("SERPER_API_KEY not configured")
```

### Error Recovery Strategies

1. **Rate Limit Strategy**: Uses `Retry-After` header or built-in delays
2. **Network Error Strategy**: Basic retry with exponential backoff
3. **Quota/Auth Errors**: No automatic retry, requires manual intervention

## Development Guidelines

### Extending Services

To add new services:

1. **Simple Pattern**: Follow the existing simple service patterns
2. **Basic Error Handling**: Implement basic exception handling
3. **Testing**: Write unit tests with mocking for external APIs
4. **Documentation**: Update this README with new service information

### Simple Service Guidelines

```python
class NewService:
    """Simple service description."""

    def __init__(self):
        """Initialize service."""
        self.config = getattr(settings, 'CONFIG_NAME', 'default')

    def main_operation(self, required_param: str) -> Dict[str, Any]:
        """
        Primary service operation.

        Args:
            required_param: Description of required parameter

        Returns:
            Dictionary with operation results
        """
        try:
            # Simple implementation
            return {"success": True, "data": result}
        except Exception as e:
            logger.error(f"Operation failed: {str(e)}")
            raise
```

### Testing Services

Services should have basic test coverage. Example test pattern:

```python
from unittest.mock import Mock, patch
from django.test import TestCase, override_settings

class TestSerperClient(TestCase):

    @override_settings(SERPER_API_KEY="test-key")
    def setUp(self):
        self.client = SerperClient()

    @patch('requests.Session.post')
    def test_successful_search(self, mock_post):
        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"organic": []}
        mock_post.return_value = mock_response

        # Test search
        results, metadata = self.client.search("test query")

        # Assertions
        self.assertIsInstance(results, dict)
        self.assertIn("organic", results)
```

### Performance Considerations

1. **Caching**: Enable caching for production to reduce API costs
2. **Connection Pooling**: SerperClient uses connection pooling for efficiency
3. **Rate Limiting**: Built-in rate limiting prevents API abuse
4. **Basic Monitoring**: Error logging and basic statistics

### Security Considerations

1. **API Key Protection**: Never log or expose API keys
2. **Input Validation**: Basic validation before API calls
3. **Rate Limiting**: Built-in protection against API abuse with Redis fallback
4. **Error Information**: Error details are logged but not exposed to users
5. **Safe Redis Connections**: Automatic fallback prevents Redis connection failures from breaking the application

## Integration with Agent Grey Core Requirements Edition

The enhanced SERP execution services integrate seamlessly with the Core Requirements Edition architecture:

### Upstream Integration
- **search_strategy**: Receives SearchQuery objects with PIC framework data and domain configurations
- **review_manager**: Integrates with 9-state workflow transitions and session lifecycle management
- **accounts**: User authentication, session ownership validation, and usage tracking

### Downstream Integration  
- **results_manager**: Passes processed RawSearchResult objects for deduplication and normalisation
- **core.progress.tracker**: Real-time progress updates with component-specific tracking
- **core.services.simple_services**: Base service layer with dependency injection

### Core Services Integration
- **serp_execution.dependencies**: Dependency injection registry for session/notification providers
- **core.cache**: Distributed caching with Redis fallback capabilities
- **core.monitoring**: Performance monitoring and health check integration

## Production Deployment Considerations

### High Availability
- **Circuit Breaker Protection**: Automatic API protection with graceful degradation
- **Redis Fallback**: Automatic fallback to database caching when Redis unavailable
- **Connection Pooling**: Optimised HTTP and database connections
- **Health Checks**: Automated service health monitoring

### Scalability Features
- **Horizontal Scaling**: Stateless services supporting load balancing
- **Async Processing**: Full Celery integration for background task processing
- **Cache Distribution**: Redis-based distributed caching across instances
- **Rate Limit Coordination**: Distributed rate limiting for multi-instance deployments

### Monitoring & Observability
- **Performance Metrics**: Detailed execution timing and success rate tracking
- **Error Categorisation**: Structured error logging with actionable insights
- **Cost Tracking**: API usage monitoring with budget awareness
- **Real-time Dashboards**: Integration with monitoring systems

This enhanced service layer provides a production-ready foundation for executing systematic grey literature searches with enterprise-grade reliability, intelligent error recovery, and comprehensive observability.
