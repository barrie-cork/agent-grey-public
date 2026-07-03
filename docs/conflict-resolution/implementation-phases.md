# Implementation Phases

Phased execution plan for conflict resolution improvements.

## Phase 1: Now (Bug Fixes)

These prevent the existing conflict resolution from being usable at all. All relate to issues #85 and #87.

### 1.1 Fix `canComment` to include `IN_DISCUSSION` and `ESCALATED` statuses

- **File**: `frontend/src/stores/consensusDiscussion.ts`
- **Problem**: `canComment` only returns `true` for `PENDING` status. After first comment, backend transitions to `IN_DISCUSSION` and discussion is dead.
- **Fix**: Extend the condition to include `IN_DISCUSSION` and `ESCALATED`.
- **Test**: Post a comment, verify you can post another.

### 1.2 Add exclusion_reason field to resolution form

- **File**: `frontend/src/views/ConflictResolution.vue` and `frontend/src/stores/conflicts.ts`
- **Problem**: Resolving as EXCLUDE sends no `exclusion_reason`, backend returns 400.
- **Fix**: Add conditional text input for exclusion reason when EXCLUDE is selected. Include in API payload.
- **Test**: Resolve a conflict as EXCLUDE, verify it succeeds.

### 1.3 Preserve `session_id` in router navigation

- **File**: `frontend/src/views/ConflictResolution.vue`
- **Problem**: After resolving, navigation to conflict list loses `session_id` query param.
- **Fix**: Include `query: { session_id }` in all `router.push()` calls.
- **Test**: Resolve a conflict, verify conflict list loads without error.

### 1.4 Fix hardcoded "Methodological Conflict" badge

- **File**: `frontend/src/views/ConflictResolution.vue`
- **Problem**: Badge always shows "Methodological Conflict" regardless of actual type.
- **Fix**: Use `conflict.conflict_type` value. Add display mapping for each type.
- **Test**: View conflicts of different types, verify badge matches.

### 1.5 Add auto-advance to next conflict

- **File**: `frontend/src/views/ConflictResolution.vue` and `frontend/src/stores/conflicts.ts`
- **Problem**: After resolving, user must manually navigate back to list and find next conflict.
- **Fix**: After successful resolution, check if there's a next pending conflict in the list and navigate to it. Show "All conflicts resolved" if none remain.
- **Test**: Resolve a conflict, verify auto-navigation to next pending conflict.

### 1.6 Show API error details in toast

- **Files**: `frontend/src/stores/conflicts.ts`, `frontend/src/stores/consensusDiscussion.ts`
- **Problem**: "Failed to resolve conflict" with no detail from API response.
- **Fix**: Parse error response body and include in toast message.
- **Test**: Trigger a validation error, verify error detail is shown.

### Verification (Phase 1)

Manual: navigate the full flow (list -> open conflict -> post comment -> continue discussion -> resolve as exclude -> auto-advance to next).

Verify:
- [x] No "session_id is required" errors (fixed 2026-02-27)
- [x] Exclude resolution with reason works (fixed 2026-02-27)
- [x] Discussion continues after first comment (fixed 2026-02-27)
- [x] Conflict type badge is accurate (fixed 2026-02-27)
- [x] Auto-advances to next conflict (fixed 2026-02-27)
- [x] API errors shown with detail (fixed 2026-02-27)

**Phase 1 completed 2026-02-27.** All 6 bug fixes shipped in commit `aa887e7`.

Run: `docker compose exec web python manage.py test apps.review_results`

---

## Phase 2: Next (UX Improvements)

These make conflict resolution *good*, grounded in the research evidence.

### 2.1 Source material prominence

- Display full snippet
- Make the source URL a prominent "Open in new tab" button

### ~~2.2 Structured criterion prompt~~ -- Dropped

~~Add "Which criterion is in dispute?" dropdown before free-form discussion.~~

**Decision (2026-02-27):** Removed. Set criteria for dispute was deemed too rigid. Instead, criterion tagging moved to individual comments (`ConflictComment.criterion_tag`) as an optional lightweight annotation. The `disputed_criterion` field was added in migration 0017 and removed in migration 0019.

### 2.3 Collegial system copy

