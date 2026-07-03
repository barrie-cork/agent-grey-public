# GitHub Copilot Custom Instructions - Agent Grey

## Project Context

Agent Grey is a Django-based grey literature search and review application aligned with PRISMA 2020 systematic review reporting guidelines.

**Technology Stack**: Django 5.1.13 LTS, Python 3.12, PostgreSQL 15, Celery + Redis, Bootstrap 5

**Key Features**: 9-state workflow orchestration, PIC framework search query generation, dual-reviewer screening, PRISMA-compliant reporting for grey literature reviews

**Grey Literature Context**: Reviews non-traditional sources (government reports, policy documents, clinical guidelines) that typically lack structured abstracts and author information. Unlike database searches with full bibliographic metadata, grey literature reviews screen results based on title, snippet, and URL.

---

## Critical Rules

- **ALWAYS use Docker** -- never run Django natively (`docker compose up -d`)
- UUID primary keys for all models (`id = models.UUIDField(primary_key=True, default=uuid.uuid4)`)
- Use `apps.core.env_config` for environment variables (NOT `os.environ`)
- 9-state workflow with strict transitions (no state skipping)
- Tests MUST run in Docker with PostgreSQL (not SQLite)
- UK English spelling (organisation, colour, favour)
- No em dashes in documentation
- Rebuild Docker images after `requirements.txt` changes: `docker compose build --no-cache <service>`

---

## Quick Reference

```bash
# Start environment
docker compose up -d && docker compose exec web python manage.py migrate

# Run tests
docker compose exec web python manage.py test
docker compose exec web python manage.py test apps.<app_name>

# Lint and format
ruff check apps/ --fix && ruff format apps/

# Type checking
npx basedpyright apps/

# Django shell
docker compose exec web python manage.py shell

# Validate configuration
docker compose exec web python manage.py check --deploy

# Playwright E2E tests (Docker must be running)
docker compose exec web python manage.py create_e2e_users  # Idempotent setup
npx playwright test tests/e2e/workflows/ --project=chromium --workers=1
```

---

## Context-Specific Guidance

When working in these directories, read the corresponding `CLAUDE.md` first:

| Directory | CLAUDE.md | Content |
|-----------|-----------|---------|
| `docker/` | `docker/CLAUDE.md` | Docker troubleshooting, service architecture |
| `tests/e2e/` | `tests/e2e/CLAUDE.md` | E2E setup, Playwright patterns, test ID conventions |
| `apps/core/` | `apps/core/CLAUDE.md` | env_config, integrations, shared services |
| `apps/accounts/` | `apps/accounts/CLAUDE.md` | User model, auth forms, signup (email-only) |
| `apps/organisation/` | `apps/organisation/CLAUDE.md` | Multi-tenant models, quotas, invitations |
| `apps/review_manager/` | `apps/review_manager/CLAUDE.md` | Session lifecycle, views, signals, SSE |
| `apps/search_strategy/` | `apps/search_strategy/CLAUDE.md` | PIC models, strategy views, auto-transition signal |
| `apps/serp_execution/` | `apps/serp_execution/CLAUDE.md` | Provider abstraction, execution views, tasks |
| `apps/results_manager/` | `apps/results_manager/CLAUDE.md` | Processing models, deduplication, status views |
| `apps/review_results/` | `apps/review_results/CLAUDE.md` | Dual-workflow models, services, API, signals |
| `apps/reporting/` | `apps/reporting/CLAUDE.md` | PRISMA reports, export views, generation tasks |
| `apps/feedback/` | `apps/feedback/CLAUDE.md` | Feedback model, submission/admin views |

---

## Security Patterns (CRITICAL)

### UUID Primary Keys
**Pattern**: All models MUST use UUID primary keys for security.

```python
# ✅ CORRECT
import uuid
from django.db import models

class MyModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)

# ❌ WRONG
class MyModel(models.Model):
    # Using default AutoField allows enumeration attacks
    name = models.CharField(max_length=100)
```

**Why**: Prevents enumeration attacks where attackers guess sequential IDs to access unauthorized records. UUID provides 128-bit non-sequential identifiers.

**Flag in Review**: Any model without explicit UUID primary key declaration.

---

### Foreign Key Protection
**Pattern**: Use `on_delete=models.PROTECT` for audit trail models to prevent accidental data loss.

