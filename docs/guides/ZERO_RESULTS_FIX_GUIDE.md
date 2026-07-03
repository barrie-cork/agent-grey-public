# Zero Results Fix Guide

## Problem

Search execution completes successfully, raw results exist, but the review interface shows **"No results to review (0)"**.

## Root Cause

The batch processor had a bug where `get_or_create()` would change existing SUCCESS results to FILTERED status when encountering duplicate URLs, even though the original result should remain SUCCESS.

## Quick Fix Instructions

### Step 1: Investigate the Database State

```bash
# Via DigitalOcean App Platform Console
python manage.py investigate_session_data <session-id>
```

This will show:
- Status breakdown (SUCCESS/FILTERED/ERROR counts)
- Whether you have false duplicates (FILTERED results with no actual duplicate URLs)
- Recommendations for fixing the issue

### Step 2: Preview the Fix (Dry Run)

```bash
# See what would be fixed without making changes
python manage.py fix_false_duplicates <session-id> --dry-run
```

This shows:
- How many false duplicates will be corrected
- Sample results that will be changed
- No actual database changes

### Step 3: Apply the Fix

```bash
# Actually fix the false duplicates
python manage.py fix_false_duplicates <session-id>
```

This will:
- Change FILTERED results back to SUCCESS (if they're not true duplicates)
- Preserve actual duplicates (URLs appearing multiple times)
- Make results visible in the review interface

### Step 4: Verify

Visit the review interface:
```
https://your-agent-grey-host.example.com/review-results/overview/<session-id>/
```

You should now see your results!

## Example Session

For session `<session-id>`:

```bash
# Step 1: Investigate
python manage.py investigate_session_data <session-id>

# Step 2: Preview fix
python manage.py fix_false_duplicates <session-id> --dry-run

# Step 3: Apply fix
python manage.py fix_false_duplicates <session-id>

# Step 4: Verify
# Visit: https://your-agent-grey-host.example.com/review-results/overview/<session-id>/
```

## Alternative: Use Original Diagnostic Command

The `diagnose_zero_results` command also has fix capability:

```bash
# Diagnose and fix all issues
python manage.py diagnose_zero_results <session-id> --fix
```

This command:
- Checks for unprocessed raw results
- Corrects false duplicates
- Forces state reconciliation
- More comprehensive but slower

## Prevention

The bug has been fixed in commit `1d6c422`. New search sessions created after deployment will not experience this issue.

Existing sessions with corrupted data need to be fixed using the commands above.

## Technical Details

### The Bug (Before Fix)

```python
# OLD CODE - batch_processor.py line 256-261
if not created:
    # Handle duplicate - this is a filtered result
    processed_result.processing_status = ProcessingStatus.FILTERED
    processed_result.save(update_fields=["processing_status"])  # BUG: Overwrites original SUCCESS
    return processed_result
```

### The Fix (After Fix)

```python
# batch_processor.py - _process_single_result returns (ProcessedResult, is_new) tuple
if not created:
    # Duplicate URL found - DO NOT modify the existing result
    return processed_result, False  # Second element signals duplicate to caller
```

## Commits

- **1d6c422**: Fixed duplicate handling logic (prevents future issues)
- **9348cfd**: Added comprehensive diagnostics
- **d3ddb62**: Added fix_false_duplicates command (repairs existing data)
- **d58eee3**: Added investigate_session_data command (diagnosis tool)

## Support

If the fix doesn't work:
1. Check session status (should be `ready_for_review` or `under_review`)
2. Check browser cache (hard refresh: Ctrl+Shift+R)
3. Review diagnostic output for other issues
4. Contact developer with session ID and diagnostic output
