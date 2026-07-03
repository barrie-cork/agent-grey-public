"""
WSGI config for grey_lit_project project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# Django standard WSGI configuration - no Environment Manager needed
# Environment selection via DJANGO_SETTINGS_MODULE environment variable
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "grey_lit_project.settings.local")

# Basic environment validation without complex override logic
settings_module = os.environ.get("DJANGO_SETTINGS_MODULE", "")
environment = os.environ.get("ENVIRONMENT", "")

# Determine environment from settings if not explicitly set
if not environment:
    if "production" in settings_module:
        os.environ.setdefault("ENVIRONMENT", "production")
    elif "staging" in settings_module:
        os.environ.setdefault("ENVIRONMENT", "staging")
    else:
        os.environ.setdefault("ENVIRONMENT", "development")

print(f"[WSGI] Settings: {settings_module}")
print(f"[WSGI] Environment: {os.environ.get('ENVIRONMENT', 'unknown')}")

# Production safety check without Environment Manager
if "production" in settings_module and os.environ.get("DEBUG", "").lower() == "true":
    print("[WSGI] WARNING: DEBUG=True in production settings module")

application = get_wsgi_application()
