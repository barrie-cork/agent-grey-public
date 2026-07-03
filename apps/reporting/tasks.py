"""
Celery tasks for the reporting app.

This module implements background tasks for report generation,
notifications, and maintenance operations.
"""

import logging
import tempfile
from datetime import timedelta
from typing import Tuple

from celery import shared_task
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models import Count
from django.template.loader import render_to_string
from django.utils import timezone

from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.review_results.models import SimpleReviewDecision

from .constants import PRISMAConstants
from .models import ExportReport
from .services.email_service import ReportEmailService
from .services.performance_analytics_service import PerformanceAnalyticsService
from .services.prisma_reporting_service import PrismaReportingService
from .services.result_analysis_service import SearchResultAnalysisService
from .services.search_strategy_reporting_service import SearchStrategyReportingService

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 60  # seconds


def _is_retryable_error(exc: Exception) -> bool:
    """Determine if an exception is transient and worth retrying."""
    from django.core.exceptions import ObjectDoesNotExist

    non_retryable = (ValueError, TypeError, ImportError, ObjectDoesNotExist)
    return not isinstance(exc, non_retryable)


def _get_retry_countdown(retries: int) -> int:
    """Calculate exponential backoff delay: 60s, 120s, 240s."""
    return RETRY_BACKOFF_BASE * (2**retries)


# WeasyPrint import - ensure it's installed via: pip install weasyprint
try:
    from weasyprint import HTML

    WEASYPRINT_AVAILABLE = True
except ImportError:
    HTML = None
    WEASYPRINT_AVAILABLE = False
    logger.warning(
        "WeasyPrint not installed - PDF generation will not be available. "
        "Install with: pip install weasyprint"
    )


@shared_task(bind=True, max_retries=MAX_RETRIES)
def generate_report_task(self, report_id):
    """
    Generate a report in the background.

    Args:
        self: Celery task instance for state updates and progress tracking.
        report_id: UUID string of the ExportReport instance to generate.

    Returns:
        dict: Status information with keys for 'status' (str),
            'file_path' (str), 'file_size' (int), and optional 'error' (str).
    """

    def _safe_update_state(current: int) -> None:
        """Update task progress state, ignoring broker errors."""
        try:
            self.update_state(state="PROGRESS", meta={"current": current, "total": 100})
        except Exception as e:
            logger.debug(f"Could not update task progress state: {e}")

    try:
        # Initialize report
        report = _initialize_report(report_id)
        _safe_update_state(10)

        # Gather report data
        data, template = _gather_report_data(report)
        _safe_update_state(40)

        # Generate file content
        file_content, file_name = _generate_file_content(report, data, template)
        _safe_update_state(70)

        # Save and finalize report
        result = _save_report_file(report, file_content, file_name)
        _finalize_report(report, data)
        _safe_update_state(100)

        # Send notification (non-critical)
        try:
            send_report_ready_notification.delay(str(report.id))
        except Exception as notify_err:
            logger.warning(f"Failed to send report notification: {notify_err}")

        logger.info(f"Report generated successfully: {report.id}")
        return result

    except Exception as e:
        if _is_retryable_error(e) and self.request.retries < MAX_RETRIES:
            logger.warning(
                f"Report generation failed for {report_id}, retrying "
                f"(attempt {self.request.retries + 1}/{MAX_RETRIES}): {e}"
            )
            raise self.retry(
                exc=e, countdown=_get_retry_countdown(self.request.retries)
            )
        return _handle_report_failure(report_id, e)


def _initialize_report(report_id: str):
    """
    Initialize and validate report for generation.

    Args:
        report_id: UUID string of the ExportReport instance to initialize.

    Returns:
        ExportReport: The initialized report instance with related data.

    Raises:
        ExportReport.DoesNotExist: If report with given ID doesn't exist.
    """
    from .services.status_manager import ReportStatusManager

    report = ExportReport.objects.select_related("session", "generated_by").get(
        id=report_id
    )
    ReportStatusManager.mark_as_started(report)
    return report


