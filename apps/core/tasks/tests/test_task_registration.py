"""
Integration tests for Celery task registration and beat schedule validation.

This module ensures that all tasks referenced in CELERY_BEAT_SCHEDULE
are properly registered with Celery's autodiscovery mechanism, preventing
runtime failures where scheduled tasks cannot be found.
"""

from django.test import TestCase

from grey_lit_project.celery import app


class TestTaskRegistration(TestCase):
    """Verify all scheduled tasks are properly registered."""

    def test_ensure_tasks_registered_function(self):
        """
        Test that ensure_tasks_registered() successfully imports all task modules.

        This test directly calls the ensure_tasks_registered() function to verify
        it can be called manually (for verification scripts) and properly imports
        all task modules without errors.
        """
        from grey_lit_project.celery import ensure_tasks_registered

        # Should not raise any exceptions
        try:
            ensure_tasks_registered()
        except Exception as e:
            self.fail(f"ensure_tasks_registered() raised an exception: {e}")

        # Verify tasks are registered after calling the function
        critical_tasks = [
            "apps.core.tasks.adaptive_session_monitor",
            "apps.core.tasks.consolidated_maintenance",
            "apps.core.tasks.monitoring_statistics",
        ]

        for task_name in critical_tasks:
            with self.subTest(task=task_name):
                self.assertIn(
                    task_name,
                    app.tasks,
                    msg=f"Task '{task_name}' not registered after calling ensure_tasks_registered()",
                )

    def test_beat_schedule_tasks_are_registered(self):
        """
        Ensure all tasks in CELERY_BEAT_SCHEDULE are registered with Celery.

        This test prevents the critical issue where a task is scheduled in
        the beat configuration but not actually registered with Celery,
        which would cause the Sentry monitor to fail silently.

        See: docs/debug_reports/sentry-monitor-consolidated-maintenance-fix.md

        Note: Tasks under development may be intentionally scheduled but not
        yet implemented. This test focuses on critical production tasks.
        """
        schedule = app.conf.beat_schedule

        # Tasks that MUST be registered (critical for production)
        critical_task_keys = [
            "adaptive-session-monitor",
            "consolidated-maintenance",
            "monitoring-statistics",
        ]

        for task_key in critical_task_keys:
            if task_key in schedule:
                config = schedule[task_key]
                task_path = config["task"]
                with self.subTest(task=task_path, schedule_key=task_key):
                    self.assertIn(
                        task_path,
                        app.tasks,
                        msg=(
                            f"Critical task '{task_path}' is scheduled in "
                            f"beat_schedule['{task_key}'] "
                            f"but not registered with Celery. "
                            f"Ensure task is imported in apps.core.tasks.__init__.py"
                        ),
                    )

    def test_core_monitoring_tasks_registered(self):
        """
        Verify monitoring tasks are discoverable by Celery.

        These tasks are critical for the application's health monitoring
        and must be properly imported in apps.core.tasks.__init__.py
        """
        required_tasks = [
            "apps.core.tasks.adaptive_session_monitor",
            "apps.core.tasks.consolidated_maintenance",
            "apps.core.tasks.monitoring_statistics",
        ]

        registered_tasks = list(app.tasks.keys())

        for task_name in required_tasks:
            with self.subTest(task=task_name):
                self.assertIn(
                    task_name,
                    registered_tasks,
                    msg=(
                        f"Required task '{task_name}' not registered. "
                        f"Check task import in appropriate __init__.py"
                    ),
                )

    def test_all_beat_tasks_have_valid_schedule(self):
        """
        Verify all beat schedule entries have valid configuration.

        Ensures each task has required fields (task path, schedule)
        and optional fields are properly structured.
        """
        schedule = app.conf.beat_schedule

        for task_key, config in schedule.items():
            with self.subTest(schedule_key=task_key):
                # Check required fields
                self.assertIn(
                    "task",
                    config,
                    msg=f"Beat schedule entry '{task_key}' missing 'task' field",
                )
                self.assertIn(
                    "schedule",
                    config,
                    msg=f"Beat schedule entry '{task_key}' missing 'schedule' field",
                )

                # Validate task path format
                task_path = config["task"]
                self.assertTrue(
                    task_path.startswith("apps."),
                    msg=(
                        f"Task path '{task_path}' should start with 'apps.' "
                        f"for proper namespacing"
                    ),
                )

    def test_no_duplicate_beat_schedule_definition(self):
        """
        Ensure beat schedule is only defined in settings, not in celery.py.

        This test catches the exact issue that caused the Sentry monitor
        failure: duplicate beat_schedule definition in celery.py overriding
        the settings configuration.

        See: docs/debug_reports/sentry-monitor-consolidated-maintenance-fix.md
        """
        # Read celery.py file content
        celery_file_path = "grey_lit_project/celery.py"
        with open(celery_file_path, "r") as f:
            celery_content = f.read()

        # Check for forbidden pattern: app.conf.beat_schedule = {...}
        self.assertNotIn(
            "app.conf.beat_schedule =",
            celery_content,
            msg=(
                "Found 'app.conf.beat_schedule =' in celery.py. "
                "Beat schedule should ONLY be defined in "
                "grey_lit_project/settings/base.py as CELERY_BEAT_SCHEDULE. "
                "Redefining in celery.py overrides settings configuration."
            ),
        )

        # Verify documentation comment exists
        self.assertIn(
            "CELERY_BEAT_SCHEDULE",
            celery_content,
            msg=(
                "celery.py should contain a comment explaining that "
                "beat schedule is defined in settings/base.py"
            ),
        )
