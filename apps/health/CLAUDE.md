# Health App

Health check endpoints for monitoring and deployment.

## Endpoints

| Path | Function | Purpose |
|------|----------|---------|
| `/health/` | `health_check` | Lightweight DB-only probe for load balancer (targets <50ms) |
| `/health/detailed/` | `detailed_health_check` | Full health: database, cache, Redis, Celery, Spaces (parallel) |
| `/health/cache/` | `cache_health_check` | Cache-only health |
| `/health/ready/` | `ready_check` | Readiness probe (with startup grace period) |
| `/health/static-debug/` | `static_debug` / `static_test` | Static file serving diagnostics |
