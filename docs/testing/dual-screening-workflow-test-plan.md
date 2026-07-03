# Dual-Screening Workflow Test Plan

**Date**: 2025-10-28
**Test Session**: After Issues #27-32 fixes
**Testers**: Lead Reviewer (admin), Invited Reviewer (el.coder5050)

## Test Objectives

Validate complete dual-screening workflow from session creation through conflict resolution and completion, ensuring all fixes are working correctly.

## Pre-Test Setup

### Users
- **Lead Reviewer**: admin (admin@localhost)
- **Invited Reviewer**: el.coder5050 (el.coder5050@gmail.com)
- **Organization**: Good Society

### Expected Fixes to Validate
- ✅ Issue #27: Zero results no longer block access
- ✅ Issue #28: Enter key adds reviewer (doesn't submit form)
- ✅ Issue #29: Navigation directs to correct interface
- ✅ Issue #30: WorkQueue extracts session_id from URL
- ✅ Issue #31: Auto-created organization for users
- ✅ Issue #32: Query parameters preserved during redirect

---

## Test Cases

### Test 1: Session Creation & Setup

**Objective**: Create new dual-screening session with proper configuration

**Steps**:
1. Log in as admin
2. Navigate to `/sessions/create/`
3. Create session:
   - Title: "Dual-Screening Test"
   - Description: "Testing complete workflow after fixes"
4. Define search strategy (any valid PIC terms)
5. Navigate to review setup `/sessions/{id}/setup`
6. Configure dual-screening:
   - Min reviewers: 2
   - Invite reviewer: el.coder5050@gmail.com
   - **Test Issue #28**: Type name/email and press Enter
7. **Verify**: Reviewer added to list (not form submitted)
8. Click "Continue to Session Detail"

