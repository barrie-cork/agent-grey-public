# Agent Grey Monitoring & Observability

> **Status (updated 2026-06-17, `ponytail-cleanup`):** the **self-hosted Prometheus +
> Grafana + AlertManager** stack and **`django-prometheus`** were **removed** (dev-only,
> never run in production). What remains and is current:
> - **Sentry** (SaaS) — error tracking + performance monitoring. See [Sentry Error Tracking](#sentry-error-tracking).
> - **Custom application metrics** via `prometheus_client` in `apps/core/metrics/`, exposed at
>   **`/prometheus/metrics`** by `apps.core.views.metrics.prometheus_metrics_view` (staff/DEBUG gated),
>   toggled by `PROMETHEUS_METRICS_ENABLED`. The endpoint stays portable for any external scraper
>   (Grafana Cloud, DigitalOcean, etc.).
>
> The self-hosted-stack sections below (architecture diagram, Prometheus/Grafana/AlertManager
> setup, dashboards, alert rules, `monitoring/` configs, dev-compose services) are **retained as
> historical / optional-self-host reference only** — those configs and services no longer exist in
> the repo. The Sentry and custom-metrics guidance is current.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Components](#components)
- [Sentry Error Tracking](#sentry-error-tracking)
- [OpenTelemetry Distributed Tracing](#opentelemetry-distributed-tracing)
- [Alert Rules](#alert-rules)
- [Runbooks](#runbooks)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Production Deployment](#production-deployment)
- [Upgrading Django](#upgrading-django)

## Overview

**Current observability:**

- **Error tracking**: Sentry (SaaS) — exceptions, performance, release health.
- **Custom metrics**: business + operational counters/gauges/histograms (`prometheus_client`,
  `apps/core/metrics/`) served at `/prometheus/metrics` for any external scraper.

_Historical — self-hosted stack removed 2026-06-17 (sections below kept for reference):_

- ~~**Visualisation**: Pre-built Grafana dashboards~~
- ~~**Alerting**: 16 Prometheus alert rules~~
- ~~**Incident Response**: AlertManager + structured runbooks~~

### Technology Stack

| Component | Version | Purpose | Status |
|-----------|---------|---------|--------|
| Sentry | SaaS | Error tracking and performance monitoring | **Active** |
| prometheus-client | 0.19.0 | Custom metrics + `/prometheus/metrics` endpoint | **Active** |
| OpenTelemetry | 1.22.0 | Distributed tracing | Unchanged |
| Prometheus | v2.48.0 | Metrics storage and alerting | **Removed 2026-06-17** |
| Grafana | v10.4.0 | Visualisation dashboards | **Removed 2026-06-17** |
| AlertManager | v0.27.0 | Alert routing and notification | **Removed 2026-06-17** |
| django-prometheus | 2.3.1 | Django auto-instrumentation | **Removed 2026-06-17** |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Agent Grey Application                    │
│  ┌──────────────────┐      ┌─────────────────────────────────┐ │
│  │ Django App       │──────│ django-prometheus middleware    │ │
│  │                  │      │ /prometheus/metrics endpoint    │ │
│  └──────────────────┘      └─────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Custom Metrics (apps/core/metrics/registry.py)          │  │
│  │ - Session workflow: state transitions, durations         │  │
│  │ - Search execution: API calls, errors, latency          │  │
│  │ - Processing: deduplication, normalisation              │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP /prometheus/metrics
                              │ scrape every 15s
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                         Prometheus (port 9090)                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ TSDB Storage (15 days retention, 10GB max)              │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Alert Rules Engine                                       │  │
│  │ - 4 session alerts  - 5 search alerts                   │  │
│  │ - 7 infrastructure alerts                                │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
         │                                    │
         │ PromQL queries                     │ Alerts
         │                                    │
         ↓                                    ↓
┌──────────────────────────┐    ┌────────────────────────────────┐
│  Grafana (port 3000)     │    │ AlertManager (port 9093)       │
│  - Overview dashboard    │    │ - Route by severity            │
│  - Performance dashboard │    │ - Group/inhibit rules          │
│  - Search dashboard      │    │ - Slack/PagerDuty/Email        │
│  - User activity         │    │ - Notification templates       │
└──────────────────────────┘    └────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Agent Grey application running
- `.env.dev.local` file configured

### Start Monitoring Stack

```bash
# Start all monitoring services
docker compose -f docker compose.development.yml up -d prometheus grafana alertmanager

# Check service health
docker compose -f docker compose.development.yml ps prometheus grafana alertmanager

# View logs
docker compose logs -f prometheus
docker compose logs -f grafana
docker compose logs -f alertmanager
```

### Access UIs

- **Prometheus**: http://localhost:9090
  - Metrics explorer: http://localhost:9090/graph
  - Alert rules: http://localhost:9090/rules
  - Targets: http://localhost:9090/targets

- **Grafana**: http://localhost:3000
  - Username: `admin`
  - Password: configured in `.env.dev.local` (default: `admin`)
  - Dashboards: Navigate to Dashboards → Browse

- **AlertManager**: http://localhost:9093
  - Active alerts: http://localhost:9093/#/alerts
  - Silences: http://localhost:9093/#/silences

### Verify Metrics Collection

```bash
# Check Prometheus is scraping Agent Grey
curl http://localhost:9090/api/v1/targets | grep agent-grey

# Query a sample metric
curl 'http://localhost:9090/api/v1/query?query=agent_grey_session_state'

# Check alert rules loaded
curl http://localhost:9090/api/v1/rules | grep -c '"alert"'
# Should return: 16
```

## Components

### 1. Prometheus

**Configuration**: `monitoring/prometheus/prometheus.yml`

**Key Settings**:
```yaml
global:
  scrape_interval: 15s      # Scrape metrics every 15 seconds
  evaluation_interval: 15s  # Evaluate alert rules every 15 seconds

scrape_configs:
  - job_name: 'agent-grey-web'
    metrics_path: '/prometheus/metrics'
    static_configs:
      - targets: ['web:8000']
```

**Storage**:
- Retention: 15 days
- Max size: 10GB
- Volume: `prometheus_data`

**Useful Queries**:
```promql
# Current sessions by state
agent_grey_session_state

# Session creation rate (last 5 minutes)
rate(agent_grey_session_transitions_total{to_state="draft"}[5m])

# Search API error rate
rate(agent_grey_search_api_errors_total[5m])

# HTTP request latency (p95)
histogram_quantile(0.95, rate(django_http_requests_latency_seconds_bucket[5m]))
```

### 2. Grafana

**Configuration**: `monitoring/grafana/provisioning/`

**Dashboards**:

1. **Overview** (`overview.json`)
   - Active sessions by state
   - Session throughput
   - HTTP request rates
   - System resource usage

2. **Performance** (`performance.json`)
   - Request latency percentiles
   - Database query performance
   - Cache hit rates
   - Memory and CPU trends

3. **Search Execution** (`search_execution.json`)
   - Search query rates
   - API error tracking
   - Result counts
   - Search duration

4. **User Activity** (`user_activity.json`)
   - Active users
   - Session creation trends
   - Review decisions
   - User engagement metrics

**Datasource**: Automatically provisioned Prometheus connection

### 3. AlertManager

**Configuration**: `monitoring/alertmanager/alertmanager.yml`

**Notification Channels**:

| Severity | Channels | Repeat Interval |
|----------|----------|-----------------|
| Critical | PagerDuty + Slack | 1 hour |
| Warning | Slack | 2 hours |
| Info | Slack | 12 hours |

**Routing Tree**:
```
default (email to ops team)
├── severity: critical → pagerduty-critical (continue: true)
├── severity: critical → slack-critical
├── severity: warning → slack-warning
├── severity: info → slack-info
└── maintenance: true → null (silence)
```

**Inhibition Rules**:
- Critical alerts suppress warning alerts for same alertname + service
- DatabaseDown suppresses all connection-related alerts
- ServiceDown suppresses all alerts for that service

## Sentry Error Tracking

### Overview

Sentry provides real-time error tracking, performance monitoring, and release health insights for Agent Grey. It complements Prometheus by capturing detailed error context, stack traces, and user impact data.

**Integration**: `sentry-sdk` with Django, Celery, and Redis integrations

### Configuration

**Environment Variables** (`.env.dev.local` / `.env.local`):

```bash
# Required
SENTRY_DSN=https://your-dsn@sentry.io/project-id

# Optional
SENTRY_ENVIRONMENT=production          # local_development, staging, production
SENTRY_RELEASE=1.0.0                  # Git commit SHA or version
SENTRY_TRACES_SAMPLE_RATE=0.01        # 1% transaction sampling (free tier)
SENTRY_PROFILES_SAMPLE_RATE=0.0       # Profiling disabled (free tier)
```

**Settings Files**:
- **Production**: `grey_lit_project/settings/production.py:620-665`
- **Development**: `grey_lit_project/settings/local.py:130-214`
- **Staging**: Uses production configuration

### Features Enabled

**1. Error Tracking**
- Automatic exception capture with full stack traces
- Breadcrumbs for request/response lifecycle
- User context (authenticated user ID)
- Environment tags (production, staging, local_development)
- Release tracking for regression detection

**2. Performance Monitoring**
```python
# Transaction sampling rates
production: 10%    # Balance cost vs visibility
staging: 50%       # Higher sampling for testing
development: 5%    # Minimal overhead
```

**3. Integrations Active**

| Integration | Purpose | Configuration |
|-------------|---------|---------------|
| `DjangoIntegration` | HTTP requests, middleware spans | transaction_style="url", cache_spans=True |
| `CeleryIntegration` | Background task tracking | monitor_beat_tasks=True, propagate_traces=True |
| `RedisIntegration` | Cache operation monitoring | Auto-instrumentation enabled |
| `LoggingIntegration` | Capture WARNING+ log entries | event_level=logging.WARNING |

**4. Ignored Errors**

The following errors are suppressed to reduce noise:

```python
# Production & Development
ignore_errors=[
    "Http404",                          # Normal - user accessed non-existent page
    "KeyboardInterrupt",                # Development - manual interruption
    "SystemExit",                       # Normal - graceful shutdown
    "DisallowedHost",                   # Security - invalid Host header
    "PermissionDenied",                 # Expected - unauthorized access attempts
    "redis.exceptions.NoScriptError",   # Benign - django_redis auto-falls back to EVAL
]

# Additional Development-only
ignore_errors += [
    "ValidationError",                  # Expected - form validation failures
    "OperationalError",                 # Development - DB connection issues
    "ConnectionError",                  # Development - network instability
    "BrokenPipeError",                  # Development - client disconnection
]
```

### Common Error Patterns

#### 1. Redis NoScriptError (Resolved 2025-10-07)

**Pattern**: `redis.exceptions.NoScriptError: No matching script. Please use EVAL.`

**Cause**: django_redis uses Lua scripts (EVALSHA) for atomic cache operations. When Redis restarts or evicts scripts, it throws NoScriptError before automatically falling back to EVAL.

**Impact**: None - functionality continues normally

**Resolution**: Added to `ignore_errors` list (production.py:664, local.py:213)

**Example Sentry Alert**:
```
NoScriptError: No matching script. Please use EVAL.
  File: django_redis/client.py:1286

Occurred 30+ times in 20 minutes (2025-10-07 00:41-01:01 IST)
Status: Resolved - Now suppressed in Sentry
```

#### 2. SearchResultProcessor Position Errors (Resolved 2025-10-07)

**Pattern**: Position calculation failures in batch processing

**Cause**: Using `batch.index(result)` which fails with duplicate results or object equality issues

**Impact**: Failed to save search results to database

**Resolution**:
- Replaced with explicit enumeration: `for batch_idx, result in enumerate(batch)`
- Enhanced error logging with structured context
- File: `apps/serp_execution/services/result_processor.py:86-138`

**Before**:
```python
position = batch.index(result) + i + 1  # Unreliable
```

**After**:
```python
for batch_idx, result in enumerate(batch):
    position = i + batch_idx + 1  # Reliable, explicit
```

#### 3. PermissionDenied (Expected)

**Pattern**: User attempts to access session they don't own

**Cause**: Authorization checks in `apps/search_strategy/views.py:65`

**Impact**: None - expected behaviour for security

**Status**: Already in `ignore_errors` - alerts suppressed

### Monitoring Sentry Health

#### Check Sentry Status

```bash
# Verify Sentry is configured
docker compose exec web python -c "
import sentry_sdk
print('Sentry Hub:', sentry_sdk.Hub.current.client)
print('DSN configured:', bool(sentry_sdk.Hub.current.client))
"

# Check pending events
docker compose logs web | grep "Sentry is attempting to send"
```

#### Recent Errors Dashboard

Access Sentry dashboard to view:
- **Issues**: https://sentry.io/organizations/your-org/issues/
- **Performance**: https://sentry.io/organizations/your-org/performance/
- **Releases**: https://sentry.io/organizations/your-org/releases/

#### Alert Storm Analysis

When experiencing high alert volumes:

1. **Identify Pattern**:
   ```bash
   # Check error types and counts
   docker compose logs web --since 1h | grep "\[ERROR\]" | \
     jq -r '.exception_type' | sort | uniq -c | sort -rn
   ```

2. **Check Infrastructure**:
   ```bash
   # Database health
   docker compose exec db psql -U user -c "SELECT count(*) FROM pg_stat_activity;"

   # Redis health
   docker compose exec redis redis-cli INFO stats | grep total_connections

   # Celery workers
   docker compose exec web celery -A grey_lit_project inspect active
   ```

3. **Review Ignore List**:
   - Are these errors truly benign?
   - Should they be suppressed or investigated?
   - Update `ignore_errors` in settings if appropriate

### Best Practices

**1. Error Classification**

| Error Type | Action | Sentry Handling |
|------------|--------|-----------------|
| **Critical Bugs** | Immediate fix | Alert + Issue created |
| **Expected Exceptions** | Log for monitoring | Add to `ignore_errors` |
| **Benign Errors** | Suppress | Add to `ignore_errors` |
| **Performance Issues** | Investigate trace | Use Performance monitoring |

**2. Alert Fatigue Prevention**

```python
# ❌ Bad: Alert on every permission check
# Will cause hundreds of alerts from legitimate access denials

# ✅ Good: Suppress expected authorization failures
ignore_errors=["PermissionDenied"]

# ✅ Better: Log for audit trail, suppress in Sentry
logger.info("Unauthorized access attempt", extra={"user_id": user.id})
```

**3. Error Context Enhancement**

```python
# ❌ Basic error logging
logger.error(f"Failed to process: {str(e)}")

# ✅ Enhanced with structured context
logger.error(
    "Failed to process search results",
    extra={
        "execution_id": execution_id,
        "position": position,
        "result": result,
        "error_type": type(e).__name__,
    },
    exc_info=True  # Include full traceback
)
```

**4. Sampling Configuration**

```python
# Production: Conservative for Sentry free tier (5K errors, 10K perf units/month)
SENTRY_TRACES_SAMPLE_RATE = 0.01  # 1% of transactions
SENTRY_PROFILES_SAMPLE_RATE = 0.0  # Profiling disabled

# High-traffic endpoints: Lower sampling
# Critical paths: Higher sampling (configure per-transaction)
```

### Troubleshooting Sentry

#### Sentry Not Capturing Errors

**Symptom**: Errors occurring but not appearing in Sentry

```bash
# Check DSN configured
docker compose exec web python -c "
from django.conf import settings
import os
print('DSN:', os.getenv('SENTRY_DSN', 'NOT SET'))
"

# Check client initialized
docker compose exec web python -c "
import sentry_sdk
client = sentry_sdk.Hub.current.client
print('Client:', client)
print('Enabled:', client is not None)
"

# Test error capture
docker compose exec web python -c "
import sentry_sdk
sentry_sdk.capture_message('Test error from Agent Grey')
print('Test event sent')
"
```

**Solutions**:
- Verify `SENTRY_DSN` in environment file
- Check `ignore_errors` list - error might be suppressed
- Review Sentry quota limits (check dashboard)
- Verify network connectivity to sentry.io

#### Too Many Alerts

**Symptom**: Sentry alert storm (>30 alerts in short period)

```bash
# Analyse alert patterns
docker compose logs web --since 2h | grep "\[ERROR\]" | \
  jq -r '.exception_type' | sort | uniq -c | sort -rn | head -10

# Check for benign errors
docker compose logs web --since 1h | grep "NoScriptError" | wc -l
```

**Solutions**:
1. Identify benign errors (like NoScriptError)
2. Add to `ignore_errors` in settings
3. Restart web service: `docker compose restart web`
4. Monitor for recurrence

#### Missing Context in Errors

**Symptom**: Sentry errors lack useful debugging information

**Solution**: Enhance error logging with `extra` context

```python
# Add structured context
logger.error(
    "Operation failed",
    extra={
        "user_id": request.user.id,
        "session_id": session.id,
        "request_path": request.path,
        "correlation_id": correlation_id,
    },
    exc_info=True
)
```

### Integration with Other Tools

**Sentry + Prometheus**:
- Sentry: Detailed error context, stack traces, user impact
- Prometheus: Aggregate metrics, trends, alerting thresholds
- Use together: Prometheus alerts trigger investigation → Sentry provides error details

**Sentry + Grafana**:
- Create Grafana dashboard linking to Sentry issues
- Use annotations to mark releases
- Correlate error spikes with deployment events

**Sentry + OpenTelemetry**:
- Distributed tracing spans appear in Sentry Performance
- Link errors to specific trace IDs
- End-to-end request visibility

## OpenTelemetry Distributed Tracing

### Overview

OpenTelemetry provides distributed tracing for Agent Grey, allowing you to track requests across services and identify performance bottlenecks.

**Configuration**: `apps/core/telemetry_config.py`

### Features

- **Auto-instrumentation**: Django, Redis, HTTP requests
- **Console Export**: Development mode outputs traces to logs
- **OTLP Export**: Production sends to Jaeger/Grafana Tempo
- **Span Context**: Request IDs, user context, custom attributes

### Viewing Traces

**Development**:
```bash
# Traces output to console in JSON format
docker compose logs web | grep '"name":' | jq .
```

**Production (Jaeger)**:
- UI: http://localhost:16686
- Service: `agent-grey`
- View traces, spans, and performance metrics

### Key Traces

| Operation | Typical Duration | Alerts If |
|-----------|------------------|-----------|
| HTTP Request | < 500ms | > 2s |
| Database Query | < 100ms | > 1s |
| Redis Cache GET | < 10ms | > 50ms |
| Search API Call | < 5s | > 10s |
| Result Processing | < 2s | > 10s |

## Alert Rules

### Session Workflow Alerts (4 rules)

**File**: `monitoring/prometheus/alerts/session_alerts.rules.yml`

1. **SessionsStuckInExecuting** (warning)
   - Sessions in 'executing' state for >15 minutes
   - Runbook: `docs/runbooks/stuck-sessions.md`

2. **HighSessionTransitionFailureRate** (critical)
   - >10% of state transitions failing
   - Indicates database or transaction issues

3. **AbnormallyLongSessionStateTime** (warning)
   - p95 duration >1 hour in non-review states
   - Performance degradation indicator

4. **NoSessionsCreatedRecently** (info)
   - No new sessions in 2 hours
   - Potential user onboarding issue

### Search Execution Alerts (5 rules)

**File**: `monitoring/prometheus/alerts/search_alerts.rules.yml`

1. **HighSearchErrorRate** (critical)
   - >10% of searches failing
   - Check Serper API status

2. **SerperAPIRateLimitApproaching** (warning)
   - >25 requests/minute (limit: 30/min)
   - Implement throttling

3. **SearchAPITimeoutSpike** (warning)
   - >0.5 timeouts/second
   - Network or API latency issues

4. **SearchResultsConsistentlyEmpty** (warning)
   - >50% of searches returning empty
   - Query generation issues

5. **SlowSearchQueries** (warning)
   - p95 duration >10 seconds
   - Expected <5 seconds

### Infrastructure Alerts (7 rules)

**File**: `monitoring/prometheus/alerts/infrastructure_alerts.rules.yml`

1. **HighHTTP5xxRate** (critical)
   - >5 HTTP 5xx errors per minute
   - Application errors

2. **DatabaseConnectionPoolExhausted** (critical)
   - >10 OperationalErrors in 2 minutes
   - Connection pool exhausted

3. **SlowDatabaseQueries** (warning)
   - p95 query time >1 second
   - Check for missing indexes

4. **LowCacheHitRate** (warning)
   - Cache hit rate <50% for 15 minutes
   - Expected >80%

5. **HighMemoryUsage** (warning)
   - Memory usage >2GB for 10 minutes
   - Risk of OOM

6. **HighCPUUsage** (warning)
   - CPU usage >80% for 10 minutes
   - Performance degradation

7. **CeleryQueueBacklog** (warning)
   - >100 tasks in search queue for 10 minutes
   - Workers overloaded

## Runbooks

Runbooks provide structured incident response procedures.

### Available Runbooks

1. **Template**: `docs/runbooks/TEMPLATE.md`
   - Standard structure for creating new runbooks
   - Includes: Symptom, Impact, Diagnosis (4 steps), Resolution, Escalation, Prevention

2. **Stuck Sessions**: `docs/runbooks/stuck-sessions.md`
   - For `SessionsStuckInExecuting` alert
   - Covers: Celery issues, API problems, database connection issues
   - Includes verification commands and success criteria

### Creating New Runbooks

1. Copy the template:
   ```bash
   cp docs/runbooks/TEMPLATE.md docs/runbooks/my-alert.md
   ```

2. Fill in sections:
   - Alert information (name, severity, component)
   - Symptom description
   - User and business impact
   - 4-step diagnosis procedure
   - Quick fix and permanent fix
   - Verification steps

3. Link from alert rule:
   ```yaml
   annotations:
     runbook_url: "https://docs.agent-grey.example.com/runbooks/my-alert"
   ```

## Configuration

### Environment Variables

**File**: `.env.dev.local`

```bash
# Grafana
GRAFANA_ADMIN_PASSWORD=admin

# AlertManager Notifications
SMTP_PASSWORD=placeholder                    # Email notifications
SLACK_WEBHOOK_URL=https://hooks.slack.com/... # Slack notifications
PAGERDUTY_SERVICE_KEY=placeholder            # PagerDuty integration
```

### Configuring Slack Notifications

1. Create Slack app: https://api.slack.com/apps
2. Enable Incoming Webhooks
3. Create webhook for your channel
4. Update `.env.dev.local`:
   ```bash
   SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
   ```
5. Update `monitoring/alertmanager/alertmanager.yml`:
   ```yaml
   slack_configs:
     - api_url: 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'
       channel: '#alerts-critical'
   ```
6. Restart AlertManager:
   ```bash
   docker compose restart alertmanager
   ```

### Configuring Email Notifications

1. Update `.env.dev.local`:
   ```bash
   SMTP_PASSWORD=your-smtp-password
   ```

2. Uncomment email config in `monitoring/alertmanager/alertmanager.yml`:
   ```yaml
   global:
     smtp_from: 'alertmanager@agent-grey.example.com'
     smtp_smarthost: 'smtp.gmail.com:587'
     smtp_auth_username: 'alertmanager@agent-grey.example.com'
     smtp_auth_password: '${SMTP_PASSWORD}'
     smtp_require_tls: true
   ```

3. Uncomment default receiver email:
   ```yaml
   receivers:
     - name: 'default'
       email_configs:
         - to: 'ops-team@agent-grey.example.com'
   ```

### Adding New Metrics

**Location**: `apps/core/metrics/registry.py`

```python
from prometheus_client import Counter, Histogram, Gauge

# 1. Define metric
export_operations = Counter(
    'agent_grey_exports_total',
    'Total export operations',
    ['format', 'status']  # Labels for filtering
)

# 2. Instrument code
from apps.core.metrics import export_operations

def generate_export(format):
    try:
        result = create_export(format)
        export_operations.labels(format=format, status='success').inc()
        return result
    except Exception as e:
        export_operations.labels(format=format, status='error').inc()
        raise
```

### Adding New Alert Rules

1. Choose appropriate file:
   - Session workflow → `session_alerts.rules.yml`
   - Search/API → `search_alerts.rules.yml`
   - Infrastructure → `infrastructure_alerts.rules.yml`

2. Add rule:
   ```yaml
   - alert: MyNewAlert
     expr: my_metric_total > 100
     for: 5m
     labels:
       severity: warning
       service: agent-grey
       component: my-component
     annotations:
       summary: "Brief description"
       description: "Detailed description with {{ $value }}"
       impact: "User/business impact"
       runbook_url: "https://docs.agent-grey.example.com/runbooks/my-alert"
       dashboard_url: "http://localhost:3000/d/dashboard-id"
   ```

3. Validate rule:
   ```bash
   docker compose exec prometheus promtool check rules /etc/prometheus/alerts/my_alerts.rules.yml
   ```

4. Reload Prometheus:
   ```bash
   curl -X POST http://localhost:9090/-/reload
   ```

## Troubleshooting

### Prometheus Not Scraping

**Symptom**: No metrics in Prometheus

```bash
# Check targets
curl http://localhost:9090/api/v1/targets

# Check web service is exposing metrics
curl http://localhost:8000/prometheus/metrics

# Check Prometheus logs
docker compose logs prometheus | grep ERROR
```

**Solution**:
- Verify `web` service is healthy
- Check `/prometheus/metrics` endpoint is accessible
- Verify Prometheus can resolve `web:8000` (Docker network)

### Alert Not Firing

**Symptom**: Alert should be firing but isn't

```bash
# Check alert rule is loaded
curl http://localhost:9090/api/v1/rules | grep "MyAlert"

# Test alert expression
curl 'http://localhost:9090/api/v1/query?query=YOUR_ALERT_EXPRESSION'

# Check alert state
curl http://localhost:9090/api/v1/alerts
```

**Common Issues**:
- Expression syntax error (check Prometheus logs)
- `for` duration not yet elapsed
- Labels don't match routing rules

### AlertManager Not Receiving Alerts

**Symptom**: Alerts firing in Prometheus but not in AlertManager

```bash
# Check Prometheus → AlertManager connection
curl http://localhost:9090/api/v1/alertmanagers

# Check AlertManager health
curl http://localhost:9093/-/healthy

# Check AlertManager logs
docker compose logs alertmanager
```

**Solution**:
- Verify `alertmanager:9093` is reachable from Prometheus
- Check `prometheus.yml` alerting configuration
- Restart both services

### Grafana Dashboard Not Loading Data

**Symptom**: Dashboard panels showing "No data"

```bash
# Check datasource connection
curl -u <user>:<password> http://localhost:3000/api/datasources

# Test query directly in Prometheus
curl 'http://localhost:9090/api/v1/query?query=agent_grey_session_state'
```

**Solution**:
- Verify Prometheus datasource configured correctly
- Check query syntax in panel
- Verify time range includes data

### High Cardinality Warnings

**Symptom**: Prometheus logs show high cardinality warnings

```bash
# Check metric cardinality
curl http://localhost:9090/api/v1/status/tsdb | grep numSeries
```

**Solution**:
- Avoid user IDs or session IDs as labels
- Use aggregation instead of per-entity metrics
- Consider recording rules for pre-aggregation

## Development

### Local Testing

```bash
# Start monitoring stack
docker compose up -d prometheus grafana alertmanager

# Generate test metrics
docker compose exec web python manage.py shell
>>> from apps.core.metrics import session_state_gauge
>>> session_state_gauge.labels(state='draft').set(5)

# View metrics
curl http://localhost:8000/prometheus/metrics | grep agent_grey

# Test alert expression
curl 'http://localhost:9090/api/v1/query?query=agent_grey_session_state{state="draft"}'
```

### Adding Dashboard Panels

1. Open Grafana: http://localhost:3000
2. Navigate to dashboard
3. Click "Add panel"
4. Configure query using Prometheus datasource
5. Save dashboard
6. Export JSON: Dashboard settings → JSON Model
7. Save to `monitoring/grafana/provisioning/dashboards/`
8. Restart Grafana to load

### Testing Alerts

**Method 1: Modify threshold temporarily**

```yaml
# Lower threshold to trigger easily
- alert: TestAlert
  expr: agent_grey_session_state{state="draft"} > 0  # Was: > 100
  for: 1m  # Was: 5m
```

**Method 2: Send test alert via API**

```bash
# Send test alert to AlertManager
curl -X POST http://localhost:9093/api/v2/alerts -H "Content-Type: application/json" -d '[
  {
    "labels": {
      "alertname": "TestAlert",
      "severity": "warning",
      "service": "agent-grey"
    },
    "annotations": {
      "summary": "Test alert",
      "description": "This is a test"
    },
    "startsAt": "2025-10-04T12:00:00Z",
    "endsAt": "2025-10-04T12:30:00Z"
  }
]'
```

## Production Deployment

### Pre-deployment Checklist

- [ ] Configure real Slack webhook URL
- [ ] Configure SMTP credentials for email
- [ ] Configure PagerDuty service key
- [ ] Set strong Grafana admin password
- [ ] Review and tune alert thresholds
- [ ] Test alert notification delivery
- [ ] Create runbooks for all critical alerts
- [ ] Set up Prometheus remote storage (optional)
- [ ] Configure Grafana OAuth/LDAP (optional)
- [ ] Set up SSL/TLS termination
- [ ] Configure retention policies
- [ ] Document escalation procedures

### Production Configuration

**prometheus.yml**:
```yaml
global:
  scrape_interval: 30s       # Reduce load
  evaluation_interval: 30s

storage:
  tsdb:
    retention.time: 30d      # Increase retention
    retention.size: 50GB
```

**alertmanager.yml**:
```yaml
global:
  resolve_timeout: 5m

route:
  group_wait: 10s            # Send initial alert quickly
  group_interval: 5m         # Group subsequent alerts
  repeat_interval: 4h        # Re-notify if not resolved
```

**Grafana**:
- Enable OAuth/LDAP authentication
- Set up read-only viewers
- Configure SMTP for dashboard sharing
- Set up Grafana Cloud sync (optional)

### Scaling Considerations

**Prometheus**:
- Use federation for multi-region deployments
- Configure remote write to long-term storage (e.g., Thanos, Cortex)
- Implement recording rules for frequently queried aggregations

**AlertManager**:
- Run multiple replicas for high availability
- Configure cluster mode for alert deduplication
- Use external storage (e.g., Redis) for silences

**Grafana**:
- Run multiple instances behind load balancer
- Use external database (PostgreSQL) for dashboard storage
- Configure image rendering service for PDF exports

### Backup Strategy

```bash
# Backup Prometheus data
docker run --rm -v prometheus_data:/data -v $(pwd):/backup alpine \
  tar czf /backup/prometheus-$(date +%Y%m%d).tar.gz /data

# Backup Grafana dashboards
docker compose exec grafana grafana-cli admin export-dashboards \
  > grafana-dashboards-$(date +%Y%m%d).json

# Backup AlertManager configuration
cp monitoring/alertmanager/alertmanager.yml \
  alertmanager-$(date +%Y%m%d).yml.backup
```

## Upgrading Django

When upgrading Django from 4.2.x to a newer version, follow these steps to ensure monitoring compatibility.

### 1. Check django-prometheus Compatibility

```bash
# Check latest django-prometheus version
pip index versions django-prometheus

# Check compatibility matrix
# https://github.com/korfuri/django-prometheus#compatibility
```

**Compatibility** (as of January 2025):
- Django 4.2: django-prometheus 2.3.1 ✅
- Django 5.0: django-prometheus 2.4.0+ (check releases)
- Django 5.1+: Verify compatibility before upgrading

### 2. Update Requirements

**File**: `requirements/base.txt`

```txt
# Before
django-prometheus==2.3.1

# After (example for Django 5.0)
django-prometheus==2.4.0
```

### 3. Test Metrics Endpoint

```bash
# After upgrading
docker compose exec web python manage.py runserver

# Verify metrics still accessible
curl http://localhost:8000/prometheus/metrics | grep django_http

# Check for deprecation warnings
docker compose logs web | grep -i "deprecat"
```

### 4. Update Middleware (if needed)

Newer Django versions may change middleware ordering requirements.

**File**: `grey_lit_project/settings/base.py`

```python
MIDDLEWARE = [
    'django_prometheus.middleware.PrometheusBeforeMiddleware',  # MUST be first
    'django.middleware.security.SecurityMiddleware',
    # ... other middleware ...
    'django_prometheus.middleware.PrometheusAfterMiddleware',   # MUST be last
]
```

### 5. Test Database Instrumentation

Django ORM changes may affect database metrics.

```bash
# Generate some database queries
docker compose exec web python manage.py shell
>>> from apps.review_manager.models import SearchSession
>>> SearchSession.objects.count()

# Check database metrics
curl http://localhost:8000/prometheus/metrics | grep django_db
```

### 6. Update Custom Metrics (if needed)

If Django changes internal APIs that your custom metrics depend on:

```python
# File: apps/core/metrics/registry.py

# Before (Django 4.2)
from django.db import connection
queries = len(connection.queries)

# After (Django 5.x) - if API changed
from django.db import connections
queries = sum(len(c.queries) for c in connections.all())
```

### 7. Regression Testing

Run full test suite to catch any issues:

```bash
# Unit tests
docker compose exec web python manage.py test

# Check all metrics still exporting
curl http://localhost:8000/prometheus/metrics | wc -l
# Should return similar count as before upgrade

# Check Prometheus still scraping
curl http://localhost:9090/api/v1/targets | grep agent-grey

# Verify alert rules still valid
docker compose exec prometheus promtool check rules /etc/prometheus/alerts/*.rules.yml
```

### 8. Known Upgrade Issues

**Django 4.2 → 5.0**:
- `django.utils.timezone.utc` deprecated → use `datetime.timezone.utc`
- Check if affects custom metrics with timestamps

**Django 5.0 → 5.1**:
- Check django-prometheus release notes for any breaking changes
- Test caching backend compatibility

**General**:
- Always upgrade in development/staging first
- Monitor Prometheus error logs after upgrade
- Check for increased metric cardinality
- Verify dashboard queries still work

### 9. Rollback Plan

If metrics break after Django upgrade:

```bash
# 1. Rollback Docker image
docker compose down
docker compose up -d --build

# 2. Or pin django-prometheus to working version
# requirements/base.txt
django-prometheus==2.3.1  # Pinned - compatible with Django 4.2

# 3. Rebuild
docker compose build web
docker compose up -d
```

### 10. Post-Upgrade Checklist

- [ ] All metrics endpoints responding (HTTP 200)
- [ ] Metric names unchanged (or update dashboards/alerts)
- [ ] Prometheus scraping successfully
- [ ] Alert rules still valid
- [ ] Grafana dashboards still rendering
- [ ] No increase in error metrics
- [ ] Custom metrics still recording
- [ ] Database instrumentation working
- [ ] Cache instrumentation working
- [ ] Request instrumentation working

## Additional Resources

### Documentation

- **Prometheus**: https://prometheus.io/docs/
- **Grafana**: https://grafana.com/docs/
- **AlertManager**: https://prometheus.io/docs/alerting/latest/alertmanager/
- **django-prometheus**: https://github.com/korfuri/django-prometheus
- **PromQL**: https://prometheus.io/docs/prometheus/latest/querying/basics/

### Useful Links

- Prometheus best practices: https://prometheus.io/docs/practices/naming/
- Grafana dashboard best practices: https://grafana.com/docs/grafana/latest/dashboards/build-dashboards/best-practices/
- AlertManager routing tree editor: https://prometheus.io/webtools/alerting/routing-tree-editor/
- PromQL tutorial: https://prometheus.io/docs/prometheus/latest/querying/examples/

### Support

For issues or questions:

1. Check this README
2. Check relevant runbook in `docs/runbooks/`
3. Check Prometheus/Grafana/AlertManager logs
4. Consult upstream documentation
5. Raise issue in project repository

---

**Version**: 1.1.0 (Phase 5 Complete + Sentry Integration)
**Last Updated**: 2025-10-07
**Maintained By**: Engineering Team
**Recent Updates**:
- Added comprehensive Sentry error tracking documentation
- Documented common error patterns and resolutions
- Added OpenTelemetry distributed tracing section
- Updated troubleshooting guides for alert storms
