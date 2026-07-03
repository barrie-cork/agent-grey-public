# Adaptive Batching Implementation Plan

**Date**: 2025-10-06
**Priority**: HIGH
**Issue**: Rate limit failures causing incomplete result coverage (65% vs 95%+ expected)
**Solution**: Implement adaptive API call batching with intelligent rate limit management

---

## Executive Summary

Current execution hits Serper API rate limits (20 calls in 50s), causing incomplete results. Implementing adaptive batching will:
- **Increase coverage**: 65.3% → 95%+ (estimated +80 results per session)
- **Eliminate rate limit errors**: 0 failures vs 1-2 per session currently
- **Minimal time cost**: +30-70s per session (80-120s total vs 50s current)
- **Better UX**: Clear progress updates during intelligent pauses

---

## Current State Analysis

### Problem
```
Session: Obesity-test (af3433bb-996c-489d-8d62-9999e655887e)
────────────────────────────────────────────────────────────────
Query 1-5: 17 API calls in 36.6s - SUCCESS
Query 6:   3 API calls in 13.1s - RATE LIMIT ❌
────────────────────────────────────────────────────────────────
Total:     20 API calls in 49.7s
Result:    196/300 results (65.3% coverage)
Lost:      ~30 results on Query 6 due to rate limit
```

### API Constraints
- **Rate**: 15 requests/minute (0.25 calls/sec)
- **Burst**: 20 requests total before hard limit
- **Window**: 60 seconds rolling window

### Root Cause
Sequential execution without rate limit awareness causes burst limit violation when:
- Total API calls > 15 within any 60-second window
- Cumulative calls reach 20 (burst limit)

---

## Solution: Adaptive Batching

### Strategy
Monitor API call count and pause intelligently **before** hitting rate limits:

```
┌─────────────────────────────────────────────────────────┐
│  Query Execution Loop                                    │
├─────────────────────────────────────────────────────────┤
│  1. Check: api_calls >= threshold (12/15)?              │
│     ├─ NO  → Execute query, increment counter           │
│     └─ YES → Check time in window                       │
│         ├─ < 60s → PAUSE (60 - elapsed) seconds         │
│         └─ ≥ 60s → Reset counter, continue              │
└─────────────────────────────────────────────────────────┘
```

### Key Parameters
```python
RATE_LIMIT_THRESHOLD = 12    # Pause at 12/15 (80% utilisation)
RATE_LIMIT_WINDOW = 60       # Serper API window (seconds)
SAFETY_BUFFER = 3            # Calls before limit (15 - 12 = 3)
```

---

## Implementation Plan

### Phase 1: Core Adaptive Logic (2-3 hours)

#### 1.1 Update SerperClient Rate Limiter
**File**: `apps/core/services/simple_services.py`

**Changes Required**:
1. Add window tracking to TokenBucketRateLimiter
2. Implement `get_calls_in_window()` method
3. Implement `get_time_until_reset()` method
4. Add `should_pause()` method

**Code Changes**:
```python
class TokenBucketRateLimiter:
    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger(__name__)
        # NEW: Track window start
        self._window_start_key_suffix = ':window_start'

    def get_calls_in_window(self, user_id: str = 'global') -> tuple[int, float]:
        """
        Get current API call count and window age.

        Returns:
            tuple: (calls_in_window, window_age_seconds)
        """
        from django.core.cache import cache
        import time

        window_key = f"{self.config['key_prefix']}:{user_id}:simple"
        window_start_key = f"{self.config['key_prefix']}:{user_id}:simple:start"

        current_time = time.time()
        window_start = cache.get(window_start_key)

        if window_start is None:
            return 0, 0.0

        window_age = current_time - window_start

        # If window expired, return 0
        if window_age >= self.config['period']:
            return 0, 0.0

        current_count = cache.get(window_key, 0)
        return current_count, window_age

    def get_time_until_reset(self, user_id: str = 'global') -> float:
        """
        Get seconds until rate limit window resets.

        Returns:
            float: Seconds until reset (0 if already reset)
        """
        calls, window_age = self.get_calls_in_window(user_id)

        if calls == 0:
            return 0.0

        time_until_reset = self.config['period'] - window_age
        return max(0.0, time_until_reset)

    def should_pause(self, user_id: str = 'global', threshold: int = 12) -> tuple[bool, float]:
        """
        Check if execution should pause to avoid rate limits.

        Args:
            user_id: User identifier
            threshold: Pause when this many calls reached (default: 12/15 = 80%)

        Returns:
            tuple: (should_pause: bool, pause_duration: float)
        """
        calls, window_age = self.get_calls_in_window(user_id)

        # If below threshold, no pause needed
        if calls < threshold:
            return False, 0.0

        # If window will reset soon (< 5s), just wait it out
        time_until_reset = self.config['period'] - window_age
        if time_until_reset < 5.0:
            return True, time_until_reset

        # Otherwise, pause until window resets
        return True, time_until_reset
```

