#!/usr/bin/env python
"""
Test runner script for SERP execution module.

Usage:
    python run_tests.py                    # Run all tests
    python run_tests.py models            # Run only model tests
    python run_tests.py services          # Run only service tests
    python run_tests.py views             # Run only view tests
    python run_tests.py tasks             # Run only task tests
    python run_tests.py integration       # Run only integration tests
    python run_tests.py forms             # Run only form tests
    python run_tests.py coverage          # Run with coverage report
"""

import logging
import os
import sys

import django
from django.conf import settings
from django.test.utils import get_runner

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Add project root to Python path
project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
sys.path.insert(0, project_root)

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "grey_lit_project.settings.test")
django.setup()


def run_tests(
    test_labels=None, verbosity=1, interactive=True, failfast=False, keepdb=False
):
    """Run the test suite."""
    TestRunner = get_runner(settings)
    test_runner = TestRunner(
        verbosity=verbosity, interactive=interactive, failfast=failfast, keepdb=keepdb
    )

    if not test_labels:
        test_labels = ["apps.serp_execution"]

    failures = test_runner.run_tests(test_labels)

    if failures:
        sys.exit(1)


def run_with_coverage():
    """Run tests with coverage report."""
    import coverage

    # Start coverage
    cov = coverage.Coverage(
        source=["apps/serp_execution"],
        omit=[
            "*/tests/*",
            "*/migrations/*",
            "*/__init__.py",
            "*/apps.py",
            "*/admin.py",
        ],
    )
    cov.start()

    # Run tests
    run_tests()

    # Stop coverage and generate report
    cov.stop()
    cov.save()

    logger.info("\n\nCoverage Report:")
    logger.info("=" * 70)
    cov.report()

    # Generate HTML report
    html_dir = os.path.join(project_root, "htmlcov")
    cov.html_report(directory=html_dir)
    logger.info(f"\nDetailed HTML coverage report generated in: {html_dir}")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run SERP execution tests")
    parser.add_argument(
        "test_type",
        nargs="?",
        choices=[
            "all",
            "models",
            "services",
            "views",
            "tasks",
            "integration",
            "forms",
            "coverage",
        ],
        default="all",
        help="Type of tests to run",
    )
    parser.add_argument(
        "--verbosity", type=int, choices=[0, 1, 2, 3], default=2, help="Verbosity level"
    )
    parser.add_argument(
        "--failfast", action="store_true", help="Stop on first test failure"
    )
    parser.add_argument(
        "--keepdb", action="store_true", help="Preserve test database between runs"
    )

    args = parser.parse_args()

    # Map test types to test labels
    test_mapping = {
        "all": ["apps.serp_execution"],
        "models": ["apps.serp_execution.tests.test_models"],
        "services": ["apps.serp_execution.tests.test_services"],
        "views": ["apps.serp_execution.tests.test_views"],
        "tasks": ["apps.serp_execution.tests.test_tasks"],
        "integration": ["apps.serp_execution.tests.test_integration"],
        "forms": ["apps.serp_execution.tests.test_forms"],
    }

    if args.test_type == "coverage":
        run_with_coverage()
    else:
        test_labels = test_mapping.get(args.test_type, ["apps.serp_execution"])
        run_tests(
            test_labels=test_labels,
            verbosity=args.verbosity,
            failfast=args.failfast,
            keepdb=args.keepdb,
        )


if __name__ == "__main__":
    main()
