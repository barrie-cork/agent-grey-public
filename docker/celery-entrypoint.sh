#!/bin/bash
set -e

# Ensure UTC timezone
export TZ=UTC

echo "Starting Celery worker for Agent Grey..."
echo "Redis URL: ${CELERY_BROKER_URL}"
echo "Worker concurrency: ${CELERY_CONCURRENCY:-2}"
echo "Log level: ${CELERY_LOG_LEVEL:-info}"
echo "Timezone: ${TZ:-UTC}"

# Wait for Redis to be ready
echo "Waiting for Redis..."
for i in {1..30}; do
    if python -c "import redis; redis.from_url('${CELERY_BROKER_URL}').ping()" 2>/dev/null; then
        echo "Redis is ready!"
        break
    fi
    echo "Waiting for Redis... ($i/30)"
    sleep 2
done

# Start Celery worker
echo "Starting Celery worker..."
exec celery -A grey_lit_project worker \
    --loglevel=${CELERY_LOG_LEVEL:-info} \
    --concurrency=${CELERY_CONCURRENCY:-2} \
    --max-tasks-per-child=${CELERY_MAX_TASKS_PER_CHILD:-100} \
    --time-limit=${CELERY_TASK_TIME_LIMIT:-600} \
    --soft-time-limit=${CELERY_TASK_SOFT_TIME_LIMIT:-540}
