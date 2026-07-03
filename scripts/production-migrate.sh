#!/bin/bash
#
# Production-safe migration script for Agent Grey
# Handles the status_detail column migration conflict robustly
#
# Usage: ./scripts/production-migrate.sh

set -e  # Exit on any error

echo "🔍 Starting production-safe migration process..."

# Function to run Django management commands
run_django_cmd() {
    python manage.py "$@"
}

# Check if we're in the right directory
if [ ! -f "manage.py" ]; then
    echo "❌ Error: manage.py not found. Please run from project root."
    exit 1
fi

# Step 1: Check current migration state
echo "📋 Checking current migration state..."
run_django_cmd fix_migration_state --dry-run

# Step 2: Fix any migration state issues
echo "🔧 Fixing migration state if needed..."
run_django_cmd fix_migration_state

# Step 3: Run migrations normally
echo "📦 Running database migrations..."
run_django_cmd migrate --verbosity=2

# Step 4: Collect static files
echo "📄 Collecting static files..."
run_django_cmd collectstatic --noinput --verbosity=2

# Step 5: Create cache table if it doesn't exist
echo "🗄️ Creating cache table..."
run_django_cmd createcachetable --verbosity=2 || true

# Step 6: Run Django system checks
echo "✅ Running system checks..."
run_django_cmd check --deploy

echo "🎉 Production migration completed successfully!"
echo "📊 Migration summary:"
run_django_cmd showmigrations --verbosity=2