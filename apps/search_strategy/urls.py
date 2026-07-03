from django.urls import path

from . import views

app_name = "search_strategy"

urlpatterns = [
    # Main search strategy form
    path(
        "session/<uuid:session_id>/",
        views.SearchStrategyView.as_view(),
        name="strategy_form",
    ),
    # AJAX API endpoints
    path(
        "api/session/<uuid:session_id>/update/",
        views.update_strategy_ajax,
        name="update_strategy_ajax",
    ),
    path(
        "session/<uuid:session_id>/check-query-lengths/",
        views.check_query_lengths_ajax,
        name="check_query_lengths_ajax",
    ),
    path(
        "api/session/<uuid:session_id>/status/",
        views.strategy_status_api,
        name="strategy_status_api",
    ),
]
