# Accounts App

Authentication and user management.

## Model

- `User` -- custom user model with UUID primary key

## Views

| View | Purpose |
|------|---------|
| `SignUpView` | Registration. **Email-only form** (`email`, `password1`, `password2`). Username auto-generated from email prefix |
| `LoginView` | Authentication via `CustomAuthenticationForm` |
| `ProfileView` | User profile management. Shows "Your Organisations" section with active memberships |

## Forms

| Form | Notes |
|------|-------|
| `SignUpForm` | **No `username`, `first_name`, or `last_name` fields** |
| `ProfileForm` | Email update with validation |
| `CustomAuthenticationForm` | Login with custom validation |
| `AdminUserCreationForm` | Admin-only user creation |

## Other Files

- `signals.py` -- post-save/post-login signals
- `backends.py` -- custom authentication backend
- `permissions.py` -- `Permissions` class: centralised permission string registry and `get_role_permissions(role)` mapping for 5 organisation roles (INFORMATION_SPECIALIST, SENIOR_RESEARCHER, LEAD_REVIEWER, REVIEWER, OBSERVER). Conflict permissions (CONFLICT_VIEW, CONFLICT_COMMENT, CONFLICT_RESOLVE) are restricted to SENIOR_RESEARCHER and INFORMATION_SPECIALIST; REVIEWER and LEAD_REVIEWER access their own conflicts via `is_conflicting_reviewer` view-level checks instead of role permissions.
