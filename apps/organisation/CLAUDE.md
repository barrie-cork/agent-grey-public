# Organisation App

Multi-tenant organisation management.

## Models

| Model | Purpose |
|-------|---------|
| `Organisation` | Tenant with review/user quotas. Methods: `is_at_review_quota`, `is_at_user_quota`, `is_member` |
| `OrganisationMembership` | User-organisation link with role-based permissions (`save()` sets permissions) |
| `OrganisationInvitation` | Magic link invitations (`get_magic_link_url_name`) |

## Views

| View | Purpose |
|------|---------|
| `CreateOrganisationView` | Create named org from profile page. Creator becomes INFORMATION_SPECIALIST (owner) |
| `OrganisationDashboardView` | Org dashboard (metrics, members, invite form). Enforces membership check. Invite form shown only to `can_manage_users` members (Information Specialist) |
| `InviteUserView` | Send invitations (POST) |
| `AcceptInvitationView` | Magic link acceptance (GET/POST) |
| `OrganisationMetricsAPIView` | Organisation metrics API |

## Templates

| Template | Location | Purpose |
|----------|----------|---------|
| `organisation/create.html` | `templates/organisation/` | Create organisation form |
| `organisation/dashboard.html` | `templates/organisation/` | Org dashboard: metrics cards, members list, invite form (owner-only), pending invitations, quota status |
| `organisation/invitation_accept.html` | `templates/organisation/` | Magic link landing page (GET) with accept button |
| `organisation/invitation_invalid.html` | `templates/organisation/` | Expired/revoked/accepted invitation page |
| `organisation/invitation_error.html` | `templates/organisation/` | Acceptance failure page (e.g. email mismatch) |

## Other Files

- `forms.py` -- `CreateOrganisationForm` (name field, auto-slug generation)
- `middleware.py` -- organisation context middleware
- `context.py` -- organisation context utilities
- `api/` -- API endpoints
- `services/` -- organisation services
