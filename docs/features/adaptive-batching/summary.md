# Adaptive Batching - Quick Summary

**Date**: 2025-10-06
**Priority**: HIGH
**Implementation Time**: 4-6 hours

---

## Problem

Current execution hits API rate limits, losing 30-35% of available results:

```
Session: Obesity-test
├─ Queries 1-5: 17 API calls ✅
├─ Query 6:     3 API calls ❌ RATE LIMIT
└─ Result:      196/300 (65.3% coverage)
```

---

## Solution

Adaptive API call batching with intelligent pausing:

```python
# Pseudo-code
for each query:
    if api_calls >= 12 (of 15/min limit):
        if elapsed_time < 60s:
            pause(60 - elapsed_time)
            reset_counter()

    execute_query()
```

---

## Impact

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| **Coverage** | 65% | 95%+ | +30% |
| **Rate Limit Errors** | 1-2/session | 0 | -100% |
| **Execution Time** | 50s | 80-120s | +60% |
| **Results** | 196/300 | 285/300 | +89 |

**Value Proposition**: +1 minute execution for +30% data coverage

---

## Implementation Phases

### Phase 1: Core Logic (2-3 hours)
- ✅ Update `TokenBucketRateLimiter` with window tracking
- ✅ Add `should_pause()` method
- ✅ Integrate into `execute_search_session_simple` task
- ✅ Add pause/resume events

**Files Modified**:
- `apps/core/services/simple_services.py`
- `apps/serp_execution/tasks/simple_tasks.py`
- `apps/core/state_machine/events.py`

### Phase 2: UI Enhancements (1-2 hours)
- ✅ Add pause indicator to execution status page
- ✅ Show countdown during pauses
- ✅ Update progress messages

**Files Modified**:
- `templates/serp_execution/execution_status.html`
- `apps/serp_execution/static/serp_execution/js/session_monitor.js`

### Phase 3: Testing & Validation (1 hour)
- ✅ Unit tests for adaptive logic
- ✅ Integration test with 6-query session
- ✅ Verify 0 rate limit errors
- ✅ Confirm coverage improvement

---

## Key Code Changes

### 1. Rate Limiter Enhancement
```python
# apps/core/services/simple_services.py
class TokenBucketRateLimiter:
    def should_pause(self, user_id='global', threshold=12):
        """Check if should pause to avoid rate limits."""
        calls, window_age = self.get_calls_in_window(user_id)

        if calls < threshold:
            return False, 0.0

        time_until_reset = self.config['period'] - window_age
        return True, time_until_reset
```

### 2. Adaptive Execution
```python
# apps/serp_execution/tasks/simple_tasks.py
for i, query in enumerate(queries, 1):
    # Check if should pause
    should_pause, pause_duration = rate_limiter.should_pause(
        threshold=12  # 80% of 15/min
    )

    if should_pause:
        logger.warning(f"Pausing {pause_duration:.0f}s for rate limits")
        emit_pause_event(pause_duration)
        time.sleep(pause_duration)
        emit_resume_event()

    # Execute query
    execute_query_with_pagination(query)
```

### 3. Progress Events
```python
# During pause
emit(QueryProgressEvent(
    status='pausing',
    metadata={'pause_duration': 45, 'reason': 'rate_limit_threshold'}
))

# After pause
emit(QueryProgressEvent(
    status='resuming',
    metadata={'after_pause': 45}
))
```

---

## Configuration

```python
# grey_lit_project/settings/base.py
SERP_RATE_LIMIT_CONFIG = {
    'threshold': 12,      # Pause at 80% (12/15)
    'window': 60,         # 60-second window
    'safety_buffer': 3,   # Reserve 3 calls
    'min_pause': 5.0,     # Min pause duration
    'enabled': True,      # Feature toggle
}
```

---

## Testing Plan

1. **Unit Tests**: Rate limiter pause logic
2. **Integration Test**: 6-query session (obesity search)
3. **Validation**:
   - ✅ No rate limit errors
   - ✅ Coverage ≥95%
   - ✅ Execution time <2 minutes
   - ✅ UI shows pause countdown

---

## Success Criteria

- ✅ 0 rate limit errors per session
- ✅ ≥95% result coverage (vs 65% current)
- ✅ <2 minutes for 6-query session
- ✅ Clear UI feedback during pauses

---

## Rollback

**Quick disable** (if issues):
```python
# settings/production.py
SERP_RATE_LIMIT_CONFIG = {'enabled': False}
```

**Full rollback**: Revert commits, redeploy previous version

---

## Next Steps

1. **Review plan**: `docs/adaptive_batching_implementation_plan.md`
2. **Approve implementation**
3. **Execute Phase 1**: Core logic (2-3 hours)
4. **Execute Phase 2**: UI updates (1-2 hours)
5. **Test & validate**: (1 hour)
6. **Deploy to staging**: Monitor 5 sessions
7. **Deploy to production**: If validation successful

---

## Related Documents

- **Full Plan**: `docs/adaptive_batching_implementation_plan.md`
- **Bug Fix**: `docs/bug_fix_rate_limit_detection.md`
- **Test Results**: Session `af3433bb-996c-489d-8d62-9999e655887e`

---

**Status**: READY FOR IMPLEMENTATION
**Estimated Benefit**: +89 results per session, 0 errors, better UX
