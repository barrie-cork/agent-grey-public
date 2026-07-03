"""
Test cases for reporting app Celery tasks.

This module tests background task execution, file generation,
cleanup operations, and error handling for report generation.
"""

from datetime import timedelta
from unittest.mock import Mock, patch
from uuid import uuid4

from celery.exceptions import Retry
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.tests.utils import create_test_user
from apps.reporting.models import ExportReport
from apps.reporting.tasks import (
    MAX_RETRIES,
    RETRY_BACKOFF_BASE,
    _get_retry_countdown,
    _is_retryable_error,
    cleanup_expired_reports,
    generate_bulk_reports,
    generate_comprehensive_report_data,
    generate_report_task,
    import_excel_backup_task,
    send_report_ready_notification,
)
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession

User = get_user_model()


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class GenerateReportTaskTest(TestCase):
    """Test the main report generation task."""

    def setUp(self):
        """Create test data."""
        # Patch update_state to avoid needing a real Celery context
        self._update_state_patcher = patch.object(
            generate_report_task, "update_state", return_value=None
        )
        self._update_state_patcher.start()

        self.user = create_test_user(username_prefix="test@example.com")
        self.session = SearchSession.objects.create(
            title="Test Session",
            description="Test Description",
            owner=self.user,
            status="completed",
        )
        self.report = ExportReport.objects.create(
            session=self.session,
            generated_by=self.user,
            report_type="full_report",
            export_format="pdf",
            title="Test Report",
            status="pending",
            file_size_bytes=0,
        )

    def tearDown(self):
        """Restore Celery config."""
        self._update_state_patcher.stop()

    @patch(
        "apps.reporting.services.report_generators.factory.ReportGeneratorFactory.create"
    )
    @patch("django.db.models.fields.files.FieldFile.save")
    @patch("django.core.files.storage.default_storage.size")
    @patch("django.core.files.storage.default_storage.exists")
    @patch("apps.reporting.tasks.send_report_ready_notification.delay")
    def test_successful_pdf_generation(
        self, mock_notify, mock_exists, mock_size, mock_field_save, mock_factory
    ):
        """Test successful PDF report generation."""
        mock_exists.return_value = True
        mock_size.return_value = 1024
        mock_field_save.side_effect = lambda name, content, save=True: setattr(
            self.report.file_path, "name", f"reports/{name}"
        )
        mock_generator = Mock()
        mock_generator.generate.return_value = b"%PDF-1.4 test content"
        mock_generator.get_file_extension.return_value = "pdf"
        mock_factory.return_value = mock_generator

        result = generate_report_task(str(self.report.id))  # type: ignore[call-arg]

        self.assertEqual(result["status"], "completed")
        self.assertIn("file_path", result)

        self.report.refresh_from_db()
        self.assertEqual(self.report.status, "completed")
        self.assertEqual(self.report.progress_percentage, 100)
        self.assertIsNotNone(self.report.completed_at)
        self.assertIsNotNone(self.report.expires_at)

        mock_notify.assert_called_once_with(str(self.report.id))

    @patch(
        "apps.reporting.services.report_generators.factory.ReportGeneratorFactory.create"
    )
    @patch("django.db.models.fields.files.FieldFile.save")
    @patch("apps.reporting.tasks.send_report_ready_notification.delay")
    @patch("django.core.files.storage.default_storage.size", return_value=512)
    @patch("django.core.files.storage.default_storage.exists", return_value=True)
    def test_csv_generation(
        self, mock_exists, mock_size, mock_notify, mock_field_save, mock_factory
    ):
        """Test CSV report generation."""
        self.report.report_type = "results_summary"
        self.report.export_format = "csv"
        self.report.save()

        mock_field_save.side_effect = lambda name, content, save=True: setattr(
            self.report.file_path, "name", f"reports/{name}"
        )
        mock_generator = Mock()
        mock_generator.generate.return_value = b"col1,col2\nval1,val2"
        mock_generator.get_file_extension.return_value = "csv"
        mock_factory.return_value = mock_generator

        result = generate_report_task(str(self.report.id))  # type: ignore[call-arg]

        self.assertEqual(result["status"], "completed")

    @patch(
        "apps.reporting.services.report_generators.factory.ReportGeneratorFactory.create"
    )
    @patch("django.db.models.fields.files.FieldFile.save")
    @patch("apps.reporting.tasks.send_report_ready_notification.delay")
    @patch("django.core.files.storage.default_storage.size")
    @patch("django.core.files.storage.default_storage.exists")
    def test_json_generation(
        self, mock_exists, mock_size, mock_notify, mock_field_save, mock_factory
    ):
        """Test JSON report generation."""
        self.report.report_type = "results_summary"
        self.report.export_format = "json"
        self.report.save()

        mock_exists.return_value = True
        mock_size.return_value = 256
        mock_field_save.side_effect = lambda name, content, save=True: setattr(
            self.report.file_path, "name", f"reports/{name}"
        )
        mock_generator = Mock()
        mock_generator.generate.return_value = b'{"key": "value"}'
        mock_generator.get_file_extension.return_value = "json"
        mock_factory.return_value = mock_generator

        result = generate_report_task(str(self.report.id))  # type: ignore[call-arg]

        self.assertEqual(result["status"], "completed")

        self.report.refresh_from_db()
        self.assertTrue(self.report.file_name.endswith(".json"))

    @patch(
        "apps.reporting.services.report_generators.factory.ReportGeneratorFactory.create"
    )
    @patch("django.db.models.fields.files.FieldFile.save")
    @patch("apps.reporting.tasks.send_report_ready_notification.delay")
    @patch("django.core.files.storage.default_storage.size")
    @patch("django.core.files.storage.default_storage.exists")
    def test_prisma_flow_generation(
        self, mock_exists, mock_size, mock_notify, mock_field_save, mock_factory
    ):
        """Test PRISMA flow diagram generation."""
        self.report.report_type = "prisma_flow"
        self.report.save()

        mock_exists.return_value = True
        mock_size.return_value = 2048
        mock_field_save.side_effect = lambda name, content, save=True: setattr(
            self.report.file_path, "name", f"reports/{name}"
        )
        mock_generator = Mock()
        mock_generator.generate.return_value = b"<svg>prisma flow</svg>"
        mock_generator.get_file_extension.return_value = "pdf"
        mock_factory.return_value = mock_generator

        result = generate_report_task(str(self.report.id))  # type: ignore[call-arg]

        self.assertEqual(result["status"], "completed")

    @patch(
        "apps.reporting.services.report_generators.factory.ReportGeneratorFactory.create"
    )
    @patch("django.db.models.fields.files.FieldFile.save")
    @patch("apps.reporting.tasks.send_report_ready_notification.delay")
    @patch("django.core.files.storage.default_storage.size")
    @patch("django.core.files.storage.default_storage.exists")
    def test_search_strategy_generation(
        self, mock_exists, mock_size, mock_notify, mock_field_save, mock_factory
    ):
        """Test search strategy report generation."""
        self.report.report_type = "search_strategy"
        self.report.save()

        mock_exists.return_value = True
        mock_size.return_value = 1536
        mock_field_save.side_effect = lambda name, content, save=True: setattr(
            self.report.file_path, "name", f"reports/{name}"
        )
        mock_generator = Mock()
        mock_generator.generate.return_value = b"<html>strategy report</html>"
        mock_generator.get_file_extension.return_value = "pdf"
        mock_factory.return_value = mock_generator

        result = generate_report_task(str(self.report.id))  # type: ignore[call-arg]

        self.assertEqual(result["status"], "completed")

    @patch(
        "apps.reporting.services.report_generators.factory.ReportGeneratorFactory.create"
    )
    @patch("django.db.models.fields.files.FieldFile.save")
    @patch("apps.reporting.tasks.send_report_ready_notification.delay")
    @patch("django.core.files.storage.default_storage.size")
    @patch("django.core.files.storage.default_storage.exists")
    def test_progress_updates(
        self, mock_exists, mock_size, mock_notify, mock_field_save, mock_factory
    ):
        """Test that progress is updated during generation."""
        mock_exists.return_value = True
        mock_size.return_value = 1024
        mock_field_save.side_effect = lambda name, content, save=True: setattr(
            self.report.file_path, "name", f"reports/{name}"
        )
        mock_generator = Mock()
        mock_generator.generate.return_value = b"test content"
        mock_generator.get_file_extension.return_value = "pdf"
        mock_factory.return_value = mock_generator

        generate_report_task(str(self.report.id))  # type: ignore[call-arg]

        self.report.refresh_from_db()
        self.assertEqual(self.report.progress_percentage, 100)

    def test_invalid_report_type(self):
        """Test handling of invalid report type."""
        self.report.report_type = "invalid_type"
        self.report.save()

        result = generate_report_task(str(self.report.id))  # type: ignore[call-arg]

        self.assertEqual(result["status"], "failed")
        self.assertIn("Unknown report type", result["error"])

        self.report.refresh_from_db()
        self.assertEqual(self.report.status, "failed")
        self.assertIn("Unknown report type", self.report.error_message)

    def test_invalid_export_format(self):
        """Test handling of invalid export format."""
        self.report.export_format = "xyz"
        self.report.save()

        result = generate_report_task(str(self.report.id))  # type: ignore[call-arg]

        self.assertEqual(result["status"], "failed")
        self.assertIn("Unknown format type", result["error"])

    def test_report_not_found(self):
        """Test handling when report doesn't exist."""
        fake_id = str(uuid4())
        result = generate_report_task(fake_id)  # type: ignore[call-arg]

        self.assertEqual(result["status"], "failed")
        self.assertIn("does not exist", result["error"])

    @patch(
        "apps.reporting.services.report_generators.pdf_generator.PDFReportGenerator.generate"
    )
    def test_generator_error(self, mock_generate):
        """Test handling of generator errors triggers retry."""
        mock_generate.side_effect = Exception("Generator error")

        with patch.object(
            generate_report_task, "retry", side_effect=Retry()
        ) as mock_retry:
            with self.assertRaises(Retry):
                generate_report_task(str(self.report.id))  # type: ignore[call-arg]

            mock_retry.assert_called_once()


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@agentgrey.test",
    SITE_DOMAIN="localhost:8000",
)
class SendReportReadyNotificationTest(TestCase):
    """Test the notification task sends emails."""

    def setUp(self):
        """Create test data."""
        from django.core import mail

        self.user = create_test_user(username_prefix="test@example.com")
        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.user,
        )
        self.report = ExportReport.objects.create(
            session=self.session,
            generated_by=self.user,
            title="Test Report",
            report_type="full_report",
            export_format="pdf",
            file_size_bytes=1048576,
            status="completed",
        )
        # Clear outbox after setUp to discard welcome emails from user creation
        mail.outbox = []

    def test_successful_notification_sends_email(self):
        """Test successful notification sends an email."""
        from django.core import mail

        result = send_report_ready_notification(str(self.report.id))

        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)

        email = mail.outbox[0]
        self.assertEqual(email.subject, f"Report Ready: {self.report.title}")
        self.assertIn(self.user.email, email.to)
        self.assertIn("Test Report", email.body)
        self.assertIn("Test Session", email.body)

    def test_successful_notification_includes_download_link(self):
        """Test email contains a download link."""
        from django.core import mail

        result = send_report_ready_notification(str(self.report.id))

        self.assertTrue(result)
        email = mail.outbox[0]
        # Check HTML alternative contains download URL and button text
        html_content = email.alternatives[0][0]
        self.assertIn(f"/reporting/reports/{self.report.id}/download/", html_content)
        self.assertIn("Download Report", html_content)

    @patch("apps.reporting.tasks.logger")
    def test_successful_notification_logs(self, mock_logger):
        """Test successful notification logs confirmation."""
        result = send_report_ready_notification(str(self.report.id))

        self.assertTrue(result)
        mock_logger.info.assert_called_once()
        log_message = mock_logger.info.call_args[0][0]
        self.assertIn(self.user.email, log_message)

    def test_notification_report_not_found(self):
        """Test handling when report doesn't exist."""
        fake_id = str(uuid4())
        result = send_report_ready_notification(fake_id)

        self.assertFalse(result)

    @patch("apps.reporting.tasks.logger")
    def test_notification_error_handling(self, mock_logger):
        """Test error handling in notification with non-existent report."""
        fake_id = str(uuid4())
        result = send_report_ready_notification(fake_id)

        self.assertFalse(result)
        mock_logger.error.assert_called_once()

    def test_notification_no_user(self):
        """Test handling when report has no generated_by user."""
        self.report.generated_by = None
        self.report.save()

        # This may raise an error which triggers retry
        with patch.object(send_report_ready_notification, "retry", side_effect=Retry()):
            try:
                result = send_report_ready_notification(str(self.report.id))
                self.assertFalse(result)
            except Retry:
                pass  # Expected: retry is triggered for the AttributeError