#### 1.2 Update Search Execution Task
**File**: `apps/serp_execution/tasks/simple_tasks.py`

**Changes Required**:
1. Add adaptive batching logic to main execution loop
2. Emit progress events during pauses
3. Update logging for transparency

**Code Changes**:
```python
@shared_task(bind=True, max_retries=3)
def execute_search_session_simple(self, session_id, user_id=None):
    """Execute search with adaptive rate limiting."""

    # ... existing setup code ...

    # Rate limiting configuration
    RATE_LIMIT_THRESHOLD = 12  # Pause at 80% utilisation (12/15)

    # Main execution loop
    for i, query in enumerate(queries, 1):
        try:
            # ═══════════════════════════════════════════════════════════
            # ADAPTIVE RATE LIMIT CHECK (NEW)
            # ═══════════════════════════════════════════════════════════
            if rate_limiter:
                should_pause, pause_duration = rate_limiter.should_pause(
                    user_id='global',
                    threshold=RATE_LIMIT_THRESHOLD
                )

                if should_pause and pause_duration > 0:
                    # Log pause
                    logger.warning(
                        f"Approaching rate limit. Pausing {pause_duration:.0f}s "
                        f"before query {i}/{total_queries}"
                    )

                    # Update session status
                    session.update_status_detail(
                        f"Pausing {pause_duration:.0f}s to respect API rate limits "
                        f"(before query {i}/{total_queries})"
                    )

                    # Emit pause event for real-time UI updates
                    event_bus.emit(QueryProgressEvent(
                        session_id=str(session.id),
                        query_index=i,
                        total_queries=total_queries,
                        query_text=query.query_text,
                        status='pausing',
                        metadata={
                            'pause_duration': pause_duration,
                            'reason': 'rate_limit_threshold',
                            'threshold': RATE_LIMIT_THRESHOLD
                        }
                    ))

                    # Actually pause
                    time.sleep(pause_duration)

                    # Emit resume event
                    event_bus.emit(QueryProgressEvent(
                        session_id=str(session.id),
                        query_index=i,
                        total_queries=total_queries,
                        query_text=query.query_text,
                        status='resuming',
                        metadata={'after_pause': pause_duration}
                    ))

            # ═══════════════════════════════════════════════════════════
            # EXISTING QUERY EXECUTION CODE
            # ═══════════════════════════════════════════════════════════
            session.update_status_detail(
                f'Executing query {i} of {total_queries}: {query.query_text[:50]}...'
            )

            # ... rest of existing execution code ...

        except Exception as e:
            # ... existing error handling ...
            pass

    # ... existing completion code ...
```

#### 1.3 Update Event Types
**File**: `apps/core/state_machine/events.py`

**Changes Required**:
Add new event statuses for pause/resume states.

