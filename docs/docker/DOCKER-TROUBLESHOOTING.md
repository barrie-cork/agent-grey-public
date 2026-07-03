# Docker Troubleshooting Guide

Comprehensive troubleshooting guide for common Docker and container issues in Agent Grey.

## Table of Contents

1. [Migration Issues](#migration-issues)
2. [Module Not Found Errors](#module-not-found-errors)
3. [Database Connection Problems](#database-connection-problems)
4. [Container Health Issues](#container-health-issues)
5. [Port Conflicts](#port-conflicts)
6. [Performance Issues](#performance-issues)
7. [Build Failures](#build-failures)
8. [Quick Diagnostics](#quick-diagnostics)

---

## Migration Issues

### ⚠️ NEW: Migration Inconsistency (Web Container Unhealthy)

**Symptom:**
```
Container agent-grey-core-requirements-web-1 is unhealthy
django.db.utils.ProgrammingError: column "status" already exists
django.db.utils.ProgrammingError: relation "export_repo_generat_1afb68_idx" already exists
```

**Root Cause:**
Database schema exists but Django migration history is corrupted or out of sync.

**Quick Fix (Automated):**

```bash
# Use the automated fix script
./scripts/fix-migration-inconsistency.sh

# Or for specific app
./scripts/fix-migration-inconsistency.sh reporting
```

**Manual Fix:**

```bash
# 1. Identify problematic app from logs
docker compose logs web | grep "django.db.utils.ProgrammingError"

# 2. Clear migration history for that app
docker compose exec db psql -U thesis_grey_user -d thesis_grey_dev_db -c \
  "DELETE FROM django_migrations WHERE app = 'reporting';"

# 3. Fake-apply migrations (schema already exists)
docker compose exec web python manage.py migrate reporting --fake

# 4. Restart web container
docker compose restart web

# 5. Verify all services healthy
docker compose ps
```

**See:** [Complete Migration Inconsistency Recovery Guide](../troubleshooting/MIGRATION-INCONSISTENCY-RECOVERY.md)

---

### Symptom: UndefinedColumn or Migration Errors

```
psycopg2.errors.UndefinedColumn: column "tags" of relation "search_sessions" does not exist
```

**Diagnosis:**

```bash
# Check migration status
docker compose exec web python manage.py showmigrations

# Check for unapplied migrations
docker compose exec web python manage.py migrate --plan

# Run automated health check
docker compose exec web python scripts/check-migration-health.py
```

**Solution 1: Apply Missing Migrations**

```bash
# Run migrations
docker compose exec web python manage.py migrate

# If that fails, try with fake-initial
docker compose exec web python manage.py migrate --fake-initial
```

**Solution 2: Reset Migrations (Development Only)**

⚠️ **WARNING:** This will delete all data in your local database!

```bash
# Stop all containers and remove volumes
docker compose down -v

# Restart with fresh database
docker compose up -d

# Migrations run automatically in entrypoint
# Verify with: docker compose logs web
```

**Solution 3: Fake Problematic Migration**

If a specific migration is causing issues:

```bash
# List all migrations
docker compose exec web python manage.py showmigrations

# Fake the problematic migration
docker compose exec web python manage.py migrate <app_name> <migration_number> --fake

# Then run migrations normally
docker compose exec web python manage.py migrate
```

**Prevention:**

- Always run migrations after pulling new code
- Use `docker compose down -v` for clean starts
- Check migration status before rebuilding containers
- Run `./scripts/check-migration-health.py` weekly
- Commit migration files to git

---

## Module Not Found Errors

### Symptom: ModuleNotFoundError

```
ModuleNotFoundError: No module named 'drf_spectacular'
```

**Diagnosis:**

```bash
# Check which container has the error
docker compose logs --tail=100 | grep "ModuleNotFoundError"

# Check installed packages in container
docker compose exec <service-name> pip list | grep <package-name>
```

**Solution 1: Rebuild Specific Container**

```bash
# Rebuild the affected service
docker compose build --no-cache <service-name>
docker compose up -d <service-name>
```

Example for multiple services:
```bash
docker compose build --no-cache dramatiq celery_worker celery_beat flower
docker compose up -d dramatiq celery_worker celery_beat flower
```

**Solution 2: Verify Requirements File**

```bash
# Check if package is in requirements
grep -r "drf-spectacular" requirements/

# Verify requirements are being copied correctly
docker compose exec <service-name> ls -la /app/requirements/
```

**Solution 3: Manual Installation (Temporary)**

```bash
# Install package manually in running container
docker compose exec <service-name> pip install drf-spectacular

# Restart the service
docker compose restart <service-name>
```

**Solution 4: Full Rebuild**

```bash
# Complete rebuild of all services
docker compose down --remove-orphans
docker builder prune -a -f
docker compose build --no-cache
docker compose up -d
```

**Prevention:**

- Always rebuild containers after updating requirements files
- Use `--no-cache` flag when dependencies change
- Verify `requirements/base.txt` is properly structured

---

## Database Connection Problems

### Symptom: Database Connection Timeout

```
⏳ Waiting for database... (attempt 10/30)
```

**Diagnosis:**

```bash
# Check database container status
docker compose ps db

# Check database logs
docker compose logs db

# Test database connection
docker compose exec db psql -U thesis_grey_user -d thesis_grey_dev_db -c "SELECT 1;"
```

**Solution 1: Restart Database**

```bash
# Restart database container
docker compose restart db

# Wait for it to be healthy
docker compose ps db
```

**Solution 2: Check Network Connectivity**

```bash
# Check if containers can reach each other
docker compose exec web ping db

# Check network configuration
docker network ls
docker network inspect agent-grey-core-requirements_dev_network
```

**Solution 3: Verify Database Environment Variables**

```bash
# Check database configuration
docker compose config | grep -A 10 "db:"

# Verify environment variables in web container
docker compose exec web env | grep DATABASE
docker compose exec web env | grep POSTGRES
```

**Solution 4: Reset Database**

⚠️ **WARNING:** This deletes all data!

```bash
docker compose down
docker volume rm agent-grey-core-requirements_postgres_data
docker compose up -d db
docker compose exec web python manage.py migrate
```

**Prevention:**

- Use `depends_on` with health checks in docker compose
- Implement retry logic in entrypoint scripts
- Monitor database health endpoints

---

## Container Health Issues

### Symptom: Container Shows "Unhealthy" Status

```bash
# Check unhealthy containers
docker compose ps
```

**Diagnosis:**

```bash
# Check health check configuration
docker inspect agent-grey-core-requirements-<service-name>-1 | grep -A 10 "Health"

# View recent logs
docker compose logs --tail=50 <service-name>

# Check specific health check endpoint
curl http://localhost:<port>/health/
```

**Solution 1: Restart Unhealthy Container**

```bash
docker compose restart <service-name>
```

**Solution 2: Rebuild Container**

```bash
docker compose build <service-name>
docker compose up -d <service-name>
```

**Solution 3: Check Dependencies**

```bash
# If web depends on db and redis
docker compose ps db redis

# Restart in dependency order
docker compose restart db redis web
```

**Common Health Check Issues:**

| Service | Common Issues | Solution |
|---------|---------------|----------|
| web | Database not ready | Wait for db health check |
| celery_worker | Redis not available | Restart redis first |
| flower | Can't connect to broker | Check celery_worker status |
| nginx | Upstream not ready | Ensure web is healthy |

**Prevention:**

- Configure proper health checks with retries
- Set appropriate health check intervals
- Use startup delays for dependent services

---

## Port Conflicts

### Symptom: Port Already in Use

```
Error: bind: address already in use
```

**Diagnosis:**

```bash
# Check what's using the port (Linux/WSL)
lsof -i :8000
netstat -tulpn | grep :8000

# Check what's using the port (Windows)
netstat -ano | findstr :8000
```

**Solution 1: Kill Process Using Port**

```bash
# Find and kill process (Linux/WSL)
lsof -ti :8000 | xargs kill -9

# Kill process (Windows)
# Get PID from netstat output, then:
taskkill /PID <pid> /F
```

**Solution 2: Change Port Mapping**

Edit `docker-compose.yml`:
```yaml
services:
  web:
    ports:
      - "8001:8000"  # Change 8000 to 8001
```

**Solution 3: Stop Conflicting Docker Containers**

```bash
# List all running containers
docker ps

# Stop specific container
docker stop <container-name>

# Or stop all
docker stop $(docker ps -q)
```

**Common Port Mappings:**

| Service | Port | Purpose |
|---------|------|---------|
| web | 8000 | Django application |
| nginx | 8800 | Reverse proxy |
| db | 5433 | PostgreSQL |
| redis | 6379 | Redis cache |
| flower | 5555 | Celery monitoring |
| prometheus | 9090 | Metrics |
| grafana | 3000 | Dashboards |
| jaeger | 16686 | Tracing UI |

---

## Performance Issues

### Symptom: Slow Container Performance

**Diagnosis:**

```bash
# Check container resource usage
docker stats

# Check disk space
docker system df

# Check specific container
docker stats agent-grey-core-requirements-web-1
```

**Solution 1: Clean Up Docker Resources**

```bash
# Remove stopped containers
docker container prune -f

# Remove unused images
docker image prune -a -f

# Remove unused volumes
docker volume prune -f

# Remove build cache
docker builder prune -a -f

# Complete cleanup
docker system prune -a -f --volumes
```

**Solution 2: Optimize Docker Settings**

For WSL2 on Windows, create/edit `~/.wslconfig`:

```ini
[wsl2]
memory=8GB
processors=4
swap=2GB
```

**Solution 3: Reduce Log Size**

```bash
# Clear logs for specific container
truncate -s 0 $(docker inspect --format='{{.LogPath}}' agent-grey-core-requirements-web-1)

# Or configure log rotation in docker-compose.yml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

**Solution 4: Use Docker BuildKit**

```bash
# Enable BuildKit for faster builds
export DOCKER_BUILDKIT=1
docker compose build
```

**Prevention:**

- Regular cleanup of unused resources
- Monitor container resource usage
- Use multi-stage builds to reduce image size
- Implement proper logging rotation

---

## Build Failures

### Symptom: Docker Build Fails

**Diagnosis:**

```bash
# View build logs
docker compose build <service-name> 2>&1 | tee build.log

# Check available disk space
df -h

# Check Docker daemon status
docker info
```

**Solution 1: Clear Build Cache**

```bash
docker builder prune -a -f
docker compose build --no-cache <service-name>
```

**Solution 2: Fix Dockerfile Issues**

Common issues:
- Missing files in build context
- Incorrect COPY paths
- Network issues during pip install

```bash
# Test build with verbose output
DOCKER_BUILDKIT=0 docker compose build --progress=plain <service-name>
```

**Solution 3: Check Network Connectivity**

```bash
# Test connectivity during build
docker run --rm python:3.12-slim ping -c 3 pypi.org

# Use different mirror if needed
docker compose build --build-arg PIP_INDEX_URL=https://pypi.org/simple
```

**Solution 4: Increase Docker Resources**

If builds fail with memory errors:

1. Increase Docker Desktop memory allocation
2. For WSL2, edit `~/.wslconfig`
3. Restart Docker daemon

**Prevention:**

- Keep Dockerfile optimized
- Use .dockerignore to exclude unnecessary files
- Layer caching for faster builds
- Regular Docker system cleanup

---

## Quick Diagnostics

### Health Check Script

Run this to diagnose common issues:

```bash
#!/bin/bash
# save as: scripts/docker-health-check.sh

echo "=== Docker System Status ==="
docker system df
echo ""

echo "=== Container Status ==="
docker compose ps
echo ""

echo "=== Unhealthy Containers ==="
docker compose ps | grep -i "unhealthy"
echo ""

echo "=== Recent Errors ==="
docker compose logs --tail=20 --since=5m 2>&1 | grep -i "error"
echo ""

echo "=== Database Connection ==="
docker compose exec -T db psql -U thesis_grey_user -d thesis_grey_dev_db -c "SELECT 1;" 2>&1
echo ""

echo "=== Redis Connection ==="
docker compose exec -T redis redis-cli ping 2>&1
echo ""

echo "=== Web Service Health ==="
curl -s http://localhost:8000/health/ || echo "Web service not responding"
echo ""

echo "=== Disk Usage ==="
df -h | grep -E "Filesystem|docker"
echo ""
```

Make it executable and run:

```bash
chmod +x scripts/docker-health-check.sh
./scripts/docker-health-check.sh
```

### Common Command Reference

```bash
# View all container logs
docker compose logs

# Follow specific service logs
docker compose logs -f web

# Restart specific service
docker compose restart <service-name>

# Rebuild specific service
docker compose build <service-name> && docker compose up -d <service-name>

# Execute command in container
docker compose exec <service-name> <command>

# Shell into container
docker compose exec <service-name> bash

# Check container resource usage
docker stats

# View container processes
docker compose exec <service-name> ps aux

# Check container environment
docker compose exec <service-name> env
```

### Emergency Reset

When all else fails:

```bash
# Complete teardown and rebuild
docker compose down -v --remove-orphans --rmi all
docker builder prune -a -f
docker system prune -a -f --volumes

# Rebuild from scratch
docker compose build --no-cache
docker compose up -d

# Run migrations
docker compose exec web python manage.py migrate

# Collect static files
docker compose exec web python manage.py collectstatic --noinput

# Rebuild frontend
cd frontend && npm run build && cd ..
```

---

## Getting Help

### Gather Diagnostic Information

When reporting issues, include:

```bash
# System information
docker version
docker compose version
uname -a  # or systeminfo on Windows

# Container status
docker compose ps

# Recent logs
docker compose logs --tail=100 > docker-logs.txt

# Docker system info
docker system df > docker-df.txt
docker info > docker-info.txt

# Environment
docker compose config > docker-config.txt
```

### Useful Debugging Tools

```bash
# View detailed container information
docker inspect <container-id>

# Monitor container events
docker events

# View container filesystem changes
docker diff <container-id>

# Export container filesystem
docker export <container-id> > container.tar

# View container logs with timestamps
docker compose logs --timestamps --tail=100
```

---

## Related Documentation

- [Docker Rebuild Guide](./DOCKER-REBUILD-GUIDE.md)
- [Environment Variable Configuration](../deployment/ENVIRONMENT-VARIABLE-CONFIGURATION.md)
- [Health Check Configuration](../deployment/HEALTH-CHECK-CONFIGURATION.md)
- [DigitalOcean Configuration](../deployment/DIGITALOCEAN-CONFIGURATION.md)
