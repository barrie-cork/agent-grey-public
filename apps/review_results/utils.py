"""
Simple utility functions for the review_results app.
"""

from .services.simple_export_service import SimpleExportService
from .services.simple_review_progress_service import SimpleReviewProgressService

# Initialize services (uses dependency injection with default providers)
progress_service = SimpleReviewProgressService()
export_service = SimpleExportService()


# Simple utility functions
def calculate_review_progress(session_id: str):
    """Calculate basic review progress for a session."""
    return progress_service.get_progress_summary(session_id)


def export_review_decisions(session_id: str, format_type: str = "csv"):
    """Export review decisions for a session."""
    return export_service.export_review_decisions(session_id, format_type)
