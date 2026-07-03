# Docker Environment (Agent Grey)

## CRITICAL: Docker-Only Operation

**Never run Django natively.** Root cause of Issue #34 (6h debugging reduced to 20min with checklist).

### Quick Environment Check

```bash
# Core services (4 containers)
docker compose ps
# Should show: web, db, redis, celery_worker

# Should be EMPTY (no native Django)
ps aux | grep "python manage.py runserver"

# Verify Docker is serving
curl -I http://localhost:8000/ | grep Server
```

## Services

### Core (default -- 4 containers)

| Service | Port | Purpose |
|---------|------|---------|
| **web** | 8000 (5678 debug) | Django application server (Gunicorn+Uvicorn ASGI in production/staging) |
| **db** | 5433 | PostgreSQL 15 |
| **redis** | 6379 | Cache + Celery broker |
| **celery_worker** | -- | Async task processing |

### Optional Profiles

| Profile | Command | Services Added |
|---------|---------|----------------|
| `scheduler` | `--profile scheduler` | celery_beat (local dev only; production embeds beat in `celery_worker` via `CELERY_BEAT_EMBEDDED=true`) |
| `monitoring` | `--profile monitoring` | flower (5555), warning_monitor (self-hosted prometheus/grafana/alertmanager removed 2026-06-17) |
| `proxy` | `--profile proxy` | nginx (8800) |
| `admin` | `--profile admin` | pgadmin (8080) |

## Common Failure Modes

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| Blank page after code fix | Native Django running | `sudo pkill -f runserver && docker compose up -d` |
| Redis connection failed | Native Django (no Redis link) | Use Docker: `docker compose up -d` |
| Env vars not loaded | Stale containers | `docker compose up -d --force-recreate` (`restart` does NOT reload `env_file`) |
| Port already in use | Stale process | `docker compose down && sudo lsof -ti:8000 \| xargs kill` |
| Exit code 137 (OOM) | Instance too small | Use `apps-s-1vcpu-1gb-fixed` minimum in `.do/app.yaml` |

## Local Dev Superuser

After a fresh `flush`, recreate the superuser:

```bash
docker compose exec web python manage.py shell -c "
from apps.accounts.models import User
User.objects.create_superuser(username='admin', email='admin@example.com', password='<see .env or memory>')
"
```

Credentials are stored in Claude Code auto-memory (not committed to git).

## Starting Environment

```bash
docker compose up -d
docker compose ps                    # Verify
docker compose logs -f web           # Watch logs
docker compose exec web python manage.py migrate  # Run migrations
docker compose exec web python manage.py shell    # Django shell
```

## Debugging Checklist (Issue #34 Pattern)

When bug persists after code fix, check in this order:

1. `docker compose ps` -- is Docker running?
2. `ps aux | grep runserver` -- is native Django running? Kill it.
3. `curl -I http://localhost:8000/ | grep Server` -- which server is actually serving?
4. `docker compose logs web` -- any errors?
5. `docker compose restart web` -- clear stale state

## Multi-Stage Build (Dockerfile)

The production `Dockerfile` has three stages:

1. **base** -- Python 3.12 + system dependencies (WeasyPrint, PostgreSQL client)
2. **frontend** -- `node:22-slim`, runs `npm ci` + `npx vite build`, outputs to `/app/static/dist`
3. **production** -- Copies Python deps, project code, then `COPY --from=frontend` for built assets, then `collectstatic`

`static/dist/` is gitignored and dockerignored. The only frontend assets in the production image come from the Node.js build stage. Local `npm run build` is still used for development but is not needed for deployment.

## Migration Inconsistency Errors

**Symptom**: `django.db.migrations.exceptions.InconsistentMigrationHistory`

```bash
# Automated fix
./scripts/fix-migration-inconsistency.sh

# Verify consistency
docker compose exec web python scripts/check-migration-health.py
```

## URL Route Persistence

**Symptom**: Deleted route still returns 200 (not 404)
**Root Cause**: Django `APPEND_SLASH` middleware creates redirects even for non-existent routes with related patterns. Check with `curl -I http://localhost:8000/path` for a 301 redirect.

## Reference Documents

- **Issue #34 RCA**: `docs/fixes/issue-34-native-django-server-2025-11-02.md`
- **Full Troubleshooting**: `docs/docker/DOCKER-TROUBLESHOOTING.md`
- **RCA archive** (12 files): `docs/fixes/archive/2025-10-deployment-fixes/`
- **Migration recovery**: `docs/troubleshooting/MIGRATION-INCONSISTENCY-RECOVERY.md`
- **Zero results guide**: `docs/guides/ZERO_RESULTS_FIX_GUIDE.md`