class CleanupExpiredReportsTest(TestCase):
    """Test the cleanup task for expired reports."""

    def setUp(self):
        """Create test data with various report states."""
        self.user = create_test_user(username_prefix="test@example.com")
        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.user,
        )

        self.expired_report = ExportReport.objects.create(
            session=self.session,
            generated_by=self.user,
            title="Expired Report",
            report_type="full_report",
            export_format="pdf",
            status="completed",
            file_path="reports/expired.pdf",
            file_size_bytes=1024,
            expires_at=timezone.now() - timedelta(days=1),
        )

        self.valid_report = ExportReport.objects.create(
            session=self.session,
            generated_by=self.user,
            title="Valid Report",
            report_type="full_report",
            export_format="pdf",
            status="completed",
            file_path="reports/valid.pdf",
            file_size_bytes=2048,
            expires_at=timezone.now() + timedelta(days=29),
        )

        self.expired_pending = ExportReport.objects.create(
            session=self.session,
            generated_by=self.user,
            title="Expired Pending",
            report_type="full_report",
            export_format="pdf",
            status="pending",
            file_size_bytes=0,
            expires_at=timezone.now() - timedelta(days=1),
        )

    @patch("django.core.files.storage.default_storage.exists")
    @patch("django.core.files.storage.default_storage.delete")
    def test_cleanup_expired_reports(self, mock_delete, mock_exists):
        """Test cleanup removes only expired completed reports."""
        mock_exists.return_value = True

        result = cleanup_expired_reports()

        self.assertEqual(result["cleaned_count"], 1)
        self.assertEqual(result["freed_space"], 1024)

        self.expired_report.refresh_from_db()
        self.assertEqual(self.expired_report.status, "expired")
        self.assertEqual(self.expired_report.file_path, "")

        self.valid_report.refresh_from_db()
        self.assertEqual(self.valid_report.status, "completed")
        self.assertEqual(self.valid_report.file_path, "reports/valid.pdf")

        self.expired_pending.refresh_from_db()
        self.assertEqual(self.expired_pending.status, "pending")

        mock_delete.assert_called_once_with("reports/expired.pdf")

    @patch("django.core.files.storage.default_storage.exists")
    def test_cleanup_missing_files(self, mock_exists):
        """Test cleanup handles missing files gracefully."""
        mock_exists.return_value = False

        result = cleanup_expired_reports()

        self.assertEqual(result["cleaned_count"], 1)
        self.assertEqual(result["freed_space"], 0)

    @patch("django.core.files.storage.default_storage.exists")
    @patch("django.core.files.storage.default_storage.delete")
    def test_cleanup_delete_error(self, mock_delete, mock_exists):
        """Test cleanup continues despite individual file errors."""
        mock_exists.return_value = True
        mock_delete.side_effect = Exception("Delete failed")

        ExportReport.objects.create(
            session=self.session,
            generated_by=self.user,
            title="Another Expired",
            status="completed",
            file_path="reports/another.pdf",
            file_size_bytes=512,
            expires_at=timezone.now() - timedelta(hours=1),
        )

        result = cleanup_expired_reports()

        # When file deletion fails, the exception is caught but cleaned_count
        # does not increment (mark_as_expired is never reached)
        self.assertEqual(result["cleaned_count"], 0)

    def test_cleanup_no_expired_reports(self):
        """Test cleanup when no expired reports exist."""
        self.expired_report.delete()

        result = cleanup_expired_reports()

        self.assertEqual(result["cleaned_count"], 0)
        self.assertEqual(result["freed_space"], 0)

    @patch("apps.reporting.models.ExportReport.objects.filter")
    def test_cleanup_task_error(self, mock_filter):
        """Test cleanup triggers retry on transient error."""
        mock_filter.side_effect = Exception("Database error")

        with patch.object(
            cleanup_expired_reports, "retry", side_effect=Retry()
        ) as mock_retry:
            with self.assertRaises(Retry):
                cleanup_expired_reports()

            mock_retry.assert_called_once()
            call_kwargs = mock_retry.call_args[1]
            self.assertEqual(call_kwargs["countdown"], RETRY_BACKOFF_BASE)