**Expected Results**:
- ✅ Session created successfully
- ✅ Enter key adds reviewer without submitting
- ✅ Configuration saved with invited_reviewers
- ✅ Session shows "Dual-Screening" button (Issue #29)

---

### Test 2: Search Execution

**Objective**: Execute search and verify results

**Steps**:
1. From session detail, execute search
2. Wait for completion → `ready_for_review` status
3. **Verify session detail page shows**:
   - Status: "Ready for Review"
   - Button text: "Start Dual-Screening" (not "Start Review")
   - URL on button: `/screening/?session_id={uuid}`
   - Progress: X results ready

**Expected Results**:
- ✅ Search completes successfully
- ✅ Navigation button shows "Start Dual-Screening" (Issue #29)
- ✅ Results count is accurate
- ✅ Invitation email sent to el.coder5050

---

### Test 3: Lead Reviewer Access

**Objective**: Lead reviewer can access dual-screening SPA

**Steps**:
1. Still logged in as admin
2. Click "Start Dual-Screening" button
3. **Verify URL**: `/screening/?session_id={uuid}`
4. **Verify page loads** (not blank) - Issues #30, #32
5. **Verify Work Queue displays**:
   - Progress statistics (Pending, My Claims, Completed, Conflicts)
   - "Claim Next Result" button
   - List of results with status
6. **Test hard refresh** (Ctrl+Shift+R)
7. **Verify**: Page still loads with data (Issue #32)

**Expected Results**:
- ✅ SPA loads without errors
- ✅ session_id extracted from URL (Issue #30)
- ✅ Work queue shows results
- ✅ Hard refresh preserves session_id (Issue #32)
- ✅ No blank page issues

---

### Test 4: Lead Reviewer Screening

**Objective**: Complete screening decisions as lead reviewer

**Steps**:
1. In Work Queue, click "Claim Next Result"
2. Review result details (title, URL, snippet)
3. Make decision: INCLUDE or EXCLUDE
4. Add optional notes
5. Submit decision
6. **Verify**: Returned to work queue
7. Repeat for 5-10 results
8. **Verify Work Queue updates**:
   - Pending count decreases
   - My Claims count increases
   - Completed count increases

**Expected Results**:
- ✅ Results claim successfully
- ✅ Screening interface works
- ✅ Decisions save correctly
- ✅ Progress updates in real-time

---

### Test 5: Invited Reviewer Access

**Objective**: Invited reviewer can access and work independently

**Steps**:
1. Log out admin
2. Log in as el.coder5050
3. Check email for invitation (or navigate directly)
4. Navigate to session detail page
5. **Verify session detail shows**:
   - "You are a reviewer on this session"
   - "Start Dual-Screening" button
   - **Test Issue #27**: Should work even if 0 results scenario
6. Click "Start Dual-Screening"
7. **Verify URL**: Same as lead reviewer
8. **Verify Work Queue shows**:
   - Different set of unclaimed results
   - **No visibility** of admin's progress (blinding)
   - Own progress only

**Expected Results**:
- ✅ Invited reviewer has access
- ✅ Same URL works for both reviewers
- ✅ Blinding enforced (can't see admin's decisions)
- ✅ Can claim and screen independently

---

### Test 6: Invited Reviewer Screening

**Objective**: Complete screening decisions as invited reviewer

**Steps**:
1. Still logged in as el.coder5050
2. Claim and screen same results that admin screened
3. **Make different decisions** (INCLUDE vs EXCLUDE)
4. Screen 5-10 results total
5. **Verify**: Some overlap with admin's results

**Expected Results**:
- ✅ Can claim results independently
- ✅ Decisions save under el.coder5050
- ✅ No indication of admin's decisions shown
- ✅ Progress tracked separately

---

### Test 7: Blinding Enforcement

**Objective**: Verify reviewers cannot see each other's decisions

**Steps**:
1. As el.coder5050, view Work Queue
2. **Check for any indicators** of admin's decisions:
   - Decision badges
   - Vote counts
   - Progress bars showing "others completed"
3. Navigate to Team Dashboard (if accessible)
4. **Verify**: No detailed decision breakdown until both complete
5. Log back in as admin
6. **Verify**: Same blinding applies to admin

**Expected Results**:
- ✅ No visibility into other reviewer's decisions
- ✅ No vote counts or decision indicators
- ✅ Blinding maintained until both reviewers complete
- ✅ Dashboard respects blinding rules

---

### Test 8: Conflict Detection

**Objective**: System detects conflicts when reviewers disagree

**Steps**:
1. Ensure both reviewers have screened same results
2. With conflicting decisions (admin: INCLUDE, el.coder5050: EXCLUDE)
3. Navigate to Conflicts view
4. **Verify Conflict List shows**:
   - Result details
   - Conflict badge/indicator
   - "Resolve Conflict" button
5. Click on a conflict
6. **Verify Conflict Resolution page shows**:
   - Result details
   - Both reviewers' decisions (now visible)
   - Resolution options
   - Discussion/notes area

**Expected Results**:
- ✅ Conflicts detected automatically
- ✅ Conflict count accurate
- ✅ Conflict details show both decisions
- ✅ Resolution interface works

---

### Test 9: Conflict Resolution

**Objective**: Lead reviewer can resolve conflicts

**Steps**:
1. Log in as admin (lead reviewer)
2. Navigate to conflict
3. Review both decisions
4. Make final decision: INCLUDE or EXCLUDE
5. Add resolution notes
6. Submit resolution
7. **Verify**: Conflict removed from list
8. **Verify**: Final decision recorded

**Expected Results**:
- ✅ Lead reviewer can resolve
- ✅ Resolution saves correctly
- ✅ Conflict marked as resolved
- ✅ Final decision applied

---

### Test 10: Completion Workflow

**Objective**: Session can be completed after all reviews done

**Steps**:
1. Ensure both reviewers completed all assigned results
2. Ensure all conflicts resolved
3. As admin, navigate to session detail
4. Click "Complete Review" button
5. **Verify**:
   - No error about pending reviewers (Issue #27 related)
   - Session status changes to `completed`
   - Completion timestamp recorded
6. **Verify session detail shows**:
   - "View Report" button
   - Final statistics (IRR, inclusion rate, etc.)

**Expected Results**:
- ✅ Completion succeeds when all work done
- ✅ No false "pending reviewer" errors
- ✅ Status updates correctly
- ✅ Report generation available

---

### Test 11: Edge Cases

**Objective**: Validate fixes handle edge cases

#### Test 11a: Zero Results Session (Issue #27)
1. Create session with search that returns 0 results
2. Configure dual-screening
3. Try to access review interface
4. **Verify**: No blocking error (can access to see "0 results")

#### Test 11b: Hard Refresh Everywhere (Issue #32)
1. Navigate to various SPA routes:
   - `/screening/?session_id={uuid}`
   - `/screening/work-queue?session_id={uuid}`
   - `/screening/conflicts?session_id={uuid}`
2. Hard refresh on each
3. **Verify**: session_id preserved, page loads correctly

#### Test 11c: Direct URL Access
1. Copy complete URL with session_id
2. Open in new tab/incognito
3. **Verify**: Redirects to login, then back to correct page with session_id

---

## Success Criteria

### Critical (Must Pass)
- [ ] Both reviewers can access dual-screening SPA
- [ ] Session_id preserved in URL across navigation
- [ ] Blinding enforced (reviewers can't see each other's decisions)
- [ ] Conflicts detected when reviewers disagree
- [ ] Completion works when all reviews done
- [ ] No blank page issues

### Important (Should Pass)
- [ ] Enter key adds reviewer without form submission
- [ ] Navigation shows "Start Dual-Screening" for dual-screening sessions
- [ ] Hard refresh works without losing session_id
- [ ] Zero results sessions don't block access
- [ ] Users have organization context automatically

### Nice-to-Have
- [ ] Real-time updates via SSE
- [ ] Progress tracking accurate
- [ ] Email notifications sent
- [ ] IRR metrics calculated

---

## Test Execution Log

**Session ID**: _____________

**Date**: 2025-10-28

**Results**:
- Test 1 (Session Creation): ⬜ Pass ⬜ Fail
- Test 2 (Search Execution): ⬜ Pass ⬜ Fail
- Test 3 (Lead Access): ⬜ Pass ⬜ Fail
- Test 4 (Lead Screening): ⬜ Pass ⬜ Fail
- Test 5 (Invited Access): ⬜ Pass ⬜ Fail
- Test 6 (Invited Screening): ⬜ Pass ⬜ Fail
- Test 7 (Blinding): ⬜ Pass ⬜ Fail
- Test 8 (Conflict Detection): ⬜ Pass ⬜ Fail
- Test 9 (Conflict Resolution): ⬜ Pass ⬜ Fail
- Test 10 (Completion): ⬜ Pass ⬜ Fail
- Test 11 (Edge Cases): ⬜ Pass ⬜ Fail

**Issues Found**:

**Overall Status**: ⬜ Pass ⬜ Fail

---

## Notes

- All tests should be executed in order
- Document any issues found with steps to reproduce
- Take screenshots of any errors
- Record session IDs for debugging
- Check browser console for JavaScript errors
- Monitor Django logs for backend errors
