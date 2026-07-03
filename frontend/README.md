# Agent Grey -- Frontend Overview

A Vue 3 single-page application (SPA) embedded within a Django application for systematic review screening workflows. This document is intended as a design onboarding guide.

## Technology Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Framework | Vue 3.5 + TypeScript 5.9 | Composition API, `<script setup>` |
| Build | Vite 7 | Dev server + production bundler |
| Styling | Tailwind CSS v4 | Utility-first, OKLCH colour space |
| Component library | shadcn-vue (Reka UI) | Unstyled primitives with custom theme |
| Icons | Lucide Vue Next | Consistent line-icon set |
| State management | Pinia | Per-domain stores |
| Routing | Vue Router 4 | Lazy-loaded views |
| Storybook | Storybook 10 | Component development + visual testing |
| Unit tests | Vitest 4 | With happy-dom |

## Design System Architecture

The design system is token-driven and lives in three layers:

```
tokens.css             -- Design tokens (colours, typography, spacing, shadows, radii)
  |
main.css               -- Vue SPA styles (imports tokens, base layer, component styles)
django.css             -- Django template styles (imports tokens, template scanning)
  |
shadcn-vue components  -- UI primitives consuming tokens via Tailwind classes
  |
shared components      -- Domain-specific components (decisions, conflicts, comments)
  |
views                  -- Full page compositions
```

### Design Tokens (`src/assets/styles/tokens.css`)

All tokens are defined using Tailwind CSS v4's `@theme inline` directive. Colours use the **OKLCH** colour space for perceptually uniform lightness.

#### Brand Palette

| Token | OKLCH Value | Role |
|-------|------------|------|
| `--color-deep-navy` | `oklch(0.25 0.05 250)` | Primary brand, headings, navigation |
| `--color-teal-blue` | `oklch(0.62 0.12 185)` | Accent, links, focus rings |
| `--color-amber-gold` | `oklch(0.78 0.16 75)` | Highlights, warnings |
| `--color-off-white` | `oklch(0.98 0.003 90)` | Page backgrounds |
| `--color-cool-grey-light` | `oklch(0.91 0.005 250)` | Secondary surfaces |
| `--color-cool-grey-dark` | `oklch(0.58 0.02 250)` | Muted text |

Each brand colour has `-light` and `-dark` variants for hover/active states.

#### Semantic Colour Mapping

Tokens map to shadcn-vue's expected semantic names:

| Semantic Token | Maps To | Usage |
|---------------|---------|-------|
| `--color-primary` | Deep Navy | Buttons, navigation bar |
| `--color-secondary` | Cool Grey Light | Secondary actions, tags |
| `--color-accent` | Teal Blue | Links, focus indicators |
| `--color-muted` | Neutral 100 | Disabled states, backgrounds |
| `--color-destructive` | Error Red | Delete actions, error states |

#### Status Colours

Four semantic status sets, each with base / light / dark variants:

- **Success** (green, hue 145) -- completed states, include decisions
- **Warning** (amber, hue 75) -- caution states, maybe decisions
- **Error** (red, hue 25) -- error states, exclude decisions
- **Info** (blue, hue 250) -- informational callouts

#### Decision Colours

Domain-specific colours for the review screening workflow:

| Decision | Colour | Token prefix |
|----------|--------|-------------|
| Include | Green (hue 145) | `--color-decision-include` |
| Exclude | Red (hue 25) | `--color-decision-exclude` |
| Maybe | Amber (hue 70) | `--color-decision-maybe` |

#### Conflict Status Colours

| Status | Colour | Token prefix |
|--------|--------|-------------|
| Pending | Slate | `--color-status-pending` |
| In Discussion | Blue | `--color-status-discussion` |
| Resolved | Green | `--color-status-resolved` |
| Escalated | Amber | `--color-status-escalated` |

#### Neutral Scale

An 11-step grey scale from `neutral-50` (near white) to `neutral-950` (near black), all on hue 250 for cool-toned consistency.

#### Typography

| Token | Value |
|-------|-------|
| `--font-family-sans` | Inter, system fallbacks |
| `--font-family-mono` | SF Mono, Monaco, monospace fallbacks |
| Font sizes | `xs` (0.75rem) through `8xl` (6rem) |
| Font weights | light (300), normal (400), medium (500), semibold (600), bold (700) |

#### Other Token Categories

- **Shadows**: `sm` through `2xl`, plus `focus`, `card`, `card-hover`
- **Border radius**: `sm` (0.125rem) through `full` (9999px), plus `card` and `button` shortcuts
- **Z-index scale**: `dropdown` (1000) through `toast` (1080)
- **Transitions**: `fast` (100ms), `base` (150ms), `slow` (300ms), `slower` (500ms)
- **Container widths**: `sm` (540px) through `2xl` (1320px)

#### Dark Mode

Dark mode tokens are defined under a `.dark` class but are **not yet activated** in the UI. The token overrides are ready and cover background, foreground, card, primary, secondary, muted, accent, and border colours.

#### High Contrast

A `@media (prefers-contrast: high)` block increases primary and border contrast for accessibility.

## Component Library

### UI Primitives (`src/components/ui/`)

Built with **shadcn-vue** (backed by Reka UI headless primitives). These are unstyled accessible components themed via Tailwind utility classes and design tokens.