class GenerateComprehensiveReportDataTest(TestCase):
    """Test comprehensive report data generation."""

    def setUp(self):
        """Create test data."""
        self.user = create_test_user(username_prefix="test@example.com")
        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.user,
        )

        self.result1 = ProcessedResult.objects.create(
            session=self.session,
            title="Result 1",
        )
        self.result2 = ProcessedResult.objects.create(
            session=self.session,
            title="Result 2",
        )

    @patch("apps.reporting.tasks.PrismaReportingService")
    @patch("apps.reporting.tasks.PerformanceAnalyticsService")
    @patch("apps.reporting.tasks.SearchResultAnalysisService")
    @patch("apps.reporting.tasks.SearchStrategyReportingService")
    def test_comprehensive_data_generation(
        self, mock_strategy, mock_result, mock_perf, mock_prisma
    ):
        """Test generation of comprehensive report data."""
        mock_prisma_instance = Mock()
        mock_prisma_instance.generate_prisma_flow_data.return_value = {"flow": "data"}
        mock_prisma_instance.generate_checklist_data.return_value = {
            "checklist": "data"
        }
        mock_prisma_instance.analyze_exclusion_reasons.return_value = {
            "exclusions": "data"
        }
        mock_prisma_instance.get_irr_metrics.return_value = {}
        mock_prisma_instance.get_conflict_summary.return_value = {}
        mock_prisma_instance.get_configuration_changes.return_value = []
        mock_prisma.return_value = mock_prisma_instance

        mock_perf_instance = Mock()
        mock_perf_instance.calculate_search_performance_metrics.return_value = {
            "metrics": "data"
        }
        mock_perf_instance.generate_execution_timeline.return_value = {
            "timeline": "data"
        }
        mock_perf.return_value = mock_perf_instance

        mock_result_instance = Mock()
        mock_result_instance.calculate_result_statistics.return_value = {
            "total_results": 2,
            "results_included": 1,
            "results_excluded": 1,
            "results_pending": 0,
            "duplicates_removed": 1,
            "completion_percentage": 100,
        }
        mock_result_instance.analyze_quality_distribution.return_value = {
            "quality": "data"
        }
        mock_result.return_value = mock_result_instance

        mock_strategy_instance = Mock()
        mock_strategy_instance.analyze_search_strategy.return_value = {
            "strategy": "data"
        }
        mock_strategy_instance.calculate_query_effectiveness.return_value = {
            "effectiveness": "data"
        }
        mock_strategy.return_value = mock_strategy_instance

        data = generate_comprehensive_report_data(str(self.session.id))

        self.assertIn("session", data)
        self.assertIn("generated_at", data)
        self.assertIn("prisma_flow", data)
        self.assertIn("prisma_checklist", data)
        self.assertIn("search_strategy", data)
        self.assertIn("query_effectiveness", data)
        self.assertIn("result_statistics", data)
        self.assertIn("quality_distribution", data)
        self.assertIn("exclusion_analysis", data)
        self.assertIn("performance_metrics", data)
        self.assertIn("execution_timeline", data)
        self.assertIn("summary", data)

        summary = data["summary"]
        self.assertEqual(summary["total_results"], 2)
        self.assertEqual(summary["included_results"], 1)
        self.assertEqual(summary["excluded_results"], 1)
        self.assertEqual(summary["duplicate_count"], 1)
        self.assertEqual(summary["review_completion"], 100)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class GenerateBulkReportsTest(TestCase):
    """Test bulk report generation."""

    def setUp(self):
        """Create test data."""
        self.user = create_test_user(username_prefix="test@example.com")
        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.user,
        )

    @patch("apps.reporting.tasks.generate_report_task.delay")
    def test_bulk_report_generation(self, mock_generate):
        """Test generating multiple reports at once."""
        report_types = ["prisma_flow", "full_report", "search_strategy"]

        result = generate_bulk_reports(str(self.session.id), report_types, "pdf")

        self.assertEqual(result["status"], "queued")
        self.assertEqual(len(result["report_ids"]), 3)

        reports = ExportReport.objects.filter(session=self.session)
        self.assertEqual(reports.count(), 3)

        report_types_created = set(reports.values_list("report_type", flat=True))
        self.assertEqual(report_types_created, set(report_types))

        for report in reports:
            self.assertTrue(report.parameters.get("bulk"))

        self.assertEqual(mock_generate.call_count, 3)

    def test_bulk_generation_invalid_session(self):
        """Test bulk generation with invalid session."""
        result = generate_bulk_reports(str(uuid4()), ["full_report"], "pdf")

        self.assertEqual(result["status"], "failed")
        self.assertIn("error", result)

    @patch("apps.reporting.tasks.generate_report_task.delay")
    def test_bulk_generation_error_handling(self, mock_generate):
        """Test bulk generation triggers retry on transient error."""
        mock_generate.side_effect = Exception("Task queue error")

        with patch.object(
            generate_bulk_reports, "retry", side_effect=Retry()
        ) as mock_retry:
            with self.assertRaises(Retry):
                generate_bulk_reports(str(self.session.id), ["full_report"], "pdf")

            mock_retry.assert_called_once()


