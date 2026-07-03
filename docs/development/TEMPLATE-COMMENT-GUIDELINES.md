# Django Template Comment Guidelines

## The Problem

Django's `{# ... #}` comment syntax **only works for single-line comments**. When spread across multiple lines, any `{% %}` template tags inside the "comment" are actually executed as real code.

This can cause serious issues including:
- **RecursionError**: If a commented `{% include %}` references the same template
- **Unexpected behaviour**: Template tags execute when they shouldn't
- **Security risks**: Unintended code execution

### Example: The Bug

```django
{#
  Usage example:
  {% include 'components/alert.html' with message="Hello" %}
#}
```

**What happens:** Django parses the `{% include %}` tag as real code, causing the alert template to be included. If this is inside `alert.html` itself, it creates infinite recursion.

## Correct Patterns

### Single-Line Comments

Use `{# ... #}` only for comments that fit on a single line:

```django
{# This is a safe single-line comment #}
{# Usage: include 'template.html' with var=value #}
```

### Multi-Line Comments

Use `{% comment %}...{% endcomment %}` for multi-line comments:

```django
{% comment %}
This is a safe multi-line comment.
Usage: {% include 'components/alert.html' with message="Hello" %}
The include tag above will NOT be executed.
{% endcomment %}
```

### Documentation Blocks

For component documentation, always use `{% comment %}` blocks:

```django
{% comment %}
Component: Alert
Displays a styled alert message.

Props:
  - message (required): The alert text
  - variant: "info" | "success" | "warning" | "error" (default: "info")

Example:
  {% include 'components/alert.html' with message="Hello" variant="success" %}
{% endcomment %}

<div class="alert alert-{{ variant|default:'info' }}">
    {{ message }}
</div>
```

## Incorrect Patterns (AVOID)

### Multi-Line {# #} Comments

**NEVER** spread `{# #}` across multiple lines:

```django
{#
  BAD: This comment contains template tags that WILL execute!
  {% include 'template.html' %}
  {% if condition %}...{% endif %}
#}
```

### {# #} With Template Tags

Even on a single line, be cautious with template tags in comments:

```django
{# BAD if this line is ever split during editing #}
{# Usage: {% include 'very-long-template-name.html' with param1=value1 param2=value2 %} #}
```

Better: Use `{% comment %}` when documenting template tag usage.

## Automated Enforcement

### Audit Script

Run the audit script to check all templates:

```bash
# Check all templates
python3 scripts/audit_template_comments.py

# Verbose output
python3 scripts/audit_template_comments.py --verbose
```

The script:
- Scans all HTML templates in `templates/` and `apps/*/templates/`
- Detects multi-line `{# #}` comments containing template tags
- Ignores safe `{% comment %}` blocks
- Returns exit code 1 if issues found (suitable for CI)

### Pre-commit Hook

The project includes a pre-commit hook that runs automatically:

```yaml
# In .pre-commit-config.yaml
- id: template-comment-audit
  name: Django Template Comment Audit
  entry: python3 scripts/audit_template_comments.py
  language: system
  types: [html]
```

To install pre-commit hooks:

```bash
pip install pre-commit
pre-commit install
```

To run manually:

```bash
pre-commit run template-comment-audit --all-files
```

To bypass in emergencies:

```bash
git commit --no-verify -m "Emergency fix"
```

## Fixing Violations

When the audit script reports an issue:

1. **Locate the file and lines** from the error message
2. **Identify the multi-line comment** starting with `{#`
3. **Convert to {% comment %} block**:

Before:
```django
{#
  Multi-line documentation
  {% include 'example.html' %}
#}
```

After:
```django
{% comment %}
Multi-line documentation
{% include 'example.html' %}
{% endcomment %}
```

4. **Run the audit again** to verify the fix

## History

This issue was discovered on 2026-01-01 when component template documentation caused `RecursionError` in production. The following templates were fixed:

- `templates/components/alert.html`
- `templates/components/button.html`
- `templates/components/card.html`
- `templates/components/collapsible.html`
- `templates/components/form-field.html`

## Related Resources

- [Django Template Language Documentation](https://docs.djangoproject.com/en/stable/ref/templates/language/#comments)
- `scripts/audit_template_comments.py` - Audit script source code
- `.pre-commit-config.yaml` - Pre-commit hook configuration
