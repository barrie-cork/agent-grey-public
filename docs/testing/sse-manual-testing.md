# SSE Manual Testing Procedure

**Created**: 12th October 2025
**Django Version**: 5.2.7
**Status**: Testing Guide ✅

## Overview

This document provides comprehensive manual testing procedures for Agent Grey's Server-Sent Events (SSE) implementation. Follow these tests to verify SSE functionality before and after deployment.

## Prerequisites

### Test Environment Setup

1. **Local Development**:
   ```bash
   docker compose up -d
   # Ensure web and database services running
   ```

2. **Staging Environment**:
   ```bash
   docker compose -f docker compose.staging.yml up -d --build
   ```

3. **Test User Account**:
   ```bash
   # Create test user if needed
   docker compose exec web python manage.py createsuperuser
   ```

4. **Test Session**:
   - Create a search session via UI
   - Note the session UUID for testing

### Required Tools

- **Browser**: Chrome, Firefox, Safari, or Edge (latest version)
- **curl**: For command-line testing
- **DevTools**: Browser developer tools

## Test Suite

### Test 1: Browser DevTools Connection Verification

**Objective**: Verify SSE connection established and events received

**Steps**:
1. Log in to Agent Grey
2. Navigate to session detail page: `/sessions/<uuid>/`
3. Open DevTools (F12)
4. Go to **Network** tab
5. Filter by **EventStream** or search for "stream"
6. Look for connection to `/sessions/<uuid>/stream/`

**Expected Results**:
- ✅ Connection shows status "pending" (stays open)
- ✅ Connection type: `text/event-stream`
- ✅ Status: `200 OK`
- ✅ Response headers include:
  - `Content-Type: text/event-stream`
  - `Cache-Control: no-cache`
  - `X-Accel-Buffering: no`

**Verify Events**:
1. In DevTools Network tab, click on the SSE request
2. Go to **Messages** or **Response** tab
3. Should see events like:
   ```
   data: {"type": "connected", "session_id": "..."}
   data: {"type": "status_update", "status": "draft", ...}
   ```

**Screenshot**: Capture DevTools showing active EventStream connection

**Pass Criteria**: Connection established, at least one event received

---

### Test 2: Connection Status Indicator

**Objective**: Verify connection status indicator updates correctly

**Steps**:
1. Navigate to session detail page
2. Observe connection status indicator (top of page)
3. Initially should show "○ Connecting..."
4. After connection: "● Connected"

**Expected Results**:
- ✅ Initially: "○ Connecting..." (grey)
- ✅ After 1-2 seconds: "● Connected" (green)
- ✅ Indicator remains green during active connection

**To Test Disconnection**:
1. Stop web server: `docker compose stop web`
2. Observe indicator changes to "◔ Reconnecting..." (orange/yellow)
3. After 5 failed attempts (5 seconds), should show "○ Disconnected" (red)
4. Restart server: `docker compose start web`
5. Indicator should return to "● Connected" (green)

**Pass Criteria**: Connection indicator accurately reflects connection state

---

### Test 3: Real-Time Status Updates

**Objective**: Verify session status updates pushed instantly via SSE

**Prerequisites**: Session in `ready_to_execute` state

**Steps**:
1. Open session detail page in browser
2. Keep DevTools Network tab open (EventStream filter)
3. Click "Execute Search" button (or use API/admin to change status)
4. Observe changes **without refreshing page**

**Expected Results**:
- ✅ Status badge updates from "Ready to Execute" → "Executing"
- ✅ Badge colour changes (blue → yellow)
- ✅ Progress bar appears and updates
- ✅ DevTools shows `status_update` events received
- ✅ Updates appear within 1 second of status change

**Advanced Test**:
1. Open same session in **two browser tabs**
2. Change status in one tab (or via admin)
3. Verify both tabs receive update simultaneously

**Pass Criteria**: Status updates appear instantly without page refresh, both tabs update in sync

---

### Test 4: Terminal State Handling

**Objective**: Verify SSE connection closes on session completion

**Prerequisites**: Session that will complete (or can be manually set to `completed`)

