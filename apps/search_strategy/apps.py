from django.apps import AppConfig


class SearchStrategyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.search_strategy"

    def ready(self):
        """Import signal handlers when app is ready."""