```python
# ✅ CORRECT (audit trail preservation)
class ReviewerDecision(models.Model):
    reviewer = models.ForeignKey(User, on_delete=models.PROTECT)
    result = models.ForeignKey(SearchResult, on_delete=models.PROTECT)
    decision = models.CharField(max_length=20)

# ❌ WRONG (audit trail destruction risk)
class ReviewerDecision(models.Model):
    reviewer = models.ForeignKey(User, on_delete=models.CASCADE)  # Deletes audit history!
    result = models.ForeignKey(SearchResult, on_delete=models.CASCADE)
```

**Why**: Audit trails must be immutable for PRISMA reporting. CASCADE deletion violates systematic review requirements for complete decision history.

**Flag in Review**: CASCADE on foreign keys to User or any audit-related model.

---

### Authentication Requirements
**Pattern**: All views require authentication unless explicitly public.

```python
# ✅ CORRECT
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView

class SessionListView(LoginRequiredMixin, ListView):
    model = SearchSession

# ❌ WRONG (missing authentication)
class SessionListView(ListView):  # Anyone can access!
    model = SearchSession
```

**Why**: Grey literature search sessions contain research data that must be user-scoped. Unauthenticated access exposes sensitive research workflows.

**Flag in Review**: Any view class without LoginRequiredMixin or function view without @login_required decorator.

---

## Performance Requirements (HIGH)

### Response Time Target
**Target**: < 500ms for most views
**Monitor**: Use Django Debug Toolbar in development
**Flag**: Any view taking > 1000ms is a critical performance issue

**Profiling Pattern**:
```python
# Add to view for profiling
import time
start = time.time()
# ... view logic ...
print(f"View execution: {(time.time() - start) * 1000:.2f}ms")
```

---

### N+1 Query Prevention
**Pattern**: Use `select_related()` for foreign keys and `prefetch_related()` for reverse foreign keys / many-to-many.

```python
# ✅ CORRECT (1 query for sessions, 1 for related owners and strategies)
sessions = SearchSession.objects.select_related('owner', 'strategy').all()

# ❌ WRONG (N+1 query - 1 for sessions + N for owners + N for strategies)
sessions = SearchSession.objects.all()
for session in sessions:
    print(session.owner.username)  # Database query per iteration!
    print(session.strategy.title)  # Another query per iteration!
```

**Dashboard Example** (HIGH-TRAFFIC VIEW):
```python
# ✅ CORRECT
def get_queryset(self):
    return SearchSession.objects.select_related(
        'owner', 'strategy'
    ).prefetch_related(
        'queries', 'activities'
    ).filter(owner=self.request.user)
```

**Flag in Review**: Any queryset accessed in a loop without select_related/prefetch_related when accessing related objects.

---

### Database Indexing
**Pattern**: Index all fields used in `filter()`, `exclude()`, or `order_by()`.

```python
# ✅ CORRECT
class SearchSession(models.Model):
    status = models.CharField(max_length=20, db_index=True)  # Filtered frequently
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)  # Ordered by

# ❌ WRONG (missing indexes on filtered fields)
class SearchSession(models.Model):
    status = models.CharField(max_length=20)  # filter(status='executing') is slow!
    created_at = models.DateTimeField(auto_now_add=True)  # order_by('-created_at') is slow!
```

**Composite Index Example**:
```python
class Meta:
    indexes = [
        models.Index(fields=['owner', 'status']),  # Common filter combination
        models.Index(fields=['-created_at']),  # Descending order
    ]
```

**Flag in Review**: CharField, IntegerField, or DateTimeField used in queries without `db_index=True` or composite index.

---

## Django Best Practices (MEDIUM)

### 9-State Workflow State Machine
**States**: draft → defining_search → ready_to_execute → executing → processing_results → ready_for_review → under_review → completed → archived

**Rules**:
- No state skipping (must transition sequentially)
- Validate transitions with `can_transition_to()` before saving
- Auto-transition states (executing, processing_results, ready_for_review) change without user intervention
- Automatic timestamps: `started_at` on `executing`, `completed_at` on `completed`

```python
# ✅ CORRECT (validated state transition)
if session.can_transition_to('executing'):
    session.status = 'executing'
    session.started_at = timezone.now()
    session.save()
    # Log activity
    SessionActivity.objects.create(
        session=session,
        activity_type='state_change',
        details={'from': 'ready_to_execute', 'to': 'executing'}
    )

# ❌ WRONG (skips validation, breaks audit trail)
session.status = 'completed'  # May skip required intermediate states!
session.save()
```

**Flag in Review**: Direct `session.status = <value>` assignment without `can_transition_to()` check.

---

### Async View Requirements
**Pattern**: Async views MUST use `@transaction.non_atomic_requests` decorator and `sync_to_async` for database operations.

