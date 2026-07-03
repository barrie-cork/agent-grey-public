"""Security configuration builders.

This module provides centralized Content Security Policy (CSP) configuration
to eliminate repetitive environment variable parsing.

Created: 2025-10-17
Purpose: Phase 2 of Post-Deployment Refactoring Plan
"""

from typing import Dict, List, Tuple

from apps.core.env_config import get_env, get_env_bool


class CSPConfigBuilder:
    """Build Content Security Policy configuration.

    Eliminates 21 repetitive CSP get_env() calls by providing data-driven
    configuration with environment variable overrides.
    """

    # Define CSP directives with defaults
    # Format: directive_name: (default_value, env_var_name)
    CSP_DIRECTIVES: Dict[str, Tuple[str, str]] = {
        "DEFAULT_SRC": ("'self'", "CSP_DEFAULT_SRC"),
        "SCRIPT_SRC": (
            "'self' 'unsafe-inline' https://cdn.jsdelivr.net",
            "CSP_SCRIPT_SRC",
        ),
        "STYLE_SRC": (
            "'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com",
            "CSP_STYLE_SRC",
        ),
        "IMG_SRC": ("'self' data: https:", "CSP_IMG_SRC"),
        "FONT_SRC": (
            "'self' https://cdn.jsdelivr.net https://fonts.gstatic.com",
            "CSP_FONT_SRC",
        ),
        "CONNECT_SRC": ("'self' https://cdn.jsdelivr.net", "CSP_CONNECT_SRC"),
        "MEDIA_SRC": ("'self'", "CSP_MEDIA_SRC"),
        "OBJECT_SRC": ("'none'", "CSP_OBJECT_SRC"),
        "FRAME_SRC": ("'none'", "CSP_FRAME_SRC"),
        "BASE_URI": ("'self'", "CSP_BASE_URI"),
        "FORM_ACTION": ("'self'", "CSP_FORM_ACTION"),
    }

    @classmethod
    def build(cls) -> Dict[str, List[str]]:
        """Build CSP configuration from environment variables.

        Loads each CSP directive from environment variables or uses defaults,
        then splits values on whitespace to create lists for django-csp.

        Returns:
            Dictionary with CSP_* settings for Django
        """
        csp_config = {}

        for directive_name, (default_value, env_var) in cls.CSP_DIRECTIVES.items():
            # Get value from environment or use default
            value = get_env(env_var, default=default_value)

            # Convert to list (split on whitespace)
            if value:
                csp_config[f"CSP_{directive_name}"] = value.split()
            else:
                csp_config[f"CSP_{directive_name}"] = []

        # Handle boolean and optional directives
        csp_config["CSP_REPORT_ONLY"] = get_env_bool("CSP_REPORT_ONLY", default=False)
        csp_config["CSP_REPORT_URI"] = get_env("CSP_REPORT_URI", default=None)

        # Exclude admin paths from CSP if needed (for development/debugging)
        exclude_prefixes = get_env("CSP_EXCLUDE_URL_PREFIXES", default="/admin")
        if exclude_prefixes:
            csp_config["CSP_EXCLUDE_URL_PREFIXES"] = tuple(exclude_prefixes.split())
        else:
            csp_config["CSP_EXCLUDE_URL_PREFIXES"] = ()

        return csp_config
