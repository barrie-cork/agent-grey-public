#!/bin/bash
set -e

echo "Starting Agent Grey - Systematic Grey Literature Search and Review WebApp..."
echo "Environment: Production"
echo "Port: ${PORT:-8000}"

# Essential startup tasks only - minimize time to first health check response
echo "🚀 Fast startup mode - essential tasks only"

# Pre-flight check: Verify database connectivity before attempting migrations
echo "Testing database connection..."
if ! python manage.py check --database default --settings=grey_lit_project.settings.production; then
    echo "❌ FATAL: Cannot connect to database"
    echo "❌ Check DATABASE_URL environment variable and database availability"
    exit 1
fi
echo "✅ Database connection verified"

# Critical: Run migrations first (required for app to function)
# Migrations are now FATAL - application cannot start with inconsistent database schema
echo "Applying migrations (FATAL ON FAILURE)..."
if ! python manage.py migrate --noinput --verbosity 2 --settings=grey_lit_project.settings.production; then
    echo "❌ FATAL: Migration failed - cannot start application"
    echo "❌ Application requires consistent database schema to function"
    echo "❌ Check logs above for specific migration error details"
    exit 1
fi
echo "✅ Migrations applied successfully"

# Seed SERP provider configs (idempotent -- safe after flush/reset)
echo "Seeding SERP provider configs..."
python manage.py seed_provider_configs --settings=grey_lit_project.settings.production || echo "⚠️  Provider seeding failed, continuing..."

# Start server immediately - health checks need this running
# Note: collectstatic and createcachetable run during docker build (Dockerfile lines 78-82)
echo "Starting Gunicorn+Uvicorn ASGI server..."
exec gunicorn \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers ${GUNICORN_WORKERS:-2} \
    --timeout ${GUNICORN_TIMEOUT:-120} \
    --graceful-timeout 10 \
    --keep-alive 65 \
    --worker-class uvicorn.workers.UvicornWorker \
    --max-requests ${GUNICORN_MAX_REQUESTS:-500} \
    --max-requests-jitter ${GUNICORN_MAX_REQUESTS_JITTER:-50} \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    grey_lit_project.asgi:application
