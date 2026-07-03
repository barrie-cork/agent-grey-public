"""URL routes for the browser-extension ingestion API."""

from django.urls import path

from .extension_views import (
    ExtensionAddResultView,
    ExtensionSessionListView,
    ExtensionVisitIngestView,
)

urlpatterns = [
    path("sessions/", ExtensionSessionListView.as_view(), name="extension_sessions"),
    path("visits/", ExtensionVisitIngestView.as_view(), name="extension_visits"),
    path("add-result/", ExtensionAddResultView.as_view(), name="extension_add_result"),
]
