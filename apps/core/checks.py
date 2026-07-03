"""
Django system checks for production configuration validation.

These checks run during startup (manage.py check) and help catch
configuration errors before they cause runtime failures.

Created: 2024-10-16
Enhanced: 2025-10-17 (Phase 3 of Post-Deployment Refactoring Plan)
"""

import os

from django.conf import settings
from django.core.checks import Critical, Error, Warning, register


@register()
def check_allowed_cidr_nets_dependency(app_configs, **kwargs):
    """
    Verify netaddr library is installed when ALLOWED_CIDR_NETS is configured.

    Django's ALLOWED_CIDR_NETS setting requires the netaddr library to function.
    Without it, Django silently ignores ALLOWED_CIDR_NETS and falls back to
    exact hostname matching, which will cause DigitalOcean health checks to fail.

    This check prevents the silent failure mode by explicitly validating the
    dependency is available.
    """
    errors = []

    # Only check if ALLOWED_CIDR_NETS is configured
    if hasattr(settings, "ALLOWED_CIDR_NETS") and settings.ALLOWED_CIDR_NETS:
        try:
            from netaddr import IPAddress, IPNetwork  # noqa: F401

            # Verify we can actually use it
            try:
                test_network = IPNetwork("10.244.0.0/16")
                test_ip = IPAddress("10.244.32.3")

                # Validate basic CIDR matching works
                if test_ip not in test_network:
                    errors.append(
                        Error(
                            "netaddr library CIDR validation not working correctly",
                            hint="Test IP 10.244.32.3 should be in 10.244.0.0/16 network",
                            id="core.E002",
                        )
                    )
            except Exception as e:
                errors.append(
                    Error(
                        f"netaddr library validation failed: {e}",
                        hint="Check netaddr installation: pip install netaddr==0.10.1",
                        id="core.E003",
                    )
                )

        except ImportError:
            errors.append(
                Error(
                    "netaddr library required for ALLOWED_CIDR_NETS but not installed",
                    hint=(
                        "Install netaddr: pip install netaddr==0.10.1\n"
                        "Add to requirements/base.txt: netaddr==0.10.1\n"
                        "Without netaddr, Django will SILENTLY IGNORE ALLOWED_CIDR_NETS "
                        "and health checks from DigitalOcean pod IPs (10.244.0.0/16) will fail!"
                    ),
                    id="core.E001",
                )
            )

    return errors


@register()
def check_allowed_hosts_patterns(app_configs, **kwargs):
    """
    Validate ALLOWED_HOSTS doesn't contain invalid patterns.

    Django's ALLOWED_HOSTS only supports:
    - Exact hostname matches: "example.com"
    - Subdomain wildcards: ".example.com" (matches *.example.com)
    - Allow all (insecure): "*"

    It does NOT support:
    - Shell-style globs: "10.244.*"
    - IP wildcards: "10.*.*.1"
    - Regex patterns

    For IP ranges, use ALLOWED_CIDR_NETS instead (Django 4.1+).
    """
    warnings = []

    if hasattr(settings, "ALLOWED_HOSTS"):
        for host in settings.ALLOWED_HOSTS:
            # Check for invalid wildcard patterns
            if "*" in host and host != "*" and not host.startswith("."):
                warnings.append(
                    Warning(
                        f"Invalid ALLOWED_HOSTS pattern detected: '{host}'",
                        hint=(
                            f"Django does not support shell-style glob patterns like '{host}'. "
                            "For IP ranges, use ALLOWED_CIDR_NETS instead. "
                            "Example: ALLOWED_CIDR_NETS = ['10.244.0.0/16']"
                        ),
                        id="core.W001",
                    )
                )

            # Check for patterns that look like IP ranges
            if host.count(".") == 3 and "*" in host:
                warnings.append(
                    Warning(
                        f"IP wildcard pattern detected in ALLOWED_HOSTS: '{host}'",
                        hint=(
                            "Use ALLOWED_CIDR_NETS for IP range validation. "
                            f"Replace '{host}' with proper CIDR notation in ALLOWED_CIDR_NETS. "
                            "Example: ALLOWED_CIDR_NETS = ['10.244.0.0/16']"
                        ),
                        id="core.W002",
                    )
                )

    return warnings


