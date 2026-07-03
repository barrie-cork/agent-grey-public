# Static Files Directory Structure

This directory contains project-wide static files for the Thesis Grey Django application with a unified design system implementation.

## Directory Structure

```
static/
├── css/                    # Project-wide CSS files
│   ├── design-system/      # Unified Design System (NEW)
│   │   ├── tokens.css      # Design tokens (320+ variables)
│   │   └── components.css  # Reusable component library
│   └── style.css          # Main stylesheet with Bootstrap 5 customizations
├── js/                     # Project-wide JavaScript files
│   └── main.js            # Main JavaScript with common functionality
├── images/                 # Project-wide images
│   └── (logos, icons, etc.)
├── admin/                  # Django admin customizations
│   └── (admin-specific CSS/JS overrides)
└── README.md              # This file
```

## App-Specific Static Files

Each Django app can have its own static files in:
```
apps/{app_name}/static/{app_name}/
├── css/
├── js/
└── images/
```

### Currently Created App Static Directories:
- `apps/accounts/static/accounts/css/` - Authentication-specific styles (unified with design system)
- `apps/search_strategy/static/search_strategy/` - Search strategy UI components (unified)
- `apps/review_manager/static/review_manager/` - Dashboard and session management (unified)
- `apps/review_results/static/review_results/` - Results review interface (unified)
- `apps/results_manager/static/results_manager/` - Results processing components (unified)
- `apps/serp_execution/static/serp_execution/` - Search execution interface (unified)
- `apps/reporting/static/reporting/` - Reporting and PRISMA diagram visualization (unified)

## Unified Design System (2025-01-27)

The project now implements a comprehensive unified design system that eliminates UI/UX inconsistencies across all Django apps.

### Architecture:
- **Foundation Layer**: Bootstrap 5.3.0 as base framework
- **Token Layer**: `design-system/tokens.css` - 320+ design tokens
- **Component Layer**: `design-system/components.css` - Reusable component library
- **App Layer**: App-specific CSS using design system variables

### Key Features:
- ✅ **Single Primary Color**: `#0d6efd` used consistently across all apps
- ✅ **Unified Components**: Cards, buttons, forms, alerts, badges with consistent styling
- ✅ **Design Tokens**: Colors, spacing, typography, shadows, animations
- ✅ **Accessibility**: WCAG 2.1 AA compliant with focus indicators and high contrast support
- ✅ **Responsive**: Mobile-first design with consistent breakpoints
- ✅ **Performance**: Optimized CSS with minimal duplication

## JavaScript Framework

The project uses vanilla JavaScript with a main application object (`ThesisGrey`) that provides:
- CSRF token handling for AJAX requests
- Toast notification system
- Loading state management
- Form validation helpers
- API utilities

## Usage in Templates

### Loading Static Files:
```django
{% load static %}

<!-- Bootstrap 5 CSS (via CDN) -->
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">

<!-- Design System CSS (proper cascade order) -->
<link rel="stylesheet" href="{% static 'css/design-system/tokens.css' %}">
<link rel="stylesheet" href="{% static 'css/design-system/components.css' %}">

<!-- Main CSS -->
<link rel="stylesheet" href="{% static 'css/style.css' %}">

<!-- App-specific CSS overrides -->
{% block extra_css %}{% endblock %}

<!-- JavaScript -->
<script src="{% static 'js/main.js' %}"></script>
```

### Using the ThesisGrey JavaScript Object:
```javascript
// Show a toast notification
ThesisGrey.ui.showToast('Success message', 'success');

// Set button loading state
ThesisGrey.ui.setButtonLoading(button, true);

// Make API calls
ThesisGrey.api.get('/api/endpoint/')
    .then(data => console.log(data))
    .catch(error => console.error(error));
```

## Design System Usage

### Using Design System Components:
```django
<!-- Reusable Card Component -->
{% include 'components/card.html' with
   title="Session Details"
   content="Card content here"
   variant="interactive"
%}

<!-- Unified Button Component -->
{% include 'components/button.html' with
   text="Save Changes"
   variant="primary"
   size="lg"
   type="submit"
%}

<!-- Standardized Form Field -->
{% include 'components/form-field.html' with
   field=form.email
   label="Email Address"
   required=True
%}

<!-- Alert Component -->
{% include 'components/alert.html' with
   message="Success! Your action was completed."
   variant="success"
   dismissible=True
%}
```

### CSS Development Guidelines:
1. **Use design tokens**: Reference `--tg-*` variables, never hardcode values
2. **Use component classes**: Prefer `tg-card`, `tg-btn`, etc. over custom styles
3. **Follow naming convention**: `--tg-{category}-{property}` (e.g., `--tg-color-primary`)
4. **Extend systematically**: Add new tokens to `tokens.css`, new components to `components.css`
5. **Maintain accessibility**: Ensure focus indicators and semantic markup

### JavaScript:
1. Extend the `ThesisGrey` object for new functionality
2. Use the provided API utilities for consistency
3. Follow the established patterns for UI interactions
4. Ensure compatibility with Bootstrap 5 components

### File Organization:
1. Project-wide assets go in `/static/`
2. App-specific assets go in `apps/{app}/static/{app}/`
3. Use descriptive filenames
4. Keep files organized by type (css/, js/, images/)

## Django Settings

The static files are configured in `settings/base.py`:
```python
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'  # Production
STATICFILES_DIRS = [
    BASE_DIR / 'static',  # Development
]
```

## Collecting Static Files

For production deployment:
```bash
python manage.py collectstatic
```

This will collect all static files from `STATICFILES_DIRS` and app directories into `STATIC_ROOT` for serving by the web server.
