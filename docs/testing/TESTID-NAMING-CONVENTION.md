# Test ID Naming Convention

> Reference guide for `data-testid` attributes used in E2E and visual regression testing.

Created: 2025-12-30
Last Updated: 2026-02-22

## Naming Pattern

Use semantic action names following the format:

```
{action}-{context}-{element-type}
```

Where:
- **action**: The primary user action or purpose (submit, create, delete, filter, nav)
- **context**: The domain context or resource type (login, session, result, comment)
- **element-type**: The UI element suffix (-btn, -input, -link, -card, -row)

## Element Type Reference

### Buttons

| Pattern | Example | Usage |
|---------|---------|-------|
| `submit-{form}-btn` | `submit-login-btn` | Form submission buttons |
| `create-{resource}-btn` | `create-session-btn` | Resource creation buttons |
| `delete-{resource}-btn` | `delete-session-btn` | Deletion buttons |
| `{action}-{context}-btn` | `claim-result-btn` | Action buttons |
| `filter-{type}-btn` | `filter-pending-btn` | Filter toggle buttons |
| `cancel-{action}-btn` | `cancel-create-btn` | Cancel/dismiss buttons |

### Inputs

| Pattern | Example | Usage |
|---------|---------|-------|
| `input-{field}` | `input-username` | Text inputs |
| `input-{field}` | `input-search-query` | Search inputs |
| `input-{field}` | `input-comment-text` | Textarea inputs |

**Note:** For backwards compatibility, some existing inputs use legacy patterns (`username`, `password`). These should be preserved.

### Links

| Pattern | Example | Usage |
|---------|---------|-------|
| `link-{destination}` | `link-forgot-password` | Page navigation links |
| `nav-{destination}` | `nav-dashboard` | Navigation menu links |

### Cards and Rows

| Pattern | Example | Usage |
|---------|---------|-------|
| `{resource}-card` | `session-card` | Card components |
| `{resource}-row` | `result-row` | Table/list rows |
| `{resource}-item` | `conflict-item` | List items |

### Containers

| Pattern | Example | Usage |
|---------|---------|-------|
| `{feature}-container` | `work-queue` | Feature containers |
| `{resource}-list` | `conflict-list` | List containers |
| `{resource}-grid` | `session-grid` | Grid containers |

### Status and Indicators

| Pattern | Example | Usage |
|---------|---------|-------|
| `status-badge` | `status-badge` | Status indicators |
| `{resource}-status` | `session-status` | Resource-specific status |
| `progress-{type}` | `progress-count` | Progress indicators |
| `error-alert` | `error-alert` | Error messages |

## Quick Reference Table

| Element | Pattern | Example |
|---------|---------|---------|
| Submit button | `submit-{form}-btn` | `submit-login-btn` |
| Create button | `create-{resource}-btn` | `create-session-btn` |
| Delete button | `delete-{resource}-btn` | `delete-session-btn` |
| Text input | `input-{field}` | `input-username` |
| Navigation link | `nav-{destination}` | `nav-dashboard` |
| Card component | `{resource}-card` | `session-card` |
| List row | `{resource}-row` | `result-row` |
| Container | descriptive name | `work-queue` |
| Status | `{context}-status` | `session-status` |

## Anti-Patterns to Avoid

### 1. Generic Names
```html
<!-- BAD -->
<button data-testid="button">Submit</button>
<button data-testid="btn1">Create</button>
<input data-testid="input1" />

<!-- GOOD -->
<button data-testid="submit-login-btn">Submit</button>
<button data-testid="create-session-btn">Create</button>
<input data-testid="input-username" />
```

### 2. Implementation-Specific Names
```html
<!-- BAD: References component internals -->
<div data-testid="vue-component-wrapper">
<button data-testid="onclick-handler">

<!-- GOOD: Describes user-facing purpose -->
<div data-testid="work-queue">
<button data-testid="claim-result-btn">
```

### 3. CSS Class-Like Names
```html
<!-- BAD: Looks like CSS class -->
<button data-testid="btn-primary-large">
<div data-testid="card-container-flex">

<!-- GOOD: Semantic action names -->
<button data-testid="submit-signup-btn">
<div data-testid="session-card">
```

