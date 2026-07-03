"""
Django management command to load test user fixtures from environment variables.

This command creates test users based on environment variables, replacing the need
for hardcoded JSON fixtures with passwords.

Usage:
    python manage.py load_test_fixtures [--dry-run] [--category CATEGORY] [--force]
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

User = get_user_model()


class Command(BaseCommand):
    help = "Load test user fixtures from environment variables"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without actually creating users",
        )
        parser.add_argument(
            "--category",
            type=str,
            help="Load only users from specific category (e.g., adminTestUsers, securityTestUsers)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Update existing users with new data from environment variables",
        )
        parser.add_argument(
            "--list-categories",
            action="store_true",
            help="List available user categories",
        )
        parser.add_argument(
            "--generate-fixtures",
            action="store_true",
            help="Generate fixture file from environment variables",
        )

    def handle(self, *args, **options):
        if options["list_categories"]:
            self._list_categories()
            return

        if options["generate_fixtures"]:
            self._generate_fixture_file()
            return

        # Generate and process fixtures
        fixtures = self._get_fixtures(options)
        fixtures = self._filter_fixtures_by_category(fixtures, options)

        # Process fixtures and get results
        results = self._process_fixtures(fixtures, options)
        self._display_summary(results, options)

    def _get_fixtures(self, options):
        """Get fixtures from environment variables."""
        fixtures = self._generate_fixtures()
        if not fixtures:
            raise CommandError("No fixtures generated. Check environment variables.")
        return fixtures

    def _filter_fixtures_by_category(self, fixtures, options):
        """Filter fixtures by category if specified."""
        if options["category"]:
            if options["category"] not in fixtures:
                available = ", ".join(fixtures.keys())
                raise CommandError(
                    f'Category "{options["category"]}" not found. Available: {available}'
                )
            fixtures = {options["category"]: fixtures[options["category"]]}
        return fixtures

    def _process_fixtures(self, fixtures, options):
        """Process all fixtures and return results."""
        results = {"created": 0, "updated": 0, "skipped": 0}

        with transaction.atomic():
            for category_name, category_data in fixtures.items():
                if (
                    not isinstance(category_data, dict)
                    or "description" not in category_data
                ):
                    continue

                self._display_category_header(category_name, category_data)
                self._process_category_users(category_data, options, results)

        return results

    def _display_category_header(self, category_name, category_data):
        """Display category processing header."""
        self.stdout.write(f"\n=== Processing {category_name} ===")
        self.stdout.write(f"Description: {category_data['description']}")

    def _process_category_users(self, category_data, options, results):
        """Process all users in a category."""
        for user_key, user_data in category_data.items():
            if not self._is_valid_user_data(user_key, user_data):
                continue

            if options["dry_run"]:
                self._handle_dry_run(user_data)
                continue

            self._process_user(user_data, options, results)

    def _is_valid_user_data(self, user_key, user_data):
        """Check if user data is valid for processing."""
        if user_key in ["description", "note"] or not isinstance(user_data, dict):
            return False
        return "username" in user_data

    def _handle_dry_run(self, user_data):
        """Handle dry run display for a user."""
        username = user_data["username"]
        email = user_data["email"]
        self.stdout.write(f"  Would process: {username} ({email})")

    def _process_user(self, user_data, options, results):
        """Process a single user (create or update)."""
        username = user_data["username"]

        try:
            user = User.objects.get(username=username)
            if options["force"]:
                self._update_existing_user(user, user_data)
                self.stdout.write(self.style.WARNING(f"  Updated: {username}"))
                results["updated"] += 1
            else:
                self.stdout.write(self.style.NOTICE(f"  Skipped (exists): {username}"))
                results["skipped"] += 1

        except User.DoesNotExist:
            self._create_new_user(user_data)
            self.stdout.write(self.style.SUCCESS(f"  Created: {username}"))
            results["created"] += 1

    def _update_existing_user(self, user, user_data):
        """Update an existing user with new data."""
        user.email = user_data["email"]
        user.first_name = user_data.get("first_name", "")
        user.last_name = user_data.get("last_name", "")
        user.is_staff = user_data.get("is_staff", False)
        user.is_superuser = user_data.get("is_superuser", False)
        user.set_password(user_data["password"])
        user.save()

    def _create_new_user(self, user_data):
        """Create a new user from user data."""
        user = User.objects.create(
            username=user_data["username"],
            email=user_data["email"],
            first_name=user_data.get("first_name", ""),
            last_name=user_data.get("last_name", ""),
            is_staff=user_data.get("is_staff", False),
            is_superuser=user_data.get("is_superuser", False),
        )
        user.set_password(user_data["password"])
        user.save()

    def _display_summary(self, results, options):
        """Display processing summary."""
        if options["dry_run"]:
            self.stdout.write(self.style.NOTICE("\n=== DRY RUN COMPLETE ==="))
        else:
            self.stdout.write(self.style.SUCCESS("\n=== SUMMARY ==="))
            self.stdout.write(f"Created: {results['created']}")
            self.stdout.write(f"Updated: {results['updated']}")
            self.stdout.write(f"Skipped: {results['skipped']}")
            total = sum(results.values())
            self.stdout.write(f"Total processed: {total}")

    def _generate_fixtures(self):
        """Generate fixtures using the standalone script."""
        try:
            # Run the fixture generation script
            script_path = (
                Path(settings.BASE_DIR) / "scripts" / "generate_user_fixtures.py"
            )

            if not script_path.exists():
                raise CommandError(
                    f"Fixture generation script not found: {script_path}"
                )

            # Create temporary file for output
            with tempfile.NamedTemporaryFile(
                mode="w+", suffix=".json", delete=False
            ) as temp_file:
                temp_file_path = temp_file.name

            try:
                # Run the script with output to temporary file
                result = subprocess.run(
                    ["python", str(script_path), "--output", temp_file_path],
                    capture_output=True,
                    text=True,
                    cwd=settings.BASE_DIR,
                )

                if result.returncode != 0:
                    raise CommandError(f"Fixture generation failed: {result.stderr}")

                # Load the generated fixtures
                with open(temp_file_path, "r", encoding="utf-8") as f:
                    fixtures = json.load(f)

                return fixtures

            finally:
                # Clean up temporary file
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)

        except Exception as e:
            raise CommandError(f"Error generating fixtures: {e}")

    def _list_categories(self):
        """List available user categories."""
        fixtures = self._generate_fixtures()

        self.stdout.write("Available user categories:")
        for category_name, category_data in fixtures.items():
            if isinstance(category_data, dict) and "description" in category_data:
                user_count = sum(
                    1
                    for k, v in category_data.items()
                    if isinstance(v, dict) and "username" in v
                )
                self.stdout.write(
                    f"  - {category_name}: {category_data['description']} ({user_count} users)"
                )

    def _generate_fixture_file(self):
        """Generate and save fixture file."""
        try:
            script_path = (
                Path(settings.BASE_DIR) / "scripts" / "generate_user_fixtures.py"
            )

            if not script_path.exists():
                raise CommandError(
                    f"Fixture generation script not found: {script_path}"
                )

            # Run the script
            result = subprocess.run(
                ["python", str(script_path)],
                capture_output=True,
                text=True,
                cwd=settings.BASE_DIR,
            )

            if result.returncode != 0:
                raise CommandError(f"Fixture generation failed: {result.stderr}")

            self.stdout.write(result.stdout)

        except Exception as e:
            raise CommandError(f"Error generating fixture file: {e}")