@register()
def check_digitalocean_health_check_config(app_configs, **kwargs):
    """
    Validate DigitalOcean-specific health check configuration.

    DigitalOcean App Platform health checks originate from Kubernetes pod IPs
    in the 10.244.0.0/16 CIDR range. These requests must be allowed or
    deployments will fail with 400 errors.
    """
    warnings = []

    # Only check in production environment
    environment = getattr(settings, "ENVIRONMENT", "")
    deployment_type = getattr(settings, "DEPLOYMENT_TYPE", "")

    if environment == "production" or deployment_type == "digitalocean":
        has_cidr_nets = (
            hasattr(settings, "ALLOWED_CIDR_NETS") and settings.ALLOWED_CIDR_NETS
        )

        if not has_cidr_nets:
            warnings.append(
                Warning(
                    "ALLOWED_CIDR_NETS not configured for DigitalOcean deployment",
                    hint=(
                        "Add to production settings:\n"
                        "ALLOWED_CIDR_NETS = ['10.244.0.0/16']  # DigitalOcean pod network\n"
                        "Without this, health checks from Kubernetes probes will fail!"
                    ),
                    id="core.W003",
                )
            )
        else:
            # Check if the DigitalOcean pod network is included
            digitalocean_cidr = "10.244.0.0/16"
            if digitalocean_cidr not in settings.ALLOWED_CIDR_NETS:
                warnings.append(
                    Warning(
                        "DigitalOcean pod network not in ALLOWED_CIDR_NETS",
                        hint=(
                            f"Add '{digitalocean_cidr}' to ALLOWED_CIDR_NETS:\n"
                            f"ALLOWED_CIDR_NETS = {settings.ALLOWED_CIDR_NETS + [digitalocean_cidr]}"
                        ),
                        id="core.W004",
                    )
                )

    return warnings


@register()
def check_required_environment_variables(app_configs, **kwargs):
    """
    Check that required environment variables are set in production.

    Critical environment variables must be set for the application to
    function correctly. This check prevents startup with missing config.
    """
    errors = []

    # Only check in production/staging environments
    environment = getattr(settings, "ENVIRONMENT", "")
    if environment not in ["production", "staging"]:
        return errors

    # Required variables for production
    required_vars = {
        "SECRET_KEY": "Django cryptographic signing key",
        "DATABASE_URL": "PostgreSQL database connection string",
    }

    for var_name, description in required_vars.items():
        value = os.environ.get(var_name, "")
        if not value or not value.strip():
            errors.append(
                Critical(
                    f"Required environment variable '{var_name}' not set",
                    hint=(
                        f"{description} is required for {environment} deployment.\n"
                        f"Set {var_name} in DigitalOcean: Apps → Settings → Environment Variables"
                    ),
                    id=f"core.C00{len(errors) + 1}",
                )
            )

    return errors


@register()
def check_database_url_format(app_configs, **kwargs):
    """
    Validate DATABASE_URL format in production.

    Ensures DATABASE_URL has correct scheme and SSL mode for security.
    """
    warnings = []

    environment = getattr(settings, "ENVIRONMENT", "")
    if environment not in ["production", "staging"]:
        return warnings

    database_url = os.environ.get("DATABASE_URL", "")

    if database_url:
        # Check for localhost in production
        if environment == "production" and any(
            host in database_url.lower() for host in ["localhost", "127.0.0.1", "::1"]
        ):
            errors = [
                Critical(
                    "DATABASE_URL points to localhost in production",
                    hint=(
                        "Use DigitalOcean Managed PostgreSQL connection string.\n"
                        "Localhost is not accessible from DigitalOcean App Platform."
                    ),
                    id="core.C003",
                )
            ]
            return errors

        # Check for SSL mode
        if environment == "production" and "sslmode=require" not in database_url:
            warnings.append(
                Warning(
                    "DATABASE_URL missing SSL mode parameter",
                    hint=(
                        "Add '?sslmode=require' to connection string for secure connections.\n"
                        "Example: postgresql://user:pass@host:port/db?sslmode=require"
                    ),
                    id="core.W005",
                )
            )

    return warnings


