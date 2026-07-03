"""
URL configuration for results_manager app.

NOTE: This app primarily works in the background via Celery tasks.
Web UI URLs have been archived to apps/results_manager/archive/urls_archived.py

Results are accessed through the review_results app after automatic processing.
We now provide a processing status view for better user feedback during processing.
"""

from django.urls import path

from .views import ProcessingStatusAPIView, ProcessingStatusView

app_name = "results_manager"

urlpatterns = [
    # Processing status views for user feedback during processing
    path(
        "processing/<uuid:session_id>/",
        ProcessingStatusView.as_view(),
        name="processing_status",
    ),
    path(
        "api/processing/<uuid:session_id>/",
        ProcessingStatusAPIView.as_view(),
        name="processing_status_api",
    ),
    # Main processing is triggered automatically by SERP execution completion
    # Results are viewed through the review_results app after processing
]

# Test APIs have been archived to docs/examples/archived-code/test_apis.py
# These endpoints were only used for testing and are no longer needed