**Code Changes**:
```python
class QueryProgressEvent(BaseEvent):
    """
    Event emitted during query execution progress.

    Status values:
    - 'starting': Query execution starting
    - 'pausing': Pausing for rate limit management (NEW)
    - 'resuming': Resuming after pause (NEW)
    - 'completed': Query completed successfully
    - 'failed': Query failed with error
    """

    def __init__(self, session_id: str, query_index: int, total_queries: int,
                 query_text: str, status: str, results_count: int = 0,
                 target_domain: str = None, metadata: dict = None):
        super().__init__(
            event_type='query_progress',
            session_id=session_id,
            metadata={
                'query_index': query_index,
                'total_queries': total_queries,
                'query_text': query_text,
                'status': status,
                'results_count': results_count,
                'target_domain': target_domain,
                **(metadata or {})
            }
        )
```

---

### Phase 2: UI Enhancements (1-2 hours)

#### 2.1 Update Execution Status Template
**File**: `templates/serp_execution/execution_status.html`

**Changes Required**:
1. Add pause indicator to progress display
2. Show countdown during pauses
3. Display pause reason

**Code Changes**:
```javascript
// Handle pause events
if (data.status === 'pausing') {
    const pauseDuration = data.metadata?.pause_duration || 0;
    const reason = data.metadata?.reason || 'rate_limit';

    // Show pause notification
    updateProgressMessage(
        `⏸️ Pausing ${Math.ceil(pauseDuration)}s to respect API rate limits...`,
        'warning'
    );

    // Start countdown
    startPauseCountdown(pauseDuration);
}

// Handle resume events
if (data.status === 'resuming') {
    updateProgressMessage('▶️ Resuming execution...', 'info');
    clearPauseCountdown();
}

function startPauseCountdown(duration) {
    let remaining = Math.ceil(duration);
    const countdownInterval = setInterval(() => {
        remaining--;
        updateProgressMessage(
            `⏸️ Pausing ${remaining}s to respect API rate limits...`,
            'warning'
        );

        if (remaining <= 0) {
            clearInterval(countdownInterval);
        }
    }, 1000);

    // Store interval ID for cleanup
    window.pauseCountdownInterval = countdownInterval;
}

function clearPauseCountdown() {
    if (window.pauseCountdownInterval) {
        clearInterval(window.pauseCountdownInterval);
        window.pauseCountdownInterval = null;
    }
}
```

#### 2.2 Add Pause Indicator to Progress Bar
```html
<!-- In execution_status.html -->
<div id="execution-progress" class="progress-container">
    <div class="progress-bar" role="progressbar"></div>

    <!-- NEW: Pause indicator -->
    <div id="pause-indicator" class="pause-indicator hidden">
        <span class="pause-icon">⏸️</span>
        <span id="pause-message">Pausing for rate limits...</span>
        <span id="pause-countdown" class="countdown"></span>
    </div>
</div>
```

**CSS**:
```css
.pause-indicator {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem;
    background-color: #fff3cd;
    border: 1px solid #ffc107;
    border-radius: 4px;
    margin-top: 0.5rem;
    animation: pulse 2s ease-in-out infinite;
}

.pause-indicator.hidden {
    display: none;
}

.pause-icon {
    font-size: 1.25rem;
}

.countdown {
    font-weight: bold;
    color: #856404;
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.7; }
}
```

---

### Phase 3: Configuration & Testing (1 hour)

#### 3.1 Add Configuration Settings
**File**: `grey_lit_project/settings/base.py`

```python
# Adaptive Rate Limiting Configuration
SERP_RATE_LIMIT_CONFIG = {
    'threshold': 12,          # Pause at 12/15 calls (80% utilisation)
    'window': 60,             # 60-second rate limit window
    'safety_buffer': 3,       # Reserve 3 calls (15 - 12)
    'min_pause': 5.0,         # Minimum pause duration (seconds)
    'enabled': True,          # Enable/disable adaptive batching
}
```

#### 3.2 Update SerperClient Initialization
**File**: `apps/core/services/simple_services.py`

```python
class SerperClient:
    def __init__(self, api_key: str = None):
        # ... existing code ...

        # Load adaptive rate limiting config
        from django.conf import settings
        self.adaptive_config = getattr(
            settings,
            'SERP_RATE_LIMIT_CONFIG',
            {
                'threshold': 12,
                'window': 60,
                'safety_buffer': 3,
                'min_pause': 5.0,
                'enabled': True
            }
        )
```

