"""
SERP provider registry and factory functions.

Provides pluggable provider support with a registry pattern.
"""

import logging

from .base import SerpProvider
from .searchapi_provider import SearchAPIProvider
from .serper_provider import SerperProvider

logger = logging.getLogger(__name__)

# Provider class registry: maps provider_key to provider class
_provider_classes: dict[str, type] = {
    "serper": SerperProvider,
    "searchapi_bing": SearchAPIProvider,
}


def register_provider(provider_key: str, provider_class: type) -> None:
    """Register a new provider class.

    Args:
        provider_key: Unique key for the provider (e.g. 'serpapi').
        provider_class: Class implementing the SerpProvider protocol.
    """
    _provider_classes[provider_key] = provider_class
    logger.info(f"Registered SERP provider: {provider_key}")


def get_provider(provider_key: str = "serper") -> SerpProvider:
    """Get an instantiated provider by key.

    Args:
        provider_key: Provider key to look up. Defaults to 'serper'.

    Returns:
        Instantiated SerpProvider.

    Raises:
        ValueError: If provider_key is not registered.
    """
    provider_class = _provider_classes.get(provider_key)
    if provider_class is None:
        available = ", ".join(_provider_classes.keys())
        raise ValueError(
            f"Unknown SERP provider '{provider_key}'. Available: {available}"
        )
    return provider_class()


def get_default_provider() -> SerpProvider:
    """Get the system default provider.

    Checks SerpProviderConfig for a default, falls back to 'serper'.

    Returns:
        Instantiated SerpProvider.
    """
    try:
        from .config import SerpProviderConfig

        default_config = SerpProviderConfig.objects.filter(
            is_default=True, is_enabled=True
        ).first()
        if default_config:
            return get_provider(default_config.provider_key)
    except Exception:
        # During migrations or if table doesn't exist yet
        pass

    return get_provider("serper")


def get_provider_display_name(provider_key: str) -> str:
    """Get the display name for a provider.

    Checks SerpProviderConfig first, falls back to provider class attribute.

    Args:
        provider_key: Provider key to look up.

    Returns:
        Human-readable display name.
    """
    try:
        from .config import SerpProviderConfig

        config = SerpProviderConfig.objects.filter(provider_key=provider_key).first()
        if config:
            return config.display_name
    except Exception:
        pass

    provider_class = _provider_classes.get(provider_key)
    if provider_class and hasattr(provider_class, "display_name"):
        return provider_class.display_name
    return provider_key


def list_providers() -> list[str]:
    """List all registered provider keys."""
    return list(_provider_classes.keys())


def get_provider_for_config(config=None) -> SerpProvider:
    """Get provider from a SerpProviderConfig instance.

    Args:
        config: SerpProviderConfig instance, or None for default.

    Returns:
        Instantiated SerpProvider.
    """
    if config is None:
        return get_default_provider()
    return get_provider(config.provider_key)


def get_enabled_provider_choices() -> list[tuple[str, str]]:
    """Return (provider_key, display_name) tuples for all enabled providers."""
    try:
        from .config import SerpProviderConfig

        return list(
            SerpProviderConfig.objects.filter(is_enabled=True)
            .order_by("display_name")
            .values_list("provider_key", "display_name")
        )
    except Exception:
        return []


def get_default_provider_key() -> str:
    """Return the provider_key of the system default provider."""
    try:
        from .config import SerpProviderConfig

        default = SerpProviderConfig.objects.filter(
            is_default=True, is_enabled=True
        ).first()
        if default:
            return default.provider_key
    except Exception:
        pass
    return "serper"


__all__ = [
    "SearchAPIProvider",
    "SerpProvider",
    "SerperProvider",
    "get_default_provider",
    "get_default_provider_key",
    "get_enabled_provider_choices",
    "get_provider",
    "get_provider_display_name",
    "get_provider_for_config",
    "list_providers",
    "register_provider",
]
