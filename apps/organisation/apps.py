"""Django app configuration for organisation."""

from django.apps import AppConfig


class OrganisationConfig(AppConfig):
    """Configuration for the organisation app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.organisation"
    verbose_name = "Organisation Management"

    def ready(self):
        """
        Perform app initialisation.

        Called when Django starts up.
        """
        # Import signals here if needed in future
        pass