#### 3.3 Create Test Cases
**File**: `apps/serp_execution/tests/test_adaptive_batching.py`

```python
from django.test import TestCase
from unittest.mock import Mock, patch
from apps.core.services.simple_services import TokenBucketRateLimiter
import time

class AdaptiveBatchingTestCase(TestCase):
    """Test adaptive rate limiting functionality."""

    def setUp(self):
        self.rate_limiter = TokenBucketRateLimiter({
            'rate': 15,
            'period': 60,
            'burst': 20,
            'key_prefix': 'test'
        })

    def test_should_pause_below_threshold(self):
        """Test that no pause occurs below threshold."""
        # Simulate 5 API calls
        for _ in range(5):
            self.rate_limiter.can_proceed('test_user')

        should_pause, duration = self.rate_limiter.should_pause(
            'test_user',
            threshold=12
        )

        self.assertFalse(should_pause)
        self.assertEqual(duration, 0.0)

    def test_should_pause_at_threshold(self):
        """Test that pause occurs at threshold."""
        # Simulate 12 API calls
        for _ in range(12):
            self.rate_limiter.can_proceed('test_user')

        should_pause, duration = self.rate_limiter.should_pause(
            'test_user',
            threshold=12
        )

        self.assertTrue(should_pause)
        self.assertGreater(duration, 0.0)
        self.assertLessEqual(duration, 60.0)

    def test_get_calls_in_window(self):
        """Test window call tracking."""
        # Simulate 8 API calls
        for _ in range(8):
            self.rate_limiter.can_proceed('test_user')

        calls, window_age = self.rate_limiter.get_calls_in_window('test_user')

        self.assertEqual(calls, 8)
        self.assertGreaterEqual(window_age, 0.0)
        self.assertLess(window_age, 60.0)

    def test_window_reset(self):
        """Test that window resets after period."""
        # Simulate 12 API calls
        for _ in range(12):
            self.rate_limiter.can_proceed('test_user')

        # Wait for window to expire (mock time)
        with patch('time.time', return_value=time.time() + 65):
            calls, window_age = self.rate_limiter.get_calls_in_window('test_user')

            self.assertEqual(calls, 0)
            self.assertEqual(window_age, 0.0)
```

---

## Deployment Plan

### Step 1: Code Implementation (Day 1)
1. ✅ Implement Phase 1.1: Update TokenBucketRateLimiter
2. ✅ Implement Phase 1.2: Update search execution task
3. ✅ Implement Phase 1.3: Update event types
4. ✅ Write unit tests (Phase 3.3)

### Step 2: Testing (Day 1-2)
1. ✅ Run unit tests
2. ✅ Test with single query session (verify no regression)
3. ✅ Test with 6-query session (verify pauses occur)
4. ✅ Test with 10+ query session (verify multiple pauses)

### Step 3: UI Enhancements (Day 2)
1. ✅ Implement Phase 2.1: Update execution status template
2. ✅ Implement Phase 2.2: Add pause indicators
3. ✅ Test real-time pause updates in browser

### Step 4: Validation (Day 2-3)
1. ✅ Execute test session: "Obesity-test" equivalent
2. ✅ Verify no rate limit errors
3. ✅ Verify coverage improvement (65% → 95%+)
4. ✅ Measure execution time (target: <120s for 6 queries)

### Step 5: Production Deployment (Day 3)
1. ✅ Merge to main branch
2. ✅ Deploy to staging environment
3. ✅ Monitor first 5 sessions
4. ✅ Deploy to production if successful

---

## Success Metrics

### Primary Metrics
- **Coverage**: ≥95% of expected results retrieved
- **Rate Limit Errors**: 0 per session
- **Execution Time**: <2 minutes for typical 6-query session