class RetryHelperTests(TestCase):
    """Test retry helper functions."""

    def test_is_retryable_error_returns_true_for_transient_errors(self):
        """Transient errors (ConnectionError, OSError, RuntimeError) are retryable."""
        self.assertTrue(_is_retryable_error(ConnectionError("lost")))
        self.assertTrue(_is_retryable_error(OSError("disk")))
        self.assertTrue(_is_retryable_error(RuntimeError("fail")))
        self.assertTrue(_is_retryable_error(Exception("generic")))

    def test_is_retryable_error_returns_false_for_permanent_errors(self):
        """Permanent errors (ValueError, TypeError, ImportError, DoesNotExist) are not retryable."""
        self.assertFalse(_is_retryable_error(ValueError("bad input")))
        self.assertFalse(_is_retryable_error(TypeError("wrong type")))
        self.assertFalse(_is_retryable_error(ImportError("missing")))
        self.assertFalse(_is_retryable_error(ExportReport.DoesNotExist("not found")))

    def test_get_retry_countdown_exponential_backoff(self):
        """Countdown doubles with each retry: 60, 120, 240."""
        self.assertEqual(_get_retry_countdown(0), RETRY_BACKOFF_BASE)
        self.assertEqual(_get_retry_countdown(1), RETRY_BACKOFF_BASE * 2)
        self.assertEqual(_get_retry_countdown(2), RETRY_BACKOFF_BASE * 4)


