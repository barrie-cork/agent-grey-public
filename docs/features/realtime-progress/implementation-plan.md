# Real-Time SERP Execution Progress Updates - Implementation Plan

## Executive Summary

This document outlines the plan to implement real-time progress updates for the SERP execution page showing detailed query-by-query progress including pagination details (e.g., "Query 1/5 completed: 50 results (5 pages, reason: limit_reached)").

**Current Status:** Infrastructure is 80% complete. SSE, event bus, and pagination tracking exist but need integration fixes.

**Key Issues Identified:**
1. UI shows "0/0 queries" - Quick Status API not returning query counts correctly
2. `simple_monitor.js` is used instead of the more feature-rich `session_monitor.js`
3. Pagination details captured in backend but not displayed in frontend

---

## Problem Analysis

### Issue 1: Zero Query Counts in UI

**Root Cause:** The Quick Status API (session_endpoints.py:314) queries `SearchQuery` objects, but during execution these may not be created yet.

```python
# Current code at session_endpoints.py:314
total_queries = SearchQuery.objects.filter(session=session).count()
```

**Issue:** If search execution starts before SearchQuery records are persisted, count returns 0.

### Issue 2: Simple Monitor vs Session Monitor

**Current State:**
- `session_detail.html` uses `simple_monitor.js` (basic polling)
- More advanced `session_monitor.js` exists with SSE support and query-level tracking
- The execution status page has better UI but simpler monitoring

**Gap:** Need to either:
1. Upgrade `simple_monitor.js` with SSE capabilities, OR
2. Switch `session_detail.html` to use `session_monitor.js`

### Issue 3: Pagination Details Not Displayed

**Backend:**
- `step_metadata.pagination` contains: `pages_fetched`, `stopped_reason`, `max_pages`
- Logged to console: `simple_tasks.py:186-189`
- Stored in database: `SearchExecution.step_metadata`

**Frontend:**
- UI elements exist (`#pagination-status`, `#page-progress-bar`)
- But not populated with actual pagination data

---

## Architecture Overview

### Current Real-Time Infrastructure

```
┌─────────────────┐
│  Celery Task    │
│ simple_tasks.py │
└────────┬────────┘
         │
         ├──> Emits QueryProgressEvent
         │    (query_index, total_queries,
         │     status, results_count)
         │
         ├──> Updates step_metadata
         │    (pagination: {pages_fetched,
         │     stopped_reason, max_pages})
         │
         └──> Updates SearchExecution
              (status, api_result_count)

         ↓

┌─────────────────┐
│   Event Bus     │
│ event_bus.py    │
└────────┬────────┘
         │
         ├──> SSE Stream (/core/sse/session/{id}/events/)
         │
         └──> Event Subscribers

         ↓

┌─────────────────┐       ┌─────────────────┐
│ SessionMonitor  │  OR   │ SimpleMonitor   │
│ session_monitor │       │ simple_monitor  │
│      .js        │       │      .js        │
└─────────────────┘       └─────────────────┘
    (SSE-based)              (Polling-based)
         │                        │
         └────────────────────────┘
                    │
                    ↓
         ┌─────────────────────┐
         │    UI Updates       │
         │ - Query counts      │
         │ - Current query     │
         │ - Pagination status │
         └─────────────────────┘
```

---

## Implementation Plan

### Phase 1: Fix Query Count Display (High Priority)

**Goal:** Show correct "X/Y queries" during execution

**Changes Required:**

#### 1.1 Fix Quick Status API Query Counting

**File:** `apps/serp_execution/api/session_endpoints.py:314`

**Current:**
```python
total_queries = SearchQuery.objects.filter(session=session).count()
```

**Fix:** Use denormalized queries or get from strategy:
```python
# Option A: Use denormalized relationship
total_queries = session.search_queries_denorm.count()

# Option B: Get from strategy (more reliable)
if hasattr(session, 'search_strategy'):
    total_queries = session.search_strategy.search_queries.count()
else:
    total_queries = 0
```

**Estimated Time:** 15 minutes
**Risk:** Low
**Impact:** High - Fixes "0/0 queries" issue immediately

#### 1.2 Update Simple Monitor to Display Counts

**File:** `apps/serp_execution/static/serp_execution/js/simple_monitor.js`

**Current:** Likely not parsing `query_stats` from API response

**Fix:** Ensure monitor reads and displays:
```javascript
if (data.query_stats) {
    this.updateCountDisplay(
        data.query_stats.completed_queries,
        data.query_stats.total_queries,
        data.query_stats.running_queries,
        data.query_stats.failed_queries
    );
}
```

**Estimated Time:** 30 minutes
**Risk:** Low
**Impact:** High - Makes counts visible in UI

---

