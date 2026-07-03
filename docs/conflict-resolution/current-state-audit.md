# Current State Audit: Conflict Resolution in Agent Grey

Last audited: 2026-02-27

## Architecture Overview

### Models (`apps/review_results/models.py`)

| Model | Purpose | Status |
|-------|---------|--------|
| `ConflictResolution` | Core conflict record. Status: PENDING/IN_DISCUSSION/ESCALATED/RESOLVED. Links to `ProcessedResult` via FK, conflicting decisions via M2M. | Working |
| `ConflictComment` | Threaded discussion. FK to conflict + author. Supports replies. | Working |
| `RevoteProposal` | Formal re-vote proposal. Status: PROPOSED/ACCEPTED/COMPLETED/EXPIRED. | Working |
| `InDiscussionVote` | Straw poll within discussion. Linked to a ConflictComment. | Working (but can't close from UI) |
| `InDiscussionVoteResponse` | Individual responses to straw polls (INCLUDE/EXCLUDE/MAYBE). | Working |

### Services

| Service | File | Key Methods |
|---------|------|-------------|
| `ReviewCoordinationService` | `services/review_coordination_service.py` | `detect_conflicts()`, `resolve_conflict()`, `get_pending_conflicts()` |
| `BlindingService` | `services/blinding_service.py` | `should_blind()`, `can_view_decision()`, `get_blinding_status()` |

### API Layer (`api/conflict_views.py`)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/conflicts/` | GET | List conflicts (filterable by session, status) |
| `/api/conflicts/{id}/` | GET | Conflict detail with decisions |
| `/api/conflicts/{id}/details/` | GET | Full conflict data including comments and votes |
| `/api/conflicts/{id}/resolve/` | POST | Resolve a conflict (server-authoritative method) |
| `/api/conflicts/{id}/discuss/` | POST | Legacy: add discussion comment |
| `/api/conflicts/{id}/comments/` | POST | Create discussion comment |
| `/api/conflicts/{id}/propose-revote/` | POST | Propose a re-vote |
| `/api/conflicts/{id}/proposals/{id}/accept/` | POST | Accept a re-vote proposal |
| `/api/conflicts/{id}/proposals/{id}/submit-decision/` | POST | Submit re-vote decision |
| `/api/conflicts/{id}/discussion-votes/` | POST | Propose a straw poll |
| `/api/conflicts/{id}/discussion-votes/{id}/respond/` | POST | Respond to a straw poll |
| `/api/conflicts/{id}/escalate/` | POST | Escalate to arbitrator |
| `/api/conflicts/{id}/stream/` | GET | SSE real-time updates |

### Frontend (Vue 3 SPA)

| File | Purpose |
|------|---------|
| `frontend/src/views/ConflictList.vue` | Conflict list with filtering, pagination, summary stats |
| `frontend/src/views/ConflictResolution.vue` | Two-column layout: left (source material + decisions), right (discussion + actions) |
| `frontend/src/stores/conflicts.ts` | Conflict CRUD operations, resolution submission, auto-advance (`getNextPendingConflict`) |
| `frontend/src/stores/consensusDiscussion.ts` | Discussion state, comment submission, straw polls |
| `frontend/src/composables/useConflictSSE.ts` | SSE connection management |
| `frontend/src/lib/errors.ts` | Shared `extractErrorMessage` helper for DRF error response parsing |

### Resolution Methods

Configured per-session in `ReviewConfiguration.conflict_resolution_method`:

| Method | Code | Behaviour |
|--------|------|-----------|
| Consensus | `CONSENSUS` | Threaded discussion until mutual agreement |
| Lead Arbitration | `LEAD_ARBITRATION` | Lead reviewer decides |
| Designated Arbitrator | `DESIGNATED_ARBITRATOR` | Third-party decides (blinded) |
| Majority | `MAJORITY` | Auto-resolves with 3+ reviewers |

## Known Bugs

### Resolved (2026-02-27, commit `aa887e7`)

Bugs 1-6 were fixed in Phase 1. See `implementation-phases.md` for details.

1. ~~`canComment` breaks after first comment~~ -- Extended status check to include `IN_DISCUSSION` and `ESCALATED`
2. ~~Missing exclusion_reason in resolution form~~ -- Added conditional text input (max 100 chars) when EXCLUDE selected
3. ~~session_id lost on navigation after resolution~~ -- All `router.push()` calls now preserve `session_id` query param
4. ~~Hardcoded "Methodological Conflict" badge~~ -- Now uses `formatConflictType(conflict.conflict_type)` with all backend types
5. ~~No auto-advance to next conflict~~ -- Added `getNextPendingConflict()` with auto-navigation after resolution
6. ~~API error details not shown in toast~~ -- Shared `extractErrorMessage` helper parses DRF error responses

### Open

#### 7. Straw poll can't be closed from UI

`InDiscussionVote` has a status field, but there's no UI control or API endpoint to close/finalise a poll.

#### ~~8. pendingCount/resolvedCount are client-local~~ -- Fixed in Phase 2A

Server-side `session_counts` now returned by `ConflictListView` API. Frontend uses these for metrics cards, filter tabs, and progress bar.

## UX Gap Analysis

| Aspect | Current State | Research Best Practice | Gap |
|--------|--------------|----------------------|-----|
| Reasoning capture | Not collected during screening | Mandatory before seeing other's vote | Major |
| Source material | Snippet shown, small, truncated | Full snippet prominently displayed | Moderate |
| Discussion structure | Free-form comment thread | Exclusion-reason-anchored with structured prompts | Major |
| Tone/framing | Neutral/technical labels | Collegial framing ("investigate together") | Minor |
| Auto-advance | Auto-advances to next pending conflict | Auto-advance with progress indicator | ~~Minor~~ Implemented (Phase 2A) |
| Time-boxing | SLA nudges: 72h discuss / 24h re-vote / 48h arbitrate. Email reminders at 50% and 90%. Amber/red visual indicators in conflict list and detail views. | 72h discuss / 24h re-vote / 48h arbitrate (customisable by lead reviewer) | ~~Moderate~~ Implemented (Phase 2C) |
| Batch progress | No indicator | "Discussing 5 of 23 assessments" header | ~~Minor~~ Implemented (Phase 2A) |
| Arbitrator blinding | Arbitrator sees everything | Arbitrator sees reasons, not who voted how | Moderate |

## Test Coverage

36 test files in `apps/review_results/tests/`. Key coverage:
- Conflict detection and resolution service (good)
- Blinding enforcement (good)
- Consensus API endpoints (basic)
- SSE real-time (basic)
- SLA time-boxing: `test_conflict_sla.py` (10 model tests), `test_sla_task.py` (7 task tests), `test_review_configuration_sla.py` (4 config tests)
- Discussion flow end-to-end (missing -- manual testing only)
- Vue component behaviour (no unit tests)

## Files Modified in Recent Bug Fixes (#80-83)

| File | Changes | Issue |
|------|---------|-------|
| `apps/review_results/views/legacy_views.py` | Fixed redirect URLs, added total_results sync, added IRR auto-trigger | #83, #82, #80 |
| `apps/review_manager/signals_denormalized.py` | Added WF2 stats calculation, signal handlers, cascade sync | #81, #82 |
| `apps/review_results/api/dashboard_views.py` | Added POST IRR trigger endpoint | #80 |
| `apps/review_results/api/urls.py` | Added irr-calculate URL pattern | #80 |
| `apps/review_results/static/review_results/js/kappa_widget.js` | Rewritten for POST+poll pattern | #80 |

## Files Modified in Phase 1 Bug Fixes (#85, #87)

| File | Changes |
|------|---------|
| `frontend/src/stores/consensusDiscussion.ts` | Fixed `canComment` status check, `extractErrorMessage` for all error handlers |
| `frontend/src/views/ConflictResolution.vue` | Exclusion reason field, session_id preservation, dynamic badge, auto-advance, error detail toasts |
| `frontend/src/stores/conflicts.ts` | Added `getNextPendingConflict()`, `extractErrorMessage` for error handlers |
| `frontend/src/types/index.ts` | Added `exclusion_reason` to `ResolveConflictInput` |
| `frontend/src/lib/errors.ts` | **New file**: shared `extractErrorMessage` helper |
