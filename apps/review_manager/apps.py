from django.apps import AppConfig


class ReviewManagerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.review_manager"

    def ready(self):
        """Initialize app when Django starts."""
        # Import and register signals for denormalized fields
        from .signals_denormalized import register_denormalized_signals

        register_denormalized_signals()

        # Import signals module to register signal handlers (including invitation sending)
        from . import signals  # noqa: F401
