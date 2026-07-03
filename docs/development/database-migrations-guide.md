# Database Migrations Guide

**Status**: Active
**Last Updated**: 2025-10-14
**Applies To**: Django 5.1+, PostgreSQL 15, SQLite 3

## Overview

This guide documents best practices for writing Django migrations that work correctly across multiple database backends, particularly PostgreSQL (production) and SQLite (CI tests).

## Table of Contents

1. [Key Principles](#key-principles)
2. [Database Vendor Checks](#database-vendor-checks)
3. [Common Migration Patterns](#common-migration-patterns)
4. [Case Studies](#case-studies)
5. [Testing Migrations](#testing-migrations)
6. [Troubleshooting](#troubleshooting)

---

## Key Principles

### 1. Database Portability

**Rule**: Write migrations that work on both PostgreSQL and SQLite unless there's a compelling reason not to.

**Why**:
- PostgreSQL is used in production
- SQLite is used in CI for fast tests
- Both must support the same migrations

**When to Use Database-Specific Code**:
- PostgreSQL-only features (e.g., `ArrayField`, GIN indexes, full-text search)
- SQLite limitations (e.g., limited ALTER TABLE support)
- Performance optimisations specific to one backend

### 2. State vs Database Operations

Django migrations track two things:
1. **Model state**: Django's understanding of what fields exist
2. **Database schema**: Actual tables and columns in the database

**Critical**: These must stay synchronised. Use `migrations.SeparateDatabaseAndState` when you need to manually manage this separation.

### 3. Migration Dependencies

Always check migration dependencies:
- Third-party apps (e.g., `constance`, `django_dramatiq`)
- Custom apps in your project
- Django built-in apps (`contenttypes`, `auth`)

---

## Database Vendor Checks

### Pattern: Check Database Backend

```python
from django.db import migrations

def migrate_forward(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        # PostgreSQL-specific code
        schema_editor.execute("ALTER TABLE ...")
    elif schema_editor.connection.vendor == "sqlite":
        # SQLite-specific code
        schema_editor.execute("CREATE TABLE ...")
    else:
        raise NotImplementedError(
            f"Migration not supported for {schema_editor.connection.vendor}"
        )

class Migration(migrations.Migration):
    operations = [
        migrations.RunPython(migrate_forward, migrations.RunPython.noop),
    ]
```

### Available Vendor Values

- `"postgresql"` - PostgreSQL
- `"sqlite"` - SQLite
- `"mysql"` - MySQL
- `"oracle"` - Oracle

---

## Common Migration Patterns

### 1. PostgreSQL-Only Features (Schema Creation)

**Use Case**: PostgreSQL schemas, GIN indexes, full-text search

**Pattern**: Skip operation on SQLite

```python
def create_metadata_schema(apps, schema_editor):
    """
    Create PostgreSQL metadata schema for codebase tracking.
    Skipped on SQLite as it doesn't support schemas.
    """
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            """
            CREATE SCHEMA IF NOT EXISTS _metadata;

            CREATE TABLE IF NOT EXISTS _metadata.codebase_meta (
                id INTEGER PRIMARY KEY DEFAULT 1,
                data JSONB NOT NULL DEFAULT '{}'::jsonb,
                CONSTRAINT single_row CHECK (id = 1)
            );
            """
        )

def drop_metadata_schema(apps, schema_editor):
    """Drop metadata schema (PostgreSQL only)."""
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("DROP SCHEMA IF EXISTS _metadata CASCADE;")

class Migration(migrations.Migration):
    operations = [
        migrations.RunPython(create_metadata_schema, drop_metadata_schema),
    ]
```

**Example**: `apps/core/migrations/0003_add_metadata_schema.py`

---

### 2. Primary Key Type Change (Integer → UUID)

**Use Case**: Converting an integer primary key to UUID

**Challenge**: PostgreSQL supports ALTER TABLE operations, but SQLite requires table recreation.

**Pattern**: Database-specific implementations with state synchronisation

```python
import json
import uuid
from django.db import migrations, models

def migrate_to_uuid_postgresql(apps, schema_editor):
    """PostgreSQL: Use ALTER TABLE operations."""
    # Step 1: Add temporary UUID field
    schema_editor.execute(
        "ALTER TABLE core_configuration ADD COLUMN temp_uuid_id UUID;"
    )

    # Step 2: Populate UUID values
    schema_editor.execute(
        """
        UPDATE core_configuration
        SET temp_uuid_id = gen_random_uuid()
        WHERE temp_uuid_id IS NULL;
        """
    )

    # Step 3: Make UUID field non-nullable
    schema_editor.execute(
        "ALTER TABLE core_configuration ALTER COLUMN temp_uuid_id SET NOT NULL;"
    )

    # Step 4: Drop old primary key
    schema_editor.execute(
        "ALTER TABLE core_configuration DROP CONSTRAINT core_configuration_pkey CASCADE;"
    )
    schema_editor.execute(
        "ALTER TABLE core_configuration DROP COLUMN id;"
    )

    # Step 5: Rename temp_uuid_id to id
    schema_editor.execute(
        "ALTER TABLE core_configuration RENAME COLUMN temp_uuid_id TO id;"
    )

    # Step 6: Add primary key constraint
    schema_editor.execute(
        "ALTER TABLE core_configuration ADD PRIMARY KEY (id);"
    )


def migrate_to_uuid_sqlite(apps, schema_editor):
    """SQLite: Recreate table with new schema."""
    Configuration = apps.get_model("core", "Configuration")

    # Get existing data
    existing_configs = list(
        Configuration.objects.values(
            'id', 'key', 'value', 'description', 'created_at',
            'updated_at', 'updated_by_id'
        )
    )

    # Create new table with UUID primary key
    schema_editor.execute(
        """
        CREATE TABLE core_configuration_new (
            id TEXT PRIMARY KEY NOT NULL,
            key VARCHAR(100) NOT NULL UNIQUE,
            value TEXT NOT NULL,
            description TEXT NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            updated_by_id INTEGER NULL,
            FOREIGN KEY (updated_by_id) REFERENCES accounts_user(id)
        );
        """
    )

    # Migrate data with new UUID primary keys
    for config_data in existing_configs:
        new_uuid = str(uuid.uuid4())
        # IMPORTANT: Serialize JSON for SQLite parameter binding
        value_json = json.dumps(config_data['value']) if isinstance(
            config_data['value'], dict
        ) else config_data['value']

        schema_editor.execute(
            """
            INSERT INTO core_configuration_new
                (id, key, value, description, created_at, updated_at, updated_by_id)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            [
                new_uuid,
                config_data['key'],
                value_json,
                config_data['description'],
                config_data['created_at'],
                config_data['updated_at'],
                config_data['updated_by_id'],
            ]
        )

    # Drop old table and rename
    schema_editor.execute("DROP TABLE core_configuration;")
    schema_editor.execute(
        "ALTER TABLE core_configuration_new RENAME TO core_configuration;"
    )


def migrate_to_uuid(apps, schema_editor):
    """Route to database-specific migration."""
    if schema_editor.connection.vendor == "postgresql":
        migrate_to_uuid_postgresql(apps, schema_editor)
    elif schema_editor.connection.vendor == "sqlite":
        migrate_to_uuid_sqlite(apps, schema_editor)
    else:
        raise NotImplementedError(
            f"UUID migration not implemented for {schema_editor.connection.vendor}"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_configuration_created_at"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            # Database operations (actual SQL changes)
            database_operations=[
                migrations.RunPython(migrate_to_uuid, migrations.RunPython.noop),
            ],
            # State operations (Django's understanding of schema)
            state_operations=[
                # Add temporary UUID field
                migrations.AddField(
                    model_name="configuration",
                    name="temp_uuid_id",
                    field=models.UUIDField(default=uuid.uuid4, null=True),
                ),
                # Remove old integer id
                migrations.RemoveField(
                    model_name="configuration",
                    name="id",
                ),
                # Rename temp_uuid_id to id
                migrations.RenameField(
                    model_name="configuration",
                    old_name="temp_uuid_id",
                    new_name="id",
                ),
            ],
        ),
    ]
```

**Key Points**:
- **PostgreSQL**: Use native ALTER TABLE support
- **SQLite**: Recreate table (SQLite limitation)
- **SeparateDatabaseAndState**: Keeps Django's state synchronised
- **JSON Serialisation**: SQLite doesn't support dict parameter binding

**Example**: `apps/core/migrations/0005_configuration_uuid_proper.py`

---

### 3. ArrayField (PostgreSQL-Only)

**Use Case**: Models using `django.contrib.postgres.fields.ArrayField`

**Problem**: ArrayField is PostgreSQL-only and causes SQLite errors

**Solution 1: Use PostgreSQL in Tests** (Recommended)

Update test settings to use PostgreSQL when `DATABASE_URL` is available:

```python
# grey_lit_project/settings/test.py
import os
from .base import *

if "DATABASE_URL" in os.environ:
    import dj_database_url

    DATABASES = {
        "default": dj_database_url.parse(
            os.environ["DATABASE_URL"],
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    # SQLite fallback for quick local tests
    # WARNING: Will fail on models using ArrayField
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "test_db.sqlite3",
        }
    }
```

**Solution 2: Use JSONField** (Alternative)

If SQLite compatibility is critical, use `JSONField` instead:

```python
# Before (PostgreSQL only)
from django.contrib.postgres.fields import ArrayField
from django.db import models

class SearchStrategy(models.Model):
    population_terms = ArrayField(
        models.CharField(max_length=200),
        default=list,
        blank=True,
    )

# After (Cross-database)
from django.db import models

class SearchStrategy(models.Model):
    population_terms = models.JSONField(
        default=list,
        blank=True,
        help_text="List of population search terms",
    )
```

**Trade-offs**:
- JSONField is less type-safe than ArrayField
- PostgreSQL-specific query operators won't work
- Validation must be done in Python, not database

---

### 4. No-Op Migrations

**Use Case**: Migration is no longer needed but must stay in chain

**Pattern**: Empty operations with clear documentation

```python
class Migration(migrations.Migration):
    """
    No-op migration - UUID conversion already handled by migration 0005.

    This migration was originally generated to alter the id field to UUID,
    but migration 0005 was later updated to handle the full UUID conversion
    including both database changes and Django state updates. This migration
    is kept for historical migration chain integrity but performs no operations.
    """

    dependencies = [
        ("core", "0005_configuration_uuid_proper"),
    ]

    operations = [
        # No operations needed - migration 0005 handles everything
    ]
```

**When to Use**:
- Migrations that became redundant after refactoring
- Avoiding migration conflicts in deployed environments
- Maintaining migration chain continuity

**Example**: `apps/core/migrations/0006_alter_configuration_id_alter_configuration_value.py`

---

## Case Studies

### Case Study 1: Core Configuration UUID Migration

**Problem**: Convert `Configuration` model from integer PK to UUID PK while maintaining data and supporting both PostgreSQL and SQLite.

**Context**:
- Production uses PostgreSQL
- CI tests use SQLite
- Model has existing data that must be preserved
- Foreign key relationships exist

**Solution**: Database-aware migration with state synchronisation

**Files**:
- Migration: `apps/core/migrations/0005_configuration_uuid_proper.py`
- Model: `apps/core/models.py`

**Lessons Learned**:
1. **SQLite Limitation**: Cannot ALTER TABLE to change primary key type
2. **Solution**: Recreate table with new schema on SQLite
3. **State Management**: Use `SeparateDatabaseAndState` to keep Django's state correct
4. **JSON Binding**: SQLite parameter binding doesn't support Python dicts
5. **UUID Generation**: PostgreSQL has `gen_random_uuid()`, SQLite needs Python `uuid.uuid4()`

**Commit**: `7802564`

---

### Case Study 2: ArrayField SQLite Incompatibility

**Problem**: `SearchStrategy` model uses `ArrayField` which is PostgreSQL-only, causing SQLite test failures with error:
```
sqlite3.OperationalError: near "[]": syntax error
```

**Context**:
- Test settings hardcoded SQLite backend
- GitHub Actions sets `DATABASE_URL` to PostgreSQL
- Django ignored `DATABASE_URL` due to hardcoded settings

**Solution**: Check for `DATABASE_URL` environment variable and use PostgreSQL when available

**Files**:
- Settings: `grey_lit_project/settings/test.py`
- Model: `apps/search_strategy/models.py`

**Code**:
```python
if "DATABASE_URL" in os.environ:
    import dj_database_url
    DATABASES = {
        "default": dj_database_url.parse(os.environ["DATABASE_URL"])
    }
else:
    # SQLite fallback
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", ...}}
```

**Lessons Learned**:
1. **Model Constraints**: PostgreSQL-specific field types require PostgreSQL tests
2. **Environment Detection**: Check for environment variables to support CI
3. **Graceful Degradation**: Provide SQLite fallback with clear warnings
4. **Documentation**: Document which features require PostgreSQL

**Commit**: `df15c07`

---

### Case Study 3: Constance Database Timing Issue

**Problem**: Tests fail with error:
```
psycopg2.errors.UndefinedTable: relation "constance_constance" does not exist
```

**Context**:
- Django-Constance tries to read from database during app initialization
- This happens **before** migrations complete
- Timing issue specific to test environment setup

**Solution**: Override Constance backend to use memory storage in tests

**Files**:
- Settings: `grey_lit_project/settings/test.py`

**Code**:
```python
# Override Constance backend to use memory instead of database
CONSTANCE_BACKEND = "constance.backends.memory.MemoryBackend"
```

**Lessons Learned**:
1. **Initialisation Order**: Some apps access database during import
2. **Test Isolation**: Tests should not depend on database state during setup
3. **Backend Flexibility**: Many Django apps support multiple backends
4. **Memory Backends**: Perfect for tests (fast, no dependencies)

**Commit**: `97197b3`

---

## Testing Migrations

### Local Testing

#### Test with SQLite
```bash
# Remove old database
rm -f test_db.sqlite3

# Run migrations
python manage.py migrate --settings=grey_lit_project.settings.test

# Verify schema (if sqlite3 available)
sqlite3 test_db.sqlite3 ".schema core_configuration"
```

#### Test with PostgreSQL (Docker)
```bash
# Ensure services are running
docker compose up -d

# Run migrations
docker compose exec web python manage.py migrate

# Check schema
docker compose exec db psql -U thesis_grey_user -d thesis_grey_dev_db -c "\d core_configuration"

# Verify data preservation
docker compose exec db psql -U thesis_grey_user -d thesis_grey_dev_db -c "SELECT id, key FROM core_configuration LIMIT 5;"
```

### GitHub Actions Testing

Migrations run automatically in CI:
- `.github/workflows/test.yml` line 179-181
- PostgreSQL service container (line 110-121)
- All migrations run before tests (line 180-181)

### Migration Testing Checklist

- [ ] **Fresh Database**: Test migration on empty database
- [ ] **Existing Data**: Test migration with sample data
- [ ] **Both Backends**: Test on PostgreSQL and SQLite
- [ ] **Reverse Migration**: Test migration rollback (if applicable)
- [ ] **Foreign Keys**: Verify FK relationships preserved
- [ ] **Indexes**: Check indexes are created correctly
- [ ] **Performance**: Test with realistic data volumes

---

## Troubleshooting

### Error: "duplicate column name: id"

**Cause**: Migration trying to add a column that already exists

**Solution**:
1. Check if migration uses `RenameField` (SQLite limitation)
2. Use table recreation pattern for SQLite
3. Separate database operations from state operations

**Example**: See Case Study 1

---

### Error: "near \"[]\": syntax error"

**Cause**: Using PostgreSQL-specific `ArrayField` with SQLite

**Solution**:
1. Use PostgreSQL for tests (recommended)
2. OR convert ArrayField to JSONField
3. Update test settings to check `DATABASE_URL`

**Example**: See Case Study 2

---

### Error: "relation \"constance_constance\" does not exist"

**Cause**: App trying to access database during initialization, before migrations run

**Solution**:
1. Override app backend to use memory storage in tests
2. Defer database access until after setup
3. Check app configuration in test settings

**Example**: See Case Study 3

---

### Error: "multiple primary keys for table X are not allowed"

**Cause**: Migration trying to add primary key where one already exists

**Solution**:
1. Check for redundant `AlterField` operations
2. Review migration dependencies
3. Convert redundant migration to no-op

**Pattern**:
```python
class Migration(migrations.Migration):
    """No-op migration - already handled by previous migration."""
    operations = []
```

---

### Error: "UndefinedTable: relation X does not exist"

**Cause**: Migration depends on table created by another app, but order is wrong

**Solution**:
1. Add explicit migration dependency
2. Check `INSTALLED_APPS` order
3. Ensure third-party app migrations run first

**Pattern**:
```python
class Migration(migrations.Migration):
    dependencies = [
        ("other_app", "0001_initial"),  # Explicit dependency
        ("my_app", "0002_previous"),
    ]
```

---

## Best Practices Summary

### DO ✅

- **Check database vendor** when using backend-specific features
- **Test on both** PostgreSQL and SQLite before committing
- **Use `SeparateDatabaseAndState`** for complex schema changes
- **Document** why migrations are database-specific
- **Serialize JSON** for SQLite parameter binding
- **Check dependencies** for third-party app migrations
- **Use memory backends** for apps in test settings when possible

### DON'T ❌

- **Don't assume** all Django operations work on all databases
- **Don't skip** migration testing on both backends
- **Don't use** `RenameField` for primary keys on SQLite
- **Don't access** database during app initialization
- **Don't hardcode** database backend in test settings if CI needs different backend
- **Don't create** redundant migrations that repeat operations
- **Don't ignore** migration warnings in CI logs

---

## References

### Django Documentation

- [Migrations](https://docs.djangoproject.com/en/5.1/topics/migrations/)
- [SeparateDatabaseAndState](https://docs.djangoproject.com/en/5.1/ref/migration-operations/#separatedatabaseandstate)
- [RunPython](https://docs.djangoproject.com/en/5.1/ref/migration-operations/#runpython)
- [Database Functions](https://docs.djangoproject.com/en/5.1/ref/databases/)

### Internal Documentation

- [Async Middleware](./async-middleware.md)
- [Testing Guide](../testing/README.md)
- [Django 5.2 Upgrade Notes](../upgrades/django-5-2-modernization-notes.md)

### Related Files

- `.github/workflows/test.yml` - CI migration testing
- `grey_lit_project/settings/test.py` - Test database configuration
- `apps/core/migrations/` - Migration examples

---

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2025-10-14 | 1.0 | Initial documentation covering UUID migration, ArrayField, and Constance fixes |

---

**Maintained by**: Development Team
**Review Schedule**: Quarterly or after major Django upgrades
**Questions**: Refer to migration commit messages or GitHub issues