**Steps**:
1. Navigate to session detail page
2. Keep DevTools Network tab open
3. Wait for session to reach `completed` state (or manually set via admin)
4. Observe behaviour

**Expected Results**:
- ✅ Receive `complete` event: `{"type": "complete", "final_status": "completed"}`
- ✅ SSE connection closes gracefully
- ✅ Connection status indicator shows completion
- ✅ Page reloads automatically after 2 seconds
- ✅ No reconnection attempts after completion

**Verify Console**:
```javascript
// Expected console log
[SSE] Connected to session: <uuid>
[SSE] Status update: executing (45%)
[SSE] Status update: completed (100%)
[SSE] Session complete: completed
[SSE] Disconnected
```

**Pass Criteria**: Connection closes cleanly on completion, no errors

---

### Test 5: Multi-Tab Behaviour

**Objective**: Verify multiple SSE connections to same session work correctly

**Steps**:
1. Log in to Agent Grey
2. Open session detail page in **3 separate tabs**
3. Verify all 3 tabs show connection indicator as "Connected"
4. Open DevTools in one tab, verify 3 separate EventStream connections
5. Change session status (via admin or API)
6. Verify all 3 tabs update simultaneously

**Expected Results**:
- ✅ All tabs establish independent SSE connections
- ✅ Server handles 3 concurrent connections without issues
- ✅ All tabs receive events simultaneously (<100ms variance)
- ✅ No race conditions or conflicts between tabs
- ✅ Closing one tab doesn't affect others

**Resource Check**:
```bash
# Monitor server connections
docker compose exec web sh -c "ps aux | grep python"
# Should see multiple worker processes handling connections
```

**Pass Criteria**: Multiple tabs work independently, no performance degradation

---

### Test 6: Graceful Fallback to Polling

**Objective**: Verify automatic fallback when SSE unavailable

**Simulate SSE Failure**:

**Method 1: Block EventSource in DevTools**
1. Open DevTools → Sources → Event Listener Breakpoints
2. Add breakpoint on "DOMContentLoaded"
3. In console, execute:
   ```javascript
   delete window.EventSource;
   ```
4. Reload page

**Method 2: Simulate Network Error**
1. Open DevTools → Network tab
2. Set throttling to "Offline" temporarily during connection
3. Observe fallback behaviour

**Expected Results**:
- ✅ Console shows: `[SSE] EventSource not supported, falling back to polling`
- ✅ Connection indicator shows "Disconnected"
- ✅ Page still receives status updates (via polling endpoint)
- ✅ Polling requests visible in Network tab: `/api/session/<uuid>/status/`
- ✅ Polling interval: ~500ms
- ✅ No JavaScript errors

**Pass Criteria**: System gracefully falls back to polling, no data loss

---

### Test 7: Reconnection with Exponential Backoff

**Objective**: Verify automatic reconnection attempts with increasing delays

**Steps**:
1. Navigate to session detail page
2. Verify connection established (green indicator)
3. Stop web server: `docker compose stop web`
4. Observe reconnection attempts in console

**Expected Console Output**:
```javascript
[SSE] Connection opened
[SSE] Connected to session: <uuid>
[SSE] Connection error: [object Event]
[SSE] Reconnecting in 1000ms (attempt 1)
[SSE] Connection error: [object Event]
[SSE] Reconnecting in 2000ms (attempt 2)
[SSE] Connection error: [object Event]
[SSE] Reconnecting in 4000ms (attempt 3)
[SSE] Connection error: [object Event]
[SSE] Reconnecting in 8000ms (attempt 4)
[SSE] Connection error: [object Event]
[SSE] Reconnecting in 16000ms (attempt 5)
[SSE] Max reconnect attempts reached, falling back to polling
```

**Timing Verification**:
- Attempt 1: 1 second delay
- Attempt 2: 2 second delay
- Attempt 3: 4 second delay
- Attempt 4: 8 second delay
- Attempt 5: 16 second delay
- After 5 attempts: Fallback to polling

**Restart Server**:
```bash
docker compose start web
```

**Expected**: Polling continues, page functional

**Pass Criteria**: Exponential backoff observed, graceful fallback after 5 attempts

---

