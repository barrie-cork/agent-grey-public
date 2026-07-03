# Visual Testing and Playwright MCP

Technical reference for UI inspection workflows using Playwright MCP and the responsive screenshot suite.

## Playwright MCP Setup

### Configuration

Playwright MCP is configured as a project-level MCP server in `.mcp.json`:

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest", "--headless"]
    }
  }
}
```

The server runs in **headless mode** by default for automated inspection. To switch to headed mode for interactive debugging, remove `--headless` from the args.

### Stale Browser Lock

**Before starting a new Claude Code session**, close the browser from the previous session to avoid a stale lock. If you see errors about a stale lock or the browser failing to connect:

```bash
# Kill any lingering headless Chrome processes from a previous Playwright MCP session
pkill -f 'chromium.*--headless' || true
pkill -f 'chrome.*--headless' || true
```

Alternatively, use `browser_close` at the end of each session to cleanly shut down the browser before exiting Claude Code. The stale lock occurs because the headless browser process from a previous session may still be running and holding the lock file.

### Verification

After restarting Claude Code, confirm the server is connected:

1. Check the status line shows `playwright` as connected
2. Run: `mcp__playwright__browser_navigate` to `http://localhost:8000/accounts/login/`
3. Run: `mcp__playwright__browser_snapshot` to confirm DOM is accessible
4. Run: `mcp__playwright__browser_evaluate` to check a computed style

### Key MCP Tools

| Tool | Purpose |
|------|---------|
| `browser_navigate` | Load a URL |
| `browser_snapshot` | Get accessible DOM tree (preferred over screenshot for actions) |
| `browser_take_screenshot` | Capture visual state as PNG |
| `browser_evaluate` | Run JS to check computed styles, dimensions, element state |
| `browser_resize` | Change viewport size |
| `browser_click` | Interact with elements (requires ref from snapshot) |
| `browser_fill_form` | Fill form fields |

## UI Improvement Workflow

### The Iterative Loop

This is the core feedback loop for perfecting UI layout:

```
1. Navigate to page (browser_navigate)
2. Set viewport (browser_resize)
3. Take snapshot (browser_snapshot) -- inspect DOM structure
4. Check computed styles (browser_evaluate) -- verify CSS values
5. Identify issue
6. Edit CSS/template
7. Rebuild Vite (npm run build:django in frontend/)
8. Reload page (browser_navigate to same URL)
9. Verify fix (browser_snapshot + browser_evaluate)
10. Repeat until perfect
```

### Quick Verification Pattern

```js
// Check sidebar margin on content wrapper
browser_evaluate: () => {
  const el = document.getElementById('content-wrapper');
  const styles = window.getComputedStyle(el);
  return { marginLeft: styles.marginLeft, width: styles.width };
}

// Check if sidebar is visible
browser_evaluate: () => {
  const sidebar = document.getElementById('sidebar');
  const styles = window.getComputedStyle(sidebar);
  return { transform: styles.transform, display: styles.display, visibility: styles.visibility };
}

// Check element dimensions and position
browser_evaluate: () => {
  const el = document.querySelector('.your-selector');
  const rect = el.getBoundingClientRect();
  return { top: rect.top, left: rect.left, width: rect.width, height: rect.height };
}
```

## Viewport Definitions

These match the responsive screenshot suite in `responsive-screenshots.spec.ts`:

| Name | Width | Height | Sidebar Behaviour | Breakpoint |
|------|-------|--------|-------------------|------------|
| mobile-375x667 | 375 | 667 | Hidden, hamburger toggle | < xl |
| tablet-768x1024 | 768 | 1024 | Hidden, hamburger toggle | < xl |
| small-laptop-1024x768 | 1024 | 768 | Hidden, hamburger toggle | < xl |
| laptop-1280x800 | 1280 | 800 | Visible (xl breakpoint) | >= xl (1280px) |
| desktop-1920x1080 | 1920 | 1080 | Visible | >= xl (1280px) |