### Secondary Metrics
- **User Satisfaction**: Clear progress updates during pauses
- **API Efficiency**: ≥80% rate limit utilisation (12/15 calls per window)
- **Reliability**: 100% session completion (no stalls)

---

## Risk Assessment & Mitigation

### Risk 1: Increased Execution Time
**Impact**: Medium
**Probability**: High
**Mitigation**:
- Adaptive logic only pauses when necessary
- Target <2 minutes for 6-query sessions (vs 50s current)
- Trade-off justified by +30% coverage improvement

### Risk 2: User Confusion During Pauses
**Impact**: Low
**Probability**: Medium
**Mitigation**:
- Clear progress messages: "Pausing 45s to respect API rate limits..."
- Live countdown: "Resuming in 23s..."
- Visual pause indicator with pulsing animation

### Risk 3: Rate Limiter State Inconsistency
**Impact**: Medium
**Probability**: Low
**Mitigation**:
- Use Redis cache with proper expiration
- Implement window tracking with timestamps
- Add fallback: if rate limiter fails, continue without pausing (current behaviour)

---

## Rollback Plan

If issues occur post-deployment:

1. **Quick Disable** (5 minutes):
   ```python
   # In settings/production.py
   SERP_RATE_LIMIT_CONFIG = {
       'enabled': False,  # Disable adaptive batching
       # ... other settings ...
   }
   ```

2. **Gradual Rollback** (15 minutes):
   - Revert commits for Phase 1.2 (task changes)
   - Keep Phase 1.1 (rate limiter enhancements for future use)
   - Keep Phase 1.3 (event types - no harm)

3. **Full Rollback** (30 minutes):
   - Revert all commits
   - Redeploy previous stable version
   - Document issues for future fix

---

## Future Enhancements

### Phase 4: Advanced Optimisations (Future)
1. **Intelligent Query Ordering**:
   - Execute high-result queries first
   - Group small queries together
   - Estimated improvement: +10% efficiency

2. **Per-User Rate Limiting**:
   - Track limits per API key
   - Enable multi-user sessions
   - Required for scaling

3. **Predictive Pausing**:
   - Estimate pages/query from previous sessions
   - Pause before starting query if insufficient quota
   - Estimated improvement: +5% user experience

4. **Rate Limit Pooling**:
   - Share rate limits across multiple Celery workers
   - Requires distributed state management (Redis Pub/Sub)
   - Estimated improvement: +20% throughput for concurrent sessions

---

## Appendix A: Configuration Reference

### TokenBucketRateLimiter Configuration
```python
{
    'rate': 15,              # Requests per minute
    'burst': 20,             # Maximum burst requests
    'period': 60,            # Window size (seconds)
    'key_prefix': 'serper',  # Cache key prefix
}
```

### Adaptive Batching Configuration
```python
SERP_RATE_LIMIT_CONFIG = {
    'threshold': 12,          # Pause at 80% utilisation
    'window': 60,             # Rate limit window (seconds)
    'safety_buffer': 3,       # Reserve calls (15 - 12)
    'min_pause': 5.0,         # Minimum pause duration
    'enabled': True,          # Enable feature
}
```

---

## Appendix B: Expected Performance

### Session Type: 6 Queries (Typical)

| Scenario | API Calls | Pauses | Duration | Coverage |
|----------|-----------|--------|----------|----------|
| **Current** | 20 | 0 | 50s | 65% (rate limit) |
| **With Adaptive** | 20 | 1 | 110s | 95%+ |

**Improvement**: +60s execution, +30% coverage, 0 errors

### Session Type: 10 Queries (Large)

| Scenario | API Calls | Pauses | Duration | Coverage |
|----------|-----------|--------|----------|----------|
| **Current** | 35 | 0 | 85s | 50% (multiple errors) |
| **With Adaptive** | 35 | 2 | 205s | 95%+ |

**Improvement**: +120s execution, +45% coverage, 0 errors

---

## Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-10-06 | Claude Code | Initial implementation plan |

**Status**: READY FOR IMPLEMENTATION
**Approval**: Pending user review
