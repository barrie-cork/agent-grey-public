# Review Results App

Dual-workflow review system for include/exclude decisions on processed grey literature results.

## Models (14)

| Model | Workflow | Purpose |
|-------|----------|---------|
| `SimpleReviewDecision` | #1 | OneToOne with ProcessedResult, single reviewer decision |
| `ReviewerDecision` | #2 | Many-per-result, versioned audit trail (`save()` override enforces immutability, `allow_update=True` required) |
| `ReviewerAssignment` | #2 | Tracks reviewer-to-result assignments |
| `ConflictResolution` | #2 | Conflict records between reviewers, supports revote proposals and discussion. `sla_reminders_sent` JSONField tracks sent thresholds. `get_sla_info()` computes deadline/urgency from `ReviewConfiguration` SLA fields |
| `ConflictComment` | #2 | Discussion thread on conflict resolutions |
| `RevoteProposal` | #2 | Proposal + acceptance tracking for revotes |
| `InDiscussionVote` | #2 | Straw poll proposals within conflict discussions (linked to a comment) |
| `InDiscussionVoteResponse` | #2 | Individual votes on straw polls (Include/Exclude/Maybe) |
| `InterRaterReliability` | #2 | Cohen's Kappa calculations per session |
| `ReviewerCompletion` | Both | Per-reviewer progress tracking (owner record created on `ready_for_review`) |
| `ReviewSession` | Both | Links review activity to a session |
| `ResultSkip` | #1 | Tracks skipped results |
| `URLAccessLog` | Both | Logs URL access during review (PRISMA compliance) |
| `ConflictAccessLog` | #2 | Logs conflict page access |

## Services (10)

| Service | Workflow | Key Methods |
|---------|----------|-------------|
| `ManualResultService` | Both | `add_manual_result` (validates session state, checks URL uniqueness, creates `ProcessedResult` with provenance, increments `ReviewerCompletion.total_results` for WF2) |
| `ReviewClaimService` | #1 | `claim_next_result` (atomic `SELECT FOR UPDATE SKIP LOCKED`), `release_claim`, `skip_result`, `get_assigned_results` |
| `BlindingService` | #2 | `should_blind`, `can_view_decision`, `filter_decisions_for_user`, `get_blinding_status` |
| `ReviewCoordinationService` | #2 | `submit_reviewer_decision`, `detect_conflicts`, `resolve_conflict`, `get_pending_conflicts` |
| `InterRaterReliabilityService` | #2 | `calculate_cohens_kappa`, `calculate_percentage_agreement`, `get_irr_metrics`, `get_per_reviewer_breakdown` |
| `ReviewService` | Both | `get_review_stats`, `get_filtered_results`, `get_processing_stats` |
| `SimpleReviewProgressService` | #1 | Progress tracking for single-reviewer workflow |
| `EmailNotificationService` | #2 | Email alerts for conflicts, IRR threshold, consensus reached, SLA reminders (50%/90% thresholds) |
| `ReviewCacheManager` | Both | Cache layer for review data |
| `SimpleExportService` | #1 | Export review data |

## API Layer (`api/`)

### Access control (GH #230)
All session-scoped endpoints resolve the session via `get_validated_session` /
`get_validated_result` / `get_validated_conflict` in `api/utils.py`. Access is
**hybrid**, set per endpoint via the `allow_roles` parameter on those helpers:

- **Screening** (work queue, claim, decide, release, result detail, manual add,
  blinding status) = **participation only**: session owner or accepted-invitation
  reviewer (`check_session_access`). No `allow_roles`. Bare org membership grants
  nothing -- this closes the read leak AND the claim->submit write leak.
- **Conflict oversight** (list, detail, resolve, discuss, comment, discussion
  detail) = participation OR `allow_roles=[CONFLICT_VIEW]`; the action itself is
  then gated by the endpoint's secondary check (`CONFLICT_RESOLVE` to resolve,
  `is_conflicting_reviewer`/`CONFLICT_COMMENT` to comment).
- **Conflict participation** (escalate, revote propose/accept/submit, straw polls)
  = participation only + `is_conflicting_reviewer` (conflicting reviewers are
  always participants).
- **Dashboards / IRR** = participation OR `allow_roles=[REVIEW_CREATE,
  CONFLICT_VIEW]`, plus the existing `_has_dashboard_access` role gate.

The old org-membership "fast path" is gone; `_has_session_access` now matches
`check_session_access` plus the opt-in role tier. Tests make a reviewer a real
participant with `apps.core.tests.utils.make_session_participant(session, user)`.

### `core_views.py` -- Work Queue & Manual Addition (Both Workflows)
- `AddManualResultView` (POST) -- add manually discovered result during screening (validates session state, deduplicates URL, returns 201/400/409)
- `ClaimResultView` (POST) -- atomic claim next result
- `SubmitDecisionView` (POST) -- submit include/exclude/maybe decision
- `release_result` -- release a claimed result
- `get_result_detail` -- single result with metadata
- `get_work_queue` -- session-scoped paginated work queue with computed per-result status (`pending`/`claimed_by_me`/`decided_by_me`/`conflict`). Requires `session_id` query param. Supports `status` filter and `page`/`per_page` pagination.
- `get_blinding_status` -- blinding state for session