def _gather_report_data(report):
    """
    Gather data based on report type using service layer pattern.

    Args:
        report: ExportReport instance containing session and type information.

    Returns:
        tuple: Two-element tuple containing:
            - dict: Report data specific to the report type
            - str: Template path for rendering the report

    Raises:
        ValueError: If report type is not recognized.
    """
    session = report.session

    if report.report_type == "prisma_flow":
        service = PrismaReportingService()
        data = service.generate_prisma_flow_data(str(session.id))
        template = "reporting/exports/prisma_flow.html"

    elif report.report_type == "full_report":
        data = generate_comprehensive_report_data(session.id)
        template = "reporting/exports/full_report.html"

    elif report.report_type == "search_strategy":
        service = SearchStrategyReportingService()
        data = {
            "session": session,
            "analysis": service.analyze_search_strategy(str(session.id)),
            "effectiveness": service.calculate_query_effectiveness(str(session.id)),
        }
        template = "reporting/exports/search_strategy.html"

    elif report.report_type == "results_summary":
        service = SearchResultAnalysisService()
        data = {
            "session": session,
            "statistics": service.calculate_result_statistics(str(session.id)),
            "quality_distribution": service.analyze_quality_distribution(
                str(session.id)
            ),
        }
        template = "reporting/exports/results_summary.html"

    elif report.report_type == "bibliography":
        included_results = ProcessedResult.objects.filter(
            session=session, simplereviewdecision__decision="include"
        ).distinct()
        data = {
            "session": session,
            "results": included_results,
        }
        template = "reporting/exports/bibliography.html"

    elif report.report_type == "offline_backup":
        # Offline backup Excel export - minimal data needed as generator handles data collection
        data = {
            "session_id": str(session.id),
            "session": session,
        }
        template = None  # Excel generator doesn't use HTML templates

    else:
        raise ValueError(f"Unknown report type: {report.report_type}")

    # Update progress
    from .services.status_manager import ReportStatusManager

    ReportStatusManager.update_progress(report, 50)

    return data, template


def _generate_file_content(report, data, template) -> Tuple[ContentFile, str]:
    """
    Generate file content based on export format using the strategy pattern.

    Args:
        report: ExportReport instance with format and metadata.
        data: Dictionary containing report data from service layers.
        template: String path to the HTML template for rendering.

    Returns:
        tuple: Two-element tuple containing:
            - ContentFile: Generated file content ready for storage
            - str: Generated filename with appropriate extension

    Raises:
        ValueError: If export format is not supported.
        ImportError: If required libraries for format are missing.
    """
    from .services.report_generators.factory import ReportGeneratorFactory

    try:
        logger.info(
            f"Starting content generation for report {report.id}: "
            f"{report.report_type} in {report.export_format} format"
        )

        # Create appropriate generator
        generator = ReportGeneratorFactory.create(report.export_format)
        logger.info(f"Created {generator.__class__.__name__} for report {report.id}")

        # Generate content
        content_bytes = generator.generate(report, data)
        file_content = ContentFile(content_bytes)

        logger.info(
            f"Successfully generated {len(content_bytes)} bytes of content for report {report.id}"
        )

        # Generate filename
        file_name = f"{report.report_type}_{report.id}.{generator.get_file_extension()}"

        # Update progress
        from .services.status_manager import ReportStatusManager

        ReportStatusManager.update_progress(report, 80)

        return file_content, file_name

    except Exception as e:
        logger.error(f"Content generation failed for report {report.id}: {str(e)}")
        logger.error(
            f"Report details: type={report.report_type}, "
            f"format={report.export_format}, session={report.session.id}"
        )
        raise


def _generate_pdf_content(template, data, report) -> ContentFile:
    """
    Generate PDF content using WeasyPrint library.

    Args:
        template: String path to the HTML template for PDF generation.
        data: Dictionary containing report data for template rendering.
        report: ExportReport instance with metadata for the PDF.

    Returns:
        ContentFile: Generated PDF content wrapped in Django ContentFile.

    Raises:
        ImportError: If WeasyPrint library is not installed.
    """
    if HTML is None:
        raise ImportError(
            "WeasyPrint is required for PDF generation. Install with: pip install weasyprint"
        )

    html_content = render_to_string(
        template,
        {
            "data": data,
            "report": report,
            "generated_at": timezone.now(),
        },
    )

    # Write PDF to temporary file to avoid holding entire PDF in memory
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
        HTML(string=html_content).write_pdf(target=tmp.name)
        del html_content  # Free HTML string memory before reading PDF
        tmp.seek(0)
        return ContentFile(tmp.read())


