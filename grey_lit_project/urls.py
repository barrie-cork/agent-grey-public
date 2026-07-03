"""
URL configuration for grey_lit_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

import json

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.middleware.csrf import get_token
from django.urls import include, path
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import TemplateView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.core.views.metrics import prometheus_metrics_view


@login_required
@ensure_csrf_cookie
def vue_spa(request, path=""):
    """Serve the Vue SPA index.html for all /screening/ routes.

    Injects user and organisation context as a JSON script tag so the
    Vue auth and organisation stores can initialise without an extra API call.
    Vue Router handles client-side routing within the SPA.
    """
    index_file = settings.BASE_DIR / "static" / "dist" / "index.html"
    html = index_file.read_text()

    # Build user data for Vue stores
    user = request.user
    user_data = {
        "user": {
            "id": str(user.pk),
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
        },
    }

    # Add session context if session_id is in query params (e.g. from conflict sidebar link)
    session_id = request.GET.get("session_id")
    if session_id:
        from apps.review_manager.models import SearchSession

        try:
            session = SearchSession.objects.select_related("current_configuration").get(
                id=session_id,
                organisation__memberships__user=user,
                organisation__memberships__is_active=True,
            )
            user_data["session"] = {
                "id": str(session.pk),
                "is_workflow_2": session.current_configuration.is_workflow_2,
            }
        except (SearchSession.DoesNotExist, ValueError):
            pass

    # Add organisation and membership if available
    from apps.organisation.models import OrganisationMembership

    membership = (
        OrganisationMembership.objects.filter(user=user, is_active=True)
        .select_related("organisation")
        .first()
    )
    if membership:
        user_data["organisation"] = {
            "id": str(membership.organisation.pk),
            "name": membership.organisation.name,
            "created_at": membership.organisation.created_at.isoformat(),
        }
        user_data["membership"] = {
            "id": str(membership.pk),
            "organisation": user_data["organisation"],
            "user": user_data["user"],
            "role": membership.role,
            "joined_at": membership.joined_at.isoformat(),
        }

    # Inject CSRF token meta tag for JS access (needed when CSRF_COOKIE_HTTPONLY=True)
    csrf_token = get_token(request)
    csrf_meta = f'<meta name="csrf-token" content="{csrf_token}">'
    html = html.replace("</head>", f"{csrf_meta}\n</head>")

    # Inject user-data script tag before </body>
    user_data_tag = (
        f'<script id="user-data" type="application/json">'
        f"{json.dumps(user_data)}</script>"
    )
    html = html.replace("</body>", f"{user_data_tag}\n</body>")

    return HttpResponse(html, content_type="text/html")


def trigger_error(request):
    """Sentry test endpoint - triggers a test error."""
    # Intentional error trigger for Sentry testing
    return 1 / 0


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", include("apps.health.urls")),  # Health check endpoints
    # Prometheus metrics endpoint (Phase 3) - requires staff authentication
    path("prometheus/metrics/", prometheus_metrics_view, name="prometheus_metrics"),
    # OpenAPI Documentation (Phase 4)
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # Extension ingestion API (Phase 1 – Knox token auth + CORS for chrome-extension://)
    path("api/extension/", include("apps.review_results.api.extension_urls")),
    # Dual Screening APIs (Phase 4)
    path(
        "api/", include("apps.review_results.api.urls")
    ),  # Core, Conflict, Dashboard APIs
    path(
        "api/organisation/", include("apps.organisation.api.urls")
    ),  # Organisation APIs
    path("accounts/", include("apps.accounts.urls")),
    path("organisation/", include("apps.organisation.urls")),  # Organisation management
    path("", include("apps.review_manager.urls")),  # Dashboard at root
    path("api/review-manager/", include("apps.review_manager.api.urls")),
    path("search-strategy/", include("apps.search_strategy.urls")),
    path("execution/", include("apps.serp_execution.urls")),
    path(
        "results-manager/", include("apps.results_manager.urls")
    ),  # Re-enabled for testing
    path("review-results/", include("apps.review_results.urls")),
    path("reporting/", include("apps.reporting.urls")),
    path("core/", include("apps.core.urls")),  # Core monitoring and utilities
    path("feedback/", include("apps.feedback.urls")),  # User feedback system
    # Vue SPA catch-all for /screening/ routes (conflict resolution, work queue, dashboard)
    path("screening/", vue_spa, name="vue_spa_root"),
    path("screening/<path:path>", vue_spa, name="vue_spa"),
]

# Add Sentry debug endpoint (only in DEBUG mode for safety)
if settings.DEBUG:
    urlpatterns.append(path("sentry-debug/", trigger_error, name="sentry_debug"))
    # SSE browser compatibility test page (Phase 4 testing)
    urlpatterns.append(
        path(
            "test/sse-compatibility/",
            TemplateView.as_view(template_name="test/sse_compatibility.html"),
            name="sse_compatibility_test",
        )
    )

# Serve static and media files in development
if settings.DEBUG:
    # Django Debug Toolbar
    try:
        import debug_toolbar

        urlpatterns = [
            path("__debug__/", include(debug_toolbar.urls)),
        ] + urlpatterns
    except ImportError:
        pass

    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
