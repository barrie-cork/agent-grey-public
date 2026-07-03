# Core App

Shared utilities, configuration, and infrastructure for all apps.

## Key Modules

| Module | Purpose |
|--------|---------|
| `env_config.py` | Environment variable access (`get_env`, `get_env_bool`, `get_env_int`, etc.). **Always use this, never `os.environ`** |
| `integrations.py` | `PostHogClient` (lazy-initialised analytics), `SentryInitializer` |
| `context_processors.py` | Template context (e.g. `posthog_enabled`) |
| `interfaces.py` | Canonical `SessionProvider` protocol (cross-app DI) |
| `validation.py` | Shared validation utilities |
| `cache_utils.py` / `cache_init.py` | Cache helpers. **Never manually instantiate backends -- use `from django.core.cache import cache`** |
| `db_utils.py` | Database utilities |

## Subpackages

| Package | Purpose |
|---------|---------|
| `services/` | Shared service base classes (e.g. `BaseEmailNotificationService`). `interfaces.py` has `CacheProvider` and `RateLimiter` protocols (package-internal to services) |
| `state_machine/` | State machine infrastructure for 9-state workflow |
| `middleware/` | Request middleware |
| `monitoring/` | Observability utilities (stub tasks removed 2026-02; module retained for future use) |
| `metrics/` | Prometheus metrics |
| `progress/` | Progress tracking utilities |
| `tasks/` | Shared Celery task utilities |
| `utils/` | General utilities (`distributed_lock`, `url_utils`) |
| `management/` | Management commands |

## Config/Infra Modules

`logging.py`, `logging_config.py`, `celery_logging.py`, `redis_config.py`, `security_config.py`, `host_config.py`, `spaces_config.py`, `environment_manager.py`, `config_builders.py`