**Key breakpoint**: `xl` (1280px) controls sidebar visibility. Below xl, the sidebar is off-screen (`-translate-x-full`) and toggled via hamburger. At xl+, the sidebar is fixed and content has `xl:ml-[260px]`.

## Standard Template Anatomy

All authenticated pages share this structure from `templates/base.html`:

```
<body class="min-h-screen">
  <!-- Sidebar (hidden on auth pages) -->
  <aside id="sidebar" class="fixed w-[260px] -translate-x-full xl:translate-x-0 xl:z-30">
    Logo + Brand
    Nav links (overflow-y-auto)
    User section (shrink-0)
  </aside>

  <!-- Content wrapper - offset by sidebar -->
  <div id="content-wrapper" class="xl:ml-[260px] min-h-screen flex flex-col">
    Content header (mobile toggle + breadcrumbs)
    Messages
    <main class="flex-1 w-full max-w-7xl mx-auto px-6 py-6">
      Page content
    </main>
    Feedback button (floating)
    <footer class="border-t border-border mt-auto">
      Copyright
    </footer>
  </div>
</body>
```

## CSS Debugging Patterns

### Computed Style Checks

```js
// Verify Tailwind class is actually applied
browser_evaluate: () => {
  const el = document.querySelector('#content-wrapper');
  return window.getComputedStyle(el).marginLeft;
}
// Expected: "260px" at xl+, "0px" below xl
```

### Class Detection

```js
// Check what classes an element has
browser_evaluate: () => {
  return document.querySelector('#sidebar').className;
}
```

### Tailwind Scanner Issues

**Problem**: Tailwind CSS v4 scans Django template HTML for class usage. Classes that appear inside multi-line attributes or Django template conditionals (`{% if %}`) may not be detected, causing them to be purged from the built CSS.

**Symptoms**: Layout breaks only in production/built CSS, works in dev with full Tailwind.

**Fix**: Add missing utilities to the safelist in `frontend/src/assets/styles/django.css` under `@layer utilities`:

```css
@layer utilities {
  /* Sidebar layout -- Django template conditionals break Tailwind scanner */
  .-translate-x-full { ... }
  @media (min-width: 1280px) {
    .xl\:ml-\[260px\] { margin-left: 260px; }
    .xl\:translate-x-0 { ... }
    .xl\:z-30 { z-index: 30; }
  }
}
```

**Key file**: `frontend/src/assets/styles/django.css` -- the Tailwind entry point that includes `@source` directives for Django template scanning.

### Vite Rebuild

After editing CSS or templates:

```bash
cd frontend && npm run build:django
```

This rebuilds the CSS bundle. The Django dev server serves from `static/dist/` which is populated by the Vite build. No Docker restart needed for CSS-only changes if running the dev server natively, but in Docker:

```bash
docker compose exec agent-grey python manage.py collectstatic --noinput
```

### `vite_asset_url` vs `vite_asset`

- `{% vite_asset_url 'src/assets/styles/django.css' %}` -- returns the URL only, use with `<link rel="stylesheet">`
- `{% vite_asset 'src/assets/styles/django.css' %}` -- generates a full tag, but may produce `<script>` for CSS entries

Always use `vite_asset_url` for CSS files in `base.html`.

## Screenshot Suite

### Capture

```bash
npx playwright test tests/e2e/visual/responsive-screenshots.spec.ts --project=chromium --workers=1
```

Output: `tests/screenshots/workflow_9_state/<view-name>/<viewport>.png`

### View List

The suite captures 17 views across 5 viewports (85 screenshots total):

**Unauthenticated**: login, signup, password-reset
**Dashboard/Account**: dashboard, create-session, profile, pending-invitations, report-list
**Session views**: session-detail-draft, session-setup-draft, search-strategy-defining-search, session-detail-ready-for-review-wf1, session-detail-completed-wf1
**Review views**: review-overview, filtered-results, duplicate-groups, reporting-dashboard

