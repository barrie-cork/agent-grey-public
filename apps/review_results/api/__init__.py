"""
Dual Screening API Views.

Provides REST API endpoints for dual-reviewer systematic literature screening.
"""

# Re-export internal API functions for backwards compatibility
from apps.review_results.internal_api import (
    get_review_decisions_data as get_review_decisions_data,
    get_decision_counts as get_decision_counts,
    get_review_progress_stats as get_review_progress_stats,
)