class TaskDecoratorConfigTests(TestCase):
    """Test that task decorators have consistent retry configuration."""

    def test_generate_report_task_config(self):
        """generate_report_task has bind=True and max_retries."""
        self.assertEqual(generate_report_task.max_retries, MAX_RETRIES)

    def test_send_report_ready_notification_config(self):
        """send_report_ready_notification has bind=True and max_retries."""
        self.assertEqual(send_report_ready_notification.max_retries, MAX_RETRIES)

    def test_cleanup_expired_reports_config(self):
        """cleanup_expired_reports has bind=True and max_retries=2."""
        self.assertEqual(cleanup_expired_reports.max_retries, 2)

    def test_generate_bulk_reports_config(self):
        """generate_bulk_reports has bind=True and max_retries=2."""
        self.assertEqual(generate_bulk_reports.max_retries, 2)

    def test_import_excel_backup_task_config(self):
        """import_excel_backup_task has bind=True and max_retries=2."""
        self.assertEqual(import_excel_backup_task.max_retries, 2)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class GenerateReportTaskRetryTest(TestCase):
    """Test retry behaviour for generate_report_task."""

    def setUp(self):
        self.user = create_test_user(username_prefix="retry_report")
        self.session = SearchSession.objects.create(
            title="Retry Test Session",
            description="Testing retry logic",
            owner=self.user,
            status="completed",
        )
        self.report = ExportReport.objects.create(
            session=self.session,
            generated_by=self.user,
            report_type="full_report",
            export_format="pdf",
            title="Retry Test Report",
            status="pending",
            file_size_bytes=0,
        )

    @patch(
        "apps.reporting.services.report_generators.factory.ReportGeneratorFactory.create"
    )
    def test_retries_on_transient_error_with_backoff(self, mock_factory):
        """Task calls retry with exponential backoff on transient error."""
        mock_generator = Mock()
        mock_generator.generate.side_effect = ConnectionError("transient")
        mock_factory.return_value = mock_generator

        with patch.object(
            generate_report_task, "retry", side_effect=Retry()
        ) as mock_retry:
            with self.assertRaises(Retry):
                generate_report_task(str(self.report.id))  # type: ignore[call-arg]

            mock_retry.assert_called_once()
            call_kwargs = mock_retry.call_args[1]
            self.assertIsInstance(call_kwargs["exc"], ConnectionError)
            self.assertEqual(call_kwargs["countdown"], RETRY_BACKOFF_BASE)

    def test_no_retry_on_value_error(self):
        """Task does not retry on ValueError (non-retryable)."""
        self.report.report_type = "invalid_type"
        self.report.save()

        result = generate_report_task(str(self.report.id))  # type: ignore[call-arg]

        self.assertEqual(result["status"], "failed")
        self.assertIn("Unknown report type", result["error"])

    def test_no_retry_on_does_not_exist(self):
        """Task does not retry on DoesNotExist (non-retryable)."""
        fake_id = str(uuid4())

        result = generate_report_task(fake_id)  # type: ignore[call-arg]

        self.assertEqual(result["status"], "failed")

    @patch("apps.reporting.tasks.MAX_RETRIES", 0)
    @patch(
        "apps.reporting.services.report_generators.factory.ReportGeneratorFactory.create"
    )
    def test_returns_failure_when_retries_exhausted(self, mock_factory):
        """Task returns failure dict when max retries reached."""
        mock_generator = Mock()
        mock_generator.generate.side_effect = ConnectionError("persistent")
        mock_factory.return_value = mock_generator

        result = generate_report_task(str(self.report.id))  # type: ignore[call-arg]

        self.assertEqual(result["status"], "failed")
        self.assertIn("persistent", result["error"])


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@agentgrey.test",
    SITE_DOMAIN="localhost:8000",
)
class SendNotificationRetryTest(TestCase):
    """Test retry behaviour for send_report_ready_notification."""

    def setUp(self):
        self.user = create_test_user(username_prefix="notify_retry")
        self.session = SearchSession.objects.create(
            title="Notify Test", owner=self.user
        )
        self.report = ExportReport.objects.create(
            session=self.session,
            generated_by=self.user,
            title="Notify Report",
            report_type="full_report",
            export_format="pdf",
            file_size_bytes=1024,
            status="completed",
        )

    @patch(
        "apps.reporting.services.email_service.ReportEmailService.send_report_ready_notification"
    )
    def test_retries_on_smtp_error_with_backoff(self, mock_send):
        """Task calls retry with exponential backoff on email failure."""
        mock_send.side_effect = ConnectionError("SMTP down")

        with patch.object(
            send_report_ready_notification, "retry", side_effect=Retry()
        ) as mock_retry:
            with self.assertRaises(Retry):
                send_report_ready_notification(str(self.report.id))

            mock_retry.assert_called_once()
            call_kwargs = mock_retry.call_args[1]
            self.assertIsInstance(call_kwargs["exc"], ConnectionError)
            self.assertEqual(call_kwargs["countdown"], RETRY_BACKOFF_BASE)

    @patch(
        "apps.reporting.services.email_service.ReportEmailService.send_report_ready_notification"
    )
    def test_returns_false_when_retries_exhausted(self, mock_send):
        """Task returns False when max retries exceeded."""
        mock_send.side_effect = ConnectionError("persistent SMTP failure")

        with patch("apps.reporting.tasks.MAX_RETRIES", 0):
            result = send_report_ready_notification(str(self.report.id))

            self.assertFalse(result)

    def test_no_retry_on_report_not_found(self):
        """DoesNotExist is not retried."""
        result = send_report_ready_notification(str(uuid4()))

        self.assertFalse(result)