### Previous Captures

Responsive captures from the last run are stored in `tests/e2e/visual/responsive-captures/` (gitignored). Use these for before/after comparison.

## Known Gotchas

| Issue | Cause | Fix |
|-------|-------|-----|
| `xl:ml-[260px]` missing from built CSS | Django `{% if %}` conditional breaks Tailwind scanner | Safelisted in `django.css` `@layer utilities` |
| `-translate-x-full` not in built CSS | Multi-line class attributes break scanner | Safelisted in `django.css` |
| `{% vite_asset %}` generates `<script>` for CSS | Vite asset tag helper misidentifies CSS entry | Use `{% vite_asset_url %}` with `<link>` tag |
| Sidebar logo invisible (dark on dark) | Wrong logo variant used | Use `agent-grey-logo-login.png` with white background |
| `networkidle` timeout on session pages | SSE connections keep network active | Use `domcontentloaded` wait state |
| Feedback button overlaps content on mobile | Fixed positioning conflicts | Check `z-index` and `bottom` offset |
| Playwright MCP stale browser lock | Headless Chrome from previous session still running | `pkill -f 'chrom.*--headless'` or use `browser_close` before exiting |

---

## Dashboard Testing Plan (5 Viewports)

### Checkpoints Per Viewport

For each of the 5 viewports, verify the following using `browser_resize` + `browser_snapshot` + `browser_evaluate`:

#### Layout Structure

- [ ] Sidebar: correct visibility (hidden < 1280px, visible >= 1280px)
- [ ] Sidebar: logo + tagline visible and not clipped (xl+ only)
- [ ] Sidebar: nav links readable, no overflow (xl+ only)
- [ ] Sidebar: user section visible, not overlapping content (xl+ only)
- [ ] Content wrapper: correct left margin (0 below xl, 260px at xl+)
- [ ] Content header: sticky, full width within content wrapper
- [ ] Mobile toggle: visible below xl, hidden at xl+

#### Content Area

- [ ] Breadcrumb: "Dashboard" text visible, properly positioned
- [ ] Page title: "Your Grey Literature Reviews" readable
- [ ] Stats bar: Total/Active/Completed horizontally aligned
- [ ] Search box: full width within content area
- [ ] "New Review Session" button: visible, not clipped
- [ ] Session cards: proper grid layout (1 col mobile, 2-3 cols desktop)

#### Footer

- [ ] Copyright: "2026 Agent Grey" visible
- [ ] Feedback button: floating, not overlapping content
- [ ] Footer: not overlapping sidebar user section

#### Typography and Spacing

- [ ] No text truncation or overflow
- [ ] Consistent padding/margins
- [ ] Readable font sizes at each viewport

### Execution Procedure

For each viewport:

```
1. browser_navigate to http://localhost:8000/ (logged in)
2. browser_resize to {width}x{height}
3. browser_snapshot -- check DOM structure
4. browser_evaluate -- verify computed styles:
   - #content-wrapper marginLeft
   - #sidebar transform
   - Main content width
5. browser_take_screenshot for visual record
6. Log pass/fail for each checkpoint
```

### Pass/Fail Criteria

| Criterion | Pass | Fail |
|-----------|------|------|
| Sidebar visibility | Matches expected state for viewport | Visible when should be hidden, or vice versa |
| Content margin | 0px < xl, 260px >= xl | Content overlaps sidebar or has wrong offset |
| Text overflow | All text contained within bounds | Horizontal scroll, clipping, or truncation |
| Grid layout | Cards fill available width appropriately | Cards overflow, stack when shouldn't, or have gaps |
| Footer position | At bottom of content, not overlapping | Overlaps content or floating mid-page |
| Interactive elements | All buttons/links visible and clickable | Hidden, overlapping, or inaccessible |
