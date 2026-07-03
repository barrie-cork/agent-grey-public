# `check_strategy_completion` Signal -- Call Chain Documentation

## Signal Definition

**File:** `apps/search_strategy/signals.py:60`
**Type:** `post_save` signal on `SearchQuery` model
**dispatch_uid:** `search_strategy.check_strategy_completion`

## What It Does

When any `SearchQuery` instance is saved (created or updated), this signal handler:

1. Checks the parent session is in `draft` or `defining_search` state
2. Validates the search strategy is complete (`strategy.validate_completeness()`)
3. Confirms at least one active query exists with `query_text` populated
4. Emits `session_status_changed` signal requesting transition to `ready_to_execute`

## Downstream Effect

```
check_strategy_completion (search_strategy/signals.py:60)
  --> session_status_changed.send(requested_status="ready_to_execute")
        --> handle_status_change_request (review_manager/signals.py:269)
              --> transition_session_status (review_manager/utils.py:100)
                    --> session.save()  [status = "ready_to_execute"]
                          --> (auto-transition chain: executing -> processing_results -> ready_for_review)
```

## Production Callers (Code Paths That Trigger the Signal)

### 1. SearchStrategyView -- User submits PIC strategy form

**Entry point:** `apps/search_strategy/views.py:72` -- `SearchStrategyView.post()`

```
User submits PIC form (POST /search-strategy/<session_id>/)
  --> SearchStrategyView.post() (views.py:358)
        --> _handle_valid_form() (views.py:367)
              --> SearchStrategyService.validate_and_save_strategy() (services/search_strategy_service.py:47)
              --> SearchStrategyService.update_search_queries() (services/search_strategy_service.py:73)
                    --> SearchQuery.objects.create() (services/search_strategy_service.py:132)  [TRIGGERS SIGNAL]
```

This is the **primary production caller**. Each query created in the loop at line 132 fires `post_save`, but the signal short-circuits for sessions not in `draft`/`defining_search`, so only the last relevant save triggers the transition.

Note: `_handle_valid_form` also calls `handle_status_transition()` directly (views.py:393), which is a **parallel path** that transitions the session independently of the signal. The signal acts as a safety net.

### 2. Diagnostic endpoint -- Test session creation

**Entry point:** `apps/serp_execution/api/diagnostic_endpoints.py:130`

```
POST /api/serp/diagnostics/test-session/
  --> SearchQuery.objects.create() (diagnostic_endpoints.py:130)  [TRIGGERS SIGNAL]
```

Creates a test session with a single query for integration testing. The signal fires and may transition the test session.

### 3. check_workflow_integration management command

**Entry point:** `apps/serp_execution/management/commands/check_workflow_integration.py:52`

```
python manage.py check_workflow_integration
  --> SearchQuery.objects.create() (check_workflow_integration.py:52, 62)  [TRIGGERS SIGNAL]
```

Creates test queries to verify the workflow integration. Also calls `mark_strategy_complete()` (line 81) as a separate path.

### 4. setup_e2e_session management command (BYPASSES signal)

**Entry point:** `apps/core/management/commands/setup_e2e_session.py:313`

```
python manage.py setup_e2e_session
  --> SearchQuery.objects.bulk_create() (setup_e2e_session.py:313)  [DOES NOT TRIGGER SIGNAL]
```

Uses `bulk_create` intentionally to **avoid** triggering `check_strategy_completion`. The comment at line 312 documents this decision.

## Related Function: `mark_strategy_complete`

**File:** `apps/search_strategy/signals.py:116`

This is **not** the signal handler itself but a helper function that performs the same validation logic and emits the same `session_status_changed` signal. It is called by:

- `check_workflow_integration` management command (`apps/serp_execution/management/commands/check_workflow_integration.py:81`)

## Signal Registration

The signal is registered via the `@receiver` decorator in `apps/search_strategy/signals.py:55-58`. Note that `apps/search_strategy/apps.py` has an **empty `ready()` method** -- it does not explicitly import `signals.py`. The `@receiver(post_save, sender=SearchQuery)` decorator connects the signal at module import time, so the signal is only active once something imports the `signals` module. In practice this happens because the primary caller (`SearchStrategyService.update_search_queries`) imports `SearchQuery` from `..models`, and the service is used by `SearchStrategyView` which is loaded via URL routing at startup. This is a minor fragility -- the conventional Django pattern is to import signals in `ready()`.

## Key Design Notes

- **Idempotency:** The signal short-circuits if the session is not in `draft` or `defining_search` (line 77), preventing duplicate transitions.
- **Staleness guard:** `session.refresh_from_db(fields=["status"])` at line 74 prevents stale cached status when multiple queries are saved in sequence.
- **bulk_create bypass:** Django's `bulk_create` does not fire `post_save` signals. The E2E setup command exploits this deliberately.
- **Dual path:** The `SearchStrategyView` has both the signal-based auto-transition AND a direct `handle_status_transition()` call. The signal provides a safety net; the view provides the primary transition with user-facing messages.
