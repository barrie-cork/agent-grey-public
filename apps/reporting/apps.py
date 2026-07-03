from django.apps import AppConfig


class ReportingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reporting"

    def ready(self):
        try:
            from apps.reporting.constants import PRISMAConstants
            from apps.review_results.models import SimpleReviewDecision

            PRISMAConstants.STANDARD_EXCLUSION_REASONS = dict(
                SimpleReviewDecision.EXCLUSION_REASONS
            )
        except Exception:
            # Guard against AppRegistryNotReady if this app initialises before
            # review_results is fully registered (can occur during test collection
            # or non-standard startup sequences).
            pass
