# WF2 Hybrid Lifecycle E2E Test Plan

## Overview

End-to-end test that exercises the complete dual-screening lifecycle using a hybrid seeded+UI approach: session seeded at `ready_for_review` with pending invitations, invitation acceptance via real UI, blinded screening with deliberate disagreements, discussion-based conflict resolution, session completion with IRR metrics, and PRISMA/audit trail reporting.

## Test File

`tests/e2e/workflows/wf2-lifecycle.workflow.spec.ts`

## Approach

**Hybrid seeded+UI strategy** (refactored from #91, replacing #90):
- **Seed**: `setup_e2e_session --state ready_for_review --workflow 2 --pending-invitations --num-results 10` creates a session with 10 results and pending reviewer invitations, bypassing the unreliable auto-transition chain
- **UI**: Invitation acceptance via magic link (real browser flow)
- **API**: Screening decisions, conflict resolution, mark-complete (faster and more reliable than UI clicks)
- **UI + API**: Reporting dashboard navigation + API endpoint verification

This eliminates the SERP dependency and auto-transition chain reliability issues that caused 18 cascade-skips in the original UI-driven approach.

**Serial test mode**: `test.describe.configure({ mode: 'serial' })` -- state accumulates across tests. Must run with `--workers=1`.

**Two test users**:
- `e2e-owner@test.local` (LEAD_REVIEWER) -- session owner, lead reviewer
- `e2e-reviewer1@test.local` (REVIEWER) -- supporting reviewer, invited via magic link

## Phases

### Seed (beforeAll)
- Seeds session via `setup_e2e_session` management command
- Extracts `SESSION_ID` and `INVITATION_TOKEN` from command output
- Session is at `ready_for_review` with 10 processed results and pending invitations

### Phase 3: Invitation Acceptance (~2 tests)
- Verify 10 results are available from seeding
- Reviewer1 accepts invitation via magic link URL (real UI flow)

### Phase 4: Independent Screening (~3 tests)
- Lead screens all results: 100% INCLUDE (via API `POST /api/results/{id}/decide/`)
- Reviewer1 screens: ~70% INCLUDE, ~30% EXCLUDE (creates deliberate disagreements)
- Both mark complete via `POST /review-results/mark-complete/{id}/`
- Conflict detection triggers automatically

### Phase 5: Conflict Resolution (~4 tests)
- Verify conflicts listed via `GET /api/conflicts/?session_id={id}`
- Lead posts discussion comment via `POST /api/conflicts/{id}/comments/`
- Reviewer1 replies
- Admin resolves all conflicts via `POST /api/conflicts/{id}/resolve/` (DRF) or session owner via legacy endpoint

### Phase 6: Session Completion (~3 tests)
- Navigate to completion page
- Verify IRR metrics endpoint responds
- Verify team dashboard stats available

### Phase 7: Reporting (~5 tests)
- Reporting dashboard accessible
- PRISMA flow API returns structured data
- Report generation page accessible
- Audit trail CSV downloadable with correct Content-Type
- IRR report page accessible

## Helper Functions

`tests/e2e/workflows/helpers/wf2-helpers.ts`:

| Function | Purpose |
|----------|---------|
| `submitWf2Decision()` | POST /api/results/{id}/decide/ |
| `postConflictComment()` | POST /review-results/api/conflicts/{id}/discuss/ |
| `resolveConflictLegacy()` | POST /review-results/api/conflicts/{id}/resolve/ (session owner) |
| `resolveConflictDrf()` | POST /api/conflicts/{id}/resolve/ (requires CONFLICT_RESOLVE) |
| `getResultIds()` | GET /api/results/queue/?session_id={id} |
| `getConflictIds()` | GET legacy + DRF conflict list |
| `markReviewerComplete()` | POST /review-results/mark-complete/{id}/ with CSRF |
| `getSessionStatus()` | GET /sessions/api/session/{id}/status/ |
| `pollSessionStatus()` | Poll until expected status or timeout |

## API Endpoints Reference

| Action | Method | URL | Body |
|--------|--------|-----|------|
| Submit decision | POST | `/api/results/{resultId}/decide/` | `{ decision, exclusion_reason?, notes?, confidence_level? }` |
| Work queue | GET | `/api/results/queue/?session_id={id}&per_page=100` | -- |
| List conflicts | GET | `/api/conflicts/?session_id={id}` | -- |
| Post comment | POST | `/api/conflicts/{id}/comments/` | `{ comment }` |
| Resolve conflict | POST | `/api/conflicts/{id}/resolve/` | `{ decision, resolution_notes?, exclusion_reason? }` |
| Mark complete | POST | `/review-results/mark-complete/{sessionId}/` | CSRF form |
| Session status | GET | `/sessions/api/session/{id}/status/` | -- |
| IRR metrics | GET | `/api/sessions/{id}/irr-metrics/` | -- |
| PRISMA flow | GET | `/reporting/api/session/{id}/prisma/flow/` | -- |
| Audit trail | GET | `/reporting/sessions/{id}/audit-trail/` | -- |
| IRR report | GET | `/reporting/sessions/{id}/irr-report/` | -- |

## Running

```bash
# Prerequisites
docker compose up -d
docker compose exec agent-grey python manage.py create_e2e_users

# Run WF2 lifecycle test only
npx playwright test tests/e2e/workflows/wf2-lifecycle.workflow.spec.ts \
  --project=chromium --workers=1 --timeout=300000

# Run full suite including WF2 lifecycle
npx playwright test tests/e2e/workflows/ --project=chromium --workers=1
```

## Known Issues and Risks

| Risk | Mitigation |
|------|-----------|
| Docker not running | `beforeAll` seed fails fast with clear error |
| CSRF on form POSTs | `markReviewerComplete()` reads csrftoken cookie |
| Report generation is async (Celery) | Tolerate non-200 responses gracefully |
| Invitation already accepted | Test checks for error content and warns |

## Test Results

### 2026-03-07 (hybrid refactor)

Refactored from UI-driven to hybrid seeded+UI approach (issue #91). Previous 18 cascade-skips eliminated by seeding session data instead of depending on real SERP execution.

| Phase | Tests | Expected Result |
|-------|-------|-----------------|
| Seed | beforeAll | Session seeded with 10 results + pending invitation |
| Phase 3 | 2 | PASS (results verified + invitation accepted) |
| Phase 4 | 3 | PASS (screening + conflict detection) |
| Phase 5 | 4 | PASS (discussion + resolution) |
| Phase 6 | 3 | PASS (completion + IRR) |
| Phase 7 | 5 | PASS (reporting + audit trail) |
| **Total** | **17** | **17 pass, 0 skip** |

### 2026-02-27 (original baseline)

| Phase | Tests | Result | Notes |
|-------|-------|--------|-------|
| Phase 1 | 2 | PASS | Session creation + WF2 config works via UI |
| Phase 2 | 3 | 1 PASS, 1 SKIP, 1 PASS | Strategy save works but auto-transition timed out; 0 results returned |
| Phase 3-7 | 17 | SKIP | Cascading skip due to 0 results |
| **Total** | **22** | **4 pass, 18 skip** | Auto-transition was the blocker |