def _save_report_file(report, file_content, file_name) -> dict:
    """
    Save report file to storage and update database metadata.

    Args:
        report: ExportReport instance to update with file information.
        file_content: ContentFile containing the generated report content.
        file_name: String filename for the saved file.

    Returns:
        dict: Status information with keys for 'status' (str),
            'file_path' (str), and 'file_size' (int).

    Raises:
        Exception: If file cannot be saved or validated.
    """
    from .services.status_manager import ReportStatusManager

    # Use Django's FileField.save() which automatically uses report_upload_path() function
    # This ensures consistent path generation between model definition and file save
    logger.info(
        f"Saving report file for report {report.id}: "
        f"filename={file_name}, size={file_content.size} bytes"
    )

    # FileField.save() automatically handles path generation via upload_to function
    report.file_path.save(file_name, file_content, save=False)
    saved_path = report.file_path.name  # Get the generated path

    logger.info(f"File saved to storage: {saved_path}")

    # Verify file was actually saved before marking as completed
    if not default_storage.exists(saved_path):
        logger.error(
            f"File validation failed: {saved_path} was not found after save for report {report.id}"
        )
        raise Exception(f"Report file could not be saved to storage: {saved_path}")

    # Verify file size matches expected size
    actual_size = default_storage.size(saved_path)
    expected_size = file_content.size
    if actual_size != expected_size:
        logger.warning(
            f"File size mismatch for report {report.id}: "
            f"expected {expected_size}, got {actual_size}"
        )

    logger.info(
        f"Successfully saved report file: {saved_path} ({actual_size} bytes) for report {report.id}"
    )

    # Update report metadata
    report.file_name = file_name
    report.file_size_bytes = actual_size  # Use actual size from storage
    report.expires_at = timezone.now() + timedelta(
        days=PRISMAConstants.REPORT_EXPIRATION_DAYS
    )

    # Save with file_path included (already set by FileField.save above)
    report.save(
        update_fields=["file_path", "file_name", "file_size_bytes", "expires_at"]
    )

    # Mark as completed using status manager only after successful validation
    ReportStatusManager.mark_as_completed(report)

    return {"status": "completed", "file_path": saved_path, "file_size": actual_size}


def _finalize_report(report, data) -> None:
    """
    Update report statistics from generated data.

    Args:
        report: ExportReport instance to update with final statistics.
        data: Dictionary containing report data with statistics to extract.

    Returns:
        None: Updates report instance in-place and saves to database.
    """
    if isinstance(data, dict):
        report.total_results = data.get("total_results", 0)
        report.included_results = data.get("included_results", 0)
        report.excluded_results = data.get("excluded_results", 0)
        report.maybe_results = data.get("maybe_results", 0)
        report.save(
            update_fields=[
                "total_results",
                "included_results",
                "excluded_results",
                "maybe_results",
            ]
        )


def _handle_report_failure(report_id, error) -> dict:
    """
    Handle report generation failure with proper error logging and status updates.

    Args:
        report_id: UUID string of the failed ExportReport instance.
        error: Exception instance that caused the failure.

    Returns:
        dict: Error status with keys for 'status' (str) and 'error' (str).
    """
    from .services.status_manager import ReportStatusManager

    logger.error(f"Report generation failed for {report_id}: {str(error)}")

    try:
        # Defensive check - only update if report exists
        if ExportReport.objects.filter(id=report_id).exists():
            report = ExportReport.objects.get(id=report_id)
            ReportStatusManager.mark_as_failed(report, str(error))
        else:
            logger.warning(
                f"Report {report_id} not found - may have been deleted or never created"
            )
    except Exception as e:
        logger.exception(f"Failed to update report status for {report_id}: {e}")

    return {"status": "failed", "error": str(error)}


