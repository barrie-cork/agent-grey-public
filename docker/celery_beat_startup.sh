#!/bin/bash
set -e

echo "Starting Celery Beat Scheduler..."
echo "Environment: Production"
echo "Redis URL: ${CELERY_BROKER_URL:0:30}..."
echo "Django Settings: ${DJANGO_SETTINGS_MODULE}"

# Show Django version
echo "Django version:"
python -c "import django; print(django.get_version())"

# Test Redis connection using unified test script (with timeout)
if [[ -n "$CELERY_BROKER_URL" ]]; then
    echo "Testing Redis connection (quick test)..."
    timeout 5 python /app/scripts/lib/redis-test.py 3 || {
        echo "Redis test skipped (will retry on startup)"
    }
fi

# Initialize cache before starting beat (optional - Celery Beat will initialize on demand)
echo "Cache initialization deferred to Beat startup..."
# Cache will be initialized automatically by Celery Beat when needed
# This speeds up deployment and prevents startup failures

# Export worker type for cache detection
export WORKER_TYPE=celery-beat

# Create PID file directory with proper permissions
mkdir -p /tmp
touch /tmp/celerybeat.pid
chmod 777 /tmp/celerybeat.pid

# Start Celery Beat
echo "Starting Celery Beat scheduler..."
exec celery -A grey_lit_project beat \
    --loglevel=info \
    --pidfile=/tmp/celerybeat.pid \
    --schedule=/tmp/celerybeat-schedule
