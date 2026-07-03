#!/bin/bash
# Migration Inconsistency Fix Script
#
# This script detects and fixes common migration inconsistencies where
# the database schema exists but Django's migration history is out of sync.
#
# Usage:
#   ./scripts/fix-migration-inconsistency.sh [app_label]
#
# Examples:
#   ./scripts/fix-migration-inconsistency.sh reporting
#   ./scripts/fix-migration-inconsistency.sh  # Check all apps

set -e  # Exit on error

# Colours for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Colour

APP_LABEL="${1:-}"

echo -e "${BLUE}🔍 Migration Inconsistency Fix Tool${NC}"
echo "======================================"

# Function to check if running in Docker
is_docker() {
    [ -f /.dockerenv ]
}

# Function to execute Django management commands
run_manage() {
    if is_docker; then
        python manage.py "$@"
    else
        docker-compose exec -T web python manage.py "$@"
    fi
}

# Function to execute PostgreSQL commands
run_psql() {
    if is_docker; then
        psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c "$1"
    else
        docker-compose exec -T db psql -U thesis_grey_user -d thesis_grey_dev_db -t -c "$1"
    fi
}

# Function to check table exists
table_exists() {
    local table_name="$1"
    local result=$(run_psql "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '$table_name');")
    echo "$result" | grep -q "t"
}

# Function to check if app has migrations applied
has_applied_migrations() {
    local app="$1"
    local count=$(run_psql "SELECT COUNT(*) FROM django_migrations WHERE app = '$app';")
    [ "$count" -gt 0 ]
}

# Function to get migration count
get_migration_count() {
    local app="$1"
    run_psql "SELECT COUNT(*) FROM django_migrations WHERE app = '$app';"
}

# Function to fix app migrations
fix_app_migrations() {
    local app="$1"

    echo -e "\n${BLUE}📦 Checking app: ${app}${NC}"

    # Get the main table name for the app (simplified - you may need to adjust)
    local expected_tables=(
        "reporting_exportreport" "export_reports"
        "accounts_user"
        "search_sessions"
        "review_sessions"
    )

    local has_tables=false
    for table in "${expected_tables[@]}"; do
        if table_exists "$table"; then
            echo -e "${GREEN}  ✓ Found table: $table${NC}"
            has_tables=true
            break
        fi
    done

    if ! $has_tables && [ "$app" != "contenttypes" ] && [ "$app" != "auth" ]; then
        echo -e "${YELLOW}  ⚠️  No tables found for $app - skipping${NC}"
        return
    fi

    # Check migration status
    local migration_count=$(get_migration_count "$app" | xargs)

    if [ "$migration_count" -eq 0 ]; then
        echo -e "${YELLOW}  ⚠️  No migrations recorded but tables exist${NC}"
        echo -e "${BLUE}  🔧 Applying migrations with --fake...${NC}"
        run_manage migrate "$app" --fake
        echo -e "${GREEN}  ✅ Migrations fake-applied${NC}"
    else
        echo -e "${GREEN}  ✓ $migration_count migrations already recorded${NC}"

        # Verify consistency
        echo -e "${BLUE}  🔍 Verifying migration consistency...${NC}"
        if run_manage migrate "$app" --check 2>&1 | grep -q "already exists\|duplicate"; then
            echo -e "${RED}  ❌ Inconsistency detected!${NC}"
            echo -e "${BLUE}  🔧 Attempting fix...${NC}"

            # Clear migration history
            run_psql "DELETE FROM django_migrations WHERE app = '$app';"
            echo -e "${YELLOW}  ⚠️  Cleared migration history for $app${NC}"

            # Fake-apply migrations
            run_manage migrate "$app" --fake
            echo -e "${GREEN}  ✅ Migrations re-applied with --fake${NC}"
        else
            echo -e "${GREEN}  ✅ No inconsistencies detected${NC}"
        fi
    fi
}

# Main execution
echo ""
echo -e "${BLUE}🏥 Starting migration health check...${NC}"

if [ -n "$APP_LABEL" ]; then
    # Fix specific app
    echo -e "${BLUE}Checking single app: $APP_LABEL${NC}"
    fix_app_migrations "$APP_LABEL"
else
    # Fix all apps with migrations
    echo -e "${BLUE}Checking all apps...${NC}"

    # Get list of apps from django_migrations
    APPS=$(run_psql "SELECT DISTINCT app FROM django_migrations ORDER BY app;" 2>/dev/null || echo "")

    if [ -z "$APPS" ]; then
        echo -e "${YELLOW}⚠️  No migrations found in database${NC}"
        echo -e "${BLUE}Running initial migrations...${NC}"
        run_manage migrate
    else
        for app in $APPS; do
            app=$(echo "$app" | xargs)  # Trim whitespace
            [ -z "$app" ] && continue
            fix_app_migrations "$app"
        done
    fi
fi

echo ""
echo -e "${GREEN}✅ Migration fix process complete!${NC}"
echo ""
echo -e "${BLUE}📋 Next steps:${NC}"
echo "  1. Restart your web container: docker-compose restart web"
echo "  2. Check logs: docker-compose logs web | tail -50"
echo "  3. Run health check: python scripts/check-migration-health.py"
echo ""
