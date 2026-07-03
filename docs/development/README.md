# Development Documentation

**Status**: Active
**Last Updated**: 2025-10-14

## Overview

This directory contains guides and best practices for Agent Grey development.

---

## Getting Started

### Essential Reading

1. **[IDE Setup](./IDE_SETUP.md)** - Configure your development environment
2. **[Code Quality](./CODE_QUALITY.md)** - Linting, formatting, and testing standards
3. **[Git Workflow](./git-workflow-guide.md)** - Branching, commits, and PRs

### Quick Links

- [Main README](../../README.md) - Project overview
- [CLAUDE.md](../../CLAUDE.md) - Claude Code AI assistant guide
- [CI/CD](../ci-cd/) - Continuous integration documentation
- [Testing](../testing/) - Test suite documentation

---

## Guides by Topic

### Database & Migrations

| Guide | Description | When to Use |
|-------|-------------|-------------|
| **[Database Migrations Guide](./database-migrations-guide.md)** | Comprehensive guide to writing cross-database migrations | Writing complex migrations, troubleshooting migration errors |
| **[Migrations Quick Reference](./migrations-quick-reference.md)** | Quick patterns and troubleshooting | Quick lookup during development |

**Key Topics**:
- PostgreSQL vs SQLite compatibility
- Primary key type changes (integer → UUID)
- PostgreSQL-specific features (ArrayField, schemas)
- `SeparateDatabaseAndState` pattern
- Migration testing procedures

### Code Quality

| Guide | Description | When to Use |
|-------|-------------|-------------|
| **[Code Quality](./CODE_QUALITY.md)** | Linting, formatting, testing standards | Daily development, PR reviews |
| **[AI Code Review](./ai-code-review.md)** | Automated code review with GitHub Actions | Understanding CI checks |

**Key Topics**:
- Flake8 configuration
- Black formatting
- isort import sorting
- Pre-commit hooks

### CI/CD

| Guide | Description | When to Use |
|-------|-------------|-------------|
| **[CI Improvements Summary](./ci-improvements-summary.md)** | GitHub Actions workflow enhancements | Understanding CI pipeline |
| **[Environment Rebuild Guide](./ENVIRONMENT-REBUILD-GUIDE.md)** | Rebuilding development environment | Docker issues, dependency updates |

**Key Topics**:
- GitHub Actions workflows
- Docker compose configuration
- Environment variables
- Secret management

### Version Control

| Guide | Description | When to Use |
|-------|-------------|-------------|
| **[Git Workflow](./git-workflow-guide.md)** | Branching strategy, commit messages, PRs | Daily git operations |

**Key Topics**:
- Feature branch workflow
- Conventional commit messages
- Pull request process
- Merge strategies

---

## Common Development Tasks

### Starting Development

```bash
# Clone repository
git clone https://github.com/barrie-cork/agent-grey.git
cd agent-grey

# Start services
docker compose up -d

# Run migrations
docker compose exec web python manage.py migrate

# Create superuser
docker compose exec web python manage.py createsuperuser

# Access application
open http://localhost:8000
```

### Running Tests

```bash
# All tests
docker compose exec web python manage.py test

# Specific app
docker compose exec web python manage.py test apps.core

# With coverage
docker compose exec web coverage run --source='.' manage.py test
docker compose exec web coverage report
```

### Code Quality Checks

```bash
# Run all checks
docker compose exec web flake8
docker compose exec web python -m black --check .
docker compose exec web isort --check-only .

# Auto-fix formatting
docker compose exec web python -m black .
docker compose exec web isort .
```

### Database Operations

```bash
# Create migrations
docker compose exec web python manage.py makemigrations

# Apply migrations
docker compose exec web python manage.py migrate

# Check migration status
docker compose exec web python manage.py showmigrations

# SQL for migration
docker compose exec web python manage.py sqlmigrate app_name migration_name
```

### Django Shell

```bash
# Standard shell
docker compose exec web python manage.py shell

# Shell Plus (if installed)
docker compose exec web python manage.py shell_plus
```

---

## Development Standards

### Django Coding Standards