### 4. Dynamic IDs Without Base
```html
<!-- BAD: No way to select all items -->
<div data-testid="{{ session.id }}">

<!-- GOOD: Base testid with optional dynamic suffix -->
<div data-testid="session-card" data-session-id="{{ session.id }}">
<!-- OR for unique selection: -->
<div data-testid="session-card-{{ session.id }}">
```

### 5. Duplicates Across Components
Ensure testids are unique within a page context. If the same element appears in multiple contexts, add context prefix:

```html
<!-- BAD: Ambiguous which delete -->
<button data-testid="delete-btn">  <!-- In session card -->
<button data-testid="delete-btn">  <!-- In result row -->

<!-- GOOD: Context-aware -->
<button data-testid="delete-session-btn">
<button data-testid="delete-result-btn">
```

## Usage in Playwright Tests

### Basic Selectors
```typescript
// Single element
await page.locator('[data-testid="submit-login-btn"]').click();

// Text input
await page.fill('[data-testid="input-username"]', 'user@example.com');

// Wait for element
await page.waitForSelector('[data-testid="work-queue"]');
```

### Multiple Elements
```typescript
// Count items
const count = await page.locator('[data-testid="session-card"]').count();

// Iterate
const cards = page.locator('[data-testid="session-card"]');
for (let i = 0; i < await cards.count(); i++) {
  await cards.nth(i).click();
}
```

### Dynamic Selection
```typescript
// Select by partial match (prefix)
await page.locator('[data-testid^="session-card-"]').first().click();

// Select specific by full ID
await page.locator('[data-testid="session-card-abc123"]').click();

// Combine with other attributes
await page.locator('[data-testid="session-card"][data-status="active"]').click();
```

## Coverage by Page

### Authentication Pages

| Page | Test IDs |
|------|----------|
| Login | `username`, `password`, `login-btn`, `link-forgot-password`, `link-signup` |
| Signup | `submit-signup-btn`, `input-email`, `input-password1`, `input-password2` |
| Profile | `submit-profile-btn`, `link-change-password`, `delete-account-btn` |
| Password Reset | `input-email`, `submit-reset-btn`, `link-back-login` |

### Review Manager Pages

| Page | Test IDs |
|------|----------|
| Dashboard | `create-session-btn`, `session-card`, `input-search-sessions`, `filter-*` |
| Session Detail | `session-status-badge`, `execute-search-btn`, `invite-reviewer-btn`, `link-search-strategy` (draft/defining_search), `link-start-review` (ready_for_review/under_review), `primary-action-btn` (other states) |
| Session Setup | `submit-setup-btn` |
| Session Create | `submit-create-session-btn`, `cancel-create-btn`, form inputs |

### Screening Interface (Vue SPA)

| Component | Test IDs |
|-----------|----------|
| WorkQueue | `work-queue`, `claim-button`, `work-queue-row`, `filter-pending-btn` |
| ConflictList | `conflict-list`, `conflict-item`, `resolve-conflict-btn` |
| ScreeningDecision | `include-btn`, `exclude-btn`, `maybe-btn`, `skip-result-btn` |

### Navigation (base.html)

| Element | Test ID |
|---------|---------|
| Logo link | `nav-logo` |
| My Reviews link | `nav-dashboard` |
| Invitations link | `nav-invitations` |
| Profile link | `nav-profile` |
| Logout button | `nav-logout` |
| Login link | `nav-login` |
| Sign Up link | `nav-signup` |
| Admin Dashboard link | `nav-admin` |
| Feedback float button | `open-feedback-btn` |

### Feedback Modal

| Element | Test ID |
|---------|---------|
| Modal container | `feedback-modal` |
| Feedback type select | `input-feedback-type` |
| Subject input | `input-feedback-subject` |
| Message textarea | `input-feedback-message` |
| Submit button | `submit-feedback-btn` |
| Cancel button | `cancel-feedback-btn` |
| Toast notification | `feedback-toast` |

### Reporting Pages

