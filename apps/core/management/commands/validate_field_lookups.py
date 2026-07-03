"""
Django management command to validate field lookups across the codebase.
"""

import os
import re
from pathlib import Path
from typing import List, Tuple

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError


class FieldLookupValidator:
    """Validates Django ORM field lookups against model definitions."""

    # Django automatic fields available on all models
    DJANGO_AUTOMATIC_FIELDS = {"pk", "id"}

    def __init__(self, verbosity: int = 1):
        self.verbosity = verbosity
        self.errors = []
        self.warnings = []
        self.model_cache = {}
        self._build_model_cache()

    def _build_model_cache(self):
        """Build a cache of all models and their fields."""
        for model in apps.get_models():
            model_name = model.__name__
            app_label = model._meta.app_label

            self.model_cache[model_name] = {
                "app_label": app_label,
                "model": model,
                "fields": set(),
                "related_fields": {},
            }

            # Add Django automatic fields
            self.model_cache[model_name]["fields"].update(self.DJANGO_AUTOMATIC_FIELDS)

            # Add regular fields
            for field in model._meta.get_fields():
                field_name = field.name
                self.model_cache[model_name]["fields"].add(field_name)

                # Track related fields
                if hasattr(field, "related_model") and field.related_model:
                    related_model_name = field.related_model.__name__
                    self.model_cache[model_name]["related_fields"][field_name] = (
                        related_model_name
                    )

    def validate_lookup(
        self, model_name: str, lookup_path: str, file_path: str, line_no: int
    ) -> bool:
        """Validate a field lookup path for a model."""
        if model_name not in self.model_cache:
            self.warnings.append(f"{file_path}:{line_no} - Unknown model: {model_name}")
            return False

        parts = lookup_path.split("__")
        current_model = model_name

        for i, part in enumerate(parts):
            if current_model not in self.model_cache:
                return False

            model_info = self.model_cache[current_model]

            # Check if it's a regular field
            if part in model_info["fields"]:
                # If it's a related field, update current model
                if part in model_info["related_fields"]:
                    current_model = model_info["related_fields"][part]
                continue

            # Check for _id suffix on ForeignKey fields
            if part.endswith("_id") and part[:-3] in model_info["related_fields"]:
                # This is accessing the raw ID value of a ForeignKey
                # Example: session_id when there's a session ForeignKey
                continue

            # Check for special lookups (in, gt, lt, etc.)
            if i == len(parts) - 1 and part in [
                "in",
                "gt",
                "lt",
                "gte",
                "lte",
                "exact",
                "iexact",
                "contains",
                "icontains",
                "startswith",
                "endswith",
                "isnull",
            ]:
                return True

            # Field not found
            self.errors.append(
                f"{file_path}:{line_no} - Invalid field lookup: "
                f"{model_name}.objects.filter({lookup_path}=...) - "
                f"Field '{part}' not found on model '{current_model}'"
            )
            return False

        return True

    def extract_lookups_from_file(self, file_path: str) -> List[Tuple[str, str, int]]:
        """Extract ORM lookups from a Python file."""
        lookups = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            self.warnings.append(f"Could not read {file_path}: {e}")
            return lookups

        # Regex patterns for common ORM queries
        patterns = [
            # Model.objects.filter(field__lookup=...)
            r"(\w+)\.objects\.(?:filter|exclude|get)\s*\(\s*([a-zA-Z_]\w*(?:__[a-zA-Z_]\w*)*)\s*=",
            # Model.objects.annotate(name=Count('field__lookup'))
            r'(\w+)\.objects\.annotate\s*\([^)]*Count\s*\(\s*[\'"]([a-zA-Z_]\w*(?:__[a-zA-Z_]\w*)*)[\'"]',
            # Q(field__lookup=...)
            r"Q\s*\(\s*([a-zA-Z_]\w*(?:__[a-zA-Z_]\w*)*)\s*=",
        ]

        lines = content.split("\n")

        for line_no, line in enumerate(lines, 1):
            # Skip comments
            if line.strip().startswith("#"):
                continue

            # Check first pattern (with model)
            matches = re.finditer(patterns[0], line)
            for match in matches:
                model_name = match.group(1)
                lookup = match.group(2)
                lookups.append((model_name, lookup, line_no))

            # Check annotation pattern
            matches = re.finditer(patterns[1], line)
            for match in matches:
                model_name = match.group(1)
                lookup = match.group(2)
                lookups.append((model_name, lookup, line_no))

        return lookups

    def validate_directory(self, directory: Path) -> Tuple[int, int]:
        """Validate all Python files in a directory."""
        total_lookups = 0
        valid_lookups = 0

        for root, dirs, files in os.walk(directory):
            # Skip migrations and __pycache__
            dirs[:] = [d for d in dirs if d not in ["migrations", "__pycache__"]]

            for file in files:
                if file.endswith(".py"):
                    file_path = os.path.join(root, file)
                    lookups = self.extract_lookups_from_file(file_path)

                    for model_name, lookup, line_no in lookups:
                        total_lookups += 1
                        if self.validate_lookup(model_name, lookup, file_path, line_no):
                            valid_lookups += 1

        return total_lookups, valid_lookups


