#!/bin/bash

# Staging startup script for Agent Grey Django application
# Production-like environment with enhanced validation and monitoring

set -e

# Ensure UTC timezone
export TZ=UTC
if [ -f /etc/timezone ]; then
    echo "UTC" > /etc/timezone 2>/dev/null || true
fi
if [ -f /etc/localtime ]; then
    ln -sf /usr/share/zoneinfo/UTC /etc/localtime 2>/dev/null || true
fi

echo "🎯 Starting Agent Grey Staging Environment"
echo "=============================================="
echo "Environment: Staging"
echo "Django Settings: ${DJANGO_SETTINGS_MODULE:-grey_lit_project.settings.staging}"
echo "Debug Mode: ${DEBUG:-False}"
echo "Port: ${PORT:-8000}"
echo "Timezone: ${TZ:-UTC}"
echo "User: $(whoami)"
echo "=============================================="

# Function to check if a command succeeded
check_success() {
    if [ $? -eq 0 ]; then
        echo "✅ $1 completed successfully"
    else
        echo "❌ $1 failed"
        exit 1
    fi
}

# Function to check if a command succeeded but continue on failure
check_success_continue() {
    if [ $? -eq 0 ]; then
        echo "✅ $1 completed successfully"
    else
        echo "⚠️  $1 failed, but continuing..."
        return 0
    fi
}

# Wait for database to be ready (production-like timeout)
echo "🔍 Waiting for database connection..."
retry_count=0
max_retries=60
until python -c "
import os
import django
from django.conf import settings
from django.core.management import execute_from_command_line
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'grey_lit_project.settings.staging')
django.setup()
from django.db import connection
try:
    connection.ensure_connection()
    print('Database connected!')
except Exception as e:
    print(f'Database not ready: {e}')
    exit(1)
" 2>/dev/null; do
    retry_count=$((retry_count + 1))
    if [ $retry_count -ge $max_retries ]; then
        echo "❌ Database connection timeout after ${max_retries} attempts"
        exit 1
    fi
    echo "⏳ Waiting for database... (attempt $retry_count/$max_retries)"
    sleep 5
done
check_success "Database connection"

# Wait for Redis (Celery broker) to be ready - critical for staging
echo "🔍 Checking Redis connection..."
retry_count=0
max_retries=30
until python -c "
import redis
import os
from django.conf import settings
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'grey_lit_project.settings.staging')
django.setup()
try:
    redis_url = getattr(settings, 'CELERY_BROKER_URL', 'redis://redis_staging:6379/0')
    r = redis.from_url(redis_url)
    r.ping()
    print('Redis connected!')
except Exception as e:
    print(f'Redis not ready: {e}')
    exit(1)
" 2>/dev/null; do
    retry_count=$((retry_count + 1))
    if [ $retry_count -ge $max_retries ]; then
        echo "❌ Redis connection timeout after ${max_retries} attempts"
        exit 1
    fi
    echo "⏳ Waiting for Redis... (attempt $retry_count/$max_retries)"
    sleep 3
done
check_success "Redis connection"

# Show environment information
echo "📊 Staging Environment Info:"
python -c "
import django
import sys
import os
print(f'Python: {sys.version.split()[0]}')
print(f'Django: {django.get_version()}')
print(f'Settings Module: {os.environ.get(\"DJANGO_SETTINGS_MODULE\", \"Not set\")}')
"

# Create necessary directories
echo "📁 Creating staging directories..."
mkdir -p /app/media /app/logs /app/staticfiles
check_success "Directory creation"

# Run database migrations (production-safe)
echo "🗄️  Running database migrations..."
python manage.py migrate --check
check_success "Migration check"

python manage.py migrate
check_success "Database migrations"