### Phase 2: Add Pagination Details to UI (Medium Priority)

**Goal:** Show "50 results (5 pages, reason: limit_reached)" in real-time

**Changes Required:**

#### 2.1 Enhance QueryProgressEvent with Pagination Data

**File:** `apps/serp_execution/tasks/simple_tasks.py:195-212`

**Current:** Event only includes basic info
```python
QueryProgressEvent(
    session_id=str(session.id),
    query_index=i,
    total_queries=total_queries,
    query_text=query.query_text,
    status="completed",
    results_count=processed
)
```

**Enhancement:** Add pagination metadata
```python
QueryProgressEvent(
    session_id=str(session.id),
    query_index=i,
    total_queries=total_queries,
    query_text=query.query_text,
    status="completed",
    results_count=processed,
    pagination_info={
        "pages_fetched": pagination_info.get('pages_fetched', 1),
        "stopped_reason": pagination_info.get('stopped_reason', 'unknown'),
        "max_pages": pagination_info.get('max_pages', 10),
        "total_available": pagination_info.get('total_available')
    }
)
```

**Estimated Time:** 20 minutes
**Risk:** Low
**Impact:** Medium - Enables detailed progress tracking

#### 2.2 Update Event Type Definition

**File:** `apps/core/state_machine/events.py`

**Current:** QueryProgressEvent likely doesn't include pagination_info field

**Enhancement:** Add to event class:
```python
class QueryProgressEvent(BaseEvent):
    def __init__(
        self,
        session_id: str,
        query_index: int,
        total_queries: int,
        query_text: str,
        status: str,
        results_count: int = 0,
        target_domain: Optional[str] = None,
        pagination_info: Optional[dict] = None,  # NEW
    ):
        # ... existing code ...
        self.pagination_info = pagination_info or {}
```

**Estimated Time:** 15 minutes
**Risk:** Low
**Impact:** Required for Phase 2.1

#### 2.3 Update Frontend to Display Pagination

**File:** `apps/serp_execution/static/serp_execution/js/simple_monitor.js`

**Current:** Pagination status elements exist but unused

**Enhancement:** Add pagination display in update handler:
```javascript
updateCurrentQuery(data) {
    // ... existing query display code ...

    // NEW: Display pagination details
    if (data.pagination_info) {
        const paginationStatus = document.getElementById('pagination-status');
        const pageProgress = document.getElementById('page-progress-bar');

        const { pages_fetched, stopped_reason, max_pages } = data.pagination_info;

        // Update status text
        if (paginationStatus) {
            const reasonText = this.getStoppedReasonText(stopped_reason);
            paginationStatus.textContent = `${pages_fetched}/${max_pages} pages - ${reasonText}`;
        }

        // Update progress bar
        if (pageProgress && max_pages > 0) {
            const percent = (pages_fetched / max_pages) * 100;
            pageProgress.style.width = `${percent}%`;
            pageProgress.setAttribute('aria-valuenow', Math.round(percent));
        }
    }
}

getStoppedReasonText(reason) {
    const reasons = {
        'limit_reached': '✓ Target reached',
        'no_more_results': '✓ All results fetched',
        'rate_limited': '⚠️ Rate limited',
        'error': '❌ Error occurred',
        'unknown': 'In progress'
    };
    return reasons[reason] || reasons['unknown'];
}
```

**Estimated Time:** 45 minutes
**Risk:** Low
**Impact:** High - Provides detailed progress visibility

---

### Phase 3: Upgrade to SSE-Based Monitoring (Optional Enhancement)

**Goal:** Replace polling with Server-Sent Events for true real-time updates

**Current State:**
- `session_monitor.js` has full SSE implementation
- `simple_monitor.js` uses polling (2-second intervals)
- SSE infrastructure exists at `/core/sse/session/{id}/events/`

**Option A: Upgrade simple_monitor.js**

Add SSE support to existing simple_monitor.js:

```javascript
class SimpleSessionMonitor {
    constructor(sessionId, options) {
        this.useSSE = options.useSSE !== false;  // Default true
        if (this.useSSE) {
            this.connectSSE();
        } else {
            this.startPolling();
        }
    }

    connectSSE() {
        this.eventSource = new EventSource(
            `/core/sse/session/${this.sessionId}/events/`
        );

        this.eventSource.addEventListener('query_progress', (e) => {
            const data = JSON.parse(e.data);
            this.handleQueryProgress(data);
        });

        // Fallback to polling on error
        this.eventSource.onerror = () => {
            console.log('SSE failed, falling back to polling');
            this.startPolling();
        };
    }
}
```

**Estimated Time:** 2 hours
**Risk:** Medium (requires testing)
**Impact:** High - Eliminates 2s polling delay, reduces server load

