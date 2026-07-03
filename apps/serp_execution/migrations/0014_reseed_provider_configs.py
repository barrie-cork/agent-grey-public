# Re-seed SERP provider configs (data lost after DB flush/reset).
# Original seeds: 0012_seed_serper_provider_config, 0013_seed_searchapi_bing_provider.

from django.db import migrations


def seed_providers(apps, schema_editor):
    SerpProviderConfig = apps.get_model("serp_execution", "SerpProviderConfig")

    SerpProviderConfig.objects.get_or_create(
        provider_key="serper",
        defaults={
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
    )

    SerpProviderConfig.objects.get_or_create(
        provider_key="searchapi_bing",
        defaults={
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
    )


def reverse_seed(apps, schema_editor):
    SerpProviderConfig = apps.get_model("serp_execution", "SerpProviderConfig")
    SerpProviderConfig.objects.filter(
        provider_key__in=["serper", "searchapi_bing"]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("serp_execution", "0013_seed_searchapi_bing_provider"),
    ]

    operations = [
        migrations.RunPython(seed_providers, reverse_seed),
    ]
