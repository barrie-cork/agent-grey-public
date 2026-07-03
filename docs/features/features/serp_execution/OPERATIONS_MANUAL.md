# SERP Execution Operations Manual

## Table of Contents
1. [Configuration](#configuration)
2. [Deployment](#deployment)
3. [Monitoring](#monitoring)
4. [Troubleshooting](#troubleshooting)
5. [Performance Tuning](#performance-tuning)
6. [Cost Management](#cost-management)
7. [Maintenance](#maintenance)
8. [Emergency Procedures](#emergency-procedures)

## Configuration

### Environment Variables

#### Required Variables

```bash
# .env.dev.local or production environment

# Serper API Configuration
SERPER_API_KEY=your_serper_api_key_here  # Required: Get from serper.dev
SERPER_TIMEOUT=30                        # API request timeout in seconds
SERPER_MAX_RETRIES=3                     # Maximum retry attempts

# Rate Limiting
API_RATE_LIMIT_PER_MINUTE=30            # Requests per minute limit
API_RATE_LIMIT_BURST=10                 # Burst capacity for spikes

# Circuit Breaker
CIRCUIT_BREAKER_ENABLED=True            # Enable circuit breaker protection
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5     # Failures before opening
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=60     # Seconds before attempting recovery

# Celery Configuration
CELERY_SERP_QUEUE_NAME=serp_execution   # Queue name for SERP tasks
CELERY_SERP_CONCURRENCY=4               # Number of concurrent workers
CELERY_SERP_PREFETCH=2                  # Tasks to prefetch per worker

# Redis Configuration
REDIS_URL=redis://localhost:6379/0      # Redis connection URL
REDIS_RATE_LIMIT_DB=1                   # Redis DB for rate limiting
```

#### Optional Variables

```bash
# Performance Tuning
SERP_CACHE_ENABLED=True                 # Enable result caching
SERP_CACHE_TTL=3600                     # Cache TTL in seconds
SERP_BATCH_SIZE=50                      # Results batch processing size

# Monitoring
SERP_LOG_LEVEL=INFO                     # Logging level
SERP_METRICS_ENABLED=True               # Enable metrics collection
SERP_SENTRY_ENABLED=True                # Enable Sentry error tracking

# Cost Control
SERP_DAILY_CREDIT_LIMIT=10000          # Daily API credit limit
SERP_PER_USER_LIMIT=100                 # Per-user daily limit
SERP_ALERT_THRESHOLD=0.8                # Alert at 80% of limit
```

### Django Settings Configuration

```python
# settings/base.py

# SERP Execution Configuration
SERP_EXECUTION_CONFIG = {
    'api': {
        'provider': 'serper',  # API provider
        'base_url': 'https://google.serper.dev/search',
        'timeout': int(os.environ.get('SERPER_TIMEOUT', 30)),
        'max_retries': int(os.environ.get('SERPER_MAX_RETRIES', 3)),
    },
    'rate_limiting': {
        'requests_per_minute': int(os.environ.get('API_RATE_LIMIT_PER_MINUTE', 30)),
        'burst_capacity': int(os.environ.get('API_RATE_LIMIT_BURST', 10)),
        'redis_db': int(os.environ.get('REDIS_RATE_LIMIT_DB', 1)),
    },
    'circuit_breaker': {
        'enabled': os.environ.get('CIRCUIT_BREAKER_ENABLED', 'True') == 'True',
        'failure_threshold': int(os.environ.get('CIRCUIT_BREAKER_FAILURE_THRESHOLD', 5)),
        'recovery_timeout': int(os.environ.get('CIRCUIT_BREAKER_RECOVERY_TIMEOUT', 60)),
    },
    'execution': {
        'max_results_per_query': 100,
        'default_language': 'en',
        'default_country': 'us',
        'batch_size': int(os.environ.get('SERP_BATCH_SIZE', 50)),
    },
    'caching': {
        'enabled': os.environ.get('SERP_CACHE_ENABLED', 'True') == 'True',
        'ttl': int(os.environ.get('SERP_CACHE_TTL', 3600)),
    },
}

# Celery Task Routes
CELERY_TASK_ROUTES = {
    'apps.serp_execution.tasks.*': {
        'queue': os.environ.get('CELERY_SERP_QUEUE_NAME', 'serp_execution'),
        'routing_key': 'serp.#',
    },
}

# Celery Task Annotations
CELERY_TASK_ANNOTATIONS = {
    'apps.serp_execution.tasks.initiate_search_session_execution_task': {
        'rate_limit': '10/m',  # 10 per minute
        'time_limit': 300,      # 5 minutes hard limit
        'soft_time_limit': 240, # 4 minutes soft limit
    },
    'apps.serp_execution.tasks.execute_single_query_task': {
        'rate_limit': '30/m',   # 30 per minute
        'time_limit': 60,        # 1 minute hard limit
        'soft_time_limit': 45,   # 45 seconds soft limit
    },
}
```

### Constance Dynamic Configuration

```python
# Dynamic settings via Django Constance (runtime configurable)

CONSTANCE_CONFIG = {
    # API Settings
    'SERPER_ENABLED': (True, 'Enable Serper API calls', bool),
    'SERPER_MOCK_MODE': (False, 'Use mock API for testing', bool),

    # Rate Limiting
    'API_RATE_LIMIT_PER_MINUTE': (30, 'API requests per minute', int),
    'API_RATE_LIMIT_BURST': (10, 'Burst capacity', int),

    # Circuit Breaker
    'CIRCUIT_BREAKER_ENABLED': (True, 'Enable circuit breaker', bool),
    'CIRCUIT_BREAKER_FAILURE_THRESHOLD': (5, 'Failures before opening', int),
    'CIRCUIT_BREAKER_RECOVERY_TIMEOUT': (60, 'Recovery timeout seconds', int),

    # Cost Control
    'DAILY_CREDIT_LIMIT': (10000, 'Daily API credit limit', int),
    'CREDIT_ALERT_THRESHOLD': (8000, 'Credit alert threshold', int),

    # Performance
    'SERP_PARALLEL_EXECUTIONS': (4, 'Max parallel executions', int),
    'SERP_RETRY_DELAY': (60, 'Retry delay in seconds', int),
}
```

## Deployment

### Docker Deployment

```yaml
# docker-compose.yml
version: '3.8'

services:
  web:
    environment:
      - SERPER_API_KEY=${SERPER_API_KEY}
      - API_RATE_LIMIT_PER_MINUTE=30
      - CIRCUIT_BREAKER_ENABLED=True
    depends_on:
      - db
      - redis
      - celery_worker

  celery_worker:
    command: celery -A grey_lit_project worker -Q serp_execution -c 4
    environment:
      - SERPER_API_KEY=${SERPER_API_KEY}
      - C_FORCE_ROOT=true
    volumes:
      - ./apps:/app/apps
    depends_on:
      - redis
      - db

  celery_beat:
    command: celery -A grey_lit_project beat -l info
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
```

### Production Deployment Checklist

- [ ] Set production API key in environment
- [ ] Configure rate limits appropriately
- [ ] Enable circuit breaker protection
- [ ] Set up monitoring and alerts
- [ ] Configure backup API provider (if available)
- [ ] Test error recovery mechanisms
- [ ] Verify Celery worker scaling
- [ ] Set up cost tracking alerts
- [ ] Configure log aggregation
- [ ] Enable Sentry error tracking

## Monitoring

### Key Metrics to Monitor

#### 1. API Performance Metrics

```python
# Metrics to track
metrics = {
    'api_requests_total': Counter,       # Total API requests
    'api_requests_success': Counter,     # Successful requests
    'api_requests_failed': Counter,      # Failed requests
    'api_response_time': Histogram,      # Response time distribution
    'api_rate_limit_hits': Counter,      # Rate limit violations
    'api_credits_used': Counter,         # API credits consumed
}
```

#### 2. Execution Metrics

```python
# Session execution metrics
execution_metrics = {
    'sessions_started': Counter,
    'sessions_completed': Counter,
    'sessions_failed': Counter,
    'queries_executed': Counter,
    'results_retrieved': Counter,
    'execution_duration': Histogram,
    'retry_attempts': Counter,
}
```

#### 3. System Health Metrics

```python
# System health indicators
health_metrics = {
    'celery_queue_depth': Gauge,
    'redis_connections': Gauge,
    'circuit_breaker_state': Gauge,  # 0=closed, 1=open, 2=half-open
    'rate_limiter_tokens': Gauge,
    'error_rate': Rate,
}
```

### Monitoring Commands

```bash
# Check execution status
dc run --rm web python manage.py shell << EOF
from apps.serp_execution.models import SearchExecution
from django.utils import timezone
from datetime import timedelta

# Recent executions
recent = SearchExecution.objects.filter(
    created_at__gte=timezone.now() - timedelta(hours=1)
)
print(f"Last hour: {recent.count()} executions")
print(f"Success: {recent.filter(status='completed').count()}")
print(f"Failed: {recent.filter(status='failed').count()}")
print(f"Running: {recent.filter(status='running').count()}")

# Error analysis
errors = recent.filter(status='failed').values_list('error_message', flat=True)
for error in errors[:5]:
    print(f"Error: {error[:100]}")
EOF

# Check Celery queue status
dc exec celery_worker celery -A grey_lit_project inspect stats
dc exec celery_worker celery -A grey_lit_project inspect active
dc exec celery_worker celery -A grey_lit_project inspect reserved

# Check rate limiter status
dc run --rm web python -c "
from apps.serp_execution.services.rate_limiter import get_rate_limiter
rl = get_rate_limiter()
status = rl.get_status('serper_api')
print(f'Rate Limiter Status: {status}')
"

# Check circuit breaker status
dc run --rm web python -c "
from apps.serp_execution.services.circuit_breaker import get_serper_circuit_breaker
cb = get_serper_circuit_breaker()
print(f'Circuit Breaker State: {cb.current_state}')
print(f'Failure Count: {cb.failure_count}')
print(f'Success Count: {cb.success_count}')
"
```

### Logging Configuration

```python
# settings/base.py
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'serp_execution': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/agent-grey/serp_execution.log',
            'maxBytes': 1024 * 1024 * 100,  # 100MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'apps.serp_execution': {
            'handlers': ['serp_execution'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
```

## Troubleshooting

### Common Issues and Solutions

#### 1. API Authentication Failures

**Symptoms**: 401 or 403 errors from Serper API

**Diagnosis**:
```bash
# Test API key
dc run --rm web python -c "
import os
import requests

api_key = os.environ.get('SERPER_API_KEY')
if not api_key:
    print('ERROR: SERPER_API_KEY not set')
else:
    print(f'API Key present: {api_key[:10]}...')

    # Test API call
    headers = {'X-API-KEY': api_key}
    response = requests.post(
        'https://google.serper.dev/search',
        json={'q': 'test'},
        headers=headers
    )
    print(f'Response: {response.status_code}')
    if response.status_code != 200:
        print(f'Error: {response.text}')
"
```

**Solutions**:
- Verify API key is correct
- Check API key permissions
- Ensure key hasn't expired
- Verify billing is current

#### 2. Rate Limiting Issues

**Symptoms**: 429 errors, slow execution

**Diagnosis**:
```bash
# Check rate limit status
dc run --rm web python manage.py shell << EOF
from apps.serp_execution.services.rate_limiter import get_rate_limiter

rl = get_rate_limiter()
status = rl.get_status('serper_api')
print(f"Tokens available: {status['tokens']}")
print(f"Rate limit: {status['rate_limit']}/min")

# Check if we can make request
allowed, wait = rl.is_allowed('serper_api')
if not allowed:
    print(f"Rate limited. Wait {wait:.2f} seconds")
else:
    print("Can make request")
EOF
```

**Solutions**:
- Reduce concurrent executions
- Increase retry delays
- Implement request batching
- Consider upgrading API plan

#### 3. Circuit Breaker Open

**Symptoms**: All requests failing immediately

**Diagnosis**:
```bash
# Check circuit breaker
dc run --rm web python -c "
from apps.serp_execution.services.circuit_breaker import get_serper_circuit_breaker

cb = get_serper_circuit_breaker()
print(f'State: {cb.current_state}')
print(f'Failures: {cb.failure_count}')
print(f'Last failure: {cb.last_failure_time}')

if cb.current_state == 'open':
    print(f'Opens in: {cb.time_until_half_open()} seconds')
"
```

**Solutions**:
```python
# Manual reset (emergency only)
from apps.serp_execution.services.circuit_breaker import get_serper_circuit_breaker

cb = get_serper_circuit_breaker()
cb.close()  # Force close circuit
print("Circuit breaker reset")
```

#### 4. Stuck Executions

**Symptoms**: Sessions stuck in 'executing' state

**Diagnosis**:
```bash
# Find stuck sessions
dc run --rm web python manage.py shell << EOF
from apps.review_manager.models import SearchSession
from apps.serp_execution.models import SearchExecution
from django.utils import timezone
from datetime import timedelta

# Find sessions stuck in executing
stuck = SearchSession.objects.filter(
    status='executing',
    updated_at__lt=timezone.now() - timedelta(minutes=10)
)

for session in stuck:
    print(f"Session {session.id}: in executing for {timezone.now() - session.updated_at}")

    # Check executions
    execs = SearchExecution.objects.filter(query__session=session)
    print(f"  Total: {execs.count()}")
    print(f"  Running: {execs.filter(status='running').count()}")
    print(f"  Failed: {execs.filter(status='failed').count()}")
EOF
```

**Solutions**:
```bash
# Recovery command
dc run --rm web python manage.py fix_stuck_sessions

# Manual recovery
dc run --rm web python manage.py shell << EOF
from apps.review_manager.models import SearchSession
from apps.review_manager.services.state_manager import SessionStateManager

session = SearchSession.objects.get(id='your-session-id')
manager = SessionStateManager(session)

# Check if can transition
if manager.can_transition_to('processing_results'):
    manager.transition_to('processing_results')
    print("Transitioned to processing_results")
else:
    print("Cannot transition - manual intervention needed")
EOF
```

## Performance Tuning

### Optimization Strategies

#### 1. Celery Worker Optimization

```bash
# Optimal worker configuration
celery -A grey_lit_project worker \
    -Q serp_execution \
    -c 4 \                    # Concurrency
    --prefetch-multiplier=2 \ # Prefetch tasks
    --max-tasks-per-child=100 # Restart after 100 tasks
    --time-limit=300 \        # Hard time limit
    --soft-time-limit=240     # Soft time limit
```

#### 2. Redis Optimization

```redis
# redis.conf optimizations
maxmemory 2gb
maxmemory-policy allkeys-lru
save ""  # Disable persistence for cache
tcp-keepalive 60
timeout 300
```

#### 3. Database Query Optimization

```python
# Optimize query fetching
from django.db.models import Prefetch

# Inefficient
executions = SearchExecution.objects.filter(query__session=session)
for execution in executions:
    results = execution.raw_results.all()  # N+1 query

# Optimized
executions = SearchExecution.objects.filter(
    query__session=session
).prefetch_related(
    Prefetch('raw_results', queryset=RawSearchResult.objects.select_related())
)
```

#### 4. Batch Processing

```python
# Process results in batches
def process_results_batch(execution_id, batch_size=50):
    results = RawSearchResult.objects.filter(
        execution_id=execution_id,
        is_processed=False
    )

    for batch in chunks(results, batch_size):
        with transaction.atomic():
            for result in batch:
                # Process result
                process_single_result(result)
```

### Performance Benchmarks

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| API Response Time | < 1s | > 3s |
| Query Execution Time | < 5s | > 10s |
| Session Completion | < 5min | > 15min |
| Result Processing | < 100ms/result | > 500ms/result |
| Queue Depth | < 100 | > 500 |
| Error Rate | < 1% | > 5% |

## Cost Management

### Credit Tracking

```python
# Track API credit usage
from django.core.cache import cache
from constance import config

def track_credit_usage(credits_used):
    """Track daily credit usage."""
    today = timezone.now().date()
    key = f"serper_credits:{today}"

    # Increment usage
    current = cache.get(key, 0)
    new_total = current + credits_used
    cache.set(key, new_total, 86400)  # 24 hours

    # Check limit
    if new_total >= config.DAILY_CREDIT_LIMIT:
        # Disable API calls
        config.SERPER_ENABLED = False
        # Send alert
        send_credit_alert(new_total)

    return new_total
```

### Cost Optimization Strategies

1. **Query Deduplication**
```python
def get_or_execute_query(query_string, params):
    """Check cache before executing."""
    cache_key = generate_query_hash(query_string, params)

    # Check cache
    cached = cache.get(cache_key)
    if cached:
        return cached

    # Execute and cache
    results = execute_query(query_string, params)
    cache.set(cache_key, results, 3600)  # 1 hour
    return results
```

2. **Result Limiting**
```python
# Limit results per query based on need
def calculate_results_needed(session):
    """Calculate optimal result count."""
    if session.search_strategy.strategy_type == 'broad':
        return 100  # Maximum for broad searches
    elif session.search_strategy.strategy_type == 'focused':
        return 30   # Less for focused searches
    else:
        return 50   # Default
```

3. **User Quotas**
```python
def check_user_quota(user):
    """Check if user has quota remaining."""
    today = timezone.now().date()
    key = f"user_credits:{user.id}:{today}"

    used = cache.get(key, 0)
    limit = user.profile.daily_credit_limit or 100

    return used < limit
```

## Maintenance

### Regular Maintenance Tasks

#### Daily Tasks
- [ ] Check error logs for patterns
- [ ] Review API credit usage
- [ ] Monitor queue depth
- [ ] Verify circuit breaker status

#### Weekly Tasks
- [ ] Analyze performance metrics
- [ ] Review failed executions
- [ ] Clear old cache entries
- [ ] Update rate limits if needed

#### Monthly Tasks
- [ ] Review API usage trends
- [ ] Optimize slow queries
- [ ] Update documentation
- [ ] Test disaster recovery

### Maintenance Commands

```bash
# Clean up old executions (older than 30 days)
dc run --rm web python manage.py shell << EOF
from apps.serp_execution.models import SearchExecution
from django.utils import timezone
from datetime import timedelta

old_date = timezone.now() - timedelta(days=30)
old_executions = SearchExecution.objects.filter(
    created_at__lt=old_date,
    status__in=['completed', 'failed']
)
print(f"Deleting {old_executions.count()} old executions")
old_executions.delete()
EOF

# Clear Redis cache
dc exec redis redis-cli FLUSHDB

# Vacuum database
dc run --rm web python manage.py dbshell << EOF
VACUUM ANALYZE search_executions;
VACUUM ANALYZE raw_search_results;
EOF
```

## Emergency Procedures

### API Service Outage

```python
# Enable mock mode immediately
from constance import config
config.SERPER_MOCK_MODE = True
config.SERPER_ENABLED = False

# Notify users
from apps.core.notifications import broadcast_message
broadcast_message(
    "Search service temporarily unavailable. "
    "Your searches are queued and will execute when service resumes."
)
```

### Rate Limit Exhaustion

```python
# Emergency rate limit increase
from apps.serp_execution.services.rate_limiter import get_rate_limiter

rl = get_rate_limiter()
# Temporarily increase limit
rl.set_rate_limit('serper_api', rate=60, burst=20)

# Queue throttling
from apps.serp_execution.tasks import pause_all_executions
pause_all_executions()
```

### Database Connection Issues

```bash
# Switch to read-only mode
dc run --rm web python -c "
from constance import config
config.MAINTENANCE_MODE = True
config.READ_ONLY_MODE = True
"

# Restart database connections
dc restart web celery_worker

# Verify connectivity
dc run --rm web python manage.py dbshell -c "SELECT 1;"
```

### Complete System Recovery

```bash
# 1. Stop all services
dc down

# 2. Clear queues
dc run --rm redis redis-cli FLUSHALL

# 3. Reset circuit breakers
dc run --rm web python -c "
from apps.serp_execution.services.circuit_breaker import reset_all_breakers
reset_all_breakers()
"

# 4. Restart services
dc up -d

# 5. Verify health
dc run --rm web python manage.py check
dc run --rm web python manage.py test apps.serp_execution.tests.test_health

# 6. Resume operations
dc run --rm web python -c "
from constance import config
config.MAINTENANCE_MODE = False
config.SERPER_ENABLED = True
"
```

## Security Considerations

### API Key Security

```python
# Never log API keys
import logging

class SafeSerperClient:
    def __init__(self, api_key):
        self.api_key = api_key
        # Log only key presence, not value
        logging.info(f"API key configured: {'Yes' if api_key else 'No'}")

    def __str__(self):
        return f"SerperClient(key=***{self.api_key[-4:] if self.api_key else 'None'})"
```

### Input Sanitization

```python
def sanitize_query(query_string):
    """Sanitize search query for safety."""
    import re

    # Remove potential injection attempts
    query_string = re.sub(r'[<>\"\'`;]', '', query_string)

    # Limit length
    query_string = query_string[:2048]

    # Remove excessive whitespace
    query_string = ' '.join(query_string.split())

    return query_string
```

### Audit Logging

```python
def log_api_call(user, query, results_count, credits_used):
    """Log API calls for audit."""
    from apps.core.models import AuditLog

    AuditLog.objects.create(
        user=user,
        action='serper_api_call',
        details={
            'query': query[:100],  # Truncate for storage
            'results_count': results_count,
            'credits_used': credits_used,
            'timestamp': timezone.now().isoformat(),
        }
    )
```

## Summary

This operations manual provides comprehensive guidance for:
- Configuring and deploying SERP execution
- Monitoring system health and performance
- Troubleshooting common issues
- Optimizing performance and costs
- Maintaining system reliability
- Handling emergencies

Regular review and updates of these procedures ensure smooth operation of the SERP execution system within Agent Grey.