@register()
def check_redis_url_localhost(app_configs, **kwargs):
    """
    Check for localhost Redis URLs in production.

    Localhost Redis is not accessible from DigitalOcean App Platform
    and will cause deployment failures.
    """
    errors = []

    environment = getattr(settings, "ENVIRONMENT", "")
    if environment != "production":
        return errors

    redis_url = os.environ.get("REDIS_URL", "")

    if redis_url and any(
        host in redis_url.lower() for host in ["localhost", "127.0.0.1", "::1"]
    ):
        errors.append(
            Critical(
                "REDIS_URL points to localhost in production",
                hint=(
                    "Use DigitalOcean Managed Redis connection string.\n"
                    "Localhost is not accessible from DigitalOcean App Platform.\n"
                    "This will cause deployment failures!"
                ),
                id="core.C004",
            )
        )

    return errors


@register()
def check_secret_key_security(app_configs, **kwargs):
    """
    Validate SECRET_KEY meets security requirements.

    Checks for common insecure patterns and minimum length.
    """
    warnings = []

    environment = getattr(settings, "ENVIRONMENT", "")
    if environment not in ["production", "staging"]:
        return warnings

    secret_key = getattr(settings, "SECRET_KEY", "")

    # Check for insecure patterns
    insecure_patterns = [
        "django-insecure-",
        "secret",
        "password",
        "changeme",
        "test",
        "development",
        "example",
    ]

    if any(pattern in secret_key.lower() for pattern in insecure_patterns):
        warnings.append(
            Critical(
                "SECRET_KEY contains insecure pattern",
                hint=(
                    "Generate a secure SECRET_KEY:\n"
                    "python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'\n"
                    "Never use default or easily guessable keys in production!"
                ),
                id="core.C005",
            )
        )

    # Check minimum length
    if len(secret_key) < 50:
        warnings.append(
            Warning(
                f"SECRET_KEY too short ({len(secret_key)} chars, recommended 50+)",
                hint="Generate a longer key for better cryptographic security",
                id="core.W006",
            )
        )

    return warnings


@register()
def check_sentry_dsn_format(app_configs, **kwargs):
    """
    Validate SENTRY_DSN format if configured.

    Ensures Sentry DSN is properly formatted for error monitoring.
    """
    warnings = []

    sentry_dsn = os.environ.get("SENTRY_DSN", "")

    if sentry_dsn and sentry_dsn.strip():
        # Check for placeholder values
        if sentry_dsn in ['""', "''", "None", "null"]:
            return warnings  # Silent skip for placeholders

        # Validate DSN format
        if not sentry_dsn.startswith(("http://", "https://")):
            warnings.append(
                Warning(
                    "SENTRY_DSN has invalid format",
                    hint=(
                        "SENTRY_DSN must start with http:// or https://\n"
                        "Get DSN from Sentry.io project settings:\n"
                        "Settings → Projects → [Your Project] → Client Keys (DSN)"
                    ),
                    id="core.W007",
                )
            )

    return warnings


@register()
def check_allowed_hosts_production(app_configs, **kwargs):
    """
    Ensure ALLOWED_HOSTS is configured in production.

    ALLOWED_HOSTS is critical for security in production.
    """
    errors = []

    environment = getattr(settings, "ENVIRONMENT", "")
    if environment != "production":
        return errors

    allowed_hosts = getattr(settings, "ALLOWED_HOSTS", [])

    if not allowed_hosts:
        errors.append(
            Critical(
                "ALLOWED_HOSTS not configured in production",
                hint=(
                    "Set ALLOWED_HOSTS in environment variables:\n"
                    "ALLOWED_HOSTS=grey-lit-app-ifa37.ondigitalocean.app,localhost\n"
                    "Required for Django to accept requests!"
                ),
                id="core.C006",
            )
        )
    elif "*" in allowed_hosts:
        errors.append(
            Critical(
                "ALLOWED_HOSTS contains wildcard '*' in production",
                hint=(
                    "Wildcard allows any host - serious security risk!\n"
                    "Specify exact hostnames instead:\n"
                    "ALLOWED_HOSTS=grey-lit-app-ifa37.ondigitalocean.app"
                ),
                id="core.C007",
            )
        )

    return errors


@register()
def check_cache_configuration(app_configs, **kwargs):
    """
    Validate cache backend configuration.

    Provides informational messages about cache backend being used.
    """
    info = []

    try:
        cache_config = getattr(settings, "CACHES", {})
        default_cache = cache_config.get("default", {})
        backend = default_cache.get("BACKEND", "unknown")

        # Informational message about cache backend
        if "redis" in backend.lower():
            # Redis cache is optimal
            pass
        elif "database" in backend.lower():
            # Database cache is fallback
            info.append(
                Warning(
                    "Using database cache (Redis fallback)",
                    hint=(
                        "For better performance, configure REDIS_URL:\n"
                        "REDIS_URL=rediss://default:password@host:port/0\n"
                        "Database cache works but Redis provides better performance."
                    ),
                    id="core.W008",
                )
            )

    except Exception:
        # Don't fail on cache config inspection errors
        pass

    return info