| Page | Test IDs |
|------|----------|
| Dashboard | `prisma-flow`, `total-count`, `duplicates-count`, `reviewed-count`, `included-count`, `excluded-count`, `maybe-count`, `submit-generate-report-btn`, `return-to-search-strategy-btn`, `archive-session-btn` |
| Generate Report | `generate-report-form`, `format-card-pdf`, `format-card-csv`, `format-card-json`, `submit-generate-report-btn`, `cancel-generate-btn` |
| Import Backup | `import-form`, `link-back-review`, `import-progress`, `import-result`, `submit-import-btn`, `cancel-import-btn` |
| Report List | `filter-form`, `filter-status-completed`, `filter-status-pending`, `filter-status-failed`, `filter-format`, `filter-date-range`, `submit-filter-btn`, `clear-filter-link`, `report-row`, `view-report-link`, `download-report-link`, `delete-report-btn`, `delete-modal`, `confirm-delete-btn`, `no-reports-message` |
| Report Detail | `report-detail-container`, `report-status`, `download-report-btn`, `preview-report-link`, `generate-similar-btn` |
| PRISMA Checklist | `prisma-checklist-container`, `checklist-item` (on each checkbox), `save-checklist-btn`, `export-checklist-btn`, `print-checklist-btn`, `reset-checklist-btn`, `progress-completed-count`, `progress-bar` |

### Results Manager Pages

| Page | Test IDs |
|------|----------|
| No Results Found | `no-results-container`, `query-item`, `create-search-btn`, `link-back-session`, `link-back-dashboard` |
| Processing Status | `processing-container`, `stat-total-results`, `stat-processed-count`, `stat-duplicate-count`, `stat-unique-count`, `refresh-status-btn`, `link-session-details`, `toggle-filtering-details-btn` |

### Review Results Pages

| Page | Test IDs |
|------|----------|
| Results Overview | `result-row`, `filter-pending-btn`, `filter-included-btn`, `filter-excluded-btn`, `complete-review-btn`, `mark-complete-button`, `confirm-complete-button` |
| Filtered Results | `filtered-results-container`, `filter-type-select`, `per-page-select`, `submit-filter-btn`, `filtered-result-item`, `include-anyway-btn`, `link-back-review` |
| Duplicate Groups | `duplicate-groups-container`, `expand-all-btn`, `collapse-all-btn`, `per-page-select`, `duplicate-group-card`, `link-back-review`, `link-filtered-results`, `link-search-statistics` |
| Search Statistics | `search-stats-container`, `link-back-review`, `stat-total-queries`, `stat-completion-rate`, `stat-total-results`, `stat-failed-queries`, `query-table` |

### Search Strategy Pages

| Page | Test IDs |
|------|----------|
| Strategy Form | `save-strategy-btn`, `execute-search-btn`, `cancel-strategy-btn` |

### SERP Execution Pages

| Page | Test IDs |
|------|----------|
| Execution Status | `execution-status-container`, `status-badge`, `progress-bar`, `auto-redirect-toggle`, `retry-btn`, `reconcile-state-btn`, `link-back-strategy`, `stat-total-queries`, `stat-completed-queries`, `stat-running-queries`, `stat-failed-queries` |
| Error Recovery | `error-recovery-container`, `recovery-form`, `submit-recovery-btn`, `link-back-status` |

### Pending Approvals

| Element | Test ID |
|---------|---------|
| Container | `pending-approvals-container` |
| Table row | `approval-row` |
| Approve button | `approve-reviewers-btn` |
| Reject button | `reject-reviewers-btn` |
| View reviewers button | `view-reviewers-btn` |
| Rejection modal | `rejection-modal` |
| Rejection reason textarea | `input-rejection-reason` |
| Submit rejection button | `submit-rejection-btn` |

## Adding New Test IDs

When adding a new testid:

1. **Check existing patterns** - Use `grep -r "data-testid" apps/` to see current conventions
2. **Follow the naming pattern** - `{action}-{context}-{element-type}`
3. **Be specific** - Avoid generic names that could conflict
4. **Document coverage** - Update this file's coverage tables
5. **Test selectors** - Verify in browser DevTools before writing tests

## Backwards Compatibility

Some legacy testids exist that don't follow the current convention:

| Legacy ID | Used In | Keep For |
|-----------|---------|----------|
| `username` | login.html | E2E test compatibility |
| `password` | login.html | E2E test compatibility |
| `login-btn` | login.html | E2E test compatibility |

These should be preserved. New elements should follow the semantic convention.
