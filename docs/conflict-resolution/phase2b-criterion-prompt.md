# Phase 2B: Structured Criterion Prompt

**Task**: 2.2
**Scope**: Backend migration + API endpoint + frontend dropdown
**Status**: Planned (after Phase 2A)

## Summary

Add a "Which criterion is in dispute?" dropdown before free-form discussion begins. This anchors the conversation to a specific screening criterion, enabling future batch resolution (Phase 3.5).

## Changes Required

### Backend
- New `disputed_criterion` CharField on `ConflictResolution` model (blank=True, choices derived from `SimpleReviewDecision.EXCLUSION_REASONS`)
- Migration: `apps/review_results/migrations/`
- Serializer: add `disputed_criterion` + `disputed_criterion_display` to list and detail serializers
- API: `PATCH /api/conflicts/{id}/` to set criterion (separate from comment creation)

### Frontend
- Criterion selection dropdown shown when `disputed_criterion` is empty, conflict is unresolved, and user can comment
- Once selected, displayed as badge above discussion thread
- First comment can reference the selected criterion

### Criterion Options (from EXCLUSION_REASONS)
- Relevance to research question
- Grey literature classification
- Document type appropriateness
- Population match
- Intervention/interest match
- Context appropriateness
- Full text availability
- Language eligibility
- Other criterion

## Dependencies
- Phase 2A should be completed first (collegial copy affects labels)
- Enables Phase 3.5 (batch resolution for similar conflicts)
