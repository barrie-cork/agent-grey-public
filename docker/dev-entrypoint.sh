#!/bin/bash

# Development entrypoint script for Agent Grey Django application
# Optimized for fast development workflow with live reloading

set -e

# Ensure UTC timezone
export TZ=UTC
if [ -f /etc/timezone ]; then
    echo "UTC" > /etc/timezone 2>/dev/null || true
fi
if [ -f /etc/localtime ]; then
    ln -sf /usr/share/zoneinfo/UTC /etc/localtime 2>/dev/null || true
fi

echo "🚀 Starting Agent Grey Development Environment"
echo "=============================================="
echo "Environment: Development"
echo "Django Settings: ${DJANGO_SETTINGS_MODULE:-grey_lit_project.settings.local}"
echo "Debug Mode: ${DEBUG:-True}"
echo "Port: ${PORT:-8000}"
echo "Timezone: ${TZ:-UTC}"
echo "=============================================="

# Function to check if a command succeeded
check_success() {
    if [ $? -eq 0 ]; then
        echo "✅ $1 completed successfully"
    else
        echo "⚠️  $1 failed, but continuing..."
        return 0
    fi
}

# Wait for database to be ready
echo "🔍 Waiting for database connection..."
python manage.py wait_for_db 2>/dev/null || {
    echo "⏳ Database connection check..."
    retry_count=0
    max_retries=30
    until python -c "
import os
import django
from django.conf import settings
from django.core.management import execute_from_command_line
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'grey_lit_project.settings.local')
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
            echo "⚠️ Database connection timeout after ${max_retries} attempts, continuing anyway..."
            echo "⚠️ Some functionality may not work until database is ready"
            break
        fi
        echo "⏳ Waiting for database... (attempt $retry_count/$max_retries)"
        sleep 3
    done
}
check_success "Database connection"

# Wait for Redis (Celery broker) to be ready
echo "🔍 Checking Redis connection..."
python -c "
import redis
import os
from django.conf import settings
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'grey_lit_project.settings.local')
django.setup()
try:
    redis_url = getattr(settings, 'CELERY_BROKER_URL', 'redis://redis:6379/0')
    r = redis.from_url(redis_url)
    r.ping()
    print('Redis connected!')
except Exception as e:
    print(f'Redis not ready: {e}')
    print('Note: Celery tasks will use database fallback')
" || echo "⚠️  Redis not available - Celery will use database fallback"

# Show Django version and configuration
echo "📊 Development Environment Info:"
python -c "
import django
import sys
print(f'Python: {sys.version.split()[0]}')
print(f'Django: {django.get_version()}')
"

# Create necessary directories
echo "📁 Creating development directories..."
mkdir -p /app/media /app/logs /app/.claude/logs
check_success "Directory creation"

# Run database migrations (development-friendly)
echo "🗄️  Running database migrations..."

# First, check for migration inconsistencies
echo "🔍 Checking for migration inconsistencies..."
python -c "
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.apps import apps

try:
    recorder = MigrationRecorder(connection)
    applied_migrations = set(recorder.migration_qs.values_list('app', 'name'))

    # Check if tables exist for models
    inconsistencies = []
    with connection.cursor() as cursor:
        for app_label in ['reporting', 'accounts', 'review_manager', 'search_strategy']:
            try:
                app_config = apps.get_app_config(app_label)
                for model in app_config.get_models():
                    table_name = model._meta.db_table
                    cursor.execute(
                        \"\"\"
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables
                            WHERE table_name = %s
                        )
                        \"\"\",
                        [table_name]
                    )
                    table_exists = cursor.fetchone()[0]

                    # Check if app has migrations
                    app_migrations = [m for (app, m) in applied_migrations if app == app_label]

                    if table_exists and not app_migrations:
                        inconsistencies.append((app_label, table_name))
            except LookupError:
                pass  # App not installed

    if inconsistencies:
        print(f'⚠️  Found {len(inconsistencies)} potential migration inconsistencies')
        for app, table in inconsistencies:
            print(f'   - {app}: table {table} exists but no migrations recorded')
        print('')
        print('💡 Tip: Run ./scripts/fix-migration-inconsistency.sh to fix')
        print('')
    else:
        print('✅ No migration inconsistencies detected')