**Option B: Switch to session_monitor.js**

Update `session_detail.html` to use the more feature-rich monitor:

```html
<!-- Replace simple_monitor.js with session_monitor.js -->
<script src="{% static 'serp_execution/js/session_monitor.js' %}?v={{ VERSION }}"></script>
<script>
    window.sessionMonitor = new SessionMonitor('{{ session.id }}', {
        autoRedirect: true,
        debugMode: false
    });
</script>
```

**Estimated Time:** 1 hour
**Risk:** Medium (different UI element IDs may need mapping)
**Impact:** High - Immediate SSE support with battle-tested code

---

## Quick Status API Enhancement

### Current Implementation Issues

**File:** `apps/serp_execution/api/session_endpoints.py:282-420`

**Problems:**
1. Query counting logic unreliable during execution
2. No pagination details in recent_queries
3. Missing stopped_reason context

### Recommended Fixes

```python
@login_required
@require_http_methods(["GET"])
def session_quick_status_api(request, session_id) -> JsonResponse:
    """Enhanced quick status with pagination details."""
    try:
        session = SearchSession.objects.get(id=session_id, owner=request.user)

        # FIX 1: Reliable query counting
        if hasattr(session, 'search_strategy'):
            total_queries = session.search_strategy.search_queries.count()
        else:
            total_queries = session.search_queries_denorm.count()

        # Get executions with pagination metadata
        executions = SearchExecution.objects.filter(
            query__session=session
        ).select_related("query")

        completed_queries = executions.filter(status="completed").count()
        running_queries = executions.filter(status="running").count()

        # FIX 2: Enhanced current query with pagination
        current_query_data = None
        if session.status in ["executing", "processing_results"]:
            current_exec = executions.filter(status="running").order_by("started_at").first()

            if current_exec:
                step_meta = current_exec.step_metadata or {}
                pagination = step_meta.get("pagination", {})

                current_query_data = {
                    "execution_id": str(current_exec.id),
                    "query_text": current_exec.query.query_text,
                    "status": current_exec.status,
                    "current_page": pagination.get("pages_fetched", 1),
                    "total_pages": pagination.get("max_pages", 10),
                    "results_so_far": current_exec.api_result_count or 0,
                    "stopped_reason": pagination.get("stopped_reason"),
                }

        # FIX 3: Enhanced recent queries with pagination
        recent_queries = []
        for execution in executions.filter(status="completed").order_by("-completed_at")[:3]:
            step_meta = execution.step_metadata or {}
            pagination = step_meta.get("pagination", {})

            recent_queries.append({
                "query_text": execution.query.query_text[:60],
                "results_count": execution.api_result_count or execution.results_count,
                "pages_fetched": pagination.get("pages_fetched", 1),
                "stopped_reason": pagination.get("stopped_reason", "unknown"),
                "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
            })

        response: SessionQuickStatusResponse = {
            "session_id": str(session.id),
            "status": session.status,
            "total_queries": total_queries,
            "completed_queries": completed_queries,
            "running_queries": running_queries,
            "current_query": current_query_data,
            "recent_queries": recent_queries,
            "timestamp": timezone.now().isoformat(),
        }

        return JsonResponse(response)

    except Exception as exc:
        logger.error("Error fetching quick status: %s", exc, exc_info=True)
        return JsonResponse({"error": "Failed to fetch status"}, status=500)
```

---

## Testing Strategy

### Unit Tests

**File:** `apps/serp_execution/tests/test_query_progress_api.py`

```python
def test_quick_status_with_pagination():
    """Test that quick status includes pagination metadata."""
    session = create_test_session()
    execution = create_test_execution(session)

    # Add pagination metadata
    execution.step_metadata = {
        "pagination": {
            "pages_fetched": 5,
            "stopped_reason": "limit_reached",
            "max_pages": 10
        }
    }
    execution.save()

    response = client.get(f'/execution/api/session/{session.id}/quick-status/')
    data = response.json()

    assert data['current_query']['current_page'] == 5
    assert data['current_query']['stopped_reason'] == 'limit_reached'
```

### Integration Tests

**File:** `apps/serp_execution/tests/test_realtime_progress.py`

```python
def test_end_to_end_progress_updates():
    """Test complete flow from task to UI."""
    # 1. Start execution
    task = execute_search_session_simple.delay(session.id)

    # 2. Verify event emission
    with event_capture() as events:
        task.get(timeout=30)
        assert any(e.event_type == 'query_progress' for e in events)

    # 3. Verify API returns pagination
    response = client.get(f'/execution/api/session/{session.id}/quick-status/')
    data = response.json()
    assert 'pagination_info' in data.get('current_query', {})
```

### Manual Testing Checklist

