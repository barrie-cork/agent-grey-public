# Migrating to Dual-Workflow Review System

**Version**: 1.0.0
**Date**: November 2025
**Audience**: System Administrators, Session Owners, Technical Users

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Migration Scenarios](#migration-scenarios)
4. [Step-by-Step Migration Guide](#step-by-step-migration-guide)
5. [Data Migration Scripts](#data-migration-scripts)
6. [Validation and Testing](#validation-and-testing)
7. [Rollback Plan](#rollback-plan)
8. [Troubleshooting](#troubleshooting)

---

## Overview

### What Changed?

The dual-workflow feature introduces two distinct review modes:

**Before** (Legacy):
- All sessions used `SimpleReviewDecision` model
- Single-reviewer mode only
- No conflict detection or IRR metrics

**After** (November 2025):
- **Workflow #1**: Work Distribution (same as legacy, backward compatible)
- **Workflow #2**: Independent Screening (new PRISMA 2020 compliance mode)
- Configuration-driven workflow selection via `ReviewConfiguration.min_reviewers_per_result`

### Backward Compatibility

✅ **All existing sessions continue to work** without modification
✅ Legacy `SimpleReviewDecision` data is preserved
✅ No breaking changes to Workflow #1 (work distribution)
✅ New sessions can choose either workflow at creation time

---

## Prerequisites

### System Requirements

- Agent Grey version ≥ 2.0.0 (November 2025 release)
- Django 5.1.13 LTS
- PostgreSQL 15
- scikit-learn 1.3.2 (for Cohen's Kappa calculation)
- Vue 3.5.22 + TypeScript 5.7.3 (for consensus discussion UI)

### Database Migrations

**Required Migrations** (auto-applied during deployment):

```bash
# Review these migrations before deploying
apps/review_manager/migrations/0015_reviewconfiguration_enhancements.py
apps/review_results/migrations/0009_reviewerdecision_conflict_models.py
apps/review_results/migrations/0010_interraterreliability.py
```

**What They Add**:
- `ReviewConfiguration.conflict_resolution_method` field
- `ReviewConfiguration.blind_screening_enforced` field
- `ReviewConfiguration.irr_threshold` field
- `ReviewerDecision` model (for Workflow #2)
- `ConflictResolution` model
- `ConflictComment` model
- `InterRaterReliability` model

### Deployment Checklist

Before deploying dual-workflow feature:

- [ ] Database backup completed
- [ ] Migrations reviewed and tested in staging
- [ ] Vue SPA frontend compiled: `npm run build`
- [ ] Static files collected: `python manage.py collectstatic`
- [ ] Docker images rebuilt: `docker compose build --no-cache web`
- [ ] Celery workers restarted (for signal handlers)
- [ ] Email backend configured (for conflict notifications)

---

## Migration Scenarios

### Scenario 1: Existing Sessions (No Action Needed)

**Situation**: You have ongoing sessions created before November 2025

**Action**: ✅ **None required**

**Behavior**:
- Sessions continue using Workflow #1 (work distribution)
- `ReviewConfiguration.min_reviewers_per_result` defaults to `1`
- `SimpleReviewDecision` model continues to work
- No conflict detection or IRR calculation
- Review process unchanged

**Validation**:
```bash
# Check existing sessions still work
docker compose exec web python manage.py shell
>>> from apps.review_manager.models import SearchSession
>>> session = SearchSession.objects.first()
>>> print(session.current_configuration.min_reviewers_per_result)
1  # Confirms Workflow #1
```

### Scenario 2: New Sessions (Choose Workflow)

**Situation**: Creating a new session after November 2025 deployment

**Action**: Select workflow during session creation

**Workflow #1** (Work Distribution):
```python
ReviewConfiguration.objects.create(
    session=new_session,
    min_reviewers_per_result=1,  # ← Workflow #1 trigger
    # Conflict fields not needed
)
```

**Workflow #2** (Independent Screening):
```python
ReviewConfiguration.objects.create(
    session=new_session,
    min_reviewers_per_result=2,  # ← Workflow #2 trigger
    conflict_resolution_method='CONSENSUS',
    blind_screening_enforced=True,
    irr_threshold=0.70  # PRISMA 2020 standard
)
```

### Scenario 3: Convert Workflow #1 to Workflow #2

**Situation**: You started with Workflow #1 but now need PRISMA compliance

**Limitation**: ⚠️ **Cannot convert in-place**. Must create new session.

**Reason**: Different data models (`SimpleReviewDecision` vs `ReviewerDecision`) and review semantics (split results vs all reviewers see all results).

**Workaround**: Use data migration script (see below).

---

## Step-by-Step Migration Guide

### Migrating from Workflow #1 to Workflow #2

**Use Case**: You completed initial screening with Workflow #1 (work distribution), but now need PRISMA 2020 compliance with dual-screening and IRR metrics for publication.

#### Step 1: Export Existing Decisions

```bash
# Export current decisions to CSV for reference
docker compose exec web python manage.py shell

>>> from apps.review_results.models import SimpleReviewDecision
>>> import csv
>>> decisions = SimpleReviewDecision.objects.filter(session_id='OLD_SESSION_UUID')
>>>
>>> with open('/tmp/exported_decisions.csv', 'w') as f:
...     writer = csv.DictWriter(f, fieldnames=['result_id', 'decision', 'reviewer', 'notes'])
...     writer.writeheader()
...     for dec in decisions:
...         writer.writerow({
...             'result_id': str(dec.result.id),
...             'decision': dec.decision,
...             'reviewer': dec.reviewer.email,
...             'notes': dec.notes
...         })
>>> print(f"Exported {decisions.count()} decisions")
```

Download exported file:
```bash
docker cp web:/tmp/exported_decisions.csv ./exported_decisions.csv
```

#### Step 2: Create New Session with Workflow #2 Configuration

```python
from apps.review_manager.models import SearchSession, ReviewConfiguration
from django.contrib.auth import get_user_model

User = get_user_model()
old_session = SearchSession.objects.get(id='OLD_SESSION_UUID')

# Create new session
new_session = SearchSession.objects.create(
    title=f"{old_session.title} (Dual-Screening)",
    description=f"PRISMA 2020 compliant re-screening of: {old_session.description}",
    owner=old_session.owner,
    organization=old_session.organization,
    status='draft'
)

# Configure for Workflow #2
new_config = ReviewConfiguration.objects.create(
    session=new_session,
    min_reviewers_per_result=2,  # Dual-screening
    conflict_resolution_method='CONSENSUS',
    blind_screening_enforced=True,
    irr_threshold=0.70
)

print(f"Created new session: {new_session.id}")
```

#### Step 3: Copy Results to New Session

```python
from apps.results_manager.models import ProcessedResult

old_results = ProcessedResult.objects.filter(session=old_session)

for result in old_results:
    ProcessedResult.objects.create(
        session=new_session,
        title=result.title,
        snippet=result.snippet,
        url=result.url,
        source=result.source,
        search_query=result.search_query,
        # Copy all other fields
        duplicate_of=result.duplicate_of,
        is_excluded_by_rule=result.is_excluded_by_rule,
        # ...
    )

print(f"Copied {old_results.count()} results to new session")
```

#### Step 4: Invite Independent Reviewers

```python
from apps.review_manager.models import ReviewInvitation

# Invite primary reviewer
ReviewInvitation.objects.create(
    session=new_session,
    inviter=new_session.owner,
    invitee_email='reviewer1@example.com',
    role='PRIMARY',
    message='Please independently review all results for PRISMA compliance.'
)

# Invite secondary reviewer
ReviewInvitation.objects.create(
    session=new_session,
    inviter=new_session.owner,
    invitee_email='reviewer2@example.com',
    role='SECONDARY',
    message='Please independently review all results for PRISMA compliance.'
)

print("Invitations sent. Reviewers will receive magic link emails.")
```

#### Step 5: Execute Search (Copy Search Strategy)

```python
from apps.search_strategy.models import SearchStrategy

old_strategy = old_session.search_strategy

new_strategy = SearchStrategy.objects.create(
    session=new_session,
    population_terms=old_strategy.population_terms,
    interest_terms=old_strategy.interest_terms,
    context_terms=old_strategy.context_terms,
    # Copy all other fields
)

# Update session
new_session.search_strategy = new_strategy
new_session.save()

print("Search strategy copied. Ready to execute.")
```

#### Step 6: Transition Session to Ready for Review

```python
# Skip search execution if results already copied
new_session.status = 'ready_for_review'
new_session.save()

print(f"Session {new_session.id} ready for independent dual-screening")
```

#### Step 7: Inform Reviewers

Send email to reviewers with instructions:

```
Subject: New Dual-Screening Session Ready - {session.title}

Dear Reviewer,

A new session is ready for PRISMA 2020 compliant dual-screening:

Session: {new_session.title}
Session ID: {new_session.id}
Total Results: {result_count}

Instructions:
1. Click the magic link in your invitation email
2. Independently review ALL {result_count} results
3. Do NOT discuss decisions with other reviewers until both complete
4. Mark your review complete when finished
5. System will automatically detect conflicts and prompt for consensus discussion

IRR Target: Cohen's Kappa ≥ 0.70

Access: {session_url}

Questions? Reply to this email.

Best regards,
{session.owner.get_full_name()}
```

#### Step 8: Archive Old Session

```python
old_session.status = 'archived'
old_session.save()

print(f"Old session {old_session.id} archived. Do not delete (maintains audit trail).")
```

---

## Data Migration Scripts

### Script 1: Bulk Export Decisions

Save as `scripts/export_session_decisions.py`:

```python
#!/usr/bin/env python
"""Export session decisions to CSV for migration."""

import csv
import sys
from pathlib import Path
from apps.review_results.models import SimpleReviewDecision

def export_decisions(session_id, output_path):
    """Export all decisions for a session to CSV."""
    decisions = SimpleReviewDecision.objects.filter(
        session_id=session_id
    ).select_related('result', 'reviewer')

    if not decisions.exists():
        print(f"No decisions found for session {session_id}")
        return

    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'result_id', 'result_title', 'result_url',
            'decision', 'exclusion_reason', 'notes',
            'reviewer_email', 'created_at'
        ])
        writer.writeheader()

        for dec in decisions:
            writer.writerow({
                'result_id': str(dec.result.id),
                'result_title': dec.result.title,
                'result_url': dec.result.url,
                'decision': dec.decision,
                'exclusion_reason': dec.exclusion_reason,
                'notes': dec.notes,
                'reviewer_email': dec.reviewer.email,
                'created_at': dec.created_at.isoformat()
            })

    print(f"Exported {decisions.count()} decisions to {output_path}")

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python export_session_decisions.py <session_id> <output_path>")
        sys.exit(1)

    export_decisions(sys.argv[1], sys.argv[2])
```

**Usage**:
```bash
docker compose exec web python scripts/export_session_decisions.py \
    <session-uuid> /tmp/decisions_export.csv

docker cp web:/tmp/decisions_export.csv ./decisions_export.csv
```

### Script 2: Clone Session for Dual-Screening

Save as `scripts/clone_session_for_dual_screening.py`:

```python
#!/usr/bin/env python
"""Clone session from Workflow #1 to Workflow #2."""

import sys
from apps.review_manager.models import SearchSession, ReviewConfiguration
from apps.results_manager.models import ProcessedResult
from apps.search_strategy.models import SearchStrategy

def clone_session(old_session_id, new_title=None):
    """Clone session with Workflow #2 configuration."""

    old_session = SearchSession.objects.get(id=old_session_id)

    # Create new session
    new_session = SearchSession.objects.create(
        title=new_title or f"{old_session.title} (Dual-Screening)",
        description=old_session.description,
        owner=old_session.owner,
        organization=old_session.organization,
        status='draft'
    )

    # Configure Workflow #2
    ReviewConfiguration.objects.create(
        session=new_session,
        min_reviewers_per_result=2,
        conflict_resolution_method='CONSENSUS',
        blind_screening_enforced=True,
        irr_threshold=0.70
    )

    # Copy search strategy
    if old_session.search_strategy:
        old_strategy = old_session.search_strategy
        SearchStrategy.objects.create(
            session=new_session,
            population_terms=old_strategy.population_terms,
            interest_terms=old_strategy.interest_terms,
            context_terms=old_strategy.context_terms,
            include_guidelines_filter=old_strategy.include_guidelines_filter,
            file_type_filter=old_strategy.file_type_filter
        )

    # Copy results
    old_results = ProcessedResult.objects.filter(session=old_session)
    for result in old_results:
        ProcessedResult.objects.create(
            session=new_session,
            title=result.title,
            snippet=result.snippet,
            url=result.url,
            source=result.source,
            search_query_id=result.search_query_id,
            duplicate_of=result.duplicate_of,
            is_excluded_by_rule=result.is_excluded_by_rule
        )

    print(f"✅ Created new session: {new_session.id}")
    print(f"   Title: {new_session.title}")
    print(f"   Results copied: {old_results.count()}")
    print(f"   Workflow: #2 (Independent Screening)")
    print(f"   Next steps:")
    print(f"   1. Invite 2+ independent reviewers")
    print(f"   2. Transition session to 'ready_for_review'")
    print(f"   3. Reviewers perform independent blinded review")

    return new_session.id

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python clone_session_for_dual_screening.py <old_session_id> [new_title]")
        sys.exit(1)

    new_title = sys.argv[2] if len(sys.argv) > 2 else None
    clone_session(sys.argv[1], new_title)
```

**Usage**:
```bash
docker compose exec web python scripts/clone_session_for_dual_screening.py \
    <old-session-uuid> "My Session (PRISMA Dual-Screening)"
```

---

## Validation and Testing

### Post-Migration Validation Checklist

After migrating a session to Workflow #2:

```bash
# 1. Verify configuration
docker compose exec web python manage.py shell
>>> from apps.review_manager.models import SearchSession
>>> session = SearchSession.objects.get(id='NEW_SESSION_UUID')
>>> config = session.current_configuration
>>> assert config.min_reviewers_per_result >= 2, "Not Workflow #2"
>>> assert config.conflict_resolution_method is not None, "Missing resolution method"
>>> print("✅ Configuration valid")

# 2. Verify results copied
>>> old_count = ProcessedResult.objects.filter(session_id='OLD_SESSION_UUID').count()
>>> new_count = ProcessedResult.objects.filter(session_id='NEW_SESSION_UUID').count()
>>> assert old_count == new_count, f"Result count mismatch: {old_count} vs {new_count}"
>>> print(f"✅ {new_count} results copied")

# 3. Verify invitations created
>>> invitations = ReviewInvitation.objects.filter(session=session)
>>> assert invitations.count() >= 2, "Need at least 2 reviewers for Workflow #2"
>>> print(f"✅ {invitations.count()} invitations created")

# 4. Test blinding enforcement
>>> from apps.review_results.services.blinding_service import BlindingService
>>> blinding = BlindingService()
>>> # Before all complete, should be blinded
>>> can_view = blinding.can_view_other_decisions(session, session.owner)
>>> assert not can_view, "Blinding not enforced"
>>> print("✅ Blinding active")
```

### End-to-End Test

**Test Workflow #2 Flow**:

1. Create test session with Workflow #2 config
2. Invite 2 test users
3. Both users accept invitations
4. Both users review 10 sample results independently
5. Introduce 2 intentional conflicts (INCLUDE vs EXCLUDE)
6. Both mark review complete
7. Verify:
   - ✅ Conflicts detected automatically
   - ✅ Cohen's Kappa calculated
   - ✅ Email notifications sent
   - ✅ Conflict discussion page loads
8. Resolve conflicts via consensus
9. Complete session
10. Verify PRISMA report includes IRR section

**Automated Test**:
```bash
docker compose exec web python manage.py test \
    apps.review_results.tests.test_dual_workflow_integration
```

---

## Rollback Plan

### If Deployment Fails

**Immediate Rollback**:

```bash
# 1. Rollback database migrations
docker compose exec web python manage.py migrate review_results 0008
docker compose exec web python manage.py migrate review_manager 0014

# 2. Rollback Docker images
docker compose down
git checkout previous-stable-tag
docker compose build --no-cache
docker compose up -d

# 3. Verify existing sessions still work
docker compose exec web python manage.py shell
>>> SearchSession.objects.first().current_configuration
```

**Data Preservation**:
- All `SimpleReviewDecision` records preserved (backward compatible)
- No data loss for Workflow #1 sessions
- New Workflow #2 sessions created during deployment rollback remain in database but inactive

### If Users Report Issues

**Troubleshooting Steps**:

1. **Check session configuration**:
   ```bash
   docker compose exec web python manage.py shell
   >>> session = SearchSession.objects.get(id='SESSION_UUID')
   >>> print(f"Workflow: {session.current_configuration.min_reviewers_per_result}")
   ```

2. **Check logs for errors**:
   ```bash
   docker compose logs -f web --tail=100 | grep ERROR
   ```

3. **Verify signal handlers registered**:
   ```bash
   docker compose exec web python manage.py shell
   >>> from django.db.models import signals
   >>> from apps.review_results.models import ReviewerDecision
   >>> print(signals.post_save.receivers)
   ```

---

## Troubleshooting

### Common Migration Issues

#### Issue 1: "ReviewConfiguration has no field 'conflict_resolution_method'"

**Cause**: Migrations not applied

**Solution**:
```bash
docker compose exec web python manage.py migrate review_manager
docker compose restart web
```

#### Issue 2: "ConflictResolution model not found"

**Cause**: Migrations not applied for review_results app

**Solution**:
```bash
docker compose exec web python manage.py migrate review_results
docker compose restart web celery_worker
```

#### Issue 3: "Cohen's Kappa calculation fails"

**Cause**: scikit-learn not installed

**Solution**:
```bash
# Add to requirements.txt
scikit-learn==1.3.2

# Rebuild Docker images
docker compose build --no-cache web celery_worker
docker compose up -d
```

#### Issue 4: "Vue SPA consensus discussion page doesn't load"

**Cause**: Frontend not compiled

**Solution**:
```bash
# Compile Vue SPA
cd frontend
npm install
npm run build

# Collect static files
docker compose exec web python manage.py collectstatic --noinput
docker compose restart web
```

#### Issue 5: "Email notifications not sent for conflicts"

**Cause**: Celery workers not restarted (signal handlers not registered)

**Solution**:
```bash
docker compose restart celery_worker celery_beat
docker compose logs -f celery_worker | grep "conflict_detected"
```

### Support

**If you encounter issues not covered here**:

1. Check deployment checklist: `PRPs/dual-workflow/DEPLOYMENT_CHECKLIST.md`
2. Review architecture docs: `docs/workflows/DUAL_WORKFLOW_ARCHITECTURE.md`
3. Search GitHub issues: Label `migration`
4. Contact support: support@agent-grey.example.com

---

## Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | November 2025 | Initial migration guide for dual-workflow feature |

**Document Status**: Active
**Next Review**: March 2026
