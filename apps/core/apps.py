"""
Core app configuration.
"""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Configuration for the core app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Core"

    def ready(self):
        """App initialization."""
        # Register signal handlers when app is ready
        from apps.core.signals import register_signals

        register_signals()

        # Import system checks to register them with Django
        # This ensures our custom checks run during `manage.py check`
        from apps.core import checks  # noqa: F401