except Exception as e:
    print(f'ℹ️  Migration consistency check skipped: {e}')
" || echo "⚠️  Migration consistency check failed - continuing"

# Now run migrations
python manage.py migrate --verbosity=1
check_success "Database migrations"

# Seed SERP provider configs (idempotent -- safe after flush/reset)
echo "🔌 Seeding SERP provider configs..."
python manage.py seed_provider_configs
check_success "SERP provider seeding"

# Check migration state (removed hardcoded 0007 reference)
echo "🔍 Checking migration state..."
python -c "
from django.db import connection
try:
    with connection.cursor() as cursor:
        cursor.execute(\"\"\"
            SELECT COUNT(*) FROM django_migrations
            WHERE app = 'core'
        \"\"\")
        migration_count = cursor.fetchone()[0]
        print(f'ℹ️  Core app has {migration_count} applied migrations')
except Exception as e:
    print(f'ℹ️  Migration state check skipped: {e}')
" || echo "⚠️  Migration state check failed - continuing"

# Create cache table if it doesn't exist
echo "💾 Setting up cache table..."
python manage.py createcachetable || true
check_success "Cache table creation"

# Create development superuser if requested
if [ "${CREATE_SUPERUSER:-false}" = "true" ]; then
    echo "👤 Creating development superuser..."
    python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
admin_email = '${ADMIN_EMAIL:-admin@localhost}'
admin_username = '${ADMIN_USERNAME:-admin}'
admin_password = '${ADMIN_PASSWORD:-admin123}'

if not User.objects.filter(username=admin_username).exists():
    User.objects.create_superuser(admin_username, admin_email, admin_password)
    print(f'✅ Superuser \"{admin_username}\" created with email: {admin_email}')
    print(f'🔑 Password: {admin_password}')
else:
    print(f'ℹ️  Superuser \"{admin_username}\" already exists')
" || echo "⚠️  Superuser creation failed"
fi

# Show final status
echo "=============================================="
echo "📊 Development Environment Ready:"
echo "- Database migrations: ✅"
echo "- Cache table: ✅"
echo "- Static files: Not needed (development server)"
echo "- Admin interface: http://localhost:${PORT:-8000}/admin/"
if [ "${CREATE_SUPERUSER:-false}" = "true" ]; then
    echo "- Admin login: ${ADMIN_USERNAME:-admin} / ${ADMIN_PASSWORD:-admin123}"
fi
echo "=============================================="

# Handle different run modes
case "${1:-runserver}" in
    "runserver"|"devserver"|"")
        echo "🌐 Starting Django development server..."
        echo "🔗 Access at: http://localhost:${PORT:-8000}/"
        echo "🔧 Live reloading enabled via volume mounts"
        echo "⚡ Press Ctrl+C to stop"
        exec python manage.py runserver 0.0.0.0:${PORT:-8000}
        ;;
    "worker")
        echo "🔄 Starting Celery worker..."
        exec celery -A grey_lit_project worker -l info --concurrency=${CELERY_CONCURRENCY:-2}
        ;;
    "beat")
        echo "⏰ Starting Celery beat scheduler..."
        exec celery -A grey_lit_project beat -l info
        ;;
    "flower")
        echo "🌸 Starting Flower (Celery monitoring)..."
        exec celery -A grey_lit_project flower --port=${FLOWER_PORT:-5555}
        ;;
    "daphne")
        echo "🔌 Starting Daphne ASGI server for WebSocket support..."
        echo "🔗 WebSocket server at: http://localhost:${PORT:-8001}/"
        echo "⚡ Press Ctrl+C to stop"
        exec daphne -b 0.0.0.0 -p ${PORT:-8001} grey_lit_project.asgi:application
        ;;
    "shell")
        echo "🐍 Starting Django shell..."
        exec python manage.py shell
        ;;
    "test")
        echo "🧪 Running tests..."
        exec python manage.py test ${@:2}
        ;;
    *)
        echo "🎯 Executing custom command: $@"
        exec "$@"
        ;;
esac
