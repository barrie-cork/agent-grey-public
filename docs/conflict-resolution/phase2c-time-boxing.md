# Phase 2C: Configurable Time-Boxing (Deferred)

**Task**: 2.5
**Scope**: Backend fields + Celery periodic task + email reminders + frontend visual indicators
**Status**: Deferred -- planned as standalone future PRP

## Summary

Add SLA fields to `ReviewConfiguration` so lead reviewers can set time expectations for discussion, re-vote, and arbitration phases. SLAs are nudges (no hard locks).

## Changes Required

### Backend
- 3 new fields on `ReviewConfiguration`: `discussion_sla_hours` (default 72), `revote_sla_hours` (default 24), `arbitration_sla_hours` (default 48)
- `get_sla_info()` method on `ConflictResolution` computing deadline, percent elapsed, is_approaching, is_critical, is_overdue
- `sla_reminders_sent` JSONField on `ConflictResolution` to track sent reminders
- Celery periodic task `check_conflict_sla_reminders` (hourly) sending email at 50% and 90% thresholds
- Email templates using `BaseEmailNotificationService` pattern

### Frontend
- Amber border ring on conflict cards approaching deadline
- Red border ring on critical/overdue conflicts
- "X hours remaining" / "Overdue by X hours" timer display
- SLA configuration in review setup (if settings UI exists)

## Dependencies
- Phase 2A and 2B should be completed first
- Requires Celery beat schedule registration
