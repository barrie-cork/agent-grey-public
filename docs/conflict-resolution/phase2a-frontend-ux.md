# Phase 2A: Frontend UX Improvements

**Tasks**: 2.1 (source material prominence), 2.3 (collegial copy), 2.4 (progress bar)
**Scope**: Mostly frontend. One small backend change (session_counts in ConflictListView).
**Status**: Ready to implement

## Tasks

### 2.1 Source Material Prominence
- Remove quotation marks and italic styling from snippet display
- Replace small "View Source" link with prominent "Open Source in New Tab" button
- Improve list view snippet visibility (line-clamp-2 instead of truncate)
- Files: `ConflictResolution.vue`, `ConflictList.vue`

### 2.3 Collegial System Copy
- Replace "Conflict" with "Discussion needed" in reviewer-facing UI
- Rewrite labels per copy voice table in `vision.md`
- Add contextual help text encouraging collaborative framing
- Files: `ConflictList.vue`, `ConflictResolution.vue`, related components

### 2.4 Progress Bar and Batch Count
- Add `session_counts` (total/resolved/pending) to `ConflictListView` API response
- Replace client-side page-local counts with server-side session-wide counts
- Add progress bar and "Discussing X of Y" header
- Files: `conflict_views.py`, `conflicts.ts`, `ConflictList.vue`, `ConflictResolution.vue`

## Execution Order
1. Task 2.3 (copy) -> 2. Task 2.1 (layout) -> 3. Task 2.4 (counts + bar)
