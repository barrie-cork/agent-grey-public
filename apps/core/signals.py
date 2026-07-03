"""
Core signals for maintaining data consistency of denormalized fields.
These signals ensure denormalized session_id fields stay in sync.
"""

from django.apps import apps
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver


def get_model_lazy(app_label, model_name):
    """
    Lazy model loading to avoid circular imports.
    Returns the model class when called.
    """

    def _get_model():
        return apps.get_model(app_label, model_name)

    return _get_model


def register_signals():
    """
    Register all signals. This is called from apps.py ready() method
    to ensure models are loaded before connecting signals.
    """
    # Get model classes
    SearchQuery = apps.get_model("search_strategy", "SearchQuery")
    SimpleReviewDecision = apps.get_model("review_results", "SimpleReviewDecision")
    ProcessedResult = apps.get_model("results_manager", "ProcessedResult")

    # RawSearchResult no longer has a session field after refactoring
    # Removed the update_rawsearchresult_session signal

    # SearchExecution no longer has a session field after refactoring
    # Removed the update_searchexecution_session signal

    @receiver(
        pre_save, sender=SearchQuery, dispatch_uid="core.update_searchquery_session"
    )
    def update_searchquery_session(sender, instance, **kwargs):
        """Ensure SearchQuery.session is always in sync with strategy.session."""
        if instance.strategy_id and not instance.session_id:
            # Auto-populate session from strategy relationship
            instance.session = instance.strategy.session

    @receiver(
        pre_save,
        sender=SimpleReviewDecision,
        dispatch_uid="core.update_reviewdecision_session",
    )
    def update_reviewdecision_session(sender, instance, **kwargs):
        """Ensure SimpleReviewDecision.session is always in sync with result.session."""
        if instance.result_id and not instance.session_id:
            # Auto-populate session from relationship chain
            instance.session = instance.result.session

    # Additional consistency checks for when parent relationships change
    @receiver(
        post_save, sender=SearchQuery, dispatch_uid="core.sync_searchquery_dependents"
    )
    def sync_searchquery_dependents(sender, instance, **kwargs):
        """When SearchQuery.session changes, update dependent models."""
        # Note: After refactoring, neither SearchExecution nor RawSearchResult
        # have denormalized session fields, so no updates needed

    @receiver(
        post_save,
        sender=ProcessedResult,
        dispatch_uid="core.sync_processedresult_dependents",
    )
    def sync_processedresult_dependents(sender, instance, **kwargs):
        """When ProcessedResult.session changes, update dependent SimpleReviewDecisions."""
        if instance.session_id:
            # Update related SimpleReviewDecision
            SimpleReviewDecision.objects.filter(result=instance).update(
                session=instance.session
            )
