"""Cache backends for the core application."""

from .safe_cache import SafeDatabaseCache, get_safe_cache

__all__ = ["SafeDatabaseCache", "get_safe_cache"]