- [ ] UI shows "1/5 queries" during execution (not "0/0")
- [ ] Current query displays with pagination: "Page 3/10"
- [ ] Stopped reason shows: "✓ Target reached" or "⚠️ Rate limited"
- [ ] Recent queries show: "50 results (5 pages, limit_reached)"
- [ ] SSE connection establishes successfully
- [ ] Fallback to polling works when SSE fails
- [ ] Progress bar animates smoothly
- [ ] Auto-redirect works on completion

---

## Implementation Priority

### Phase 1: Critical Fixes (Day 1)
**Est. Time:** 1-2 hours
**Impact:** HIGH - Makes current UI functional

1. ✅ Fix query count in Quick Status API (15 min)
2. ✅ Update simple_monitor.js to display counts (30 min)
3. ✅ Test "X/Y queries" display (15 min)

### Phase 2: Pagination Details (Day 1-2)
**Est. Time:** 2-3 hours
**Impact:** HIGH - Adds detailed progress tracking

1. ✅ Add pagination_info to QueryProgressEvent (20 min)
2. ✅ Update event type definition (15 min)
3. ✅ Enhance Quick Status API with pagination (45 min)
4. ✅ Update frontend to display pagination (45 min)
5. ✅ Test pagination display (30 min)

### Phase 3: SSE Upgrade (Day 2-3, Optional)
**Est. Time:** 2-4 hours
**Impact:** MEDIUM - Improves performance, not functionality

1. ⏸️ Evaluate Option A vs Option B (30 min)
2. ⏸️ Implement chosen SSE approach (2 hours)
3. ⏸️ Test SSE with fallback (1 hour)
4. ⏸️ Document SSE configuration (30 min)

---

## Rollout Plan

### Stage 1: Development Testing
- Deploy to development environment
- Manual testing with real search sessions
- Monitor browser console for errors
- Verify SSE connections in Network tab

### Stage 2: Staging Validation
- Deploy to staging with feature flag
- A/B test: 50% simple_monitor, 50% session_monitor
- Monitor Sentry for JavaScript errors
- Collect performance metrics

### Stage 3: Production Release
- Deploy Phase 1 + Phase 2 (pagination details)
- Keep Phase 3 (SSE) behind feature flag
- Gradually enable SSE for power users
- Full rollout after 1 week of monitoring

---

## Success Metrics

### Functional Metrics
- ✅ Query counts display correctly (not "0/0")
- ✅ Pagination details visible in UI
- ✅ Stopped reason shows appropriate message
- ✅ Progress updates within 2 seconds of change

### Performance Metrics
- SSE connection success rate > 95%
- Fallback to polling < 5% of sessions
- UI update latency < 500ms
- Memory usage stable over 30-minute session

### User Experience Metrics
- Users report clearer progress visibility
- Reduction in "is it working?" support questions
- Improved confidence during long executions

---

## Risk Mitigation

### Risk 1: SSE Connection Failures
**Mitigation:** Automatic fallback to polling, graceful degradation

### Risk 2: High Event Volume
**Mitigation:** Rate limiting on SSE endpoint, event batching

### Risk 3: Browser Compatibility
**Mitigation:** Polyfill for older browsers, polling-only mode

### Risk 4: Database Load
**Mitigation:** Optimize Quick Status API queries, add caching

---

## Future Enhancements

### Page-by-Page Progress (Post-MVP)
Emit events after each pagination page:
```python
# In serper_client pagination loop
for page in range(1, max_pages + 1):
    results = fetch_page(page)
    event_bus.emit(QueryProgressEvent(
        status="fetching_page",
        page_info={"current": page, "total": max_pages, "results": len(results)}
    ))
```

### Visual Query Timeline (Post-MVP)
Add D3.js timeline visualization showing:
- Query execution sequence
- Parallel execution (if implemented)
- Time spent per query
- Pagination efficiency

### Export Progress Data (Post-MVP)
Allow users to export execution metrics:
- CSV format with per-query statistics
- Pagination efficiency report
- Rate limiting incidents

---

## Conclusion

The infrastructure for real-time SERP execution progress is largely complete. The primary issues are:

1. **Data flow breaks** (query counts not reaching UI)
2. **Missing pagination display** (data exists but not shown)
3. **Suboptimal monitoring choice** (polling vs SSE)

**Phase 1 + Phase 2 will solve the immediate problem** of showing detailed progress updates like "Query 1/5 completed: 50 results (5 pages, reason: limit_reached)".

**Phase 3 is optional** but recommended for improved performance and user experience.

**Total Implementation Time:** 5-9 hours across 2-3 days

**Maintenance:** Minimal - uses existing infrastructure

**Documentation Updated:** 2025-01-09
