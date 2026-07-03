# SERP Execution App

SERP provider integration and search result fetching.

## Models

| Model | Purpose |
|-------|---------|
| `SearchExecution` | Execution record with status tracking, retry logic (`can_retry`), provider info (`serp_provider`, `serp_provider_display`) |
| `RawSearchResult` | Raw results from SERP providers before processing |
| `SerpProviderConfig` | Per-provider configuration (in migrations) |

## Provider Abstraction (`providers/`)

| Symbol | Purpose |
|--------|---------|
| `SerpProvider` | Protocol that all providers implement |
| `register_provider` | Register a provider class |
| `get_provider` / `get_default_provider` | Resolve provider at execution time |
| `get_provider_for_config` | Resolve from `SerpProviderConfig` |
| `get_enabled_provider_choices` | Returns `(key, display_name)` tuples for form fields |
| `get_default_provider_key` | Returns default provider key string (for form defaults) |
| `list_providers` | List all registered providers |

## Views

| View | Purpose |
|------|---------|
| `SearchExecutionStatusView` | Execution progress monitoring |
| `ErrorRecoveryView` | Manual error recovery |
| `ReconcileStateView` | State reconciliation (POST) |
| `TestSessionMonitorView` | Debug/test monitoring |

## Other Key Files

- `tasks/` -- Celery tasks (execution orchestration, `simple_tasks.py` reads `search_config["serp_providers"]` for multi-provider execution; falls back to `get_default_provider()` for backward compat)
- `services/` -- execution services
- `query_executor.py` -- query execution logic
- `recovery.py` -- error recovery logic
- `dependencies.py` -- function-based DI registry (getter/setter per provider) and Default* implementations
- `constants.py` -- status constants
- `api/` -- API endpoints
