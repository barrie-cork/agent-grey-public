# Django Migrations Quick Reference

**Quick access guide for common migration patterns and solutions.**

## Quick Links

- [Full Guide](./database-migrations-guide.md) - Comprehensive documentation
- [Testing](../testing/README.md) - Test migration procedures
- [Troubleshooting](#troubleshooting) - Common errors and fixes

---

## Common Patterns

### Check Database Backend

```python
def my_migration(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        # PostgreSQL code
    elif schema_editor.connection.vendor == "sqlite":
        # SQLite code
```

### PostgreSQL-Only Features

```python
def create_pg_feature(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("CREATE SCHEMA ...")

class Migration(migrations.Migration):
    operations = [
        migrations.RunPython(create_pg_feature, migrations.RunPython.noop),
    ]
```

### Database-Specific with State Sync

```python
class Migration(migrations.Migration):
    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(db_operation),
            ],
            state_operations=[
                migrations.AddField(...),
                migrations.RemoveField(...),
            ],
        ),
    ]
```

---

## Troubleshooting

### Error: "duplicate column name: id"

**Fix**: Use `SeparateDatabaseAndState` + table recreation for SQLite

**See**: [Full Guide - Primary Key Change](./database-migrations-guide.md#2-primary-key-type-change-integer--uuid)

### Error: "near \"[]\": syntax error"

**Fix**: Use PostgreSQL for tests or convert ArrayField to JSONField

```python
# settings/test.py
if "DATABASE_URL" in os.environ:
    DATABASES = {"default": dj_database_url.parse(os.environ["DATABASE_URL"])}
```

**See**: [Full Guide - ArrayField](./database-migrations-guide.md#3-arrayfield-postgresql-only)

### Error: "relation X does not exist"

**Fix**: Use memory backend for app in test settings

```python
# settings/test.py
CONSTANCE_BACKEND = "constance.backends.memory.MemoryBackend"
```

**See**: [Full Guide - Case Study 3](./database-migrations-guide.md#case-study-3-constance-database-timing-issue)

### Error: "multiple primary keys"

**Fix**: Convert redundant migration to no-op

```python
class Migration(migrations.Migration):
    """No-op - handled by previous migration."""
    operations = []
```

---

## Testing Checklist

```bash
# Test SQLite
rm -f test_db.sqlite3
python manage.py migrate --settings=grey_lit_project.settings.test

# Test PostgreSQL
docker compose exec web python manage.py migrate
docker compose exec db psql -U thesis_grey_user -d thesis_grey_dev_db -c "\d table_name"

# Run CI tests
git push origin main
# Monitor: https://github.com/barrie-cork/agent-grey/actions
```

---

## Quick Decision Tree

```
Do you need PostgreSQL-specific features?
├─ YES → Use vendor check, skip on SQLite
└─ NO  → Can you use standard Django operations?
    ├─ YES → Use standard migrations
    └─ NO  → Do you need to change primary key?
        ├─ YES → Use SeparateDatabaseAndState + table recreation
        └─ NO  → Use RunPython with vendor check
```

---

## Key Files

| File | Purpose |
|------|---------|
| `apps/core/migrations/0005_*.py` | UUID PK conversion example |
| `apps/core/migrations/0003_*.py` | PostgreSQL schema example |
| `grey_lit_project/settings/test.py` | Test database configuration |
| `.github/workflows/test.yml` | CI migration testing |

---

## Need Help?

1. Check [Full Guide](./database-migrations-guide.md) for detailed patterns
2. Review commit messages for migration fixes
3. Search [closed issues](https://github.com/barrie-cork/agent-grey/issues?q=is%3Aissue+is%3Aclosed+migration)
4. Check [Django Docs](https://docs.djangoproject.com/en/5.1/topics/migrations/)

---

**Last Updated**: 2025-10-14
