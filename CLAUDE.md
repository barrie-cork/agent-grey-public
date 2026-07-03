# CLAUDE.md (Agent Grey)

## Project Context

**Project**: Grey literature search/review application (PRISMA 2020)
**Status**: Feature completion (E2E suite complete; priority: dual screening hardening)
**Stack**: Django 5.1.13, Python 3.12, PostgreSQL 15, Celery 5.5.3 + Redis 7.0
**Deployment**: Self-hosted via Docker
**Use Case**: Systematic review of non-traditional sources (government reports, policy documents, clinical guidelines, organisational publications, web resources)

## Critical Rules

- **ALWAYS use Docker** -- never run Django natively (`docker compose up -d`)
- UUID primary keys for all models (`id = models.UUIDField(primary_key=True, default=uuid.uuid4)`)
- Use `apps.core.env_config` for environment variables (NOT `os.environ`)
- 9-state workflow with strict transitions (no state skipping)
- Tests MUST run in Docker with PostgreSQL (not SQLite)
- UK English spelling (organisation, colour, favour)
- No em dashes in documentation
- Rebuild Docker images after `requirements.txt` changes: `docker compose build --no-cache <service>`
- **HTTP dev mode**: `CSRF_COOKIE_SECURE=False` and `SESSION_COOKIE_SECURE=False` required for local HTTP development (Cloudflare tunnel handles HTTPS in production)

## Architecture Essentials

### 9-State Workflow
`draft` > `defining_search` > `ready_to_execute` > `executing` (AUTO) > `processing_results` (AUTO) > `ready_for_review` (AUTO) > `under_review` > `completed` > `archived`

**Auto-transitions**: `ready_to_execute`, `executing`, `processing_results`, `ready_for_review` change without user action (signals + Celery tasks). `ready_to_execute` is triggered by `check_strategy_completion` signal on `SearchQuery` post_save when a complete strategy with active queries exists.

### PIC Framework
SearchStrategy: **P**opulation + **I**nterest + **C**ontext > Boolean queries with optional guidelines filter and file type filters

### Dual Workflows

**Detection**: `if session.current_configuration.is_workflow_2:` (NEVER check `min_reviewers_per_result` directly)

| Aspect | Workflow #1 | Workflow #2 |
|--------|------------|-------------|
| Config | `min_reviewers_per_result = 1` | `min_reviewers_per_result >= 2` |
| Pattern | Results SPLIT (no overlap) | Results SHARED (100% overlap) |
| Model | `SimpleReviewDecision` (OneToOne) | `ReviewerDecision` (many/result) |
| Blinding | Not needed | Enforced until all complete |
| IRR | No | Cohen's Kappa >= 0.70 |
| PRISMA | No | Yes |

