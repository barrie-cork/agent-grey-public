#!/usr/bin/env python
"""
Test runner script for the reporting app.

This script provides convenient commands to run different test suites
for the reporting app with various options.

Usage:
    python run_tests.py                    # Run all tests
    python run_tests.py --views           # Run only view tests
    python run_tests.py --coverage        # Run with coverage report
    python run_tests.py --parallel        # Run tests in parallel
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Django setup
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "grey_lit_project.settings.test")


def run_command(cmd):
    """Run a shell command and return the exit code."""
    logger.info(f"Running: {cmd}")
    return os.system(cmd)


def main():
    """Main test runner function."""
    parser = argparse.ArgumentParser(description="Run reporting app tests")

    # Test selection options
    parser.add_argument("--all", action="store_true", help="Run all tests (default)")
    parser.add_argument("--views", action="store_true", help="Run only view tests")
    parser.add_argument("--forms", action="store_true", help="Run only form tests")
    parser.add_argument("--tasks", action="store_true", help="Run only task tests")
    parser.add_argument(
        "--services", action="store_true", help="Run only service tests"
    )
    parser.add_argument(
        "--integration", action="store_true", help="Run only integration tests"
    )
    parser.add_argument("--models", action="store_true", help="Run only model tests")

    # Test options
    parser.add_argument(
        "--coverage", action="store_true", help="Run with coverage report"
    )
    parser.add_argument("--parallel", action="store_true", help="Run tests in parallel")
    parser.add_argument("--failfast", action="store_true", help="Stop on first failure")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--keepdb", action="store_true", help="Keep test database")

    args = parser.parse_args()

    # Build base command
    if args.coverage:
        base_cmd = "coverage run --source='apps.reporting' manage.py test"
    else:
        base_cmd = "python manage.py test"

    # Add test options
    test_options = []
    if args.parallel:
        test_options.append("--parallel")
    if args.failfast:
        test_options.append("--failfast")
    if args.verbose:
        test_options.append("--verbosity=2")
    if args.keepdb:
        test_options.append("--keepdb")

    # Determine which tests to run
    test_modules = []

    if args.views:
        test_modules.append("apps.reporting.tests.test_views")
    elif args.forms:
        test_modules.append("apps.reporting.tests.test_forms")
    elif args.tasks:
        test_modules.append("apps.reporting.tests.test_tasks")
    elif args.services:
        test_modules.append("apps.reporting.tests.test_services")
    elif args.integration:
        test_modules.append("apps.reporting.tests.test_integration")
    elif args.models:
        test_modules.append("apps.reporting.tests.test_models")
    else:
        # Run all tests
        test_modules.append("apps.reporting.tests")

    # Build full command
    full_cmd = f"{base_cmd} {' '.join(test_modules)} {' '.join(test_options)}"

    # Change to project directory
    os.chdir(project_root)

    # Run tests
    exit_code = run_command(full_cmd)

    # Show coverage report if requested
    if args.coverage and exit_code == 0:
        logger.info("\n" + "=" * 70)
        logger.info("Coverage Report")
        logger.info("=" * 70)
        run_command("coverage report -m")

        # Generate HTML report
        run_command("coverage html")
        logger.info("\nHTML coverage report generated in htmlcov/")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