| Component | Variants/Notes |
|-----------|---------------|
| Alert, AlertDialog | Info/warning/error/success |
| Avatar | Image + fallback initials |
| Badge | Default, secondary, destructive, outline |
| Breadcrumb | Navigation trail |
| Button | default, destructive, outline, secondary, ghost, link; sizes: default, sm, lg, icon |
| Card | Header, content, footer, description, title |
| Checkbox | With label |
| Dialog | Modal with header, footer, scroll content |
| DropdownMenu | Items, labels, separators, sub-menus |
| Input, Textarea, Label | Form controls |
| Popover | Positioned overlay |
| Progress | Percentage bar |
| ScrollArea | Custom scrollbar |
| Select | Dropdown with groups |
| Separator | Horizontal/vertical divider |
| Sheet | Slide-out panel (side drawer) |
| Skeleton | Loading placeholder |
| Sonner | Toast notifications |
| Switch | Toggle |
| Table | Data table with header, body, footer |
| Tabs | Tabbed navigation |
| Tooltip | Hover information |

### Domain Components (`src/components/shared/`)

Purpose-built components for the review workflow:

| Component | Purpose |
|-----------|---------|
| `Comment` | Single discussion comment with author and timestamp |
| `CommentForm` | Text input for adding comments |
| `CommentThread` | Threaded comment display with nesting |
| `ConflictHeader` | Conflict metadata banner (type, status, result info) |
| `DecisionCard` | Reviewer's decision display (include/exclude/maybe with rationale) |
| `ErrorAlert` | Standardised error display |
| `LoadingSpinner` | Animated loading indicator |
| `RevotePanel` | Re-vote workflow UI |
| `RevoteProposalCard` | Proposal to re-vote display |
| `StatusBadge` | Colour-coded status indicator |

### Custom UI Components

| Component | Purpose |
|-----------|---------|
| `DecisionButtons` | Include/Exclude/Maybe action buttons with domain colours |
| `ErrorDisplay` | Error state with retry action |
| `LoadingState` | Spinner/skeleton loading states |
| `ResultCard` | Search result display (title, snippet, URL, metadata) |
| `StatusBadge` (ui) | Generic status indicator with variant support |

## Application Views

The SPA serves the dual-screening review workflow under `/screening/`:

| Route | View | Purpose |
|-------|------|---------|
| `/work-queue` | WorkQueue | Reviewer's task list of results to screen |
| `/results/:id/screen` | ScreeningDecision | Individual result screening interface |
| `/conflicts` | ConflictList | List of reviewer disagreements |
| `/conflicts/:id` | ConflictResolution | Resolve a specific conflict (threaded discussion, re-vote, resolution) |
| `/dashboard` | TeamDashboard | Progress, IRR metrics, reviewer performance |
| `/component-showcase` | ComponentShowcase | Development reference (no auth required) |

## Layout Structure

The `App.vue` shell provides:

- **Navigation bar** (deep navy background) with Lucide icons, mobile hamburger menu, user dropdown
- **Main content area** with route transitions (fade animation)
- **Footer** (muted background)
- **Global loading overlay** (dark backdrop + spinner)

The navigation shows contextually: the Dashboard link is only visible to users with appropriate permissions. A conflict count badge appears when unresolved conflicts exist.

## Dual Frontend Architecture

Agent Grey has two CSS entry points because the application spans both:

1. **Vue SPA** (`main.css`) -- the screening interface described above
2. **Django templates** (`django.css`) -- server-rendered pages for session management, search strategy, authentication, organisation management

Both import the same `tokens.css`, ensuring visual consistency across the two rendering approaches. A designer working on either surface uses the same design tokens and brand palette.

The Django templates are scanned for Tailwind class usage via `@source` directives in `django.css`, covering both project-level and app-level template directories.

## State Management (Pinia Stores)

| Store | Manages |
|-------|---------|
| `auth` | User authentication, role, permissions |
| `organisation` | Current organisation context |
| `workQueue` | Result queue, claiming, pagination |
| `conflicts` | Conflict list, filtering |
| `consensusDiscussion` | Comments, re-vote proposals, SSE updates |
| `dashboard` | Team stats, IRR metrics, reviewer breakdown |

## Real-Time Updates

Server-Sent Events (SSE) via the `useConflictSSE` composable provide live updates during conflict discussions (new comments, status changes, re-vote outcomes).

## Storybook

Component stories exist for most shared and UI components. Run with:

```bash
cd frontend
npm run storybook
```

Storybook is configured with:
- **Backgrounds**: light (`oklch(98.5% 0.002 247)`) / dark (`oklch(14.1% 0.005 286)`)
- **Viewports**: mobile (375px), tablet (768px), desktop (1280px)
- **Accessibility**: a11y addon enabled (report mode)
- **Decorators**: components wrapped in `p-4 bg-background text-foreground`

Stories cover: Button, Card, Badge, Alert, Checkbox, Dialog, Input, Switch, Textarea, StatusBadge, DecisionButtons, and all shared components (Comment, CommentForm, CommentThread, ConflictHeader, DecisionCard, ErrorAlert, LoadingSpinner). View-level stories exist for ConflictResolution, ScreeningDecision, and WorkQueue.

## Key Design Files

| File | Purpose |
|------|---------|
| `src/assets/styles/tokens.css` | All design tokens (single source of truth) |
| `src/assets/styles/main.css` | Vue SPA base styles + legacy component styles |
| `src/assets/styles/django.css` | Django template styles + utility safelist |
| `src/lib/utils.ts` | `cn()` helper for Tailwind class merging |
| `.storybook/preview.ts` | Storybook theme and decorator configuration |
| `src/types/index.ts` | TypeScript interfaces matching Django models |

## Getting Started

```bash
cd frontend
npm install
npm run dev          # Dev server (hot reload)
npm run storybook    # Component explorer
npm run build        # Production build
npm run type-check   # TypeScript validation
npm run test:unit    # Unit tests
```

The Vue SPA is served by Django at `/screening/`. During development, the Vite dev server proxies API requests to the Django backend running in Docker.