```python
# ✅ CORRECT
from asgiref.sync import sync_to_async
from django.views.decorators.transaction import non_atomic_requests
from django.views import View

@non_atomic_requests
class SessionStreamView(View):
    async def get(self, request, session_id):
        # Wrap synchronous ORM calls
        session = await sync_to_async(
            SearchSession.objects.get, thread_sensitive=True
        )(pk=session_id)

        # Async streaming logic here
        async for event in self.stream_events(session):
            yield event

# ❌ WRONG (missing decorators, synchronous ORM in async)
class SessionStreamView(View):
    async def get(self, request, session_id):
        session = SearchSession.objects.get(pk=session_id)  # Blocks async event loop!
```

**Why**: Django ORM is synchronous. Using it in async views without `sync_to_async` blocks the event loop and causes performance degradation.

**Flag in Review**: `async def` view methods without `@non_atomic_requests` or ORM queries without `sync_to_async`.

---

### Service Layer Pattern
**Pattern**: Business logic belongs in service classes, not views. Views orchestrate, services execute.

```python
# ✅ CORRECT
# apps/review_results/services.py
class ReviewClaimService:
    @staticmethod
    def claim_next_result(reviewer, session):
        """Atomic result claiming with race condition protection."""
        with transaction.atomic():
            result = SearchResult.objects.select_for_update(
                skip_locked=True
            ).filter(
                session=session,
                review_status='pending'
            ).first()

            if result:
                ReviewerAssignment.objects.create(
                    result=result,
                    reviewer=reviewer,
                    role='primary'
                )
            return result

# apps/review_results/views.py
class ClaimResultView(LoginRequiredMixin, View):
    def post(self, request, session_id):
        session = get_object_or_404(SearchSession, pk=session_id)
        result = ReviewClaimService.claim_next_result(request.user, session)
        return JsonResponse({'result_id': str(result.id) if result else None})

# ❌ WRONG (business logic in view)
class ClaimResultView(LoginRequiredMixin, View):
    def post(self, request, session_id):
        # 30+ lines of complex database logic directly in view method
        with transaction.atomic():
            result = SearchResult.objects.select_for_update()...
            # Complex claiming logic here
```

**Flag in Review**: Views with > 15 lines of database/business logic. Extract to service layer.

---

## Testing Requirements (MEDIUM)

### Unit Test Coverage
**Target**: >80% coverage for new code
**Tools**: pytest, pytest-django, pytest-cov

**Pattern**: Test models, services, forms, and views separately.

```python
# ✅ CORRECT (comprehensive model testing)
import pytest
from django.core.exceptions import ValidationError

@pytest.mark.django_db
class TestSearchSession:
    def test_str_representation(self):
        session = SearchSession.objects.create(title="Test Session")
        assert str(session) == "Test Session"

    def test_can_transition_to_valid(self):
        session = SearchSession.objects.create(status='draft')
        assert session.can_transition_to('defining_search') is True

    def test_can_transition_to_invalid_skipping(self):
        session = SearchSession.objects.create(status='draft')
        assert session.can_transition_to('executing') is False  # Cannot skip states

    def test_model_validation(self):
        with pytest.raises(ValidationError):
            session = SearchSession(title="")  # Empty title invalid
            session.full_clean()
```

**Flag in Review**: New model/service/view without corresponding test file in `tests/` directory.

---

### Background Task Testing
**Pattern**: Test Celery tasks with mocked external dependencies.

```python
# ✅ CORRECT (mocked external API)
from unittest.mock import patch
import pytest

@patch('apps.serp_execution.tasks.serper_client.search')
def test_execute_search_task_success(mock_search):
    mock_search.return_value = {
        'organic': [
            {'title': 'Test Result', 'link': 'http://example.com', 'snippet': 'Test'}
        ]
    }

    result = execute_search_task.apply(query_id=query.id)

    assert result.status == "SUCCESS"
    mock_search.assert_called_once()

# ❌ WRONG (hits real external API in tests)
def test_execute_search_task():
    result = execute_search_task.apply(query_id=query.id)  # Calls Serper API!
    assert result.status == "SUCCESS"
```

**Flag in Review**: Celery task tests without `@patch` decorators for external API calls (Serper, email services).

---

## Celery Task Patterns (MEDIUM)

### Task Registration
**Pattern**: Import task modules in `grey_lit_project/celery.py:ensure_tasks_registered()` to guarantee discovery.

```python
# ✅ CORRECT (grey_lit_project/celery.py)
def ensure_tasks_registered():
    """Import all task modules to ensure Celery discovers them."""
    from apps.serp_execution import tasks as serp_tasks
    from apps.results_manager import tasks as results_tasks
    from apps.review_results import tasks as review_tasks
    # Tasks auto-register on import

# ❌ WRONG (tasks not imported, may not be discovered)
# Missing import in ensure_tasks_registered()
```

