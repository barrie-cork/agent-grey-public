"""
URL configuration for feedback app.
"""

from django.urls import path

from . import views

app_name = "feedback"

urlpatterns = [
    # AJAX endpoints for feedback submission
    path("submit/", views.FeedbackSubmissionView.as_view(), name="submit"),
    path("quick/", views.QuickFeedbackView.as_view(), name="quick_submit"),
    path("transcribe/", views.TranscribeAudioView.as_view(), name="transcribe"),
    # Admin/staff views for managing feedback
    path("list/", views.FeedbackListView.as_view(), name="list"),
    path("detail/<uuid:pk>/", views.FeedbackDetailView.as_view(), name="detail"),
    path(
        "update-status/<uuid:feedback_id>/",
        views.update_feedback_status,
        name="update_status",
    ),
    # API endpoints for statistics and analytics
    path("api/stats/", views.FeedbackStatsView.as_view(), name="stats_api"),
    path("api/export/", views.FeedbackExportView.as_view(), name="feedback_export"),
]