@shared_task(bind=True, max_retries=MAX_RETRIES)
def send_report_ready_notification(self, report_id):
    """
    Send notification when report is ready for download.

    Args:
        report_id: UUID string of the ExportReport instance that is ready.

    Returns:
        bool: True if notification sent successfully, False otherwise.
    """
    try:
        report = ExportReport.objects.select_related("generated_by", "session").get(
            id=report_id
        )

        service = ReportEmailService()
        sent = service.send_report_ready_notification(report)

        if sent:
            logger.info(
                f"Report ready email sent to {report.generated_by.email}: "
                f"{report.title}"
            )
        else:
            logger.warning(f"Report ready email failed for {report_id}: {report.title}")

        return sent

    except ExportReport.DoesNotExist:
        logger.error(f"Report {report_id} not found for notification")
        return False
    except Exception as e:
        logger.error(f"Failed to send notification for {report_id}: {str(e)}")
        if self.request.retries < MAX_RETRIES:
            raise self.retry(
                exc=e, countdown=_get_retry_countdown(self.request.retries)
            )
        return False


@shared_task(bind=True, max_retries=2)
def cleanup_expired_reports(self):
    """
    Clean up expired report files from storage.

    This task should be run periodically (e.g., daily) to remove
    old report files and free up storage space. Processes completed
    reports that have passed their expiration date.

    Returns:
        dict: Cleanup statistics with keys for 'cleaned_count' (int),
            'freed_space' (int bytes), and optional 'error' (str).
    """
    try:
        now = timezone.now()
        expired_reports = ExportReport.objects.filter(
            expires_at__lt=now, status="completed"
        ).iterator(chunk_size=100)

        cleaned_count = 0
        freed_space = 0

        for report in expired_reports:
            try:
                # Delete file if it exists
                if report.file_path and default_storage.exists(report.file_path):
                    default_storage.delete(report.file_path)
                    freed_space += report.file_size_bytes or 0

                # Update report using status manager
                from .services.status_manager import ReportStatusManager

                ReportStatusManager.mark_as_expired(report)

                cleaned_count += 1

            except Exception as e:
                logger.error(f"Failed to cleanup report {report.id}: {str(e)}")

        logger.info(
            f"Cleaned up {cleaned_count} expired reports, freed {freed_space} bytes"
        )

        return {"cleaned_count": cleaned_count, "freed_space": freed_space}

    except Exception as e:
        logger.error(f"Report cleanup task failed: {str(e)}")
        if self.request.retries < 2:
            raise self.retry(
                exc=e, countdown=_get_retry_countdown(self.request.retries)
            )
        return {"error": str(e)}


def generate_comprehensive_report_data(session_id) -> dict:
    """
    Generate comprehensive report data for full PRISMA compliance report.

    Args:
        session_id: UUID string of the SearchSession to generate report for.

    Returns:
        dict: Complete report data containing session info, PRISMA flow data,
            search strategy analysis, results statistics, performance metrics,
            and raw query/results data with summary statistics.

    Raises:
        SearchSession.DoesNotExist: If session with given ID doesn't exist.
    """
    session = SearchSession.objects.get(id=session_id)

    data = {
        "session": session,
        "generated_at": timezone.now(),
    }

    # Gather data from different domains
    data.update(_gather_prisma_data(session_id))
    data.update(_gather_strategy_data(session_id))
    data.update(_gather_results_data(session_id))
    data.update(_gather_performance_data(session_id))
    data.update(_gather_raw_data(session))

    # Calculate summary statistics
    data["summary"] = _calculate_summary_statistics(data, session)

    return data


