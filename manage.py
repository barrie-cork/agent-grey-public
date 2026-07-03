#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    # Django standard settings pattern - no Environment Manager needed
    # Use DJANGO_SETTINGS_MODULE environment variable to determine settings
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "grey_lit_project.settings.local")

    # Set default environment if not specified
    if not os.environ.get("ENVIRONMENT"):
        # Determine environment from settings module
        settings_module = os.environ.get("DJANGO_SETTINGS_MODULE", "")
        if "production" in settings_module:
            os.environ.setdefault("ENVIRONMENT", "production")
        elif "staging" in settings_module:
            os.environ.setdefault("ENVIRONMENT", "staging")
        elif "test" in settings_module:
            os.environ.setdefault("ENVIRONMENT", "test")
        else:
            os.environ.setdefault("ENVIRONMENT", "development")

    environment = os.environ.get("ENVIRONMENT", "development")
    settings_module = os.environ.get("DJANGO_SETTINGS_MODULE")

    print(f"[manage.py] Environment: {environment}")
    print(f"[manage.py] Settings: {settings_module}")

    # Basic validation - no Environment Manager override issues
    if environment == "production" and os.environ.get("DEBUG", "").lower() == "true":
        print("[manage.py] WARNING: DEBUG=True detected in production environment")

    # Validate database URL consistency (without complex Environment Manager logic)
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url and "postgres://test:test@localhost:5432/test" in db_url:
        if environment not in ["test", "ci"]:
            print(f"[manage.py] ERROR: Test database URL in {environment} environment!")
            print("[manage.py] This could lead to data loss - check your configuration")
            sys.exit(1)

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
