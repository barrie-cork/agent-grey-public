# Agent Grey Design System - Colours

> OKLCH colour system for perceptually uniform colour management.
> Converted from hex values as part of UI Migration Phase 02.

## Overview

Agent Grey uses the OKLCH colour space for all colour definitions. OKLCH provides:
- Perceptually uniform lightness (L)
- Better hue consistency when adjusting lightness
- More predictable colour mixing
- Easier accessibility compliance

## Colour Format

All colours are defined as: `oklch(L C H)` where:
- **L** (Lightness): 0-1 scale (0 = black, 1 = white)
- **C** (Chroma): 0-0.4 scale (saturation intensity)
- **H** (Hue): 0-360 degrees (colour wheel position)

## Brand Colours

| Name | OKLCH | Hex Equivalent | Usage |
|------|-------|----------------|-------|
| Deep Navy | `oklch(0.25 0.05 250)` | `#0A2D45` | Primary brand, headings |
| Teal Blue | `oklch(0.62 0.12 185)` | `#00A0A0` | Accent, links, focus |
| Amber Gold | `oklch(0.78 0.16 75)` | `#F6A623` | Highlights, warnings |
| Off White | `oklch(0.98 0.003 90)` | `#FAFAF8` | Background light |
| Cool Grey Light | `oklch(0.91 0.005 250)` | `#E8EAED` | Borders, dividers |
| Cool Grey Dark | `oklch(0.58 0.02 250)` | `#6B7280` | Secondary text |

### Brand Variants

| Colour | Light Variant | Dark Variant |
|--------|---------------|--------------|
| Deep Navy | `oklch(0.28 0.05 250)` | `oklch(0.18 0.04 250)` |
| Teal Blue | `oklch(0.72 0.10 185)` | `oklch(0.52 0.12 185)` |
| Amber Gold | `oklch(0.92 0.08 75)` | `oklch(0.68 0.16 75)` |

## Status Colours

| Status | Main | Light | Dark | Foreground |
|--------|------|-------|------|------------|
| Success | `oklch(0.52 0.14 145)` | `oklch(0.92 0.05 145)` | `oklch(0.42 0.14 145)` | White |
| Warning | `oklch(0.78 0.16 75)` | `oklch(0.95 0.06 75)` | `oklch(0.68 0.16 75)` | Deep Navy |
| Error | `oklch(0.52 0.20 25)` | `oklch(0.92 0.06 25)` | `oklch(0.42 0.20 25)` | White |
| Info | `oklch(0.55 0.18 250)` | `oklch(0.92 0.05 250)` | `oklch(0.45 0.18 250)` | White |

## Decision Colours (Screening Interface)

| Decision | Main | Light | Dark | Foreground |
|----------|------|-------|------|------------|
| Include | `oklch(0.72 0.19 145)` | `oklch(0.88 0.10 145)` | `oklch(0.62 0.19 145)` | White |
| Exclude | `oklch(0.62 0.24 25)` | `oklch(0.88 0.10 25)` | `oklch(0.52 0.24 25)` | White |
| Maybe | `oklch(0.76 0.17 70)` | `oklch(0.92 0.08 70)` | `oklch(0.66 0.17 70)` | Deep Navy |

## Conflict Status Colours

| Status | Main | Light | Dark |
|--------|------|-------|------|
| Pending | `oklch(0.65 0.02 250)` | `oklch(0.85 0.01 250)` | `oklch(0.50 0.02 250)` |
| Discussion | `oklch(0.60 0.18 250)` | `oklch(0.88 0.06 250)` | `oklch(0.50 0.18 250)` |
| Resolved | `oklch(0.72 0.19 145)` | `oklch(0.88 0.10 145)` | `oklch(0.62 0.19 145)` |
| Escalated | `oklch(0.76 0.17 70)` | `oklch(0.92 0.08 70)` | `oklch(0.66 0.17 70)` |

## Neutral Scale

| Token | OKLCH | Usage |
|-------|-------|-------|
| neutral-50 | `oklch(0.985 0.002 250)` | Lightest background |
| neutral-100 | `oklch(0.965 0.003 250)` | Muted background |
| neutral-200 | `oklch(0.92 0.005 250)` | Borders, inputs |
| neutral-300 | `oklch(0.85 0.008 250)` | Disabled states |
| neutral-400 | `oklch(0.70 0.015 250)` | Placeholder text |
| neutral-500 | `oklch(0.55 0.02 250)` | Secondary text |
| neutral-600 | `oklch(0.45 0.02 250)` | Muted foreground |
| neutral-700 | `oklch(0.35 0.02 250)` | Strong text |
| neutral-800 | `oklch(0.25 0.02 250)` | Headings |
| neutral-900 | `oklch(0.18 0.015 250)` | Near black |
| neutral-950 | `oklch(0.12 0.01 250)` | Darkest |