class Command(BaseCommand):
    help = "Validate Django ORM field lookups across the codebase"

    def add_arguments(self, parser):
        parser.add_argument(
            "--app",
            type=str,
            help="Specific app to validate (default: all apps)",
        )
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Show suggestions for fixing errors",
        )

    def handle(self, *args, **options):
        validator = FieldLookupValidator(verbosity=options["verbosity"])

        # Determine which directories to validate
        if options["app"]:
            app_path = Path("apps") / options["app"]
            if not app_path.exists():
                raise CommandError(f"App '{options['app']}' not found")
            directories = [app_path]
        else:
            # Validate all app directories
            directories = [
                Path("apps") / d
                for d in os.listdir("apps")
                if os.path.isdir(Path("apps") / d)
            ]

        # Run validation
        total_lookups = 0
        valid_lookups = 0

        for directory in directories:
            self.stdout.write(f"\nValidating {directory}...")
            dir_total, dir_valid = validator.validate_directory(directory)
            total_lookups += dir_total
            valid_lookups += dir_valid

        # Report results
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("VALIDATION SUMMARY")
        self.stdout.write("=" * 60)

        if validator.errors:
            self.stdout.write(
                self.style.ERROR(f"\nFound {len(validator.errors)} errors:")
            )
            for error in validator.errors:
                self.stdout.write(self.style.ERROR(f"  • {error}"))

                # Show fix suggestions if requested
                if options["fix"]:
                    self._suggest_fix(error)

        if validator.warnings:
            self.stdout.write(
                self.style.WARNING(f"\nWarnings ({len(validator.warnings)}):")
            )
            for warning in validator.warnings[:5]:  # Show first 5 warnings
                self.stdout.write(self.style.WARNING(f"  • {warning}"))

        # Summary statistics
        self.stdout.write(f"\nTotal lookups analyzed: {total_lookups}")
        self.stdout.write(f"Valid lookups: {valid_lookups}")

        if validator.errors:
            self.stdout.write(
                self.style.ERROR(f"Invalid lookups: {len(validator.errors)}")
            )
            self.stdout.write(self.style.ERROR("\nValidation FAILED"))
            return

        self.stdout.write(self.style.SUCCESS("\nAll field lookups are valid! ✓"))

    def _suggest_fix(self, error: str):
        """Suggest fixes for common errors."""
        if "strategy' not found on model 'SearchQuery'" in error:
            self.stdout.write(
                self.style.WARNING(
                    "    Fix: SearchQuery uses 'strategy' not 'search_strategy'"
                )
            )
        elif "session' not found on model 'SearchExecution'" in error:
            self.stdout.write(
                self.style.WARNING(
                    "    Fix: Use 'query__session' instead of direct 'session'"
                )
            )

        # Check for denormalized field suggestions
        if "query__strategy__session" in error:
            self.stdout.write(
                self.style.WARNING(
                    "    Performance tip: Consider using 'query__session' (denormalized field)"
                )
            )
