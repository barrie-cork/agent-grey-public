# Code Quality Guide

This guide covers code quality tools, standards, and workflows for Agent Grey.

## Quick Start

### Automated Setup (Recommended)

```bash
# Run the setup script
./scripts/setup-linting.sh

# Or manually:
pip install flake8 black isort pre-commit
pre-commit install
```

### Manual IDE Configuration

See [IDE_SETUP.md](./IDE_SETUP.md) for detailed IDE-specific instructions.

## Code Quality Tools

### 1. Flake8 (Linting)

**Purpose**: Catch coding errors, enforce style, and detect code smells.

**Configuration**: `.flake8` in project root

**Usage**:
```bash
# Check entire project
flake8

# Check specific file
flake8 apps/core/logging_config.py

# Check with statistics
flake8 --statistics --count
```

**Key Rules**:
- Max line length: 120 characters
- No unused imports (F401)
- No undefined names (F821)
- No unused variables (F841)
- Proper whitespace around operators (E226)
- No bare except clauses (E722)

### 2. Black (Auto-formatting)

**Purpose**: Consistent code formatting (optional, not enforced).

**Usage**:
```bash
# Format entire project
black .

# Check without modifying
black --check .

# Format specific file
black apps/core/logging_config.py
```

### 3. Pre-commit Hooks

**Purpose**: Run checks automatically before commits.

**Configuration**: `.pre-commit-config.yaml`

**Hooks Included**:
- ✅ **Automatic** (always run):
  - Trailing whitespace removal
  - End-of-file fixing
  - Merge conflict detection
  - Critical flake8 checks (syntax errors, undefined names)

- 🔧 **Manual** (run with `--hook-stage manual`):
  - Full flake8 style check
  - Django system check
  - Migration validation

**Usage**:
```bash
# Auto-runs on git commit
git commit -m "Your message"

# Run manually on all files
pre-commit run --all-files

# Run manual checks
pre-commit run --all-files --hook-stage manual

# Update hooks
pre-commit autoupdate

# Skip hooks (use sparingly)
git commit --no-verify -m "Emergency fix"
```

## Workflow

### Before Committing

1. **IDE shows issues**: Fix as you code (if IDE integration enabled)
2. **Pre-commit runs**: Automatic checks on `git commit`
3. **Fix any issues**: Hooks will prevent commit if critical errors found

### In CI/CD

GitHub Actions runs:
1. ✅ Flake8 code quality check
2. ✅ Django system check
3. ✅ Test suite
4. ✅ Build verification

## Common Issues & Fixes

### E226: Missing whitespace around operator

**❌ Bad:**
```python
result = value/100
progress = i+1
```

**✅ Good:**
```python
result = value / 100
progress = i + 1
```

### F401: Unused import

**❌ Bad:**
```python
from django.db import models
from django.utils import timezone  # Not used anywhere
```

**✅ Good:**
```python
from django.db import models
# Removed unused import
```

**Alternative** (if intentional):
```python
from django.utils import timezone  # noqa: F401
```

### F841: Unused variable

**❌ Bad:**
```python
result = expensive_computation()
# result never used
```

**✅ Good:**
```python
_ = expensive_computation()  # Explicitly ignore
# Or better: remove if truly unused
```

### E501: Line too long

**❌ Bad:**
```python
message = f"This is a very long error message that exceeds the 120 character limit and should be split"
```

**✅ Good:**
```python
message = (
    f"This is a very long error message that exceeds "
    f"the 120 character limit and should be split"
)
```

### E722: Bare except

**❌ Bad:**
```python
try:
    risky_operation()
except:
    pass
```

**✅ Good:**
```python
try:
    risky_operation()
except Exception as e:
    logger.error(f"Operation failed: {e}")
```

## Excluding Files

### Temporary Exclusions

Add to `.flake8`:

```ini
[flake8]
per-file-ignores =
    apps/legacy_module/*:E501,F401
    apps/experimental/*:F841
```

### Permanent Exclusions

Add to `.flake8`:

```ini
[flake8]
exclude =
    */migrations/*,
    */tests/*,
    legacy_code/
```

## CI/CD Integration

### GitHub Actions

The workflow `.github/workflows/test.yml` runs:

```yaml
- name: Run flake8
  run: flake8 --statistics --count
```

**To pass CI**:
1. Fix all E and F series errors
2. C and W series warnings are acceptable (complexity, style preferences)
3. Use `# noqa` sparingly for legitimate exceptions

## Best Practices

### 1. Fix Issues Early

✅ Configure IDE linting → catch issues while coding
❌ Wait for CI to fail → slower feedback loop

### 2. Commit Frequently

✅ Small, focused commits → easier to debug linting issues
❌ Large commits → harder to fix violations

### 3. Use noqa Sparingly

✅ `# noqa: F401` for legitimate re-exports
❌ `# noqa` to hide actual problems

### 4. Run Manual Checks

Before submitting PR:
```bash
pre-commit run --all-files --hook-stage manual
python manage.py check --deploy
flake8
```

### 5. Keep Tools Updated

```bash
pre-commit autoupdate
pip install --upgrade flake8 black isort
```

## Metrics

### Current Code Quality (as of fix)

- ✅ 0 critical errors (E, F series)
- ⚠️  ~30 complexity warnings (C901) - acceptable
- ⚠️  ~10 style preferences (W504) - acceptable
- ✅ All CI checks passing

### Goals

- Maintain 0 critical errors
- Reduce complexity warnings gradually through refactoring
- Keep test coverage > 80%
- All new code passes full flake8 check

## Resources

- **Flake8 docs**: https://flake8.pycqa.org/
- **Error codes**: https://www.flake8rules.com/
- **Pre-commit**: https://pre-commit.com/
- **Black**: https://black.readthedocs.io/
- **PEP 8**: https://pep8.org/

## Troubleshooting

### "Flake8 not found"

```bash
# Install in virtualenv
source venv/bin/activate
pip install flake8

# Or in Docker
docker compose exec web pip install flake8
```

### "Pre-commit not running"

```bash
# Reinstall hooks
pre-commit uninstall
pre-commit install

# Verify
pre-commit run --all-files
```

### "Too many errors"

```bash
# Focus on critical issues only
flake8 --select=E9,F

# Or use pre-commit critical checks
pre-commit run flake8-critical --all-files
```

## Getting Help

1. Check this guide and [IDE_SETUP.md](./IDE_SETUP.md)
2. Check [CLAUDE.md](../CLAUDE.md) for project-specific guidelines
3. Review `.flake8` configuration
4. Ask team members or create an issue

---

**Remember**: Code quality tools are here to help, not hinder. They catch real bugs and make code more maintainable. Happy coding! 🚀