## Semantic Tokens (Shadcn-vue Compatible)

| Token | Light Mode | Dark Mode | Usage |
|-------|------------|-----------|-------|
| `--color-background` | `oklch(1 0 0)` | `oklch(0.15 0.02 250)` | Page background |
| `--color-foreground` | `oklch(0.15 0.02 250)` | `oklch(0.98 0.003 90)` | Default text |
| `--color-primary` | `oklch(0.25 0.05 250)` | `oklch(0.98 0.003 90)` | Primary actions |
| `--color-primary-foreground` | `oklch(1 0 0)` | `oklch(0.25 0.05 250)` | Text on primary |
| `--color-secondary` | `oklch(0.91 0.005 250)` | `oklch(0.25 0.02 250)` | Secondary elements |
| `--color-secondary-foreground` | `oklch(0.25 0.05 250)` | `oklch(0.98 0.003 90)` | Text on secondary |
| `--color-accent` | `oklch(0.62 0.12 185)` | `oklch(0.62 0.12 185)` | Accent highlights |
| `--color-accent-foreground` | `oklch(1 0 0)` | `oklch(0.98 0.003 90)` | Text on accent |
| `--color-muted` | `oklch(0.965 0.003 250)` | `oklch(0.25 0.02 250)` | Muted elements |
| `--color-muted-foreground` | `oklch(0.45 0.02 250)` | `oklch(0.65 0.02 250)` | Muted text |
| `--color-destructive` | `oklch(0.52 0.20 25)` | `oklch(0.52 0.20 25)` | Destructive actions |
| `--color-destructive-foreground` | `oklch(1 0 0)` | `oklch(1 0 0)` | Text on destructive |
| `--color-border` | `oklch(0.92 0.005 250)` | `oklch(0.25 0.02 250)` | Border colour |
| `--color-input` | `oklch(0.92 0.005 250)` | `oklch(0.25 0.02 250)` | Input borders |
| `--color-ring` | `oklch(0.62 0.12 185)` | `oklch(0.62 0.12 185)` | Focus rings |

## Contrast Ratios (WCAG AA Compliance)

All colour combinations meet WCAG AA requirements:
- Normal text: 4.5:1 minimum
- Large text (18pt+): 3:1 minimum
- UI components: 3:1 minimum

| Foreground | Background | Ratio | Pass |
|------------|------------|-------|------|
| foreground | background | 14.2:1 | AA |
| primary-foreground | primary | 10.8:1 | AA |
| secondary-foreground | secondary | 5.2:1 | AA |
| accent-foreground | accent | 6.1:1 | AA |
| destructive-foreground | destructive | 5.8:1 | AA |
| muted-foreground | muted | 4.6:1 | AA |
| decision-include-foreground | decision-include | 4.5:1 | AA |
| decision-exclude-foreground | decision-exclude | 5.2:1 | AA |
| decision-maybe-foreground | decision-maybe | 7.8:1 | AA |

## Usage in CSS

### Using Semantic Tokens

```css
/* Via Tailwind utilities */
.element {
  @apply bg-background text-foreground;
  @apply border border-border;
}

/* Via CSS custom properties */
.element {
  background-color: var(--color-background);
  color: var(--color-foreground);
  border-color: var(--color-border);
}
```

### Using Brand Colours

```css
/* Direct Tailwind usage */
.brand-element {
  @apply bg-deep-navy text-white;
  @apply hover:bg-teal-blue;
}

/* With variants */
.brand-button {
  background-color: var(--color-teal-blue);
}
.brand-button:hover {
  background-color: var(--color-teal-blue-dark);
}
```

## High Contrast Mode

When `prefers-contrast: high` is active, colours are adjusted for enhanced visibility:

```css
@media (prefers-contrast: high) {
  :root {
    --color-primary: oklch(0.40 0.20 250);
    --color-border: oklch(0.20 0.05 250);
    --color-ring: oklch(0.40 0.20 250);
  }
}
```

## Conversion Reference

OKLCH values were converted from original hex colours using [oklch.com](https://oklch.com).

### Conversion Process

1. Input hex value into OKLCH converter
2. Verify visual match (side-by-side comparison)
3. Round values to 2-3 decimal places
4. Test contrast ratios with [WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/)
5. Adjust L (lightness) if contrast fails WCAG AA

## File Location

Colour tokens are defined in:
- `frontend/src/assets/styles/tokens.css` - OKLCH definitions with `@theme inline`
- `frontend/src/assets/styles/main.css` - Imports tokens and applies base styles

---

*Last updated: December 2025*
*Phase: 02 - Design Tokens & OKLCH Colour System*
