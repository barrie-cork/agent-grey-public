#!/bin/bash
#
# Production startup script with migration fix
# This script handles the status_detail column migration conflict
#

set -e  # Exit on any error

echo "🚀 Starting Agent Grey with migration fix..."

# Function to run Django management commands
run_django_cmd() {
    python manage.py "$@"
}

echo "📋 Checking and fixing migration state..."

# Run our migration state fix command
echo "🔧 Running migration state fix..."
run_django_cmd fix_migration_state

echo "📦 Running database migrations..."
run_django_cmd migrate --verbosity=2

echo "📄 Collecting static files..."
run_django_cmd collectstatic --noinput --verbosity=2

echo "🗄️ Creating cache table..."
run_django_cmd createcachetable --verbosity=2 || true

echo "✅ Running system checks..."
run_django_cmd check --deploy

echo "🎉 Migration fix and setup completed successfully!"

# Start the application
echo "🌐 Starting Gunicorn server..."
exec gunicorn grey_lit_project.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 4 \
    --threads 2 \
    --timeout 120 \
    --keepalive 10 \
    --max-requests 10000 \
    --max-requests-jitter 100 \
    --preload \
    --access-logfile - \
    --error-logfile -