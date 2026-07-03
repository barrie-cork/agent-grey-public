#!/bin/bash
set -e

echo "Starting Celery Worker..."
echo "Environment: Production"
echo "Redis URL: ${CELERY_BROKER_URL:0:30}..."
echo "Django Settings: ${DJANGO_SETTINGS_MODULE}"

# Show Django version
echo "Django version:"
python -c "import django; print(django.get_version())"

# Test Redis connection using unified test script
if [[ -n "$CELERY_BROKER_URL" ]]; then
    echo "Testing Redis connection..."
    python /app/scripts/lib/redis-test.py 5 || {
        echo "WARNING: Redis test failed - continuing anyway"
    }
fi

# Export worker type for cache detection
export WORKER_TYPE=celery

# Start Celery Worker
echo "Starting Celery worker..."

# Use CELERY_CONCURRENCY env var if set, otherwise default to 2
CONCURRENCY=${CELERY_CONCURRENCY:-2}

# Embedded beat scheduler (replaces separate celery-beat worker)
BEAT_FLAGS=""
if [[ "${CELERY_BEAT_EMBEDDED}" == "true" ]]; then
    echo "Enabling embedded Beat scheduler..."
    mkdir -p /tmp
    BEAT_FLAGS="-B --schedule=/tmp/celerybeat-schedule --pidfile=/tmp/celerybeat.pid"
fi

exec celery -A grey_lit_project worker \
    --loglevel=info \
    --concurrency="$CONCURRENCY" \
    --max-tasks-per-child=50 \
    --time-limit=300 \
    --soft-time-limit=240 \
    --without-heartbeat \
    --without-gossip \
    --without-mingle \
    $BEAT_FLAGS
