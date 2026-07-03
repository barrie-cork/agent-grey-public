"""
SerpProviderConfig model for storing SERP provider configurations.
"""

import uuid

from django.db import models

from apps.core.models import TimeStampedModel


class SerpProviderConfig(TimeStampedModel):
    """Configuration for a SERP API provider.

    Stores provider metadata, API configuration, rate limits,
    and capability information. Supports a single system-wide
    default provider via a partial unique constraint.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Provider identification
    provider_key = models.CharField(
        max_length=50,
        unique=True,
        help_text="Internal key (e.g. 'serper', 'serpapi', 'scaleserp')",
    )
    display_name = models.CharField(
        max_length=100,
        help_text="Human-readable name (e.g. 'Serper.dev')",
    )

    # API configuration
    base_url = models.URLField(
        help_text="Base API URL for this provider",
    )
    api_key_setting = models.CharField(
        max_length=100,
        blank=True,
        help_text="Django settings key for API key (e.g. 'SERPER_API_KEY')",
    )

    # Future: organisation-level default provider
    default_for_organisation = models.ForeignKey(
        "organisation.Organisation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="serp_provider_configs",
        help_text="If set, this config is the org-level default",
    )

    # Rate limiting (per-provider)
    rate_limit_per_minute = models.IntegerField(
        default=100,
        help_text="Max requests per minute for this provider",
    )
    rate_limit_burst = models.IntegerField(
        default=10,
        help_text="Burst allowance for rate limiting",
    )

    # Provider status
    is_enabled = models.BooleanField(default=True)
    is_default = models.BooleanField(
        default=False,
        help_text="Whether this is the system-wide default provider",
    )

    # Capabilities
    max_results_per_query = models.IntegerField(
        default=100,
        help_text="Maximum results this provider can return per query",
    )
    supports_pagination = models.BooleanField(default=True)
    supported_search_engines = models.JSONField(
        default=list,
        help_text="List of search engines supported (e.g. ['google', 'bing'])",
    )

    class Meta:
        db_table = "serp_provider_configs"
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"],
                condition=models.Q(is_default=True),
                name="unique_default_provider",
            )
        ]

    def __str__(self) -> str:
        default_label = " (default)" if self.is_default else ""
        return f"{self.display_name}{default_label}"