### Test 8: Load Test (10+ Concurrent Users)

**Objective**: Verify SSE performance under realistic load

**Setup**: Create 10+ test sessions

**Method 1: Automated Script**
```bash
#!/bin/bash
# load-test-sse.sh

# Get session ID
SESSION_ID="your-session-uuid"

# Get session cookie (login first)
COOKIE="sessionid=your-session-id"

# Open 10 concurrent SSE connections
for i in {1..10}; do
    echo "Starting connection $i"
    curl -N -H "Cookie: $COOKIE" \
        "http://localhost:8000/sessions/$SESSION_ID/stream/" &
done

echo "Waiting for connections..."
wait
```

**Method 2: Browser Tabs**
1. Open 10-15 browser tabs
2. Navigate to different session detail pages
3. Verify all connect successfully

**Monitoring**:
```bash
# Monitor active connections
docker compose exec web sh -c "netstat -an | grep :8000 | grep ESTABLISHED | wc -l"

# Monitor Django logs
docker compose logs -f web | grep SSE

# Monitor memory usage
docker stats web
```

**Expected Results**:
- ✅ All 10+ connections establish successfully
- ✅ Server memory usage increases linearly (~50KB per connection)
- ✅ CPU usage remains low (<10% per connection when idle)
- ✅ No connection drops or errors
- ✅ Events delivered to all connections simultaneously

**Pass Criteria**: System handles 10+ concurrent SSE connections without degradation

---

### Test 9: Network Interruption Recovery

**Objective**: Verify SSE recovers from temporary network issues

**Steps**:
1. Navigate to session detail page
2. Verify connection established
3. **Simulate network interruption**:
   - DevTools → Network tab → Set throttling to "Offline"
   - Wait 5 seconds
   - Set throttling back to "No throttling"
4. Observe recovery behaviour

**Expected Results**:
- ✅ Connection indicator shows "Reconnecting..."
- ✅ Automatic reconnection attempt within 1-2 seconds
- ✅ Connection re-established successfully
- ✅ No data loss (session state caught up)
- ✅ Console shows reconnection log

**Alternative Method** (harder interruption):
```bash
# Restart web server while connected
docker compose restart web
```

**Pass Criteria**: Connection automatically recovers, no manual intervention needed

---

### Test 10: Command-Line curl Test

**Objective**: Verify SSE endpoint works outside browser

**Prerequisites**: Valid session cookie

**Steps**:

1. **Get Session Cookie**:
   - Log in via browser
   - Open DevTools → Application → Cookies
   - Copy `sessionid` value

2. **Test SSE Endpoint**:
   ```bash
   # Replace <cookie> and <uuid> with actual values
   curl -N -H "Cookie: sessionid=<cookie>" \
       "http://localhost:8000/sessions/<uuid>/stream/"
   ```

3. **Observe Output**:
   ```
   data: {"type": "connected", "session_id": "<uuid>"}

   data: {"type": "status_update", "status": "draft", "progress": 0, ...}
   ```

**Expected Results**:
- ✅ Connection stays open (no immediate close)
- ✅ Receive `connected` event immediately
- ✅ Receive periodic `status_update` events
- ✅ Events follow SSE format: `data: {...}\n\n`
- ✅ Content-Type: `text/event-stream`

**Test with Invalid Session**:
```bash
curl -N -H "Cookie: sessionid=invalid" \
    "http://localhost:8000/sessions/<uuid>/stream/"

# Expected:
# data: {"type": "error", "message": "Session not found"}
```

**Pass Criteria**: curl receives SSE events correctly, error handling works

---

## Pass/Fail Criteria Summary

### Critical Tests (Must Pass)

| Test # | Test Name | Pass Criteria |
|--------|-----------|---------------|
| 1 | DevTools Connection | EventStream connection established |
| 2 | Connection Indicator | Indicator shows correct state |
| 3 | Real-Time Updates | Status updates without refresh |
| 4 | Terminal State | Connection closes on completion |
| 5 | Multi-Tab | Multiple tabs work independently |
| 6 | Fallback to Polling | Graceful degradation works |

### Important Tests (Should Pass)

