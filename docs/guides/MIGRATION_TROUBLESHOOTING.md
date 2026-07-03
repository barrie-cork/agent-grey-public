# Migration Troubleshooting Guide

## Problem: status_detail Column Migration Conflict

### Issue Description
The migration `0010_searchsession_status_detail` fails with:
```
django.db.utils.ProgrammingError: column "status_detail" of relation "search_sessions" already exists
```

This occurs when the `status_detail` column exists in the database but Django's migration state doesn't record it as applied.

### Root Cause
- Column was added manually or through a previous deployment
- Migration state in `django_migrations` table is out of sync with actual database schema
- Development and production databases have different migration histories

## Robust Solution: Option 3 Implementation

### 1. Management Command Approach
We created `apps/review_manager/management/commands/fix_migration_state.py` which:

- **Checks actual database schema** using `information_schema`
- **Compares with Django migration records** in `django_migrations` table
- **Safely marks migration as applied** if column exists but migration not recorded
- **Provides dry-run mode** for safe testing

### 2. Production-Safe Migration Script
The `scripts/production-migrate.sh` script:

- **Runs diagnostics first** with `--dry-run` mode
- **Fixes migration state** automatically
- **Proceeds with normal migrations** after state is consistent
- **Includes comprehensive logging** for troubleshooting
- **Runs deployment checks** to verify success

### 3. GitHub Actions Integration
The production deployment workflow:

- **Uses the robust migration script** instead of direct `migrate` command
- **Runs as a one-off container job** to ensure proper environment
- **Waits for completion** before proceeding with health checks
- **Provides detailed logging** of migration process

## Usage Instructions

### Local Development
```bash
# Check migration state
python manage.py fix_migration_state --dry-run

# Fix migration state if needed
python manage.py fix_migration_state

# Run normal migrations
python manage.py migrate
```

### Production Deployment
```bash
# Automated via deployment script
./scripts/production-migrate.sh

# Or manual step-by-step
python manage.py fix_migration_state
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check --deploy
```


## Why This is Robust

### ✅ **Proper Django Integration**
- Uses Django's `MigrationRecorder` class
- Respects Django's migration dependency system
- Maintains migration history integrity

### ✅ **Safe State Management**
- Checks actual database schema before making changes
- Never assumes migration state without verification
- Provides rollback capabilities

### ✅ **Production-Ready**
- Comprehensive error handling and logging
- Dry-run mode for testing
- Integration with deployment pipelines

### ✅ **Maintainable**
- Clear documentation and comments
- Follows Django best practices
- Easy to understand and modify

## Alternative Approaches (Not Recommended)

### ❌ Raw SQL in Migrations
- Bypasses Django's migration system
- Not portable across databases
- Difficult to maintain and debug

### ❌ Manual Migration Editing
- Can break migration dependencies
- Risk of data loss or corruption
- Not repeatable across environments

### ❌ Migration Reset
- Loses migration history
- Requires database recreation
- Not suitable for production systems

## Future Prevention

### Best Practices
1. **Never add columns manually** in production
2. **Always use Django migrations** for schema changes
3. **Test migrations in staging** before production
4. **Keep migration history consistent** across environments
5. **Use version control** for all migration files

### Monitoring
- Regular checks of migration state consistency
- Automated deployment pipeline validation
- Database schema drift detection

## Troubleshooting Commands

```bash
# Show current migration status
python manage.py showmigrations

# Show fake migrations
python manage.py showmigrations --verbosity=2

# Check specific app migrations
python manage.py showmigrations review_manager

# Verify database schema
python manage.py dbshell
\d review_manager_searchsession

# Test migration state fix
python manage.py fix_migration_state --dry-run
```

This approach ensures reliable, maintainable, and production-safe migration handling while following Django best practices.