- Follow [PEP 8](https://peps.python.org/pep-0008/)
- Follow [Django Coding Style](https://docs.djangoproject.com/en/dev/internals/contributing/writing-code/coding-style/)
- Use Class-Based Views (CBVs) where appropriate
- Use UUID primary keys for all models
- Document all public APIs with docstrings

### Template Standards

- Use Django template inheritance
- `{% extends %}` must be first line
- Load template tags at top of file
- Use `{{ variable }}` with exactly one space

### Migration Standards

- **Test on both PostgreSQL and SQLite** before committing
- Use database vendor checks for backend-specific features
- Document why migrations are database-specific
- Test migrations with existing data

See: [Database Migrations Guide](./database-migrations-guide.md)

### Testing Standards

- Maintain >80% test coverage
- Write tests for all new features
- Test both success and failure paths
- Mock external API calls

See: [Testing Documentation](../testing/)

### Git Standards

- Use conventional commit messages
- Create feature branches for all changes
- Squash commits before merging
- Include ticket numbers in commit messages

See: [Git Workflow Guide](./git-workflow-guide.md)

---

## Troubleshooting

### Common Issues

| Problem | Solution | Guide |
|---------|----------|-------|
| Migration errors | Check database compatibility | [Database Migrations](./database-migrations-guide.md#troubleshooting) |
| Docker build fails | Rebuild without cache | [Environment Rebuild](./ENVIRONMENT-REBUILD-GUIDE.md) |
| Tests fail in CI | Check PostgreSQL vs SQLite | [Migrations Quick Reference](./migrations-quick-reference.md#troubleshooting) |
| Port already in use | Stop conflicting service | `docker compose down && docker compose up -d` |
| Import errors | Rebuild dependencies | `docker compose build --no-cache web` |

### Debug Commands

```bash
# Check Django configuration
docker compose exec web python manage.py check
docker compose exec web python manage.py check --deploy

# Database connection test
docker compose exec web python manage.py shell -c "from django.db import connection; connection.ensure_connection(); print('DB: Connected')"

# View logs
docker compose logs -f web
docker compose logs -f celery_worker

# Service status
docker compose ps
```

---

## Project Architecture

### Apps

- **`apps.core`** - Shared utilities, metrics, configuration
- **`apps.accounts`** - UUID-based authentication
- **`apps.review_manager`** - 9-state workflow orchestration
- **`apps.search_strategy`** - PIC framework implementation
- **`apps.serp_execution`** - Search API integration
- **`apps.results_manager`** - Result processing pipeline
- **`apps.review_results`** - Manual review interface
- **`apps.reporting`** - PRISMA-compliant exports
- **`apps.feedback`** - User feedback system
- **`apps.health`** - Health check endpoints

### Key Technologies

- **Backend**: Django 5.1 LTS, Python 3.12
- **Database**: PostgreSQL 15 (production), SQLite 3 (tests)
- **Cache**: Redis 7
- **Background Tasks**: Celery + Dramatiq
- **Frontend**: Django Templates, Bootstrap 5, Vanilla JS
- **Monitoring**: Sentry + custom Prometheus metrics (`prometheus_client`) exposed at `/prometheus/metrics`

---

## Contributing

### Before Opening a PR

1. Run all tests locally
2. Run code quality checks
3. Update documentation if needed
4. Write/update tests for changes
5. Test on both PostgreSQL and SQLite (if migrations changed)

### PR Checklist

- [ ] Tests pass locally
- [ ] Code quality checks pass
- [ ] Documentation updated
- [ ] Conventional commit messages
- [ ] No merge conflicts
- [ ] Migrations tested on both databases

---

## Additional Resources

### Internal Documentation

- [Features](../features/) - Feature-specific documentation
- [Testing](../testing/) - Test suite and testing guides
- [Deployment](../deployment/) - Production deployment guides
- [Monitoring](../monitoring/) - Observability and monitoring
- [Security](../security/) - Security guidelines and reports

### External Resources

- [Django Documentation](https://docs.djangoproject.com/)
- [Python Documentation](https://docs.python.org/3/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Docker Documentation](https://docs.docker.com/)

---

## Questions & Support

1. **Check documentation** - Search this directory and related docs
2. **Search closed issues** - [GitHub Issues](https://github.com/barrie-cork/agent-grey/issues?q=is%3Aissue+is%3Aclosed)
3. **Check commit messages** - Often contain detailed explanations
4. **Ask the team** - Create a new GitHub issue

---

**Maintained by**: Development Team
**Review Schedule**: Quarterly or after major changes
**Last Review**: 2025-10-14