**Key Services (Workflow #2)**: `BlindingService` (enforces blinding until all complete), `ReviewCoordinationService` (conflict detection + resolution), `InterRaterReliabilityService` (Cohen's Kappa). `ReviewClaimService` handles atomic claiming for Workflow #1. Full patterns: `apps/review_results/CLAUDE.md`

**Vue SPA**: `frontend/src/views/` -- ConflictResolution (threaded discussion + re-vote + resolution), ConflictList, TeamDashboard, ScreeningDecision. SSE real-time via `review_results/api/sse_views.py`. Served by `vue_spa` view in `grey_lit_project/urls.py` at `/screening/` -- requires `@login_required`, injects user/org/membership context as `<script id="user-data">` JSON so Vue auth and organisation stores hydrate without an extra API call. When `session_id` is in the query params, also injects `session.is_workflow_2` so the Vue nav can hide WF1-only items (e.g. Work Queue). Review overview sidebar links to `/screening/conflicts?session_id=<uuid>` for WF2 sessions with pending conflicts.

## Django Apps

| App | Key Models |
|-----|------------|
| `core` | -- (env_config, context processors, PostHogClient) |
| `health` | -- |
| `accounts` | User |
| `organisation` | Organisation, OrganisationMembership, OrganisationInvitation |
| `review_manager` | SearchSession, ReviewInvitation, ReviewConfiguration |
| `search_strategy` | SearchStrategy, SearchQuery |
| `serp_execution` | SearchExecution, RawSearchResult, SerpProviderConfig |
| `results_manager` | ProcessedResult, ProcessingSession |
| `review_results` | SimpleReviewDecision, ReviewerDecision, ConflictResolution, InterRaterReliability, ReviewerCompletion |
| `reporting` | ExportReport |
| `feedback` | UserFeedback |

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Framework | Django (LTS), Python 3.12 |
| Database | PostgreSQL 15 |
| Tasks | Celery + Redis |
| Search API | Serper (default) + SearchAPI.io (Bing) via `SerpProviderConfig` |
| IRR | scikit-learn (Cohen's Kappa) |
| PDF | WeasyPrint |
| Frontend SPA | Vue 3 + TypeScript (conflict resolution) |
| Browser extension | WXT + Vue 3 + TypeScript (`extension/` dir, separate build) |
| Extension auth | django-rest-knox 5.0.2 (per-device revocable tokens, `ag_ext_` prefix) |
| Build | Vite + Node.js (multi-stage Docker build) |
| API docs | drf-spectacular (OpenAPI) |
| E2E tests | Playwright |
| Analytics | PostHog (EU Cloud) |
| Server | Gunicorn + Uvicorn (ASGI) |
| Email | Brevo (SMTP) |

## Development Standards

- PEP 8 + Django coding standards
- Class-Based Views (CBVs) with `LoginRequiredMixin` for authenticated views
- Signal-based automation (ReviewerCompletion, conflict detection, IRR calculation)
- Background tasks: import task modules in `grey_lit_project/celery.py`'s `ensure_tasks_registered()`
- Tests: >80% coverage, Docker + PostgreSQL only
- Testing skills: `pytest-django-patterns` (factory_boy patterns, dual workflow, Docker, signals)
- Never initialise Django components before `django.setup()` completes
- Never manually instantiate cache backends -- use `from django.core.cache import cache`
- **Type checking:** BasedPyright via `pyrightconfig.json` (basic mode). Django stubs supplied by `django-types` (PEP 561, in `requirements/local.txt`) which pyright auto-discovers from site-packages -- no `stubPath` needed. 2 rules suppressed (`none`): `reportMissingImports` and `reportInvalidTypeForm` (residual Django stub gaps; `django-types` is partial). 1 rule downgraded to `warning`: `reportAttributeAccessIssue` (third-party stub gaps, e.g. boto3 which ships no PEP 561 stubs; 2026-06-17, #185). Four rules re-enabled: `reportReturnType`, `reportCallIssue`, `reportOptionalMemberAccess` (2026-02-25), `reportRedeclaration` (2026-03-17). Current residual: 0 errors, 9 warnings (`basedpyright apps/`)

## Key Patterns

- **Denormalised Performance**: SearchQuery has direct session reference (avoids JOINs)
- **Atomic Claiming**: `SELECT FOR UPDATE SKIP LOCKED` for race-condition-free work queue (Workflow #1)
- **Versioned Audit Trail**: ReviewerDecision updates require `allow_update=True`, version auto-increments (Workflow #2). Immutability enforced by `save()` override.
- **Circuit Breakers**: Serper API calls protected with pybreaker
- **Auto-Transitions**: Session state changes automated via Celery tasks and signals
- **Magic Link Invitations**: `secrets.token_urlsafe(48)`, 7-day expiry, status tracking (ReviewInvitation in `review_manager`)
- **Provider Abstraction**: `SerpProvider` protocol in `serp_execution.providers` with registry, per-provider rate limiting, and `SerpProviderConfig` model. See `apps/serp_execution/CLAUDE.md`.
- **Deploy-time Frontend Build**: Vite multi-stage Docker build (`node:22-slim`). `static/dist/` gitignored; `COPY --from=frontend` in production image.
- **PostHog Analytics**: `PostHogClient` in `apps/core/integrations.py`. Disabled in tests via `POSTHOG_ENABLED = False`.
- **Email Notifications**: `BaseEmailNotificationService` in `core` with per-app subclasses. Brevo SMTP in production, console locally. SLA reminders via `check_conflict_sla_reminders` Celery beat task.
- **Log Redaction**: `SensitiveDataFilter` in `grey_lit_project/logging_filters.py` redacts sensitive data from all log output.
- **File Type Post-Processing**: `BatchProcessor` enforces file type restrictions post-normalisation (`processing_error_category='file_type_mismatch'`). See `docs/serp/google-search-operators.md`.

## Playwright E2E Gotchas

Read `tests/e2e/CLAUDE.md` for full details, common pitfalls, and conventions. Key: use `loginUser()` (not signup), `domcontentloaded` (not `networkidle`) for SSE pages, `--workers=1` for reliable runs.

## Serena MCP (Code Intelligence)

Serena provides semantic code navigation via LSP — symbol lookup, reference finding, and structure overview. It saves tokens vs reading entire files.

**How to use:** Serena tools are loaded on-demand. To access them:
1. Run `ToolSearch` for "serena" to discover available tools
2. Use `get_symbols_overview` to see top-level symbols in a file (cheaper than Read)
3. Use `find_symbol` to locate classes/functions by name across the project
4. Use `find_referencing_symbols` to find callers of a function or references to a class

**When to use Serena vs built-in tools:**
- Understanding a file's structure → `get_symbols_overview` (not Read)
- Finding where a function is called → `find_referencing_symbols` (not Grep)
- Locating a class definition → `find_symbol` (not Glob)
- Reading specific code → Read (Serena doesn't replace targeted reads)

**Activation is automatic** — do not call `activate_project` manually.

**Update memories:** After significant code changes, update `.serena/memories/` (project structure, conventions) so future sessions start with accurate context.

## Quick Reference

```bash
# Start environment
docker compose up -d && docker compose exec web python manage.py migrate

# Tests
docker compose exec web python manage.py test
docker compose exec web python manage.py test apps.<app_name>

# Code quality
ruff check apps/ --fix && ruff format apps/
npx basedpyright apps/  # Type checking (BasedPyright)

# Django shell
docker compose exec web python manage.py shell

# Validation
docker compose exec web python manage.py check --deploy

# Database reset (fresh start) -- WARNING: flush destroys data-migration-seeded
# records (SerpProviderConfig, etc). Re-seed after flush:
docker compose exec web python manage.py flush --no-input && docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_provider_configs
# Then recreate superuser -- see docker/CLAUDE.md "Local Dev Superuser"

# Migration health
docker compose exec web python scripts/check-migration-health.py

# Logging control
DEV_REQUEST_LOGGING=all DB_LOG_LEVEL=DEBUG docker compose up  # Full debugging
docker compose --profile monitoring up  # Enable flower (Celery monitoring) + warning_monitor

# Playwright E2E tests (Docker must be running)
docker compose exec web python manage.py create_e2e_users  # Idempotent setup
npx playwright test tests/e2e/workflows/ --project=chromium --workers=1  # Reliable run (149 pass, 6 skip)
npx playwright test tests/e2e/workflows/ --project=chromium --workers=2  # Faster but some parallelism flakiness
npx playwright test --project=chromium --headed --debug                   # Visual debugging
```

## Context-Specific Guidance

**Working in these directories? Check these files first:**

| Directory | CLAUDE.md | Content |
|-----------|-----------|---------|
| `docker/` | `docker/CLAUDE.md` | Docker troubleshooting, service architecture, environment checklist |
| `tests/e2e/` | `tests/e2e/CLAUDE.md` | E2E setup, Playwright patterns, test ID conventions |
| `apps/core/` | `apps/core/CLAUDE.md` | env_config, integrations, shared services, infra modules |
| `apps/accounts/` | `apps/accounts/CLAUDE.md` | User model, auth forms, signup (email-only) |
| `apps/organisation/` | `apps/organisation/CLAUDE.md` | Multi-tenant models, quotas, invitations |
| `apps/review_manager/` | `apps/review_manager/CLAUDE.md` | Session lifecycle, views, signals, SSE |
| `apps/search_strategy/` | `apps/search_strategy/CLAUDE.md` | PIC models, strategy views, auto-transition signal |
| `apps/serp_execution/` | `apps/serp_execution/CLAUDE.md` | Provider abstraction, execution views, tasks |
| `apps/results_manager/` | `apps/results_manager/CLAUDE.md` | Processing models, deduplication, status views |
| `apps/review_results/` | `apps/review_results/CLAUDE.md` | Dual-workflow models, services, API, signals |
| `apps/reporting/` | `apps/reporting/CLAUDE.md` | PRISMA reports, export views, generation tasks |
| `apps/feedback/` | `apps/feedback/CLAUDE.md` | Feedback model, submission/admin views |
| `apps/health/` | `apps/health/CLAUDE.md` | Health check endpoints |

**Comprehensive Architecture**: `docs/architecture/E2E-APPLICATION-FLOW.md`

**Documentation Index**: `docs/README.md`

## Feature Boundaries

9-state workflow, PIC search query generation, multi-provider SERP integration, automated normalisation/deduplication, single and dual screening review, manual result addition during screening, PRISMA 2020 reporting with Cohen's Kappa, multi-tenant organisations, Playwright E2E suite, PostHog analytics, email notifications (reports, invitations, conflicts, IRR, consensus, SLA reminders), browser-based source capture (toggleable Chromium extension that logs grey-lit browsing during screening into the PRISMA other-methods arm, one-click manual result promotion, token-authenticated ingestion API).

### Mandatory Post-Task Retrospective

Before completing any task, agents MUST run `/post-task-retro`. This is not optional. No task is considered complete until the retrospective has been executed. The retrospective captures lessons learned, surfaces issues encountered, and ensures continuous improvement across sessions.

## Project Memory (Operational)

This project uses `project-memory-mcp` for **operational memory** — how the system/tools work, config insights, bug patterns, skill performance. Domain content belongs in the project's own knowledge system (issue tracker, docs, etc.).

**Write when:** root cause found, command solved a problem, decision changed architecture, skill performed notably well/badly, pattern confirmed 2+ times.
**Don't write:** routine success, obvious facts, speculation, domain content, TODOs (use GitHub issues instead).

**Key types:** qa-result (30d), bug (90d), pattern (never), decision (never). `bug` = discovered root cause, NOT a known TODO.
**Voice ideas:** Store as `issue-note` tagged `idea,voice-capture` with a clean title. Process during weekly review.

Use `supersedes: <old_id>` when updating insights. Promote to `docs/memory/*.md` when a pattern appears 3+ times.

## Available Skills

Skills live in `.claude/skills/`. Use them by workflow phase:

| Phase | Skill | When to use |
|-------|-------|-------------|
| Planning | `shaping` | Before implementing a feature — capture requirements, scope, workflow impact |
| Coding | `django-models` | Creating/modifying models, optimizing queries, preventing N+1 |
| Coding | `django-forms` | Form validation, ModelForm, clean methods, CBV integration |
| Coding | `django-templates` | Template inheritance, partials, custom tags |
| Coding | `django-extensions` | Management command introspection (show_urls, shell_plus, list_model_info) |
| Coding | `celery-patterns` | Creating tasks, configuring retries, idempotency, scheduling |
| Coding | `pytest-django-patterns` | Writing tests, TDD workflow, Docker test suite |
| Quality | `code-review` | Dead code audit, unused imports, redundancy scan, tech debt cleanup |
| Quality | `refactoring` | Behavior-preserving structural changes (always green tests first) |
| Quality | `doc-drift` | Check docs match code — run after features, before session end |
| Testing | `dual-screening-test` | End-to-end manual test of the WF2 dual-screening workflow (blinding, conflicts, IRR, report); one session, or two coordinated reviewer sessions |
| Release | `pre-release-hardening` | Test suite health, feature testing, cleanup before release |
| Release | `pre-deploy-verify` | Structured 9-phase verification loop before production deployment |
| Post-task | `post-task-retro` | End of every Junior task — mandatory |
| Triage | `gather-feedback` | Export feedback from Django, cluster, create GitHub issues |
| Scheduled | `weekly-review` | Automatic Sunday 02:00 UTC — prune, promote, metrics |

**Workflow notes:**
- Before a new feature: consider `/shaping` to define requirements and workflow impact
- After implementation: `/code-review` for cleanup, then `/doc-drift` for doc sync
- Refactoring is separate from features — commit refactors independently
- `/pre-release-hardening` before any user-facing release

**Internal deployment and Junior-daemon specifics**: see `.claude/rules/internal-infra.md` (private-only; excluded from the public mirror).
