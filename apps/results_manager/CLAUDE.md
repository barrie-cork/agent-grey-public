# Results Manager App

Result normalisation and deduplication.

## Models

| Model | Purpose |
|-------|---------|
| `ProcessedResult` | Normalised result with `is_duplicate` property, `get_display_url`, `has_full_text`, `get_query_metadata`. Manual addition fields: `is_manually_added`, `manually_added_by`, `manual_addition_justification` |
| `ProcessingSession` | Tracks processing progress with heartbeat, timing, error logging |

## Deduplication

URL-based deduplication via `URLDeduplicationService`. Duplicates are marked on `ProcessedResult` with `processing_status='filtered'` and `processing_error_category='duplicate'`. No separate model -- the single source of truth is the `ProcessedResult` record status.

**Counting duplicates:**
```python
ProcessedResult.objects.filter(
    session__id=session_id,
    processing_status="filtered",
    processing_error_category="duplicate",
).count()
```

## File Type Enforcement

When a search strategy has `file_types` configured (e.g. `["pdf"]`), the batch processor enforces this in post-processing. Google's `filetype:` operator is advisory -- non-matching results slip through.

Non-matching results are stored with `processing_status='filtered'` and `processing_error_category='file_type_mismatch'`. They are excluded from the review interface but preserved for audit trail transparency.

**Key code**: `BatchProcessor._get_required_file_types()` retrieves the strategy config once per batch; `BatchProcessor._matches_file_type()` maps `DocumentType` to file type strings.

**Counting file type filtered results:**
```python
ProcessedResult.objects.filter(
    session__id=session_id,
    processing_status="filtered",
    processing_error_category="file_type_mismatch",
).count()
```

## Constants

- `DocumentType` -- `PDF`, `WORD`, `WEBPAGE`
- `ErrorCategory` -- `DUPLICATE`, `FILE_TYPE_MISMATCH`
- `ProcessingStatus` (in `services/processors/error_handler.py`) -- `SUCCESS`, `FILTERED`, `ERROR`

## Views

| View | Purpose |
|------|---------|
| `ProcessingStatusView` | Processing progress page |
| `ProcessingStatusAPIView` | Processing status API |
| `get_filtering_statistics` | Filtering stats function |

## Other Key Files

- `tasks/` -- Celery tasks for normalisation and deduplication
- `services/` -- processing pipeline services
- `utils/` -- processing utilities
- `managers.py` -- custom QuerySet managers
- `validation.py` -- result validation
- `providers.py` -- data provider pattern
- `api.py` -- API endpoints (`get_deduplication_stats()` returns `{total_results, duplicates_removed, unique_results, deduplication_rate}`)
- `constants.py` -- processing status constants