def _gather_prisma_data(session_id) -> dict:
    """
    Gather PRISMA-related data for systematic review reporting.

    Args:
        session_id: UUID string of the SearchSession.

    Returns:
        dict: PRISMA data with keys for 'prisma_flow' (flow diagram data),
            'prisma_checklist' (compliance checklist), 'exclusion_analysis'
            (reasons for excluding results), 'irr_metrics' (inter-rater
            reliability for dual-screening), 'conflict_summary' (conflict
            resolution statistics), and 'configuration_changes' (protocol
            deviations).
    """
    prisma_service = PrismaReportingService()
    return {
        "prisma_flow": prisma_service.generate_prisma_flow_data(session_id),
        "prisma_checklist": prisma_service.generate_checklist_data(session_id),
        "exclusion_analysis": prisma_service.analyze_exclusion_reasons(session_id),
        # Dual-screening additions for PRISMA compliance
        "irr_metrics": prisma_service.get_irr_metrics(session_id),
        "conflict_summary": prisma_service.get_conflict_summary(session_id),
        "configuration_changes": prisma_service.get_configuration_changes(session_id),
    }


def _gather_strategy_data(session_id) -> dict:
    """
    Gather search strategy analysis data including PIC framework analysis.

    Args:
        session_id: UUID string of the SearchSession.

    Returns:
        dict: Strategy data with keys for 'search_strategy' (PIC analysis)
            and 'query_effectiveness' (performance metrics per query).
    """
    strategy_service = SearchStrategyReportingService()
    return {
        "search_strategy": strategy_service.analyze_search_strategy(session_id),
        "query_effectiveness": strategy_service.calculate_query_effectiveness(
            session_id
        ),
    }


def _gather_results_data(session_id) -> dict:
    """
    Gather comprehensive results analysis data.

    Args:
        session_id: UUID string of the SearchSession.

    Returns:
        dict: Results data with keys for 'result_statistics' (counts and
            percentages) and 'quality_distribution' (quality score analysis).
    """
    result_service = SearchResultAnalysisService()
    return {
        "result_statistics": result_service.calculate_result_statistics(session_id),
        "quality_distribution": result_service.analyze_quality_distribution(session_id),
    }


def _gather_performance_data(session_id) -> dict:
    """
    Gather performance metrics and execution timeline data.

    Args:
        session_id: UUID string of the SearchSession.

    Returns:
        dict: Performance data with keys for 'performance_metrics' (API
            response times, success rates) and 'execution_timeline' (chronological
            execution sequence with timestamps).
    """
    performance_service = PerformanceAnalyticsService()
    return {
        "performance_metrics": performance_service.calculate_search_performance_metrics(
            session_id
        ),
        "execution_timeline": performance_service.generate_execution_timeline(
            session_id
        ),
    }


def _gather_raw_data(session) -> dict:
    """
    Gather raw query and results data for detailed reporting.

    Args:
        session: SearchSession instance to gather data from.

    Returns:
        dict: Raw data with keys for 'search_queries' (queries with statistics),
            'processed_results' (results with review decisions), and
            'review_decisions' (all manual review decisions).
    """
    results_with_decisions = _gather_results_with_decisions(session)
    queries_with_stats = _gather_queries_with_statistics(session)

    return {
        "search_queries": queries_with_stats,
        "processed_results": results_with_decisions,
        "review_decisions": SimpleReviewDecision.objects.filter(
            result__session=session
        ),
    }


def _gather_results_with_decisions(session) -> list:
    """
    Gather processed results with their review decisions for reporting.

    Args:
        session: SearchSession instance to gather results from.

    Returns:
        list: List of dictionaries, each containing result data merged
            with review decision information (decision, exclusion_reason, notes).
    """
    # Get processed results with prefetched review decisions
    # Since SimpleReviewDecision has OneToOneField, use select_related instead
    processed_results = (
        ProcessedResult.objects.filter(session=session)
        .select_related("simplereviewdecision")
        .iterator(chunk_size=200)
    )

    results_with_decisions = []
    for result in processed_results:
        result_data = _format_result_with_decision(result)
        results_with_decisions.append(result_data)

    return results_with_decisions


def _format_result_with_decision(result) -> dict:
    """
    Format a processed result with its review decision for reporting.

    Args:
        result: ProcessedResult instance to format.

    Returns:
        dict: Formatted result data with keys for id, title, url, snippet,
            publication_year, document_type, source_organization, review_decision,
            exclusion_reason, and review_notes.
    """
    # Get the review decision for this result
    try:
        decision = result.simplereviewdecision
    except SimpleReviewDecision.DoesNotExist:
        decision = None

    return {
        "id": result.id,
        "title": result.title,
        "url": result.url,
        "snippet": result.snippet,
        "publication_year": result.publication_year,
        "document_type": result.document_type,
        "source_organization": result.source_organization or "",
        "review_decision": decision.decision if decision else "pending",
        "exclusion_reason": decision.exclusion_reason if decision else None,
        "review_notes": decision.notes if decision else None,
    }


