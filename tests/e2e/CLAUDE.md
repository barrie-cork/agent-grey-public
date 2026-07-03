# E2E Testing (Agent Grey -- Playwright)

## Architecture

Two test layers exist. The `workflows/` directory is the primary suite using Page Object Models:

```
tests/e2e/
  global-setup.ts          # Creates users + seeds 7 sessions at key workflow states
  global-teardown.ts       # Deletes all E2E data (teardown_e2e_data command)
  .seeded-sessions.json    # Generated -- session IDs for fixture consumption
  fixtures/
    auth.ts                # Legacy auth helpers (loginAsReviewer, loginMultipleUsers)
    vue-helpers.ts         # Vue SPA wait utilities, organisation context
  workflows/               # Primary test suite (POM)
    fixtures/
      test-users.ts        # User creation, login helpers, defaultTestUsers
      test-sessions.ts     # Session creation, configuration, PIC strategy helpers
      seeded-sessions.ts   # Loads pre-seeded session IDs from global setup
    helpers/
      navigation.ts        # Browser history, breadcrumb, URL verification
      assertions.ts        # Reusable assertion helpers
      wf2-helpers.ts       # WF2 lifecycle API helpers (decisions, conflicts, invitations)
    pages/                 # Page Object Models (auth, dashboard, session, review, spa, etc.)
    *.workflow.spec.ts     # Workflow test specs (20+)
  WF2-LIFECYCLE-PLAN.md    # WF2 full lifecycle test plan (phases, API reference, known issues)
  archive/                 # Archived debug/legacy specs (not run by default)
  visual/                  # Visual regression tests (separate page objects)
```

### Page Object Model Pattern

All workflow tests use POM. Page objects encapsulate selectors and actions:

```typescript
import { AuthPage } from './pages/auth.page';

test('login workflow', async ({ page }) => {
  const authPage = new AuthPage(page);
  await authPage.loginAndExpectSuccess('e2e-reviewer1@test.local', 'TestPass123!');
  await authPage.expectOnDashboard();
});
```

Page objects exported from `pages/index.ts`: `AuthPage`, `DashboardPage`, `SessionPage`, `ReviewPage`, `SPAPage`.

## Global Setup and Teardown

**Setup** (`global-setup.ts`) runs once before all tests: creates test users, seeds 7 sessions at key workflow states, writes IDs to `.seeded-sessions.json`.

| Key | State | Workflow |
|-----|-------|----------|
| `draft` | draft | WF1 |
| `definingSearch` | defining_search | WF1 |
| `readyForReviewWf1` | ready_for_review | WF1 (10 results) |
| `readyForReviewWf2` | ready_for_review | WF2 (10 results) |
| `underReviewWf2` | under_review | WF2 (50% agreement, conflicts) |
| `completedWf1` | completed | WF1 |
| `completedWf2` | completed | WF2 (70% agreement) |

**Teardown** (`global-teardown.ts`) runs after all tests: calls `teardown_e2e_data`, removes `.seeded-sessions.json`.

**Consuming seeded sessions:**

```typescript
import { getSeededSessions } from './fixtures/seeded-sessions';

const sessions = getSeededSessions();
await page.goto(`/sessions/${sessions.readyForReviewWf1}/`);
```

## Authentication

Test users created by `create_e2e_users`. Login form takes **email**, not username.

- Username prefix: `e2e-`, email domain: `@test.local`, password: `TestPass123!`
- Default users and roles:
  - `e2e-reviewer1`, `e2e-reviewer2` -- `REVIEWER`
  - `e2e-owner` -- `LEAD_REVIEWER` (session owner for most tests)
  - `e2e-admin` -- `INFORMATION_SPECIALIST` (full permissions)

**Workflow layer** (preferred for new tests):

```typescript
import { loginUser, defaultTestUsers } from './fixtures/test-users';
await loginUser(page, defaultTestUsers.reviewer1.email);
```

**Legacy layer** (older root-level specs):

```typescript
import { loginAsReviewer } from '../../fixtures/auth';
await loginAsReviewer(page, 'e2e-reviewer1@test.local');
// Also loads organisation context via ensureOrganisationContext()
```

**Dynamic users** for isolation: `generateTestUser('prefix')` creates `e2e-prefix-{timestamp}@test.local`.

## Common Pitfalls

| Error | Cause | Fix |
|-------|-------|-----|
| "Invalid login credentials" | Test users missing from DB | `create_e2e_users` command |
| "Seeded sessions file not found" | Global setup didn't run | Run via `npx playwright test` |
| "Timeout waiting for locator" | Wrong selector or hidden element | Debug with `--headed --debug` |
| `toHaveURL` regex fails on `http://localhost:8000/` | Playwright matches full URL, not pathname | Use `toHaveURL('/')` (resolved against baseURL) instead of regex with `^/$` |
| `networkidle` timeout on session detail/setup | SSE connections keep network active indefinitely | Use `waitForLoadState('domcontentloaded')` for pages with SSE |
| Strict mode violation on `[role="alert"]` | Hidden feedback toast also has `role="alert"` | Exclude via `:not([data-testid="feedback-toast"])` or use `.first()` |
| PROTECT FK on teardown deleting e2e- users | Test-created sessions owned by e2e- users block deletion | Teardown filters sessions by `owner__username__startswith="e2e-"` (not just title) |
| Signup POM fills `#id_username` (doesn't exist) | `SignUpForm` has email + password only; username is auto-generated | Never add username/first_name/last_name selectors to signup POM |

Auth errors are almost always missing DB records, not CSRF/session issues.

## Critical E2E Conventions

These rules prevent recurring mistakes. Violating them causes test failures.

### Signup form is email-only
`SignUpForm` fields: `email`, `password1`, `password2`. Username is auto-generated from email prefix by the backend. There is no username, first_name, or last_name field. Do not add selectors for fields that do not exist on the form.

### Use pre-created users, not signup
New workflow tests MUST use `loginUser()` with pre-created e2e- users from `create_e2e_users`. Do NOT create users via the signup form in tests -- it creates data that is harder to clean up and couples tests to signup form implementation.

### URL assertions use string, not regex
Playwright `toHaveURL` matches against the **full URL** (e.g. `http://localhost:8000/`), not the pathname. A regex like `/^\/$|\/dashboard\//` will never match because `^/$` expects the entire string to be `/`. Use string assertions resolved against baseURL:
```typescript
// CORRECT
await expect(page).toHaveURL('/');
await expect(page).toHaveURL('/accounts/login/');

// WRONG -- regex anchored to full URL string, not pathname
await expect(page).toHaveURL(/^\/$|\/dashboard\//);
```

### Use `domcontentloaded` for SSE pages
Session detail and setup pages have Server-Sent Events (SSE) connections that prevent `networkidle` from ever resolving. Always use `waitForLoadState('domcontentloaded')` for these pages. Auth pages (login, signup, password reset) are safe with `networkidle`.

### Teardown covers all e2e- owned data
`teardown_e2e_data` deletes sessions matching `title__icontains="e2e"` OR `owner__username__startswith="e2e-"`. This catches both seeded sessions (E2E in title) and sessions created during tests (owned by e2e-owner, e2e-admin, etc.). If you add new test patterns, ensure teardown covers them.

### workers=1 for reliable runs
`playwright.config.ts` defaults to `workers: 2`. Some tests share seeded session state and flake under parallelism. Use `--workers=1` for 0-failure validation runs.

## Selector Convention

Page objects use testid-first selectors with fallbacks: `[data-testid="email"], #id_email`

Full test ID naming reference: `docs/testing/TESTID-NAMING-CONVENTION.md`