@register()
def check_ssl_redirect_production(app_configs, **kwargs):
    """
    Warn when SECURE_SSL_REDIRECT is False in production without explicit bypass.

    DigitalOcean App Platform handles SSL termination at the load balancer,
    so Django's SECURE_SSL_REDIRECT should be False. But we want to ensure
    this is intentional via the SSL_REDIRECT_HANDLED_EXTERNALLY flag.
    """
    warnings = []

    environment = getattr(settings, "ENVIRONMENT", "")
    if environment != "production":
        return warnings

    ssl_redirect = getattr(settings, "SECURE_SSL_REDIRECT", True)
    if not ssl_redirect:
        handled_externally = (
            os.environ.get("SSL_REDIRECT_HANDLED_EXTERNALLY", "").lower() == "true"
        )
        if not handled_externally:
            warnings.append(
                Warning(
                    "SECURE_SSL_REDIRECT is False in production"
                    " without explicit bypass",
                    hint=(
                        "If SSL termination is handled by a reverse proxy"
                        " (e.g. DigitalOcean App Platform), set"
                        " SSL_REDIRECT_HANDLED_EXTERNALLY=true in"
                        " environment variables to suppress this warning.\n"
                        "Otherwise, set SECURE_SSL_REDIRECT=True to enforce"
                        " HTTPS at the Django level."
                    ),
                    id="core.W009",
                )
            )

    return warnings


@register()
def check_serper_api_key_configuration(app_configs, **kwargs):
    """
    Validate SERPER_API_KEY is properly configured for production.

    Prevents the MockSerperClient from being used in production by
    catching missing or placeholder API keys at deploy time.
    """
    errors = []

    environment = getattr(settings, "ENVIRONMENT", "")
    if environment not in ["production", "staging"]:
        return errors

    api_key = getattr(settings, "SERPER_API_KEY", "")

    if not api_key:
        errors.append(
            Error(
                "SERPER_API_KEY is not configured for production",
                hint=(
                    "Set SERPER_API_KEY in DigitalOcean App Platform environment variables. "
                    "Without this, search execution will use MockSerperClient and return "
                    "fake results (see issue #115)."
                ),
                id="core.E010",
            )
        )
    elif any(
        marker in api_key.lower()
        for marker in ["development", "test", "placeholder", "replace"]
    ):
        errors.append(
            Error(
                "SERPER_API_KEY appears to be a placeholder value",
                hint=(
                    "Replace SERPER_API_KEY with a real API key from serper.dev. "
                    "Current value contains a marker suggesting it is not a real key."
                ),
                id="core.E011",
            )
        )

    return errors


@register()
def check_cors_credentials_without_origins(app_configs, **kwargs):
    """
    Validate CORS configuration when credentials are allowed.

    CORS_ALLOW_CREDENTIALS=True with no CORS_ALLOWED_ORIGINS means
    cross-origin requests with credentials will be denied by browsers.
    This is likely a misconfiguration.
    """
    errors = []

    environment = getattr(settings, "ENVIRONMENT", "")
    if environment not in ["production", "staging"]:
        return errors

    allow_credentials = getattr(settings, "CORS_ALLOW_CREDENTIALS", False)
    allowed_origins = getattr(settings, "CORS_ALLOWED_ORIGINS", [])
    allow_all = getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False)

    if allow_credentials and not allowed_origins and not allow_all:
        errors.append(
            Critical(
                "CORS_ALLOW_CREDENTIALS is True but no origins are configured",
                hint=(
                    "Set CORS_ALLOWED_ORIGINS to a list of trusted origins,"
                    " e.g.:\n"
                    "CORS_ALLOWED_ORIGINS=['https://agentgrey.app']\n"
                    "Or set CORS_ALLOW_ALL_ORIGINS=True"
                    " (not recommended for production).\n"
                    "Without allowed origins, cross-origin credentialed"
                    " requests will be rejected."
                ),
                id="core.C008",
            )
        )

    return errors