def _gather_queries_with_statistics(session) -> list:
    """
    Gather search queries with execution statistics and PIC framework data.

    Args:
        session: SearchSession instance to gather queries from.

    Returns:
        list: List of dictionaries, each containing query data with
            execution statistics (total_results, execution_count) and
            PIC terms (population, interest, context).
    """

    # Get PIC terms from search strategy
    pic_terms = _extract_pic_terms(session)

    queries_with_stats = []
    for query in session.search_queries_denorm.all():
        query_data = _format_query_with_statistics(query, pic_terms)
        queries_with_stats.append(query_data)

    return queries_with_stats


def _extract_pic_terms(session) -> dict:
    """
    Extract PIC (Population, Interest, Context) terms from search strategy.

    Args:
        session: SearchSession instance with associated search strategy.

    Returns:
        dict: PIC terms with keys for 'population', 'interest', and 'context',
            each containing comma-separated term strings or empty strings.
    """
    try:
        search_strategy = session.search_strategy
        return {
            "population": (
                ", ".join(search_strategy.population_terms)
                if search_strategy.population_terms
                else ""
            ),
            "interest": (
                ", ".join(search_strategy.interest_terms)
                if search_strategy.interest_terms
                else ""
            ),
            "context": (
                ", ".join(search_strategy.context_terms)
                if search_strategy.context_terms
                else ""
            ),
        }
    except Exception:
        # Fallback if no strategy exists
        return {"population": "", "interest": "", "context": ""}


def _format_query_with_statistics(query, pic_terms) -> dict:
    """
    Format a search query with its execution statistics and PIC terms.

    Args:
        query: SearchQuery instance to format.
        pic_terms: Dictionary containing PIC terms (population, interest, context).

    Returns:
        dict: Formatted query data with keys for id, query_text, target_domain,
            total_results, execution_count, and PIC terms (population, interest,
            context, is_primary).
    """
    from django.db.models import Count, Sum

    from apps.serp_execution.models import SearchExecution

    # Get execution statistics for this query
    exec_stats = SearchExecution.objects.filter(query=query).aggregate(
        total_results=Sum("results_count"), execution_count=Count("id")
    )

    return {
        "id": query.id,
        "query_text": query.query_text,
        "target_domain": query.target_domain,
        "total_results": exec_stats["total_results"] or 0,
        "execution_count": exec_stats["execution_count"] or 0,
        "population": pic_terms["population"],
        "interest": pic_terms["interest"],
        "context": pic_terms["context"],
        "is_primary": True,  # Default to True as field doesn't exist
    }


def _calculate_summary_statistics(data, session) -> dict:
    """
    Calculate summary statistics from gathered report data.

    Args:
        data: Dictionary containing all gathered report data.
        session: SearchSession instance for additional context.

    Returns:
        dict: Summary statistics with keys for total_results, included_results,
            excluded_results, pending_results, duplicate_count, and
            review_completion (percentage).
    """
    stats = data.get("result_statistics", {})
    return {
        "total_results": stats.get("total_results", 0),
        "included_results": stats.get("results_included", 0),
        "excluded_results": stats.get("results_excluded", 0),
        "pending_results": stats.get("results_pending", 0),
        "duplicate_count": stats.get("duplicates_removed", 0),
        "review_completion": stats.get("completion_percentage", 0),
    }


