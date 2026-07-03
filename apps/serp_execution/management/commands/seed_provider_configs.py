"""Seed SerpProviderConfig records for all supported SERP providers."""

from django.core.management.base import BaseCommand

from apps.serp_execution.providers.config import SerpProviderConfig

PROVIDERS = [
    {
        "provider_key": "serper",
        "defaults": {
            "display_name": "Serper.dev",
            "base_url": "https://google.serper.dev/search",
            "api_key_setting": "SERPER_API_KEY",
            "rate_limit_per_minute": 100,
            "rate_limit_burst": 10,
            "is_enabled": True,
            "is_default": True,
            "max_results_per_query": 100,
            "supports_pagination": True,
            "supported_search_engines": ["google"],
        },
    },
    {
        "provider_key": "searchapi_bing",
        "defaults": {
            "display_name": "SearchAPI.io (Bing)",
            "base_url": "https://www.searchapi.io/api/v1/search",
            "api_key_setting": "SEARCHAPI_API_KEY",
            "rate_limit_per_minute": 30,
            "rate_limit_burst": 5,
            "is_enabled": True,
            "is_default": False,
            "max_results_per_query": 50,
            "supports_pagination": True,
            "supported_search_engines": ["bing"],
        },
    },
]


class Command(BaseCommand):
    help = "Seed SerpProviderConfig with supported SERP providers."

    def handle(self, *args, **options):
        for provider in PROVIDERS:
            _, created = SerpProviderConfig.objects.get_or_create(
                provider_key=provider["provider_key"],
                defaults=provider["defaults"],
            )
            status = "created" if created else "already exists"
            self.stdout.write(f"  {provider['defaults']['display_name']}: {status}")

        total = SerpProviderConfig.objects.filter(is_enabled=True).count()
        self.stdout.write(
            self.style.SUCCESS(f"Done. {total} enabled provider(s) available.")
        )
