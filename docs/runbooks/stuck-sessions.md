# Runbook: Sessions Stuck in Executing State

## Alert Information

- **Alert Name**: `SessionsStuckInExecuting`
- **Severity**: warning
- **Service**: agent-grey
- **Component**: session-workflow

## Symptom

Sessions remain in "executing" state for more than 15 minutes without progressing to "processing_results" state. The session count in "executing" state is not changing.

## Impact

- **User Impact**: Users cannot complete their literature reviews. Sessions appear frozen.
- **Business Impact**: Core workflow blocked. Users may abandon sessions.
- **Urgency**: Moderate (resolve within 1 hour)

## Diagnosis

### Step 1: Verify the Alert

```bash
# Check current sessions in executing state
curl -s 'http://localhost:9090/api/v1/query?query=agent_grey_session_state{state="executing"}' | jq '.data.result[0].value[1]'

# Check if any transitions happened recently
curl -s 'http://localhost:9090/api/v1/query?query=increase(agent_grey_session_transitions_total{from_state="executing"}[15m])' | jq '.'
```

### Step 2: Check Grafana Dashboard

- Navigate to: http://localhost:3000/d/overview
- Panel: "Active Sessions by State"
- Look for: Sessions stuck in "executing" slice
- Check: "Session Throughput" for stalled progression

### Step 3: Identify Stuck Sessions

```bash
# Get stuck session IDs from database
docker compose exec web python manage.py shell << 'EOF'
from apps.review_manager.models import SearchSession
from django.utils import timezone
import datetime

cutoff = timezone.now() - datetime.timedelta(minutes=15)
stuck = SearchSession.objects.filter(
    status='executing',
    updated_at__lt=cutoff
)
for session in stuck:
    print(f"Session {session.id}: {session.title}")
    print(f"  Owner: {session.owner.email}")
    print(f"  Updated: {session.updated_at}")
    print(f"  Age: {timezone.now() - session.updated_at}")
EOF
```

### Step 4: Check Celery Workers

```bash
# Check Celery worker status
docker compose ps celery_worker

# Check active tasks
docker compose exec web python manage.py shell -c "
from celery import current_app
inspect = current_app.control.inspect()
active = inspect.active()
print('Active tasks:', active)
"

# Check worker logs for errors
docker compose logs celery_worker | grep -i "error\|exception\|timeout" | tail -30
```

### Step 5: Check Search Execution Status

```bash
# Check SearchExecution records for stuck sessions
docker compose exec web python manage.py shell << 'EOF'
from apps.serp_execution.models import SearchExecution
from apps.review_manager.models import SearchSession

stuck_sessions = SearchSession.objects.filter(status='executing')
for session in stuck_sessions:
    executions = SearchExecution.objects.filter(
        query__strategy__session=session,
        status='pending'
    )
    if executions.exists():
        print(f"Session {session.id} has {executions.count()} pending executions")
        for exec in executions[:5]:
            print(f"  - Execution {exec.id}: {exec.query.query_text[:50]}")
EOF
```

## Resolution

### Quick Fix (Immediate Mitigation)

```bash
# Run stuck session recovery task
docker compose exec web python manage.py shell -c "
from apps.review_manager.tasks.maintenance import recover_stuck_sessions
result = recover_stuck_sessions.delay()
print('Recovery task ID:', result.id)
"

# Monitor recovery task
docker compose logs celery_worker | grep "recover_stuck_sessions" | tail -20
```

**Expected Result**: Sessions should transition to appropriate states within 2 minutes

### Root Cause Investigation

**Possible Causes**:
1. Celery worker crashed or stuck
2. Serper API timeout/rate limit
3. Database connection issues
4. Network problems

```bash
# Check Celery worker health
docker compose exec celery_worker celery -A grey_lit_project inspect ping

# Check Serper API connectivity
docker compose exec web python manage.py shell -c "
from apps.core.services.serper_client import SerperClient
client = SerperClient()
result = client.test_connection()
print('API connectivity:', 'OK' if result else 'FAILED')
"

# Check database connectivity
docker compose exec web python manage.py dbshell -c "\dt"
```

### Permanent Fix Based on Root Cause

**If Celery Worker Issue**:
```bash
# Restart Celery worker
docker compose restart celery_worker

# Scale up workers if needed
docker compose up -d --scale celery_worker=3
```

**If API Rate Limit**:
```bash
# Check current API usage
curl -s 'http://localhost:9090/api/v1/query?query=rate(agent_grey_search_queries_total[1m])*60' | jq '.'

# Implement throttling in code (requires deployment)
# See: apps/serp_execution/services/rate_limiter.py
```

**If Database Connection Issue**:
```bash
# Check database connection pool
docker compose exec web python manage.py shell -c "
from django.db import connection
from django.db.utils import OperationalError
try:
    connection.ensure_connection()
    print('Database: Connected')
except OperationalError as e:
    print('Database: Error -', e)
"

# Restart database container (last resort)
docker compose restart db
```

### Verification

```bash
# Verify sessions progressing
watch -n 5 'curl -s "http://localhost:9090/api/v1/query?query=agent_grey_session_state{state=\"executing\"}" | jq ".data.result[0].value[1]"'

# Check for recent transitions
curl -s 'http://localhost:9090/api/v1/query?query=increase(agent_grey_session_transitions_total{from_state="executing"}[5m])' | jq '.'

# Check alert resolved in AlertManager
curl -s http://localhost:9093/api/v2/alerts | jq '.[] | select(.labels.alertname=="SessionsStuckInExecuting") | .status'
```

**Success Criteria**:
- Session count in "executing" decreasing
- Sessions transitioning to "processing_results" or "ready_for_review"
- Alert status: resolved
- No new stuck sessions appearing

## Escalation

1. **Level 1** (if not resolved in 30 min): Notify #engineering-oncall
2. **Level 2** (if critical sessions affected): Page on-call via PagerDuty
3. **Level 3** (if data integrity risk): Escalate to engineering lead + database admin

## Prevention

- [x] Implement stuck session auto-recovery task (already exists)
- [ ] Add circuit breaker for Serper API calls
- [ ] Implement request queue with rate limiting
- [ ] Add Celery worker auto-scaling based on queue depth
- [ ] Set up session execution timeout enforcement
- [ ] Add correlation ID tracking for better debugging

## Related

- **Grafana Dashboard**: http://localhost:3000/d/overview
- **Related Alerts**: HighSessionTransitionFailureRate, CeleryQueueBacklog
- **Code References**:
  - `apps/review_manager/tasks/maintenance.py:recover_stuck_sessions()`
  - `apps/core/services/serper_client.py`
  - `apps/review_manager/models.py:SearchSession`
- **Documentation**:
  - [Session Workflow Architecture](../architecture/session-workflow.md)
  - [Celery Task Monitoring](../operations/celery-monitoring.md)

---

**Last Updated**: 2025-10-03
**Author**: Enterprise Monitoring Team
**Reviewed**: 2025-10-03