@shared_task(bind=True, max_retries=2)
def generate_bulk_reports(self, session_id, report_types, export_format):
    """
    Generate multiple reports for a session in parallel.

    Args:
        session_id: UUID string of the SearchSession to generate reports for.
        report_types: List of strings specifying report types to generate
            (e.g., 'prisma_flow', 'full_report', 'search_strategy').
        export_format: String format for all reports (e.g., 'html', 'pdf').

    Returns:
        dict: Status information with keys for 'status' (str),
            'report_ids' (list of UUID strings), and optional 'error' (str).
    """
    try:
        session = SearchSession.objects.get(id=session_id)
        report_ids = []

        for report_type in report_types:
            # Create report record
            report = ExportReport.objects.create(
                session=session,
                generated_by=session.owner,
                report_type=report_type,
                export_format=export_format,
                title=f"{session.title} - {report_type.replace('_', ' ').title()}",
                parameters={"bulk": True},
            )

            # Queue generation task
            generate_report_task.delay(str(report.id))
            report_ids.append(str(report.id))

        return {"status": "queued", "report_ids": report_ids}

    except Exception as e:
        logger.error(f"Bulk report generation failed: {str(e)}")
        if _is_retryable_error(e) and self.request.retries < 2:
            raise self.retry(
                exc=e, countdown=_get_retry_countdown(self.request.retries)
            )
        return {"status": "failed", "error": str(e)}


@shared_task(bind=True, max_retries=MAX_RETRIES)
def generate_irr_report_task(self, report_id):
    """
    Generate Inter-Rater Reliability (IRR) report in the background.

    Args:
        self: Celery task instance for state updates and progress tracking.
        report_id: UUID string of the ExportReport instance to generate.

    Returns:
        dict: Status information with keys for 'status' (str),
            'file_path' (str), 'file_size' (int), and optional 'error' (str).
    """
    try:
        # Initialize report
        report = _initialize_report(report_id)
        self.update_state(state="PROGRESS", meta={"current": 10, "total": 100})

        # Gather IRR data using InterRaterReliabilityService
        from apps.review_results.models import ConflictResolution, InterRaterReliability

        session = report.session

        # Get all IRR records for this session
        irr_records = (
            InterRaterReliability.objects.filter(search_session=session)
            .select_related("reviewer_a", "reviewer_b")
            .order_by("-calculated_at")
        )

        # Get conflict breakdown
        conflicts = (
            ConflictResolution.objects.filter(result__session=session)
            .values("conflict_type")
            .annotate(count=Count("id"))
        )

        conflict_breakdown = {
            conflict["conflict_type"]: conflict["count"] for conflict in conflicts
        }

        # Calculate overall session metrics if we have IRR records
        if irr_records.exists():
            # Use most recent IRR calculation
            latest_irr = irr_records.first()
            cohens_kappa = latest_irr.cohens_kappa
            percentage_agreement = latest_irr.percentage_agreement
            total_comparisons = latest_irr.total_comparisons
            agreements = latest_irr.agreements
            disagreements = latest_irr.disagreements

            # Simple confidence interval estimation (95% CI)
            # Using standard error approximation for kappa
            import math

            n = total_comparisons
            se_kappa = math.sqrt((1 - cohens_kappa**2) / n) if n > 0 else 0
            ci_lower = cohens_kappa - 1.96 * se_kappa
            ci_upper = cohens_kappa + 1.96 * se_kappa
        else:
            # No IRR data available yet
            cohens_kappa = None
            percentage_agreement = 0
            total_comparisons = 0
            agreements = 0
            disagreements = 0
            ci_lower = None
            ci_upper = None

        # Build IRR data structure
        irr_data = {
            "cohens_kappa": cohens_kappa,
            "cohens_kappa_ci_lower": ci_lower,
            "cohens_kappa_ci_upper": ci_upper,
            "percentage_agreement": percentage_agreement,
            "total_comparisons": total_comparisons,
            "agreements": agreements,
            "disagreements": disagreements,
            "conflict_breakdown": conflict_breakdown,
            "meets_cochrane_standard": cohens_kappa >= 0.70
            if cohens_kappa is not None
            else False,
            "reviewer_pairs": [
                {
                    "reviewer_a": irr.reviewer_a.username if irr.reviewer_a else "N/A",
                    "reviewer_b": irr.reviewer_b.username if irr.reviewer_b else "N/A",
                    "kappa": irr.cohens_kappa,
                    "agreement": irr.percentage_agreement,
                    "comparisons": irr.total_comparisons,
                }
                for irr in irr_records
            ],
        }

        # Add session context
        data = {
            "session": session,
            "generated_at": timezone.now(),
            **irr_data,
        }

        self.update_state(state="PROGRESS", meta={"current": 40, "total": 100})

        # Generate PDF content using IRRReportGenerator
        from .services.report_generators.irr_report_generator import IRRReportGenerator

        generator = IRRReportGenerator()
        content_bytes = generator.generate(report, data)
        file_content = ContentFile(content_bytes)

        self.update_state(state="PROGRESS", meta={"current": 70, "total": 100})

        # Save and finalize report
        file_name = f"irr_report_{report.id}.pdf"
        result = _save_report_file(report, file_content, file_name)
        self.update_state(state="PROGRESS", meta={"current": 100, "total": 100})

        # Send notification
        send_report_ready_notification.delay(str(report.id))

        logger.info(f"IRR report generated successfully: {report.id}")
        return result

    except Exception as e:
        if _is_retryable_error(e) and self.request.retries < MAX_RETRIES:
            logger.warning(
                f"IRR report generation failed for {report_id}, retrying "
                f"(attempt {self.request.retries + 1}/{MAX_RETRIES}): {e}"
            )
            raise self.retry(
                exc=e, countdown=_get_retry_countdown(self.request.retries)
            )
        return _handle_report_failure(report_id, e)


