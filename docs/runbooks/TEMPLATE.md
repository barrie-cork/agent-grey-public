# Runbook: [Alert Name]

## Alert Information

- **Alert Name**: `[alert_name]`
- **Severity**: [critical|warning|info]
- **Service**: agent-grey
- **Component**: [component_name]

## Symptom

[What is happening that triggered this alert?]

## Impact

- **User Impact**: [How does this affect users?]
- **Business Impact**: [How does this affect the business?]
- **Urgency**: [How quickly must this be resolved?]

## Diagnosis

### Step 1: Verify the Alert

```bash
# Check alert status in AlertManager
curl -s http://localhost:9093/api/v2/alerts | jq '.[] | select(.labels.alertname=="[alert_name]")'

# Check Prometheus query
curl -s 'http://localhost:9090/api/v1/query?query=[alert_expr]' | jq '.data.result'
```

### Step 2: Check Grafana Dashboards

- Navigate to: [Dashboard URL]
- Look for: [What to look for in dashboard]
- Expected: [What should be normal]
- Actual: [What the problem looks like]

### Step 3: Check Logs

```bash
# Check application logs
docker compose logs web | grep -i "error\|exception" | tail -50

# Check specific error patterns
docker compose logs web | grep "[pattern]" | tail -20

# Check Celery worker logs
docker compose logs celery_worker | grep -i "error" | tail -30
```

### Step 4: Check System Resources

```bash
# Check container status
docker compose ps

# Check resource usage
docker stats --no-stream

# Check disk space
df -h
```

## Resolution

### Quick Fix (Immediate Mitigation)

```bash
# Command to immediately mitigate the issue
[commands]
```

**Expected Result**: [What should happen]

### Permanent Fix

```bash
# Command to permanently resolve the issue
[commands]
```

**Expected Result**: [What should happen]

### Verification

```bash
# Verify the fix worked
[verification commands]
```

**Success Criteria**: [How to know the issue is resolved]

## Escalation

If the issue persists after following these steps:

1. **Level 1**: Notify #engineering-oncall in Slack
2. **Level 2**: Page on-call engineer via PagerDuty (critical only)
3. **Level 3**: Escalate to engineering lead

## Prevention

[How to prevent this from happening in the future]

- [ ] Action item 1
- [ ] Action item 2
- [ ] Action item 3

## Related

- **Grafana Dashboard**: [URL]
- **Related Alerts**: [List related alerts]
- **Code References**: [Relevant code files]
- **Documentation**: [Links to relevant docs]

---

**Last Updated**: [Date]
**Author**: [Name]
**Reviewed**: [Date]
