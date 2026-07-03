"""Management command to validate deployment configuration.

This command validates deployment environment variables and configuration
to prevent silent failures and ensure configuration consistency.

Created: 2025-10-17
Purpose: Phase 3 of Post-Deployment Refactoring Plan - Task 3.5
"""

import json
import sys

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.core.utils.deployment_validation import validate_deployment_config


class Command(BaseCommand):
    """Validate deployment configuration for production readiness."""

    help = "Validate deployment configuration for production readiness"

    def add_arguments(self, parser):
        """Add command-line arguments."""
        parser.add_argument(
            "--environment",
            type=str,
            default=None,
            help="Environment to validate (production, staging, local). "
            "Defaults to auto-detect from settings.ENVIRONMENT",
        )
        parser.add_argument(
            "--format",
            type=str,
            choices=["text", "json"],
            default="text",
            help="Output format: text (human-readable) or json (machine-readable)",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Show detailed validation results with hints",
        )

    def handle(self, *args, **options):
        """Execute the validation command."""
        # Determine environment
        environment = options["environment"]
        if environment is None:
            # Auto-detect from settings
            environment = getattr(settings, "ENVIRONMENT", "production")

        output_format = options["format"]
        verbose = options["verbose"]

        # Run validation
        try:
            report = validate_deployment_config(environment=environment)
        except Exception as e:
            if output_format == "json":
                self._output_json_error(str(e))
            else:
                self.stderr.write(
                    self.style.ERROR(f"Validation failed with exception: {e}")
                )
            sys.exit(1)

        # Output results
        if output_format == "json":
            self._output_json(report)
        else:
            self._output_text(report, verbose=verbose)

        # Exit with appropriate code
        sys.exit(0 if report.passed else 1)

    def _output_text(self, report, verbose=False):
        """Output validation results in human-readable text format.

        Args:
            report: ValidationReport object
            verbose: Whether to show detailed results with hints
        """
        # Header
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(
            f"  Deployment Validation Report - {report.environment.upper()}"
        )
        self.stdout.write("=" * 70 + "\n")

        # Status
        if report.passed:
            self.stdout.write(self.style.SUCCESS("✓ Status: PASSED (no errors found)"))
        else:
            self.stdout.write(
                self.style.ERROR(
                    f"✗ Status: FAILED ({len(report.errors)} error(s) found)"
                )
            )

        # Summary counts
        self.stdout.write(f"\n  Errors:   {len(report.errors)}")
        self.stdout.write(f"  Warnings: {len(report.warnings)}")
        self.stdout.write(f"  Total Checks: {len(report.results)}\n")

        # Critical errors
        if report.errors:
            self.stdout.write("\n" + "=" * 70)
            self.stdout.write("  ERRORS (must fix before deployment)")
            self.stdout.write("=" * 70 + "\n")
            for i, error in enumerate(report.errors, 1):
                self.stdout.write(f"{i}. {self.style.ERROR(f'✗ {error}')}")

        # Warnings
        if report.warnings:
            self.stdout.write("\n" + "=" * 70)
            self.stdout.write("  WARNINGS (should review)")
            self.stdout.write("=" * 70 + "\n")
            for i, warning in enumerate(report.warnings, 1):
                self.stdout.write(f"{i}. {self.style.WARNING(f'⚠  {warning}')}")

        # Detailed results (if verbose)
        if verbose:
            self.stdout.write("\n" + "=" * 70)
            self.stdout.write("  DETAILED VALIDATION RESULTS")
            self.stdout.write("=" * 70 + "\n")

            for result in report.results:
                # Icon and message
                icon = self._get_icon(result.severity)
                style_func = self._get_style_func(result.severity)
                self.stdout.write(f"\n{style_func(f'{icon} {result.message}')}")

                # Hints (if available)
                if result.hints:
                    for hint in result.hints:
                        self.stdout.write(f"  💡 {hint}")

        # Footer
        self.stdout.write("\n" + "=" * 70)
        if report.passed:
            self.stdout.write(
                self.style.SUCCESS("  Validation passed. Configuration is valid.")
            )
        else:
            self.stdout.write(
                self.style.ERROR("  Validation failed. Fix errors before deploying.")
            )
        self.stdout.write("=" * 70 + "\n")

    def _output_json(self, report):
        """Output validation results in JSON format for CI/CD integration.

        Args:
            report: ValidationReport object
        """
        output = {
            "environment": report.environment,
            "passed": report.passed,
            "summary": {
                "errors": len(report.errors),
                "warnings": len(report.warnings),
                "total_checks": len(report.results),
            },
            "errors": report.errors,
            "warnings": report.warnings,
            "results": [
                {
                    "is_valid": result.is_valid,
                    "message": result.message,
                    "severity": result.severity,
                    "hints": result.hints,
                }
                for result in report.results
            ],
        }

        self.stdout.write(json.dumps(output, indent=2))

    def _output_json_error(self, error_message):
        """Output error in JSON format.

        Args:
            error_message: Error message string
        """
        output = {
            "environment": "unknown",
            "passed": False,
            "summary": {"errors": 1, "warnings": 0, "total_checks": 0},
            "errors": [error_message],
            "warnings": [],
            "results": [],
        }

        self.stderr.write(json.dumps(output, indent=2))

    def _get_icon(self, severity):
        """Get icon for severity level.

        Args:
            severity: Severity level string

        Returns:
            Icon string
        """
        icons = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌",
            "critical": "🔥",
        }
        return icons.get(severity, "ℹ️")

    def _get_style_func(self, severity):
        """Get Django style function for severity level.

        Args:
            severity: Severity level string

        Returns:
            Style function from self.style
        """
        if severity in ["error", "critical"]:
            return self.style.ERROR
        elif severity == "warning":
            return self.style.WARNING
        else:
            return self.style.SUCCESS