@shared_task(bind=True, max_retries=2)
def import_excel_backup_task(self, session_id, file_path, reviewer_id=None):
    """
    Import Excel backup file asynchronously.

    Args:
        self: Celery task instance for state updates
        session_id: UUID string of session to import into
        file_path: Absolute path to uploaded Excel file
        reviewer_id: User ID performing the import (optional)

    Returns:
        dict: Import summary with keys:
            - status: str ('success' or 'failed')
            - total_changes: int
            - updated: int
            - errors: int
            - error_details: list
            - error_message: str (if failed)
    """
    from django.contrib.auth import get_user_model

    from .services.excel_import_service import ExcelImportError, ExcelImportService

    try:
        logger.info(f"Starting Excel import task for session {session_id}")

        # Update task state
        self.update_state(state="PROGRESS", meta={"current": 10, "total": 100})

        # Get reviewer if ID provided
        reviewer = None
        if reviewer_id:
            User = get_user_model()
            try:
                reviewer = User.objects.get(id=reviewer_id)
            except User.DoesNotExist:
                logger.warning(
                    f"Reviewer {reviewer_id} not found, proceeding without reviewer"
                )

        # Initialize import service
        service = ExcelImportService()

        # Open file and import
        with open(file_path, "rb") as f:
            self.update_state(state="PROGRESS", meta={"current": 30, "total": 100})

            summary = service.import_excel_backup(session_id, f, reviewer=reviewer)

            self.update_state(state="PROGRESS", meta={"current": 90, "total": 100})

        # Clean up uploaded file
        try:
            import os

            os.remove(file_path)
            logger.debug(f"Cleaned up temporary file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to clean up temporary file {file_path}: {e}")

        logger.info(
            f"Excel import task completed for session {session_id}: "
            f"{summary['updated']} updated, {summary['errors']} errors"
        )

        self.update_state(state="PROGRESS", meta={"current": 100, "total": 100})

        return {"status": "success", **summary}

    except ExcelImportError as e:
        # Business logic errors are not retryable
        logger.error(f"Excel import task failed for session {session_id}: {str(e)}")
        return {
            "status": "failed",
            "error_message": str(e),
            "total_changes": 0,
            "updated": 0,
            "errors": 0,
            "error_details": [],
        }
    except Exception as e:
        logger.exception(
            f"Excel import task failed unexpectedly for session {session_id}"
        )
        if self.request.retries < 2:
            raise self.retry(
                exc=e, countdown=_get_retry_countdown(self.request.retries)
            )
        return {
            "status": "failed",
            "error_message": f"Unexpected error: {str(e)}",
            "total_changes": 0,
            "updated": 0,
            "errors": 0,
            "error_details": [],
        }