### `conflict_views/` (package) -- Conflict Resolution (Workflow #2)
Split into `resolution_views` (list/detail/resolve/escalate/discuss), `revote_views` (comments + revote flow) and `discussion_vote_views` (straw polls); all re-exported from `conflict_views/__init__.py`, so `conflict_views.X` in `api/urls.py` is unchanged.
- `ConflictListView` -- list all conflicts for session
- `ConflictDetailView` -- single conflict with decisions and comments
- `ResolveConflictView` -- resolve a conflict; resolution method is server-authoritative from `ReviewConfiguration.conflict_resolution_method` (client sends `decision` + optional `exclusion_reason` + optional `resolution_notes`; `exclusion_reason` required when decision is EXCLUDE). Org/conflict checks run before input validation (404/403/409 take priority over 400).
- `ConflictCommentCreateView` -- add discussion comment
- `ProposeRevoteView` / `AcceptRevoteView` / `SubmitRevoteDecisionView` -- revote flow
- `ProposeDiscussionVoteView` (POST) / `RespondToDiscussionVoteView` (POST) -- straw poll flow within conflict discussions

### `dashboard_views.py` -- Team Dashboard (Workflow #2)
- `get_team_stats` -- overview statistics
- `get_irr_metrics` -- Cohen's Kappa and agreement metrics
- `get_reviewer_progress` -- per-reviewer progress breakdown
- `get_session_irr_metrics` -- session-level IRR

### `sse_views.py` -- Real-time
- `conflict_discussion_stream` -- SSE for live conflict discussion updates (events: new comments, revote proposals, consensus reached, `discussion_vote_updated`)

## Django Template Views (`views/`)

| View | Purpose |
|------|---------|
| `ResultsReviewView` | Main review page: auto-transition, status filtering, workflow2 completion tracking. Sidebar shows conflict navigation card (WF2, pending conflicts > 0) linking to `/screening/conflicts?session_id=<uuid>` |
| `FilteredResultsView` | Filtered/duplicate results transparency view |
| `BulkResetReviewsView` | Bulk reset reviews (POST) |
| `SearchStatisticsView` | Per-session search statistics |

`views/api_views/` is a package (AJAX/JSON endpoints): `decision_views`, `queue_views`, `conflict_api_views`, all re-exported from `views/api_views/__init__.py`. Owner-or-invited session access uses `apps.review_manager.access.check_session_access` (shared with reporting; re-exported from `views/mixins.py` for back-compat). The "active decision for a result+reviewer" query is `ReviewerDecision.objects.active_for(result, reviewer)` (excludes revotes).

## Signals (`signals.py`)

| Handler | Trigger |
|---------|---------|
| `conflict_detected_handler` | `m2m_changed` on `conflicting_decisions.through` (`post_add`) -- notifies after decisions linked |
| `consensus_reached_handler` | All reviewers agree |
| `irr_threshold_check` | IRR recalculation after decisions |
| `review_completion_handler` | Review session completion |
| `create_reviewer_completion_on_acceptance` | Invitation accepted -- creates ReviewerCompletion |
| `create_owner_completion_on_ready_for_review` | Session reaches `ready_for_review` -- creates owner record |
| `update_reviewer_completion_progress` | New decision -- updates progress |

## Workflow Code Patterns

### Workflow #1 (Work Distribution)

```python
from apps.review_results.models import SimpleReviewDecision, ReviewerCompletion
from apps.review_results.services.review_claim_service import ReviewClaimService

# Claim batch (atomic, race-condition-free via SELECT FOR UPDATE SKIP LOCKED)
service = ReviewClaimService()
assignments = service.claim_next_batch(session=session, reviewer=reviewer, batch_size=10)

# Submit decision (OneToOne with result)
decision = SimpleReviewDecision.objects.create(
    result=result, reviewer=reviewer,
    decision='INCLUDE',  # or EXCLUDE, MAYBE
    exclusion_reason='Not relevant' if decision == 'EXCLUDE' else ''
)
# Progress auto-tracked via signal (update_reviewer_completion_progress)
```

### Workflow #2 (Independent Screening)

```python
from apps.review_results.models import ReviewerDecision, ConflictResolution
from apps.review_results.services.review_coordination_service import ReviewCoordinationService
from apps.review_results.services.blinding_service import BlindingService

# Submit blinded decision (many per result -- immutable)
decision = ReviewerDecision.objects.create(
    result=result, reviewer=reviewer,
    decision='INCLUDE',  # or EXCLUDE, MAYBE, ABSTAIN
    confidence_level=3,  # 1=Low, 2=Medium, 3=High
    exclusion_reason='Wrong population' if decision == 'EXCLUDE' else '',
    is_blinded=True  # Enforced until all reviewers complete
)
# When all complete (auto-triggered by signal):
# 1. Conflict detection  2. Cohen's Kappa  3. Email notifications
```

### Blinding Rules

Own decisions always visible. Others' decisions blinded until ALL complete. Arbitrators always unblinded. Use `BlindingService.can_view_decision(session, reviewer, target_reviewer)` (static method).

### Conflict Resolution Methods (Workflow #2 Only)

| Method | Resolution | Auto-Resolves? |
|--------|-----------|----------------|
| CONSENSUS | Threaded discussion to mutual agreement | No |
| LEAD_ARBITRATION | Lead reviewer selects final decision | No |
| DESIGNATED_ARBITRATOR | Third-party arbitrator decides (blinded) | No |
| MAJORITY | Automatic majority vote (3+ reviewers) | Yes |

## Tests (48 files)

Key test areas: concurrency (`test_concurrency.py`), blinding enforcement, N+1 queries, dual screening E2E, consensus API, email delivery integration, per-reviewer breakdown, IRR service, completion workflow, SLA time-boxing (`test_conflict_sla.py`, `test_sla_task.py`).

```bash
docker compose exec web python manage.py test apps.review_results
```