| Test # | Test Name | Pass Criteria |
|--------|-----------|---------------|
| 7 | Reconnection | Exponential backoff observed |
| 8 | Load Test | Handles 10+ connections |
| 9 | Network Recovery | Auto-reconnects after interruption |
| 10 | curl Test | Command-line access works |

## Troubleshooting Test Failures

### Test 1 Failure: No EventStream Connection

**Check**:
1. Is `/sessions/<uuid>/stream/` URL correct?
2. Is user authenticated? (check session cookie)
3. Django logs: `docker compose logs web | grep SSE`

**Common Issues**:
- URL pattern not matched: Verify regex in `urls.py`
- Authentication failure: Check `@login_required` decorator
- CSRF issues: Verify `@csrf_exempt` on SSE view

### Test 2 Failure: Indicator Stuck on "Connecting"

**Check**:
1. Browser console for JavaScript errors
2. Network tab for failed SSE requests
3. session_monitor_sse.js loaded correctly

**Common Issues**:
- JavaScript not loading: Check static files served
- CORS issues: Verify allowed origins
- EventSource API not supported: Check browser compatibility

### Test 3 Failure: No Real-Time Updates

**Check**:
1. DevTools Messages tab: Are events being received?
2. Django SSE view: Is `yield` sending events?
3. Nginx buffering: Is `proxy_buffering off` set?

**Common Issues**:
- Buffering enabled: See `docs/deployment/nginx-sse-config.md`
- Database query not returning updated data
- Event filtering logic preventing updates

### Test 4 Failure: Connection Doesn't Close

**Check**:
1. Is terminal state being reached?
2. Django SSE view: Break statement triggered?
3. Console: `complete` event received?

**Common Issues**:
- Terminal state not in `['completed', 'archived', 'failed']`
- Infinite loop in event generator
- Exception swallowed silently

## Test Report Template

```markdown
# SSE Testing Report

**Date**: YYYY-MM-DD
**Environment**: Development / Staging / Production
**Tester**: Your Name
**Django Version**: 5.2.7

## Test Results Summary

| Test # | Test Name | Result | Notes |
|--------|-----------|--------|-------|
| 1 | DevTools Connection | ✅ PASS | |
| 2 | Connection Indicator | ✅ PASS | |
| 3 | Real-Time Updates | ✅ PASS | |
| 4 | Terminal State | ✅ PASS | |
| 5 | Multi-Tab | ✅ PASS | |
| 6 | Fallback to Polling | ✅ PASS | |
| 7 | Reconnection | ✅ PASS | |
| 8 | Load Test | ✅ PASS | Tested with 15 connections |
| 9 | Network Recovery | ✅ PASS | |
| 10 | curl Test | ✅ PASS | |

## Overall Result: ✅ PASS / ❌ FAIL

**Issues Found**: None / [List issues]

**Recommendations**: [Any observations or improvements]

**Sign-off**: [Name, Date]
```

## Automation Opportunities

### Future: Automated SSE Testing

**Playwright Test Example**:
```javascript
// tests/sse.spec.js
test('SSE connection established', async ({ page }) => {
    await page.goto('/sessions/<uuid>/');

    // Wait for SSE connection
    await page.waitForSelector('#connection-status:has-text("Connected")');

    // Verify EventStream request
    const sseRequest = await page.waitForRequest(
        req => req.url().includes('/stream/')
    );

    expect(sseRequest.resourceType()).toBe('eventsource');
});
```

**Benefits**: Regression testing, CI/CD integration

## References

- `docs/features/server-sent-events.md` - SSE implementation details
- `docs/deployment/nginx-sse-config.md` - Production configuration
- [MDN: Using Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)

## Summary

This testing procedure ensures Agent Grey's SSE implementation works correctly across different scenarios. Complete all critical tests before deployment, and run the full suite after any SSE-related changes.

**Key Takeaways**:
- Test both happy path and error scenarios
- Verify graceful degradation (fallback to polling)
- Load test with realistic concurrent users
- Document any environment-specific behaviour

---

**Prepared By**: Claude Code
**Date**: 12th October 2025
**Version**: 1.0
**Status**: Testing Guide ✅
