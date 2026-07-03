# Docker Rebuild Guide

This guide provides commands for rebuilding your Docker environment with a clean slate.

## Quick Reference

### Full Clean Rebuild (Removes Everything)

```bash
docker compose down -v --remove-orphans --rmi all && docker builder prune -a -f && docker compose build --no-cache && docker compose up -d
```

### Clean Rebuild (Preserves Database)

```bash
docker compose down --remove-orphans && docker builder prune -a -f && docker compose build --no-cache && docker compose up -d
```

## Step-by-Step Commands

### 1. Full Clean Rebuild (Removes All Data)

⚠️ **Warning:** This will delete all local database data and volumes.

```bash
# Stop all containers
docker compose down

# Remove all containers, volumes, and orphans
docker compose down -v --remove-orphans

# Remove all images for this project
docker compose down --rmi all

# Clear Docker build cache
docker builder prune -a -f

# Full rebuild and restart
docker compose build --no-cache && docker compose up -d
```

### 2. Clean Rebuild (Preserves Database Data)

Recommended for most development scenarios:

```bash
# Stop all containers and remove orphans
docker compose down --remove-orphans

# Clear Docker build cache
docker builder prune -a -f

# Rebuild without cache and restart
docker compose build --no-cache && docker compose up -d
```

### 3. Quick Rebuild (Uses Cache)

Faster rebuild that uses Docker's build cache:

```bash
# Stop containers
docker compose down

# Rebuild and restart
docker compose up -d --build
```

## Post-Rebuild Steps

After rebuilding Docker containers, you need to rebuild frontend assets and collect static files:

### 1. Rebuild Vite/Vue.js Assets

```bash
cd frontend
npm run build
cd ..
```

### 2. Collect Django Static Files

```bash
docker compose exec web python manage.py collectstatic --noinput
```

### 3. Verify All Services

```bash
# Check container status
docker compose ps

# Check web service health
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health/

# View logs for specific service
docker compose logs -f web
docker compose logs -f celery_worker
docker compose logs -f dramatiq
```

## Common Issues After Rebuild

### Missing Python Dependencies

If containers show `ModuleNotFoundError`, rebuild the affected service:

```bash
docker compose build --no-cache <service-name>
docker compose up -d <service-name>
```

Example:
```bash
docker compose build --no-cache dramatiq celery_worker celery_beat
docker compose up -d dramatiq celery_worker celery_beat
```

### Database Connection Issues

Wait for the database to be fully ready:

```bash
# Check database health
docker compose ps db

# View database logs
docker compose logs db
```

### Services Not Starting

View logs to diagnose:

```bash
# All services
docker compose logs

# Specific service
docker compose logs <service-name>

# Follow logs in real-time
docker compose logs -f
```

## Service-Specific Rebuilds

### Rebuild Core Application Services

```bash
docker compose build --no-cache web
docker compose up -d web
```

### Rebuild Background Workers

```bash
docker compose build --no-cache celery_worker celery_beat dramatiq flower
docker compose up -d celery_worker celery_beat dramatiq flower
```

### Rebuild Monitoring Stack

```bash
docker compose build --no-cache prometheus grafana alertmanager
docker compose up -d prometheus grafana alertmanager
```

## Docker Cleanup Commands

### Remove Stopped Containers

```bash
docker container prune -f
```

### Remove Unused Images

```bash
docker image prune -a -f
```

### Remove Unused Volumes

```bash
docker volume prune -f
```

### Remove All Unused Resources

```bash
docker system prune -a -f --volumes
```

## Troubleshooting

### Build Taking Too Long

The `--no-cache` flag forces Docker to rebuild everything from scratch, which can take 10-20 minutes. If you're in a hurry:

1. Try a regular build first: `docker compose build`
2. Only use `--no-cache` if you have dependency or caching issues

### Out of Disk Space

```bash
# Check Docker disk usage
docker system df

# Clean up everything (use with caution)
docker system prune -a -f --volumes
```

### Port Conflicts

If ports are already in use:

```bash
# Find what's using port 8000
lsof -i :8000

# Or on Windows/WSL
netstat -ano | findstr :8000
```

## Environment-Specific Rebuilds

### Development (Default)

```bash
docker compose build --no-cache
docker compose up -d
```

### Staging

```bash
docker compose -f docker compose.staging.yml build --no-cache
docker compose -f docker compose.staging.yml up -d
```

### Production

```bash
docker compose -f docker compose.production.yml build --no-cache
docker compose -f docker compose.production.yml up -d
```

## Best Practices

1. **Always check git status** before rebuilding to ensure code is committed
2. **Use `--no-cache` sparingly** - it's slow but thorough
3. **Check logs immediately** after rebuild to catch issues early
4. **Rebuild frontend assets** after any Docker rebuild
5. **Verify health endpoints** after all services are up
6. **Back up database** before doing full clean rebuild with `-v` flag

## Quick Health Check

After rebuild, verify all services:

```bash
# All containers should show "healthy" status
docker compose ps

# Check key endpoints
curl http://localhost:8000/health/           # Django web
curl http://localhost:8800                   # Nginx
curl http://localhost:5555                   # Flower (Celery monitoring)
curl http://localhost:9090                   # Prometheus
curl http://localhost:3000                   # Grafana
curl http://localhost:16686                  # Jaeger
```

## Related Documentation

- [DigitalOcean Configuration](../deployment/DIGITALOCEAN-CONFIGURATION.md)
- [Environment Variable Configuration](../deployment/ENVIRONMENT-VARIABLE-CONFIGURATION.md)
- [Health Check Configuration](../deployment/HEALTH-CHECK-CONFIGURATION.md)
