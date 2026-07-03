# Review Manager App

Session lifecycle, 9-state workflow, invitations, and configuration.

## Models

| Model | Purpose |
|-------|---------|
| `SearchSession` | Core entity. 9-state workflow with `set_status`, `can_transition_to`, `get_allowed_transitions` |
| `ReviewConfiguration` | Workflow config. `is_workflow_2` property (see root CLAUDE.md for detection rules) |
| `ReviewInvitation` | Magic link invitations (see root CLAUDE.md for token/expiry details) |
| `SessionActivity` | Activity logging (`log_activity` classmethod) |
| `ConfigurationChange` | Audit trail for config changes |

## Views

| File | Key Views |
|------|-----------|
| `views_main.py` | `DashboardView`, `SessionCreateView`, `SessionDetailView`, `SessionDeleteView`, `SessionArchiveView` |
| `views_invitations.py` | Invitation management |
| `views_approvals.py` | Approval workflows |
| `api_views.py` | API endpoints |

**Setup guard**: Session creation now includes configuration inline — no separate setup step. `SessionCreateView` creates both the session and its initial `ReviewConfiguration` atomically.

## Signals (`signals.py`)

Custom signals: `session_created`, `session_status_changed`, `session_deleted`, `session_data_requested`. Handlers for cache invalidation and invitation dispatch.

## Other Key Files

- `signals_denormalized.py` -- denormalised field sync signals
- `access.py` -- `check_session_access(user, session)`: owner-or-accepted-invitation check, shared by review_results and reporting (acceptance enforces `user.email == invitee_email`)
- `forms.py` -- session/config forms
- `mixins.py` -- shared view mixins
- `managers.py` -- custom QuerySet managers
- `tasks/` -- Celery tasks for async operations
- `services/` -- session lifecycle services
- `views/sse.py` -- SSE for real-time session updates
