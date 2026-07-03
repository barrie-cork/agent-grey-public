"""Host and CSRF configuration management.

This module provides centralized ALLOWED_HOSTS validation and configuration
to prevent common deployment issues with Django's host validation.

Created: 2025-10-17
Purpose: Phase 2 of Post-Deployment Refactoring Plan
"""

import logging
import os
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class HostConfiguration:
    """Manage ALLOWED_HOSTS and CSRF configuration.

    Consolidates ALLOWED_HOSTS logic from 4 different locations in production.py
    with proper pattern validation and environment variable parsing.
    """

    # Default production hosts
    DEFAULT_ALLOWED_HOSTS = [
        "grey-lit-app-ifa37.ondigitalocean.app",
        "localhost",
        "127.0.0.1",
        ".ondigitalocean.app",
    ]

    # Default CIDR networks for DigitalOcean Kubernetes pods
    DEFAULT_CIDR_NETS = [
        "10.244.0.0/16",  # DigitalOcean App Platform pod network
    ]

    # Default CSRF trusted origins
    DEFAULT_CSRF_ORIGINS = [
        "https://grey-lit-app-ifa37.ondigitalocean.app",
        "https://*.ondigitalocean.app",
    ]

    @classmethod
    def get_production_config(cls) -> Dict[str, Any]:
        """Get production-safe ALLOWED_HOSTS and CSRF configuration.

        Parses environment variables with validation and provides sensible
        defaults for DigitalOcean App Platform deployment.

        Returns:
            Dictionary with ALLOWED_HOSTS, ALLOWED_CIDR_NETS, CSRF_TRUSTED_ORIGINS
        """
        # Parse ALLOWED_HOSTS from environment
        allowed_hosts_env = os.environ.get("ALLOWED_HOSTS", "")
        if allowed_hosts_env:
            allowed_hosts = [
                h.strip() for h in allowed_hosts_env.split(",") if h.strip()
            ]
        else:
            allowed_hosts = cls.DEFAULT_ALLOWED_HOSTS.copy()

        # Validate ALLOWED_HOSTS patterns
        allowed_hosts = cls._validate_allowed_hosts(allowed_hosts)

        # Parse ALLOWED_CIDR_NETS from environment
        cidr_nets_env = os.environ.get("ALLOWED_CIDR_NETS", "")
        if cidr_nets_env:
            cidr_nets = [net.strip() for net in cidr_nets_env.split(",") if net.strip()]
        else:
            cidr_nets = cls.DEFAULT_CIDR_NETS.copy()

        # Parse CSRF_TRUSTED_ORIGINS from environment
        csrf_origins_env = os.environ.get("CSRF_TRUSTED_ORIGINS", "")
        if csrf_origins_env:
            csrf_origins = [o.strip() for o in csrf_origins_env.split(",") if o.strip()]
        else:
            csrf_origins = cls.DEFAULT_CSRF_ORIGINS.copy()

        logger.info(f"ALLOWED_HOSTS: {len(allowed_hosts)} patterns")
        logger.info(f"ALLOWED_CIDR_NETS: {len(cidr_nets)} networks")
        logger.info(f"CSRF_TRUSTED_ORIGINS: {len(csrf_origins)} origins")

        return {
            "ALLOWED_HOSTS": allowed_hosts,
            "ALLOWED_CIDR_NETS": cidr_nets,
            "CSRF_TRUSTED_ORIGINS": csrf_origins,
        }

    @staticmethod
    def _validate_allowed_hosts(hosts: List[str]) -> List[str]:
        """Validate and clean ALLOWED_HOSTS patterns.

        Django ALLOWED_HOSTS supports:
        - Exact hostname matches: "example.com"
        - Subdomain wildcards: ".example.com" (matches *.example.com)
        - "*" (allow all - not recommended for production)

        Django DOES NOT support:
        - Shell-style globs: "10.244.*"
        - IP wildcards: "192.168.*.*"
        - Regex patterns
        - Callable validators

        Args:
            hosts: List of host patterns

        Returns:
            Cleaned list of valid patterns
        """
        valid_hosts = []
        invalid_patterns = []

        for host in hosts:
            # Check for invalid shell-style glob patterns
            if "*" in host and not host == "*" and not host.startswith("."):
                # Invalid pattern like "10.244.*" or "*.example.*"
                invalid_patterns.append(host)
                logger.warning(
                    f"Invalid ALLOWED_HOSTS pattern: '{host}' "
                    f"(use ALLOWED_CIDR_NETS for IP ranges)"
                )
            else:
                valid_hosts.append(host)

        if invalid_patterns:
            logger.error(
                f"Removed {len(invalid_patterns)} invalid ALLOWED_HOSTS patterns: "
                f"{invalid_patterns}"
            )

        return valid_hosts