- Rewrite labels and prompts to frame as joint investigation (see vision.md copy voice table)
- Replace "Conflict" with "Discussion needed" in reviewer-facing UI
- Add contextual help text: "Most disagreements resolve when both reviewers re-read the abstract together"

### 2.4 Progress bar and batch count

- "Resolving 5 of 23 conflicts" header in conflict resolution view
- Progress bar showing percentage of session conflicts resolved
- Server-side total counts (not client-local page counts)

### 2.5 Configurable time-boxing -- Implemented (Phase 2C)

- [x] SLA fields on `ReviewConfiguration`: `discussion_sla_hours` (72h), `revote_sla_hours` (24h), `arbitration_sla_hours` (48h)
- [x] `sla_reminders_sent` JSONField + `get_sla_info()` method on `ConflictResolution`
- [x] Hourly Celery beat task (`check_conflict_sla_reminders`) sends email reminders at 50% and 90% thresholds
- [x] Amber/red visual indicators in conflict list (left border) and detail view (ring)
- [x] 21 tests across 3 files: `test_conflict_sla.py`, `test_sla_task.py`, `test_review_configuration_sla.py`
- No hard locks -- SLAs are nudges

**Phase 2C completed 2026-02-27.**

### Verification (Phase 2)

- User testing with 2-3 reviewers on a real session
- Measure: time to resolve conflicts, number of back-and-forth comments, reviewer satisfaction
- Compare against Phase 1 baseline

---

## Phase 3: Future (Deep Work)

These require deeper architectural changes or new features.

### 3.1 Mandatory rationale on initial screening decisions

- Add `rationale` TextField to `ReviewerDecision` (and `SimpleReviewDecision`)
- Require non-empty rationale for EXCLUDE decisions (at minimum)
- Optional for INCLUDE (can be made required per-session)
- Rationale displayed automatically in conflict resolution view
- **Impact**: Changes the screening UI for all workflows

### 3.2 Abstract passage annotation

- Allow comments to reference specific passages in the source material
- Highlight mechanism: select text in abstract, anchor comment to selection
- Stored as character offset ranges on `ConflictComment`
- Visual: highlighted passage in abstract linked to discussion thread

### 3.3 Anonymous discussion phase with post-resolution attribution

- During active discussion: comments show "Reviewer A" / "Reviewer B"
- After resolution: comments attributed to actual usernames
- Reduces seniority deference during deliberation
- Maintains full audit trail for reporting

### 3.4 Arbitrator blinding

- When a conflict is escalated, the arbitrator sees decisions and reasoning but not who voted which way
- Requires: separate "arbitrator view" that strips identity from decisions
- `BlindingService` already has infrastructure for this, needs extension

### 3.5 Batch resolution for similar conflicts

- When multiple conflicts share the same criterion tag, offer "Resolve all similar"
- Show a summary: "7 conflicts about Population criterion. Apply same resolution?"
- Each still gets an individual audit record, but the decision is batch-applied
- **Note:** Originally depended on 2.2 (`disputed_criterion`). Now depends on comment-level `criterion_tag` data from `ConflictComment`.

### 3.6 Pattern analysis dashboard

- Aggregate conflict data: "Which criteria cause the most disagreements?"
- Reviewer calibration: "Reviewers A and B disagree 40% of the time on Population"
- Suggested action: "Consider a calibration meeting focused on Population criteria"
- Feeds into PRISMA reporting

---

## Dependencies

```
Phase 1 (bugs) ── COMPLETE (2026-02-27)
     │
     ▼
Phase 2 (UX) ── depends on Phase 1 completion
     │
     ├── 2.1 (source prominence) ── COMPLETE (Phase 2A)
     ├── 2.2 (criterion prompt) ── DROPPED (moved to comment-level tags)
     ├── 2.3 (collegial copy) ── COMPLETE (Phase 2A)
     ├── 2.4 (progress bar) ── COMPLETE (Phase 2A)
     ├── 2.5 (time-boxing) ── COMPLETE (Phase 2C, 2026-02-27)
     │
     ▼
Phase 3 (deep) ── depends on Phase 2 patterns being validated
     │
     ├── 3.1 (rationale) ── enables 3.2 (annotation)
     ├── 3.3 (anonymous) ── extends BlindingService
     ├── 3.5 (batch resolution) ── depends on comment criterion_tag data
     └── 3.6 (patterns) ── depends on comment criterion_tag data
```
