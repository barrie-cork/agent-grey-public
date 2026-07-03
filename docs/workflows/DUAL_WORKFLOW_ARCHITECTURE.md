# Dual-Workflow Architecture: Agent Grey Review System

**Version**: 1.0.0
**Date**: 2025-10-30
**Status**: Active
**Author**: Agent Grey Development Team

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Workflow #1: Work Distribution](#workflow-1-work-distribution-single-reviewer-with-helpers)
3. [Workflow #2: Independent Screening](#workflow-2-independent-screening-multi-reviewer-with-comparison)
4. [Architecture Comparison](#architecture-comparison)
5. [Configuration Guide](#configuration-guide)
6. [Developer Reference](#developer-reference)
7. [Decision Matrix](#decision-matrix)
8. [Migration Guide](#migration-guide)

---

## Executive Summary

Agent Grey supports **two distinct review workflows** designed for different research scenarios:

| Aspect | Workflow #1: Work Distribution | Workflow #2: Independent Screening |
|--------|--------------------------------|-----------------------------------|
| **Purpose** | Divide workload among team | PRISMA 2020/Cochrane compliance |
| **Pattern** | Different results per reviewer | Same results, independent review |
| **Reviewers** | 1 lead + 0-N helpers | 2-3+ independent reviewers |
| **Comparison** | None (results are split) | Yes (automated conflict detection) |
| **UI** | Vue SPA OR Django templates | Django templates + Vue SPA consensus |
| **Model** | `SimpleReviewDecision` | `ReviewerDecision` |
| **Use Case** | Speed, efficiency, large datasets | Quality, consensus, IRR metrics |

**Key Principle**: These workflows are **mutually exclusive** per session. A session uses one workflow or the other, never both simultaneously.

---

## Workflow #1: Work Distribution (Single-Reviewer with Helpers)

### Overview

**Purpose**: Distribute a large result set among team members to complete review faster

**Analogy**: Like dividing a stack of papers among coworkers—each person gets a different pile

**Key Characteristic**: **Results are SPLIT** among reviewers (no overlap)

### When to Use

✅ **Use Workflow #1 when**:
- Large result sets (500+ results) need quick processing
- Team wants to divide workload efficiently
- Review quality managed through other means (spot checks, training)
- No need for inter-rater reliability metrics
- Time constraints require parallel processing

❌ **Don't use Workflow #1 when**:
- Need PRISMA 2020/Cochrane compliance
- Require Cohen's Kappa or IRR metrics
- Need consensus discussion on disagreements
- Quality assurance requires independent verification

### User Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│ WORKFLOW #1: Work Distribution                                  │
└─────────────────────────────────────────────────────────────────┘

1. Lead Reviewer Creates Session
   ├─ Title: "Systematic Review - Obesity Interventions"
   ├─ Total Results: 500
   └─ Configuration:
      ├─ min_reviewers_per_result = 1  ← WORKFLOW #1 TRIGGER
      └─ conflict_resolution_method = N/A (no comparison)

2. Lead Invites Helpers (Optional)
   ├─ Invite: helper1@example.com
   ├─ Invite: helper2@example.com
   └─ System: Creates ReviewInvitation records
      └─ Signal: Creates ReviewerCompletion when accepted

3. Reviewers Claim Work Batches

   Vue SPA Mode (Recommended):
   ┌──────────────────────────────────────┐
   │ WorkQueue.vue                        │
   ├──────────────────────────────────────┤
   │ ⚡ Claim Next 10 Results             │
   │                                      │
   │ Lead:    Claims results 1-10         │
   │ Helper1: Claims results 11-20        │
   │ Helper2: Claims results 21-30        │
   │                                      │
   │ Atomic locking: SELECT FOR UPDATE    │
   │ SKIP LOCKED prevents duplicates      │
   │                                      │
   │ 10-minute timer                      │
   │ Auto-reassign if timeout             │
   └──────────────────────────────────────┘

   Django Template Mode (Alternative):
   ┌──────────────────────────────────────┐
   │ results_overview.html                │
   ├──────────────────────────────────────┤
   │ Shows ALL unreviewed results         │
   │ First-come, first-served             │
   │ No automatic batching                │
   │ Manual pagination (25/50/100)        │
   └──────────────────────────────────────┘

4. Reviewers Submit Decisions
   ├─ Model: SimpleReviewDecision (OneToOne with ProcessedResult)
   ├─ Choices: INCLUDE / EXCLUDE / MAYBE
   ├─ Optional: Exclusion reason, notes
   └─ Signal: Updates ReviewerCompletion.reviewed_results++

5. Progress Tracking
   ├─ ReviewerCompletion model tracks each reviewer:
   │  ├─ Total results: N (varies per reviewer based on claims)
   │  ├─ Reviewed results: X
   │  ├─ Progress: X/N (%)
   │  └─ Completed at: timestamp when finished
   └─ Session Detail Page shows all reviewer progress

6. Individual Completion
   ├─ Each reviewer marks their portion complete independently
   ├─ ReviewerCompletion.completed_at = now
   └─ No waiting for others (no comparison step)

7. Session Completion
   ├─ Lead clicks "Complete Session"
   ├─ Validation: All invited reviewers must be complete
   │  ├─ Blocks if any PENDING invitations exist
   │  └─ Blocks if any ACCEPTED reviewers incomplete
   ├─ No conflict detection (results were split)
   └─ Session.status → 'completed'
      └─ Redirect to reporting/PRISMA export
```

### Technical Architecture

#### Models

**Primary**: `SimpleReviewDecision`
```python
class SimpleReviewDecision(models.Model):
    """OneToOne relationship - each result has exactly one decision."""

    result = models.OneToOneField(
        ProcessedResult,
        on_delete=models.CASCADE,
        related_name='simple_decision'
    )
    session = models.ForeignKey(SearchSession, on_delete=models.CASCADE)
    reviewer = models.ForeignKey(User, on_delete=models.CASCADE)
    decision = models.CharField(
        max_length=10,
        choices=[('include', 'Include'), ('exclude', 'Exclude'), ('maybe', 'Maybe')]
    )
    exclusion_reason = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

**Supporting**: `ReviewerCompletion`
```python
class ReviewerCompletion(models.Model):
    """Tracks invited reviewer progress (Phase 2 - October 2025)."""

    invitation = models.OneToOneField(
        ReviewInvitation,
        on_delete=models.CASCADE,
        related_name='completion_status'
    )
    session = models.ForeignKey(SearchSession, on_delete=models.CASCADE)
    reviewer = models.ForeignKey(User, on_delete=models.CASCADE)
    total_results = models.IntegerField()  # Total results in session
    reviewed_results = models.IntegerField(default=0)  # Count of decisions made
    completed_at = models.DateTimeField(null=True, blank=True)

    @property
    def progress_percentage(self):
        if self.total_results == 0:
            return 0
        return (self.reviewed_results / self.total_results) * 100

    @property
    def is_complete(self):
        return self.completed_at is not None
```

#### Signal Handlers

**Location**: `apps/review_results/signals.py`

**Signal 1**: `create_reviewer_completion_on_acceptance`
```python
@receiver(post_save, sender=ReviewInvitation)
def create_reviewer_completion_on_acceptance(sender, instance, created, **kwargs):
    """Auto-create ReviewerCompletion when invitation accepted."""

    if instance.status != ReviewInvitation.STATUS_ACCEPTED:
        return

    ReviewerCompletion.objects.create(
        invitation=instance,
        session=instance.session,
        reviewer=instance.invitee,
        total_results=instance.session.total_results,
        reviewed_results=0
    )
```

**Signal 2**: `update_reviewer_completion_progress`
```python
@receiver(post_save, sender=SimpleReviewDecision)
def update_reviewer_completion_progress(sender, instance, created, **kwargs):
    """Auto-update progress when decision saved."""

    try:
        completion = ReviewerCompletion.objects.get(
            session=instance.session,
            reviewer=instance.reviewer
        )
    except ReviewerCompletion.DoesNotExist:
        return  # Not an invited reviewer (e.g., session owner)

    # Count total decisions made
    reviewed_count = SimpleReviewDecision.objects.filter(
        session=instance.session,
        reviewer=instance.reviewer
    ).count()

    completion.reviewed_results = reviewed_count

    # Auto-mark complete if all results reviewed
    if reviewed_count >= completion.total_results and completion.total_results > 0:
        if not completion.completed_at:
            completion.completed_at = timezone.now()

    completion.save(update_fields=['reviewed_results', 'completed_at', 'updated_at'])
```

#### UI Components

**Vue SPA** (Recommended):
- **Component**: `frontend/src/views/WorkQueue.vue`
- **Features**:
  - 10-result batch claiming with "Claim Next 10" button
  - Atomic locking via `SELECT FOR UPDATE SKIP LOCKED`
  - 10-minute countdown timer per batch
  - Auto-reassignment on timeout
  - Real-time progress updates
  - Keyboard shortcuts for quick review
  - Offline work support with local storage

**Django Template** (Alternative):
- **Template**: `apps/review_results/templates/review_results/results_overview.html`
- **Features**:
  - List view of all unreviewed results
  - Inline Include/Exclude buttons
  - Bulk actions checkbox
  - Pagination (25/50/100 per page)
  - Notes modal per result
  - Excel export/import for offline work
  - Progress sidebar

#### Validation Rules

**Session Completion** (`apps/review_results/views/legacy_views.py:complete_review_view`):

```python
# Block completion if PENDING invitations exist
pending_invitations = ReviewInvitation.objects.filter(
    session=session,
    status=ReviewInvitation.STATUS_PENDING
)
if pending_invitations.exists():
    messages.error(request, "Cannot complete: pending invitations exist")
    return redirect("review_results:overview", session_id=session_id)

# Block completion if ACCEPTED reviewers haven't finished
accepted_invitations = ReviewInvitation.objects.filter(
    session=session,
    status=ReviewInvitation.STATUS_ACCEPTED
).select_related('invitee')

for invitation in accepted_invitations:
    completion = ReviewerCompletion.objects.get(invitation=invitation)
    if not completion.is_complete:
        messages.error(
            request,
            f"{completion.reviewer.get_full_name()} has not completed their review"
        )
        return redirect("review_results:overview", session_id=session_id)
```

### Advantages

✅ **Speed**: Parallel processing reduces overall time
✅ **Scalability**: Handles large result sets efficiently
✅ **Flexibility**: Can add/remove helpers mid-review
✅ **Simplicity**: No conflict resolution complexity
✅ **Clear Ownership**: Each result has exactly one decision

### Limitations

⚠️ **No Validation**: Single reviewer per result (no verification)
⚠️ **No IRR Metrics**: Cannot calculate Cohen's Kappa
⚠️ **Not PRISMA Compliant**: Doesn't meet dual-screening requirements
⚠️ **Trust Required**: Quality depends on individual reviewer skill

---

## Workflow #2: Independent Screening (Multi-Reviewer with Comparison)

### Overview

**Purpose**: Multiple reviewers independently evaluate the same results for quality assurance and PRISMA 2020/Cochrane compliance

**Analogy**: Like peer review—multiple experts independently evaluate the same paper, then discuss disagreements

**Key Characteristic**: **All reviewers see ALL results** (100% overlap)

### When to Use

✅ **Use Workflow #2 when**:
- PRISMA 2020 or Cochrane methodology compliance required
- Need inter-rater reliability (Cohen's Kappa ≥0.70)
- Quality assurance requires independent verification
- Research requires documented consensus process
- Publication demands methodological rigour
- Systematic review for clinical guidelines or policy

❌ **Don't use Workflow #2 when**:
- Time constraints prevent duplicate review
- Large result sets make dual review impractical
- Quality assurance handled through other means
- IRR metrics not required
- Rapid literature scan (not systematic review)

### User Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│ WORKFLOW #2: Independent Screening (with Comparison)            │
└─────────────────────────────────────────────────────────────────┘

1. Lead Reviewer Creates Session
   ├─ Title: "Systematic Review - Obesity Interventions (PRISMA)"
   ├─ Total Results: 200
   └─ Configuration:
      ├─ min_reviewers_per_result = 2  ← WORKFLOW #2 TRIGGER
      ├─ conflict_resolution_method = CONSENSUS
      ├─ blind_screening_enforced = True
      └─ irr_threshold = 0.70 (Cohen's Kappa)

2. Lead Invites Independent Reviewers
   ├─ Invite: reviewer1@example.com (Primary)
   ├─ Invite: reviewer2@example.com (Secondary)
   ├─ Optional: reviewer3@example.com (Arbitrator)
   └─ System: Creates ReviewInvitation records
      ├─ Signal: Creates ReviewerCompletion when accepted
      └─ Each completion has total_results = 200 (ALL results)

3. Independent Review Phase (BLINDED)

   Django Template Interface:
   ┌──────────────────────────────────────┐
   │ results_overview.html (Multi-Mode)   │
   ├──────────────────────────────────────┤
   │ ⚠️ BLINDED MODE ACTIVE               │
   │                                      │
   │ Showing ALL 200 results              │
   │ Your decisions are hidden from       │
   │ other reviewers until all complete   │
   │                                      │
   │ Progress: 150 / 200 (75%)            │
   │                                      │
   │ Result #1: [Title...]                │
   │ ○ Include  ○ Exclude  ○ Maybe        │
   │                                      │
   │ Result #2: [Title...]                │
   │ ○ Include  ○ Exclude  ○ Maybe        │
   │ ...                                  │
   │                                      │
   │ [Mark My Review Complete]            │
   └──────────────────────────────────────┘

   Both reviewers work independently:
   ├─ Reviewer1: Reviews all 200 results
   │  ├─ Model: ReviewerDecision (many per result)
   │  ├─ Choices: INCLUDE / EXCLUDE / MAYBE
   │  ├─ Confidence: HIGH / MEDIUM / LOW
   │  └─ Signal: Updates ReviewerCompletion progress
   │
   └─ Reviewer2: Reviews all 200 results (same list)
      ├─ Cannot see Reviewer1's decisions (blinded)
      ├─ Model: ReviewerDecision (independent records)
      └─ Signal: Updates ReviewerCompletion progress

4. Individual Completion (with Warning)

   Reviewer1 clicks "Mark My Review Complete":
   ┌──────────────────────────────────────┐
   │ ⚠️ Incomplete Review Warning          │
   ├──────────────────────────────────────┤
   │ You have reviewed 150 of 200 results │
   │                                      │
   │ Are you sure you want to mark your   │
   │ review as complete?                  │
   │                                      │
   │ • Your decisions will be locked      │
   │ • Results compared with other        │
   │   reviewers when all complete        │
   │ • Conflicts may require discussion   │
   │                                      │
   │ [Cancel] [Accept - Mark Complete]    │
   └──────────────────────────────────────┘

   If accepted:
   ├─ ReviewerCompletion.completed_at = now
   ├─ UI shows: "Waiting for other reviewers..."
   └─ Displays other reviewers' progress:
      ├─ Reviewer1: ✅ Complete
      └─ Reviewer2: ⏳ 180 / 200 (90%)

5. Mutual Completion Triggers Comparison

   When BOTH reviewers mark complete:
   ┌──────────────────────────────────────┐
   │ AUTOMATED COMPARISON TRIGGERED        │
   └──────────────────────────────────────┘

   System automatically:
   ├─ 1. Detect Conflicts
   │    ├─ Service: ReviewCoordinationService
   │    ├─ Compare all ReviewerDecision records
   │    └─ Create ConflictResolution for disagreements:
   │       ├─ INCLUDE_EXCLUDE (hardest conflicts)
   │       ├─ EXCLUSION_REASON (different reasons)
   │       └─ LOW_CONFIDENCE (either reviewer unsure)
   │
   ├─ 2. Calculate IRR
   │    ├─ Service: IRRService
   │    ├─ Cohen's Kappa calculation (scikit-learn)
   │    ├─ Create InterRaterReliability record
   │    └─ Alert if Kappa < 0.70 (threshold not met)
   │
   └─ 3. Route to Resolution
        └─ Based on conflict_resolution_method:
           ├─ CONSENSUS → Vue SPA discussion
           ├─ LEAD_ARBITRATION → Lead resolves
           ├─ DESIGNATED_ARBITRATOR → Third party
           └─ MAJORITY → Automatic (if 3+ reviewers)

6. Conflict Resolution

   A. CONSENSUS Method:
   ┌──────────────────────────────────────┐
   │ Redirect to Vue SPA                  │
   │ /screening/?session_id={uuid}        │
   │ #conflicts                           │
   ├──────────────────────────────────────┤
   │ ConflictDiscussion.vue               │
   │                                      │
   │ Conflict #1 of 15                    │
   │                                      │
   │ Result: "Mobile apps for obesity"    │
   │                                      │
   │ Reviewer1: INCLUDE                   │
   │ "Relevant intervention study"        │
   │                                      │
   │ Reviewer2: EXCLUDE                   │
   │ "Conference abstract, not full text" │
   │                                      │
   │ ═══ Threaded Discussion ═══          │
   │                                      │
   │ Reviewer1 (2 min ago):               │
   │ "I see it's an abstract, but the    │
   │  methods are detailed enough..."     │
   │                                      │
   │ Reviewer2 (1 min ago):               │
   │ "Good point. Should we include       │
   │  abstracts if methods clear?"        │
   │                                      │
   │ [Reply] [Propose Re-vote]            │
   │                                      │
   │ After consensus reached:             │
   │ [Mark Resolved: INCLUDE] [EXCLUDE]   │
   └──────────────────────────────────────┘

   B. LEAD_ARBITRATION Method:
   ├─ Lead reviewer sees conflict list
   ├─ Views both decisions (unblinded)
   ├─ Selects final decision
   └─ ConflictResolution.resolution_decision = final choice

   C. DESIGNATED_ARBITRATOR Method:
   ├─ Third party (not original reviewers) assigned
   ├─ Reviews conflict independently (blinded from discussion)
   ├─ Makes final decision
   └─ Higher authority resolution

7. Session Completion
   ├─ All conflicts resolved
   ├─ InterRaterReliability.kappa ≥ 0.70 (or documented reason if lower)
   ├─ Lead clicks "Complete Session"
   └─ Session.status → 'completed'
      └─ PRISMA report includes:
         ├─ Cohen's Kappa score
         ├─ Number of conflicts and resolution method
         ├─ Consensus discussion summary
         └─ Full audit trail (PRISMA 2020 compliant)
```

### Technical Architecture

#### Models

**Primary**: `ReviewerDecision`
```python
class ReviewerDecision(models.Model):
    """
    Immutable audit trail - one decision per (result, reviewer, version).
    Multiple decisions per result allowed (one per reviewer).
    """

    result = models.ForeignKey(
        ProcessedResult,
        on_delete=models.CASCADE,
        related_name='reviewer_decisions'
    )
    reviewer = models.ForeignKey(User, on_delete=models.CASCADE)
    decision = models.CharField(
        max_length=10,
        choices=[('include', 'Include'), ('exclude', 'Exclude'), ('maybe', 'Maybe')]
    )
    confidence = models.CharField(
        max_length=10,
        choices=[('high', 'High'), ('medium', 'Medium'), ('low', 'Low')],
        default='medium'
    )
    exclusion_reason = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    version = models.IntegerField(default=1)  # For revotes
    is_final = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['result', 'reviewer', 'version']]
        indexes = [
            models.Index(fields=['result', 'reviewer']),
            models.Index(fields=['result', 'is_final']),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("ReviewerDecision records are immutable")
        super().save(*args, **kwargs)
```

**Supporting**: `ConflictResolution`
```python
class ConflictResolution(models.Model):
    """Tracks conflicts and their resolution."""

    result = models.ForeignKey(ProcessedResult, on_delete=models.CASCADE)
    session = models.ForeignKey(SearchSession, on_delete=models.CASCADE)

    # Conflicting decisions
    decision_1 = models.ForeignKey(
        ReviewerDecision,
        on_delete=models.CASCADE,
        related_name='conflicts_as_decision_1'
    )
    decision_2 = models.ForeignKey(
        ReviewerDecision,
        on_delete=models.CASCADE,
        related_name='conflicts_as_decision_2'
    )

    conflict_type = models.CharField(
        max_length=20,
        choices=[
            ('INCLUDE_EXCLUDE', 'Include vs Exclude'),
            ('EXCLUSION_REASON', 'Different Exclusion Reason'),
            ('LOW_CONFIDENCE', 'Low Confidence Flag'),
        ]
    )

    status = models.CharField(
        max_length=20,
        choices=[
            ('PENDING', 'Pending Review'),
            ('IN_DISCUSSION', 'Under Discussion'),
            ('ESCALATED', 'Escalated to Arbitrator'),
            ('RESOLVED', 'Resolved'),
        ],
        default='PENDING'
    )

    resolution_method = models.CharField(
        max_length=20,
        choices=[
            ('CONSENSUS', 'Mutual Consensus'),
            ('ARBITRATION', 'Designated Arbitrator'),
            ('MAJORITY', 'Majority Vote'),
            ('SENIOR_OVERRIDE', 'Senior Researcher Override'),
        ]
    )

    resolution_decision = models.CharField(
        max_length=10,
        choices=[('include', 'Include'), ('exclude', 'Exclude'), ('maybe', 'Maybe')],
        blank=True
    )

    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='conflicts_resolved'
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
```

**Supporting**: `ConflictComment`
```python
class ConflictComment(models.Model):
    """Threaded discussion for consensus resolution."""

    conflict = models.ForeignKey(
        ConflictResolution,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies'
    )

    content = models.TextField()  # Markdown support
    content_html = models.TextField(blank=True)  # Cached HTML

    is_deleted = models.BooleanField(default=False)
    is_edited = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

**Supporting**: `InterRaterReliability`
```python
class InterRaterReliability(models.Model):
    """Cohen's Kappa calculation for reviewer pairs."""

    session = models.ForeignKey(SearchSession, on_delete=models.CASCADE)
    reviewer_1 = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='irr_as_reviewer_1'
    )
    reviewer_2 = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='irr_as_reviewer_2'
    )

    cohens_kappa = models.FloatField()  # -1.0 to 1.0
    agreement_percentage = models.FloatField()  # 0-100%

    # Confusion matrix
    both_include = models.IntegerField(default=0)
    both_exclude = models.IntegerField(default=0)
    reviewer1_include_reviewer2_exclude = models.IntegerField(default=0)
    reviewer1_exclude_reviewer2_include = models.IntegerField(default=0)

    calculated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['session', 'reviewer_1', 'reviewer_2']]
```

#### Services

**ReviewCoordinationService** (`apps/review_results/services/review_coordination_service.py`):
```python
class ReviewCoordinationService:
    """Orchestrates multi-reviewer workflow."""

    def detect_conflicts(self, session):
        """
        Compare all ReviewerDecision records for conflicts.

        Returns:
            List[ConflictResolution]: Created conflict records
        """
        conflicts = []
        results = ProcessedResult.objects.filter(session=session)

        for result in results:
            decisions = ReviewerDecision.objects.filter(
                result=result,
                is_final=True
            ).select_related('reviewer')

            if decisions.count() < 2:
                continue  # Need at least 2 decisions to compare

            # Compare pairwise
            for i, dec1 in enumerate(decisions):
                for dec2 in decisions[i+1:]:
                    conflict = self._check_conflict(dec1, dec2)
                    if conflict:
                        conflicts.append(
                            ConflictResolution.objects.create(
                                result=result,
                                session=session,
                                decision_1=dec1,
                                decision_2=dec2,
                                conflict_type=conflict,
                                resolution_method=session.current_configuration.conflict_resolution_method
                            )
                        )

        return conflicts

    def _check_conflict(self, dec1, dec2):
        """Detect conflict type between two decisions."""

        # INCLUDE vs EXCLUDE (hardest conflict)
        if (dec1.decision == 'include' and dec2.decision == 'exclude') or \
           (dec1.decision == 'exclude' and dec2.decision == 'include'):
            return 'INCLUDE_EXCLUDE'

        # Both exclude but different reasons
        if dec1.decision == 'exclude' and dec2.decision == 'exclude':
            if dec1.exclusion_reason != dec2.exclusion_reason:
                return 'EXCLUSION_REASON'

        # Low confidence flag (either reviewer unsure)
        if dec1.confidence == 'low' or dec2.confidence == 'low':
            return 'LOW_CONFIDENCE'

        return None  # No conflict
```

**IRRService** (`apps/review_results/services/irr_service.py`):
```python
from sklearn.metrics import cohen_kappa_score

class IRRService:
    """Calculate inter-rater reliability metrics."""

    def calculate_cohens_kappa(self, session, reviewer1, reviewer2):
        """
        Calculate Cohen's Kappa for reviewer pair.

        Args:
            session: SearchSession
            reviewer1: User
            reviewer2: User

        Returns:
            InterRaterReliability: Created IRR record
        """
        results = ProcessedResult.objects.filter(session=session)

        reviewer1_decisions = []
        reviewer2_decisions = []

        both_include = 0
        both_exclude = 0
        r1_inc_r2_exc = 0
        r1_exc_r2_inc = 0

        for result in results:
            dec1 = ReviewerDecision.objects.filter(
                result=result,
                reviewer=reviewer1,
                is_final=True
            ).first()

            dec2 = ReviewerDecision.objects.filter(
                result=result,
                reviewer=reviewer2,
                is_final=True
            ).first()

            if not dec1 or not dec2:
                continue  # Skip if either reviewer hasn't decided

            # Convert to binary (include=1, exclude=0, maybe=0.5)
            r1_val = 1 if dec1.decision == 'include' else 0
            r2_val = 1 if dec2.decision == 'include' else 0

            reviewer1_decisions.append(r1_val)
            reviewer2_decisions.append(r2_val)

            # Build confusion matrix
            if dec1.decision == 'include' and dec2.decision == 'include':
                both_include += 1
            elif dec1.decision == 'exclude' and dec2.decision == 'exclude':
                both_exclude += 1
            elif dec1.decision == 'include' and dec2.decision == 'exclude':
                r1_inc_r2_exc += 1
            elif dec1.decision == 'exclude' and dec2.decision == 'include':
                r1_exc_r2_inc += 1

        # Calculate Cohen's Kappa using scikit-learn
        kappa = cohen_kappa_score(reviewer1_decisions, reviewer2_decisions)

        # Calculate simple agreement percentage
        total = len(reviewer1_decisions)
        agreements = both_include + both_exclude
        agreement_pct = (agreements / total * 100) if total > 0 else 0

        # Create IRR record
        irr = InterRaterReliability.objects.create(
            session=session,
            reviewer_1=reviewer1,
            reviewer_2=reviewer2,
            cohens_kappa=kappa,
            agreement_percentage=agreement_pct,
            both_include=both_include,
            both_exclude=both_exclude,
            reviewer1_include_reviewer2_exclude=r1_inc_r2_exc,
            reviewer1_exclude_reviewer2_include=r1_exc_r2_inc
        )

        return irr
```

#### UI Components

**Django Template** (Multi-Reviewer Mode):
- **Template**: `apps/review_results/templates/review_results/results_overview.html`
- **Mode Detection**: `session.current_configuration.min_reviewers_per_result >= 2`
- **Features**:
  - Shows ALL results (not paginated splits)
  - Blinding indicator: "Your decisions are hidden"
  - Progress counter: "Reviewed X of Y"
  - Completion warning modal
  - Waiting state UI when complete but others working
  - Reviewer progress list showing who's done

**Vue SPA** (Consensus Discussion):
- **Component**: `frontend/src/views/ConflictDiscussion.vue`
- **Triggered**: When resolution_method = CONSENSUS
- **Features**:
  - Side-by-side decision comparison
  - Threaded comment system (markdown support)
  - Real-time updates via SSE
  - Revote proposal workflow
  - Mark resolved button
  - Conflict navigation (prev/next)

#### Validation Rules

**Completion Warning** (New - To Be Implemented):
```javascript
// When clicking "Mark My Review Complete"
function checkCompletion() {
    const reviewed = {{ my_completion.reviewed_results }};
    const total = {{ my_completion.total_results }};

    if (reviewed < total) {
        // Show warning modal
        $('#incompleteWarningModal').modal('show');
        return false;
    } else {
        // Proceed to mark complete
        submitCompletion();
        return true;
    }
}

// If user clicks "Accept" in warning modal
function submitCompletion() {
    fetch(`/review_results/sessions/{{ session.id }}/complete-my-review/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken')
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'conflicts_detected') {
            // Redirect to Vue SPA consensus
            window.location.href = data.redirect_url;
        } else if (data.status === 'waiting') {
            // Show waiting state
            showWaitingUI();
        } else if (data.status === 'complete') {
            // Session complete, go to reporting
            window.location.href = data.redirect_url;
        }
    });
}
```

**Conflict Detection Trigger** (To Be Implemented):
```python
def mark_reviewer_complete(request, session_id):
    """Mark individual reviewer complete and trigger comparison if all done."""

    # Update ReviewerCompletion
    completion = ReviewerCompletion.objects.get(
        session_id=session_id,
        reviewer=request.user
    )
    completion.completed_at = timezone.now()
    completion.save()

    # Check if all reviewers complete
    all_completions = ReviewerCompletion.objects.filter(session_id=session_id)
    all_complete = all(c.is_complete for c in all_completions)

    if all_complete:
        # Trigger automated comparison
        from apps.review_results.services.review_coordination_service import ReviewCoordinationService
        from apps.review_results.services.irr_service import IRRService

        coordination_service = ReviewCoordinationService()
        conflicts = coordination_service.detect_conflicts(session)

        irr_service = IRRService()
        # Calculate Kappa for all reviewer pairs
        reviewers = list(User.objects.filter(
            id__in=all_completions.values_list('reviewer_id', flat=True)
        ))
        for i, r1 in enumerate(reviewers):
            for r2 in reviewers[i+1:]:
                irr_service.calculate_cohens_kappa(session, r1, r2)

        # Route based on resolution method
        config = session.current_configuration
        if config.conflict_resolution_method == 'CONSENSUS':
            return JsonResponse({
                'status': 'conflicts_detected',
                'conflict_count': len(conflicts),
                'redirect_url': f'/screening/?session_id={session.id}#conflicts'
            })
        else:
            return JsonResponse({
                'status': 'ready_for_arbitration',
                'conflict_count': len(conflicts)
            })
    else:
        # Still waiting for others
        return JsonResponse({
            'status': 'waiting',
            'complete_count': sum(1 for c in all_completions if c.is_complete),
            'total_count': all_completions.count()
        })
```

### Advantages

✅ **Quality Assurance**: Independent verification of decisions
✅ **PRISMA Compliant**: Meets dual-screening requirements
✅ **IRR Metrics**: Cohen's Kappa calculation documented
✅ **Audit Trail**: Complete immutable record of all decisions
✅ **Consensus Process**: Structured discussion for disagreements
✅ **Publication Ready**: Methodological rigour for peer review

### Limitations

⚠️ **Time Intensive**: Each result reviewed multiple times
⚠️ **Resource Heavy**: Requires multiple qualified reviewers
⚠️ **Conflict Resolution**: Discussion can be time-consuming
⚠️ **Not Scalable**: Impractical for very large result sets (>1000)

---

## Architecture Comparison

### Side-by-Side Feature Matrix

| Feature | Workflow #1: Distribution | Workflow #2: Screening |
|---------|---------------------------|------------------------|
| **Result Assignment** | Different per reviewer | Same for all reviewers |
| **Decisions per Result** | 1 (OneToOne) | 2-3+ (many) |
| **Model** | SimpleReviewDecision | ReviewerDecision |
| **Progress Tracking** | ReviewerCompletion ✅ | ReviewerCompletion ✅ |
| **Blinding** | Not applicable | Required (until all complete) |
| **Conflict Detection** | None | Automated |
| **IRR Metrics** | None | Cohen's Kappa |
| **Consensus Discussion** | None | Threaded comments (Vue) |
| **Resolution Methods** | N/A | 4 options (Consensus/Arbitration/Majority/Override) |
| **PRISMA Compliance** | No | Yes |
| **Session Completion** | When all portions done | When all conflicts resolved |
| **UI Options** | Vue SPA OR Django | Django + Vue (hybrid) |
| **Batch Claiming** | 10-result batches (Vue) | Not applicable |
| **Auto-Reassignment** | 10-minute timeout | Not applicable |
| **Revote Workflow** | None | Yes (RevoteProposal) |
| **Email Notifications** | Completion only | Conflicts + IRR alerts + Completion |

### Data Flow Comparison

**Workflow #1** (Linear):
```
Create Session → Invite Helpers → Claim Results → Review → Mark Complete → Session Complete
     ↓              ↓                 ↓              ↓           ↓              ↓
  Config       ReviewInvitation  Atomic Lock   SimpleDecision  Completion  Reporting
 (min=1)       Signal creates    (SKIP LOCKED)   Signal       validation   (PRISMA)
              ReviewerCompletion                updates count
```

**Workflow #2** (Branching):
```
Create Session → Invite Reviewers → Independent Review → Mark Complete → Trigger Comparison
     ↓                ↓                    ↓                   ↓                ↓
  Config         ReviewInvitation     ReviewerDecision    ReviewerCompletion  Compare
 (min≥2)         Signal creates       (many per result)      (all done?)    Decisions
 + method        ReviewerCompletion   + confidence                              ↓
                                                                         ┌────────┴────────┐
                                                                    Conflicts?         No conflicts
                                                                         ↓                  ↓
                                                                  Calculate IRR      Session
                                                                  Create conflicts   Complete
                                                                         ↓
                                                                  Route by method:
                                                                  ├─ CONSENSUS → Vue SPA
                                                                  ├─ ARBITRATION → Lead
                                                                  ├─ MAJORITY → Auto
                                                                  └─ OVERRIDE → Senior
                                                                         ↓
                                                                  All Resolved
                                                                         ↓
                                                                  Session Complete
```

---

## Configuration Guide

### How to Configure Each Workflow

#### Workflow #1: Work Distribution

**Session Setup** (`apps/review_manager/views.py` - Session creation form):

```python
# Django Form
class SessionConfigurationForm(forms.ModelForm):
    class Meta:
        model = ReviewConfiguration
        fields = ['min_reviewers_per_result', ...]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # For work distribution, set min_reviewers = 1
        self.fields['min_reviewers_per_result'].initial = 1
        self.fields['min_reviewers_per_result'].help_text = (
            "Set to 1 for work distribution mode (different results per reviewer). "
            "Set to 2+ for independent screening mode (all reviewers see all results)."
        )
```

**Required Settings**:
```python
{
    'min_reviewers_per_result': 1,  # ← KEY: Triggers Workflow #1
    'conflict_resolution_method': None,  # Not needed
    'blind_screening_enforced': False,  # Not needed
    'irr_threshold': None  # Not needed
}
```

#### Workflow #2: Independent Screening

**Session Setup**:

```python
# Django Form (enhanced with resolution method)
class SessionConfigurationForm(forms.ModelForm):
    class Meta:
        model = ReviewConfiguration
        fields = [
            'min_reviewers_per_result',
            'conflict_resolution_method',
            'blind_screening_enforced',
            'irr_threshold'
        ]

    RESOLUTION_CHOICES = [
        ('CONSENSUS', 'Consensus Discussion - Both reviewers discuss until agreement'),
        ('LEAD_ARBITRATION', 'Lead Arbitration - Lead reviewer makes final decision'),
        ('DESIGNATED_ARBITRATOR', 'Third Party Arbitration - Neutral expert resolves'),
        ('MAJORITY', 'Majority Vote - Requires 3+ reviewers, majority wins'),
    ]

    conflict_resolution_method = forms.ChoiceField(
        choices=RESOLUTION_CHOICES,
        required=True,
        help_text="How should conflicts be resolved?"
    )
```

**Required Settings**:
```python
{
    'min_reviewers_per_result': 2,  # ← KEY: Triggers Workflow #2 (or 3+ for majority)
    'conflict_resolution_method': 'CONSENSUS',  # Choose method
    'blind_screening_enforced': True,  # Hide decisions until all complete
    'irr_threshold': 0.70  # Cohen's Kappa threshold (PRISMA standard)
}
```

### Configuration Migration

**Existing Sessions** (created before dual-workflow implementation):
- Default: `min_reviewers_per_result = 1` (Workflow #1)
- Backward compatible: All existing sessions use SimpleReviewDecision
- No breaking changes

**New Sessions** (post-implementation):
- UI prompts: "What type of review workflow?"
  - **Option A**: Work Distribution (faster, split results)
  - **Option B**: Independent Screening (PRISMA compliant, comparison)
- Based on selection, set `min_reviewers_per_result` appropriately

---

## Developer Reference

### Model Decision Tree

```
┌─────────────────────────────────────────────────────────────────┐
│ Which model should I use for storing decisions?                 │
└─────────────────────────────────────────────────────────────────┘

START: What workflow am I implementing?
   │
   ├─ Workflow #1: Work Distribution
   │  └─ Use: SimpleReviewDecision
   │     └─ Relationship: OneToOne with ProcessedResult
   │        └─ Constraint: Each result has exactly ONE decision
   │
   └─ Workflow #2: Independent Screening
      └─ Use: ReviewerDecision
         └─ Relationship: ForeignKey to ProcessedResult
            └─ Constraint: Each result can have MULTIPLE decisions (one per reviewer)
```

### Service Decision Tree

```
┌─────────────────────────────────────────────────────────────────┐
│ Which service should I call?                                    │
└─────────────────────────────────────────────────────────────────┘

Need to detect conflicts?
└─ ReviewCoordinationService.detect_conflicts(session)
   └─ Compares ReviewerDecision records
   └─ Creates ConflictResolution records
   └─ Only for Workflow #2

Need to calculate IRR?
└─ IRRService.calculate_cohens_kappa(session, reviewer1, reviewer2)
   └─ Uses scikit-learn
   └─ Creates InterRaterReliability record
   └─ Only for Workflow #2

Need to claim work batches?
└─ ReviewClaimService.claim_next_batch(session, reviewer, batch_size=10)
   └─ Atomic locking with SELECT FOR UPDATE SKIP LOCKED
   └─ Creates ReviewerAssignment records
   └─ Only for Workflow #1 (Vue SPA mode)

Need to check completion status?
└─ ReviewerCompletion.objects.get(session=session, reviewer=user)
   └─ Works for BOTH workflows
   └─ Auto-updated by signals
```

### Template Decision Tree

```
┌─────────────────────────────────────────────────────────────────┐
│ Which template/component should I use?                          │
└─────────────────────────────────────────────────────────────────┘

For result review interface:
   │
   ├─ Workflow #1 (Work Distribution)
   │  ├─ Recommended: WorkQueue.vue (Vue SPA)
   │  │  └─ Features: Batch claiming, timer, keyboard shortcuts
   │  └─ Alternative: results_overview.html (Django)
   │     └─ Features: List view, bulk actions, Excel export
   │
   └─ Workflow #2 (Independent Screening)
      └─ Use: results_overview.html (Django) in multi-reviewer mode
         └─ Detection: session.current_configuration.min_reviewers_per_result >= 2
         └─ Shows: ALL results, blinding indicator, completion warning

For conflict resolution:
   │
   ├─ CONSENSUS method
   │  └─ Use: ConflictDiscussion.vue (Vue SPA)
   │     └─ Features: Threaded comments, markdown, SSE updates
   │
   ├─ LEAD_ARBITRATION method
   │  └─ Use: ConflictResolution.vue (Vue SPA)
   │     └─ Features: Side-by-side view, select final decision
   │
   └─ Future: Django template equivalents
      └─ Status: Not yet implemented (Vue SPA required for consensus)
```

### Signal Handler Reference

**Location**: `apps/review_results/signals.py`

| Signal | Sender | Action | Workflow |
|--------|--------|--------|----------|
| `create_reviewer_completion_on_acceptance` | ReviewInvitation | Create ReviewerCompletion | Both |
| `update_reviewer_completion_progress` | SimpleReviewDecision | Update reviewed_results count | Workflow #1 |
| `update_reviewer_completion_progress` | ReviewerDecision | Update reviewed_results count | Workflow #2 |
| `conflict_detected_handler` | ConflictResolution | Send email notification | Workflow #2 |
| `consensus_reached_handler` | ConflictResolution (status→RESOLVED) | Send email notification | Workflow #2 |
| `irr_threshold_check` | InterRaterReliability | Alert if Kappa < threshold | Workflow #2 |

**Note**: The `update_reviewer_completion_progress` signal currently only handles SimpleReviewDecision. It needs enhancement to also handle ReviewerDecision for Workflow #2.

### API Endpoints Reference

**Work Queue** (Workflow #1):
```
POST /api/sessions/{uuid}/claim/
  → Claim next 10 results
  → Returns: ReviewerAssignment records

POST /api/sessions/{uuid}/release/
  → Release claimed results (if can't finish in time)
  → Allows reassignment

POST /api/sessions/{uuid}/decide/
  → Submit SimpleReviewDecision
  → Triggers: update_reviewer_completion_progress signal
```

**Conflict Resolution** (Workflow #2):
```
GET /api/conflicts/?session_id={uuid}
  → List all conflicts for session
  → Pagination, filtering

GET /api/conflicts/{id}/
  → Conflict details with both decisions

POST /api/conflicts/{id}/discuss/
  → Add comment to conflict discussion
  → Body: {content: "markdown text", parent_id: null}

POST /api/conflicts/{id}/resolve/
  → Mark conflict resolved
  → Body: {resolution_decision: "include", resolved_by: user_id}

POST /api/conflicts/{id}/propose-revote/
  → Create RevoteProposal
  → Both reviewers re-evaluate independently
```

---

## Decision Matrix

### When to Use Which Workflow

Use this matrix to select the appropriate workflow:

| Your Scenario | Recommended Workflow | Rationale |
|---------------|---------------------|-----------|
| Large dataset (500+ results), time constraints | **Workflow #1** | Parallel processing speeds up completion |
| PRISMA 2020 systematic review | **Workflow #2** | Methodological requirement |
| Cochrane collaboration review | **Workflow #2** | Gold standard dual-screening |
| Clinical guideline development | **Workflow #2** | Quality assurance critical |
| Scoping review (exploratory) | **Workflow #1** | Speed more important than verification |
| Meta-analysis with strict inclusion | **Workflow #2** | Decision quality paramount |
| Literature scan for internal report | **Workflow #1** | Efficiency over rigour |
| PhD systematic review | **Workflow #2** | Examiner expectations |
| Grant application preliminary review | **Workflow #1** | Quick turnaround needed |
| Publication-ready systematic review | **Workflow #2** | Peer reviewer scrutiny expected |

### Team Composition Scenarios

| Team Size | Skill Level | Recommended Workflow | Configuration |
|-----------|-------------|---------------------|---------------|
| 1 lead + 2 trainees | Mixed | **Workflow #1** | Lead reviews sample for QA |
| 2 experienced researchers | Equal | **Workflow #2** | CONSENSUS method |
| 1 lead + 1 junior | Hierarchical | **Workflow #2** | LEAD_ARBITRATION |
| 3+ equal partners | Equal | **Workflow #2** | MAJORITY vote |
| 1 lead + 4 assistants | Mixed | **Workflow #1** | Split 100 results → 20 each |
| 2 reviewers + 1 senior | Tiered | **Workflow #2** | DESIGNATED_ARBITRATOR |

---

## Migration Guide

### Migrating from Single-Reviewer to Multi-Reviewer

**Scenario**: You started a session with Workflow #1 but now need PRISMA compliance

**Steps**:

1. **Export Current Decisions** (backup):
   ```python
   decisions = SimpleReviewDecision.objects.filter(session=old_session)
   # Export to Excel for reference
   ```

2. **Create New Session** (cannot convert in-place):
   ```python
   new_session = SearchSession.objects.create(
       title=f"{old_session.title} (Multi-Reviewer)",
       owner=old_session.owner,
       # Copy other metadata
   )

   new_config = ReviewConfiguration.objects.create(
       session=new_session,
       min_reviewers_per_result=2,  # ← Switch to Workflow #2
       conflict_resolution_method='CONSENSUS',
       blind_screening_enforced=True,
       irr_threshold=0.70
   )
   ```

3. **Re-Import Results**:
   ```python
   # Copy ProcessedResult records to new session
   for result in ProcessedResult.objects.filter(session=old_session):
       ProcessedResult.objects.create(
           session=new_session,
           title=result.title,
           # Copy all fields
       )
   ```

4. **Invite Reviewers**:
   ```python
   ReviewInvitation.objects.create(
       session=new_session,
       inviter=owner,
       invitee_email='reviewer@example.com',
       # Will trigger ReviewerCompletion creation on acceptance
   )
   ```

5. **Note**: Cannot preserve SimpleReviewDecision records (different model structure)

**Alternative**: If only need IRR metrics, can calculate retroactively if multiple reviewers independently used SimpleReviewDecision on same results (rare scenario).

---

## Appendices

### Appendix A: Model Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    WORKFLOW #1: Work Distribution                │
└─────────────────────────────────────────────────────────────────┘

SearchSession (1) ──────┬──────> ProcessedResult (N)
     │                  │              │
     │                  │              │ OneToOne
     │                  │              ↓
     │                  │        SimpleReviewDecision (1)
     │                  │              │
     │                  │              └─> reviewer: User
     │                  │
     └──> ReviewInvitation (N)
              │
              │ OneToOne (on acceptance)
              ↓
         ReviewerCompletion (N)
              │
              └─> reviewer: User


┌─────────────────────────────────────────────────────────────────┐
│              WORKFLOW #2: Independent Screening                  │
└─────────────────────────────────────────────────────────────────┘

SearchSession (1) ──────┬──────> ProcessedResult (N)
     │                  │              │
     │                  │              │ ForeignKey (many)
     │                  │              ↓
     │                  │        ReviewerDecision (N)
     │                  │         │         │         │
     │                  │         │         │         └─> reviewer: User (R1)
     │                  │         │         └─> reviewer: User (R2)
     │                  │         └─> version: 1, 2, 3... (for revotes)
     │                  │              │
     │                  │              ├─> ConflictResolution (N)
     │                  │              │        │
     │                  │              │        ├─> decision_1: ReviewerDecision
     │                  │              │        ├─> decision_2: ReviewerDecision
     │                  │              │        ├─> status: PENDING/IN_DISCUSSION/RESOLVED
     │                  │              │        ├─> resolution_method: CONSENSUS/ARBITRATION
     │                  │              │        ├─> resolved_by: User
     │                  │              │        │
     │                  │              │        └─> ConflictComment (N) [threaded]
     │                  │              │                 │
     │                  │              │                 ├─> author: User
     │                  │              │                 ├─> parent: ConflictComment (nullable)
     │                  │              │                 └─> content: Markdown
     │                  │              │
     │                  │              └─> RevoteProposal (N)
     │                  │                       ├─> conflict: ConflictResolution
     │                  │                       ├─> status: PROPOSED/IN_PROGRESS/COMPLETED
     │                  │                       └─> links to new ReviewerDecision (version++)
     │                  │
     │                  └──> InterRaterReliability (N)
     │                           ├─> reviewer_1: User
     │                           ├─> reviewer_2: User
     │                           ├─> cohens_kappa: Float
     │                           └─> confusion_matrix: {...}
     │
     └──> ReviewInvitation (N)
              │
              │ OneToOne (on acceptance)
              ↓
         ReviewerCompletion (N)
              │
              └─> reviewer: User
```

### Appendix B: State Machine Diagrams

**Workflow #1** (Simple Linear):
```
Session Created
      ↓
Invitations Sent (optional)
      ↓
Reviewers Claim Results (batches of 10)
      ↓
Reviewers Submit Decisions
      ↓ (Signal updates ReviewerCompletion)
Individual Reviewers Mark Complete
      ↓
All Invited Reviewers Complete?
      ├─ No → Wait
      └─ Yes → Session Complete → Reporting
```

**Workflow #2** (Complex Branching):
```
Session Created (min_reviewers_per_result ≥ 2)
      ↓
Invitations Sent (mandatory)
      ↓
Both Reviewers Accept
      ↓ (Signals create ReviewerCompletion for each)
Independent Blinded Review Phase
      ↓
Reviewer 1 Marks Complete
      ↓
Waiting State (show progress of others)
      ↓
Reviewer 2 Marks Complete
      ↓
ALL COMPLETE → Trigger Comparison
      ↓
ReviewCoordinationService.detect_conflicts()
      │
      ├─ No Conflicts Found
      │  ↓
      │  Calculate IRR (Cohen's Kappa)
      │  ↓
      │  Session Complete → Reporting
      │
      └─ Conflicts Found
         ↓
         Create ConflictResolution records
         ↓
         Calculate IRR (Cohen's Kappa)
         ↓
         Route by resolution_method:
         │
         ├─ CONSENSUS
         │  ↓
         │  Redirect to Vue SPA (ConflictDiscussion.vue)
         │  ↓
         │  Threaded Discussion
         │  ↓
         │  Revote if needed (RevoteProposal)
         │  ↓
         │  Mark Resolved (mutual agreement)
         │  ↓
         │  All Conflicts Resolved? → Session Complete
         │
         ├─ LEAD_ARBITRATION
         │  ↓
         │  Lead Reviews Conflicts (ConflictResolution.vue)
         │  ↓
         │  Lead Selects Final Decision
         │  ↓
         │  All Conflicts Resolved? → Session Complete
         │
         ├─ DESIGNATED_ARBITRATOR
         │  ↓
         │  Escalate to Third Party (blinded)
         │  ↓
         │  Arbitrator Resolves
         │  ↓
         │  All Conflicts Resolved? → Session Complete
         │
         └─ MAJORITY (requires 3+ reviewers)
            ↓
            Auto-resolve based on majority vote
            ↓
            Session Complete
```

### Appendix C: File Locations Quick Reference

**Models**:
- `apps/review_results/models.py:45-95` - SimpleReviewDecision
- `apps/review_results/models.py:246-426` - ReviewerDecision
- `apps/review_results/models.py:428-604` - ConflictResolution
- `apps/review_results/models.py:606-690` - ConflictComment
- `apps/review_results/models.py:772-850` - InterRaterReliability
- `apps/review_results/models.py:1007-1088` - ReviewerCompletion

**Services**:
- `apps/review_results/services/review_coordination_service.py` - Conflict detection
- `apps/review_results/services/irr_service.py` - Cohen's Kappa calculation
- `apps/review_results/services/review_claim_service.py` - Work queue claiming
- `apps/review_results/services/blinding_service.py` - PRISMA blinding

**Signals**:
- `apps/review_results/signals.py:240-303` - create_reviewer_completion_on_acceptance
- `apps/review_results/signals.py:306-384` - update_reviewer_completion_progress
- `apps/review_results/signals.py` (various) - Conflict/IRR notifications

**Views**:
- `apps/review_results/views/legacy_views.py:91-195` - complete_review_view (session completion validation)
- `apps/review_results/views/legacy_views.py` (to be added) - mark_reviewer_complete

**Templates**:
- `apps/review_results/templates/review_results/results_overview.html` - Django template (both workflows)
- `apps/review_results/templates/review_results/dual_screening_spa.html` - Vue SPA entry point

**Vue Components**:
- `frontend/src/views/WorkQueue.vue` - Batch claiming interface (Workflow #1)
- `frontend/src/views/ConflictResolution.vue` - Conflict resolution (Workflow #2)
- `frontend/src/views/ConflictDiscussion.vue` - Consensus discussion (Workflow #2)
- `frontend/src/views/TeamDashboard.vue` - IRR metrics display

**APIs**:
- `apps/review_results/api/conflict_views.py` - Conflict management endpoints
- `apps/review_results/api/core_views.py` - Claim/decide/release endpoints

**Tests**:
- `apps/review_results/tests/test_completion_workflow.py` - Session completion validation
- `apps/review_results/tests/test_completion_signals.py` - ReviewerCompletion signal tests
- `apps/review_results/tests/test_review_coordination_service.py` - Conflict detection tests
- `apps/review_results/tests/test_irr_service.py` - Cohen's Kappa tests

---

## Lead Reviewer Early Conflict Access

### Overview

Session owners (lead reviewers) can view conflict information during the review phase to identify calibration needs early. This feature enables proactive reviewer management while maintaining PRISMA blinding compliance.

### Access Rules

| Role | Conflict List Access | Conflict Details | Other Decisions |
|------|---------------------|------------------|-----------------|
| **Session Owner** (during review) | ✅ YES | ✅ YES (blinded) | ❌ NO (own only) |
| **Session Owner as Arbitrator** | ✅ YES | ✅ YES (full) | ✅ YES |
| **Regular Reviewer** (during review) | ❌ NO | ❌ NO | ❌ NO |
| **Any Reviewer** (after review) | ✅ YES | ✅ YES | ✅ YES |

### Session Owner View (Blinded)

When viewing conflicts during review phase, session owners see:

- **Result title**: Full title of conflicting result
- **Conflict type**: INCLUDE_EXCLUDE, EXCLUSION_REASON, or LOW_CONFIDENCE
- **Own decision**: Their decision (if they reviewed this result)
- **Decision count**: Number of reviewers who decided (e.g., "2 reviewers")
- **Conflict status**: PENDING, IN_DISCUSSION, RESOLVED

Session owners **do NOT** see:
- Other reviewers' decisions
- Other reviewers' names
- Other reviewers' notes

### Arbitrator Exception

If the session owner is also assigned as an **ARBITRATOR** for conflicts, they gain full access to:
- All reviewers' decisions
- All reviewers' notes
- Detailed conflict resolution history

This preserves the existing arbitrator exemption logic.

### Audit Trail

All early conflict access by session owners is logged in `ConflictAccessLog` for compliance auditing.

### Cohen's Kappa Widget

A right-panel widget displays session-wide inter-rater reliability metrics for all reviewers:

**Widget Features**:
- Session-wide average Cohen's Kappa
- Cochrane threshold interpretation:
  - ≥0.70 (Green): Acceptable agreement (PRISMA compliant)
  - 0.40-0.69 (Yellow): Moderate agreement (consider calibration)
  - <0.40 (Red): Poor agreement (calibration required)
- Manual refresh button (AJAX)
- Visible to ALL reviewers (not just session owner)

**API Endpoint**: `/api/sessions/{uuid}/irr-metrics/`
- Permission: `IsAuthenticated` (any reviewer can access)
- Returns session-wide summary (not individual pairs)
- Response format: `{average_kappa, average_agreement, total_pairs, meets_cochrane, ...}`

**Implementation**:
- JavaScript: `apps/review_results/static/review_results/js/kappa_widget.js`
- CSS: `apps/review_results/static/review_results/css/widgets.css`
- Template: `apps/review_results/templates/review_results/results_overview.html`

### Use Cases

1. **Calibration Meetings**: Lead reviewer identifies low Kappa (<0.70) and schedules team calibration
2. **Quality Monitoring**: Session owner detects high conflict rate and investigates
3. **Progress Tracking**: Lead reviews conflict resolution progress without viewing sensitive details

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2025-10-30 | Agent Grey Team | Initial comprehensive documentation |
| 1.1.0 | 2025-11-02 | Agent Grey Team | Added Lead Reviewer Early Conflict Access and Cohen's Kappa Widget documentation |

---

## Feedback & Questions

**Questions about this architecture?**
- Slack: #agent-grey-dev
- Email: dev@agent-grey.example.com
- GitHub: Open issue with label `documentation`

**Found an error?**
- Submit PR with corrections
- Tag with `docs-fix` label

**Need clarification?**
- Create GitHub discussion in `Q&A` category
- Reference section number for faster response

---

**End of Document**