# Check migration state for validation
echo "🔍 Validating migration state..."
python -c "
from django.db import connection
try:
    with connection.cursor() as cursor:
        cursor.execute(\"\"\"
            SELECT COUNT(*) FROM django_migrations
        \"\"\")
        total_migrations = cursor.fetchone()[0]
        print(f'ℹ️  Total applied migrations: {total_migrations}')
        
        # Check for any unapplied migrations
        from django.core.management import execute_from_command_line
        import sys
        from io import StringIO
        
        old_stdout = sys.stdout
        sys.stdout = mystdout = StringIO()
        try:
            execute_from_command_line(['manage.py', 'showmigrations', '--list'])
            output = mystdout.getvalue()
            if '[ ]' in output:
                print('⚠️  Warning: Unapplied migrations detected')
                sys.stdout = old_stdout
                print(output)
            else:
                sys.stdout = old_stdout
                print('✅ All migrations applied')
        except:
            sys.stdout = old_stdout
            print('⚠️  Could not check migration status')
except Exception as e:
    print(f'ℹ️  Migration state check failed: {e}')
"

# Create cache table (production requirement)
echo "💾 Setting up cache table..."
python manage.py createcachetable
check_success "Cache table creation"

# Collect static files (production-like)
echo "📦 Collecting static files..."
python manage.py collectstatic --noinput -v 1
check_success "Static files collection"

# Create staging superuser if requested
if [ "${CREATE_SUPERUSER:-false}" = "true" ]; then
    echo "👤 Creating staging superuser..."
    python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
admin_email = '${ADMIN_EMAIL:-staging.admin@localhost}'
admin_username = '${ADMIN_USERNAME:-staging_admin}'
admin_password = '${ADMIN_PASSWORD:-staging_admin_123}'

if not User.objects.filter(username=admin_username).exists():
    User.objects.create_superuser(admin_username, admin_email, admin_password)
    print(f'✅ Staging superuser \"{admin_username}\" created with email: {admin_email}')
    print(f'🔑 Password: {admin_password}')
else:
    print(f'ℹ️  Staging superuser \"{admin_username}\" already exists')
" || echo "⚠️  Superuser creation failed"
fi

# Production-like system checks
echo "🔍 Running Django system checks..."
python manage.py check --deploy
check_success_continue "Django system checks"

# Validate settings
echo "🔍 Validating staging configuration..."
python -c "
from django.conf import settings
import os

# Check critical settings
critical_settings = {
    'DEBUG': getattr(settings, 'DEBUG', None),
    'SECRET_KEY': bool(getattr(settings, 'SECRET_KEY', '')),
    'ALLOWED_HOSTS': getattr(settings, 'ALLOWED_HOSTS', []),
    'DATABASES': bool(getattr(settings, 'DATABASES', {})),
    'STATIC_URL': getattr(settings, 'STATIC_URL', None),
    'MEDIA_URL': getattr(settings, 'MEDIA_URL', None),
}

print('📋 Critical Settings Validation:')
for setting, value in critical_settings.items():
    if setting == 'SECRET_KEY':
        print(f'   {setting}: {\"✅ Set\" if value else \"❌ Missing\"}')
    elif setting == 'DATABASES':
        print(f'   {setting}: {\"✅ Configured\" if value else \"❌ Missing\"}')
    else:
        print(f'   {setting}: {value}')

# Check if we're in production-like mode
if getattr(settings, 'DEBUG', True):
    print('⚠️  Warning: DEBUG=True in staging environment')
else:
    print('✅ DEBUG=False (production-like)')

print(f'📍 Environment: {os.environ.get(\"ENVIRONMENT\", \"Unknown\")}')
"

# Show final status
echo "=============================================="
echo "📊 Staging Environment Ready:"
echo "- Database migrations: ✅"
echo "- Cache table: ✅"
echo "- Static files: ✅"
echo "- Redis connection: ✅"
echo "- System checks: ✅"
echo "- Admin interface: http://localhost:${PORT:-8000}/admin/"
if [ "${CREATE_SUPERUSER:-false}" = "true" ]; then
    echo "- Admin login: ${ADMIN_USERNAME:-staging_admin} / ${ADMIN_PASSWORD:-staging_admin_123}"
fi
echo "=============================================="

# Handle different run modes
case "${1:-production-server}" in
    "production-server"|"gunicorn"|"")
        echo "🚀 Starting Gunicorn+Uvicorn ASGI server (staging mode)..."
        echo "🔗 Access at: http://localhost:${PORT:-8000}/"
        echo "⚡ Press Ctrl+C to stop"
        exec gunicorn grey_lit_project.asgi:application \
            --bind 0.0.0.0:${PORT:-8000} \
            --workers ${GUNICORN_WORKERS:-4} \
            --worker-class uvicorn.workers.UvicornWorker \
            --max-requests ${GUNICORN_MAX_REQUESTS:-10000} \
            --max-requests-jitter ${GUNICORN_MAX_REQUESTS_JITTER:-100} \
            --timeout ${GUNICORN_TIMEOUT:-120} \
            --keepalive ${GUNICORN_KEEPALIVE:-65} \
            --access-logfile - \
            --error-logfile - \
            --log-level info
        ;;
    "worker")
        echo "🔄 Starting Celery worker (staging mode)..."
        exec celery -A grey_lit_project worker \
            -l info \
            --concurrency=${CELERY_CONCURRENCY:-4} \
            --max-tasks-per-child=1000 \
            --time-limit=300 \
            --soft-time-limit=240
        ;;
    "beat")
        echo "⏰ Starting Celery beat scheduler (staging mode)..."
        exec celery -A grey_lit_project beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
        ;;
    "daphne")
        echo "🔌 Starting Daphne ASGI server (staging mode)..."
        echo "🔗 WebSocket server at: http://localhost:${PORT:-8000}/"
        echo "⚡ Press Ctrl+C to stop"
        exec daphne -b 0.0.0.0 -p ${PORT:-8000} \
            --proxy-headers \
            --access-log - \
            grey_lit_project.asgi:application
        ;;
    "shell")
        echo "🐍 Starting Django shell (staging environment)..."
        exec python manage.py shell
        ;;
    "test")
        echo "🧪 Running tests (staging configuration)..."
        exec python manage.py test ${@:2}
        ;;
    *)
        echo "🎯 Executing custom command: $@"
        exec "$@"
        ;;
esac