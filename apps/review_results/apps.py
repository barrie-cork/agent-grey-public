from django.apps import AppConfig


class ReviewResultsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.review_results"

    def ready(self):
        """Import signal handlers when app is ready."""
        import apps.review_results.signals  # noqa: F401