**Flag in Review**: New `tasks.py` file without corresponding import in `ensure_tasks_registered()`.

---

### Circuit Breakers for External APIs
**Pattern**: External API calls MUST use circuit breakers to prevent cascading failures.

```python
# ✅ CORRECT (circuit breaker protection)
from pybreaker import CircuitBreaker

serper_breaker = CircuitBreaker(fail_max=5, timeout_duration=60)

@serper_breaker
def call_serper_api(query):
    """Call Serper API with circuit breaker protection."""
    response = requests.post(SERPER_API_URL, json={'q': query})
    response.raise_for_status()
    return response.json()

# ❌ WRONG (no circuit breaker - cascading failures possible)
def call_serper_api(query):
    response = requests.post(SERPER_API_URL, json={'q': query})  # Fails repeatedly if API down
    return response.json()
```

**Why**: When Serper API fails, without circuit breaker, every task retry hammers the failing service. Circuit breaker fails fast after threshold, preventing resource exhaustion.

**Flag in Review**: `requests.post()`/`requests.get()` calls to external APIs without circuit breaker decorator.

---

## Code Review Focus Areas

### 1. Security (CRITICAL)
- [ ] UUID primary keys used (`id = models.UUIDField(primary_key=True, default=uuid.uuid4)`)
- [ ] Authentication required on views (`LoginRequiredMixin` or `@login_required`)
- [ ] Foreign keys use PROTECT for audit trails (`on_delete=models.PROTECT`)
- [ ] No SQL injection vulnerabilities (use ORM, parameterized queries)
- [ ] No XSS vulnerabilities (Django template escaping enabled by default)

### 2. Performance (HIGH)
- [ ] N+1 queries avoided (`select_related()`/`prefetch_related()` on querysets)
- [ ] Database indexes on filtered/sorted fields (`db_index=True`)
- [ ] Response time < 500ms (profile with Debug Toolbar or add timing logs)
- [ ] No inefficient algorithms (O(n²) or worse - review loops and nested queries)

### 3. Django Patterns (MEDIUM)
- [ ] State machine transitions validated (`can_transition_to()` before status change)
- [ ] Async views use `@non_atomic_requests` + `sync_to_async`
- [ ] Business logic in service layer (not views)
- [ ] Template tags in alphabetical order (PEP 8 style)
- [ ] One space in template variables (`{{ var }}` not `{{var}}`)

### 4. Testing (MEDIUM)
- [ ] New code has unit tests (in `tests/` or `app/tests/`)
- [ ] Test coverage >80% (run `pytest --cov`)
- [ ] Celery tasks tested with mocks (`@patch` for external APIs)
- [ ] Edge cases covered (empty input, None values, boundary conditions)

### 5. Documentation (LOW)
- [ ] Docstrings for public functions (Google style)
- [ ] Complex logic has inline comments
- [ ] Model fields have `help_text` parameter

---

## Common Pitfalls to Flag

### Pitfall 1: Missing Migrations
**Flag**: Model changes without corresponding migration file in `migrations/` directory.

**Check**: After model changes, always run `python manage.py makemigrations` and commit the migration file.

---

### Pitfall 2: Hardcoded URLs
**Flag**: URLs hardcoded in templates or views instead of using `reverse()` or `{% url %}`.

```python
# ✅ CORRECT
from django.urls import reverse
redirect_url = reverse('session_detail', kwargs={'pk': session.id})

# ❌ WRONG
redirect_url = f'/sessions/{session.id}/'  # Breaks if URL pattern changes
```

---

### Pitfall 3: Missing Indexes on Frequent Filters
**Flag**: Fields used in `filter()` or `order_by()` without `db_index=True`.

**Example**: `SearchSession.objects.filter(status='executing')` on un-indexed `status` field causes table scan.

---

### Pitfall 4: Direct Database Writes in Views
**Flag**: Complex database operations (transactions, locking, multi-step logic) in view methods.

**Solution**: Extract to service layer for testability and reusability.

---

### Pitfall 5: Synchronous Code in Async Views
**Flag**: ORM queries or file I/O without `sync_to_async` wrapper in async view methods.

**Example**: `await session = SearchSession.objects.get(pk=id)` - missing `sync_to_async`.

---

**Word Count**: ~1,550 words
**Severity Markers**: 18 instances (CRITICAL: 3, HIGH: 4, MEDIUM: 11)
