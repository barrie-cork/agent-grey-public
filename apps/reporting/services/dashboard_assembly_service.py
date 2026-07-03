"""Assembly of the reporting dashboard context.

Extracts the heavier data-gathering that previously lived inline in
``ReportDashboardView.get_context_data``: building the PRISMA flow data (with
caching and a basic-stats fallback) and the PRISMA "other methods" form
context. Keeping it here keeps the view thin and the fallback logic in one
place.
"""

import logging

from django.core.cache import cache
from django.db import DatabaseError

from apps.reporting.forms import PrismaOtherMethodsForm
from apps.reporting.services.prisma_reporting_service import PrismaReportingService

logger = logging.getLogger(__name__)

# PRISMA flow data is cached per session for 10 minutes.
PRISMA_FLOW_CACHE_TIMEOUT = 600


def _default_prisma_flow_data() -> dict:
    """Return the zeroed default PRISMA flow structure used as a fallback."""
    return {
        "raw_search_results": 0,
        "duplicates_removed": 0,
        "results_included": 0,
        "results_excluded": 0,
        "results_maybe": 0,
        "processed_results": 0,
        "results_pending": 0,
        "identification": {
            "websites": 0,
            "organizations": 0,
            "citation_searching": 0,
            "total": 0,
        },
        "retrieval": {
            "reports_sought": 0,
            "reports_not_retrieved": 0,
            "reports_retrieved": 0,
        },
        "eligibility": {
            "reports_assessed": 0,
            "excluded": 0,
            "exclusion_reasons": {},
        },
        "included": {"total": 0},
        "summary": {"retrieval_rate": 0},
    }


def _apply_basic_stats_fallback(session, prisma_flow_data: dict) -> None:
    """Populate ``prisma_flow_data`` in place with basic counts.

    Shared fallback used when the PRISMA service is unavailable or errors. It
    pulls the processed-result count and review progress stats directly so the
    dashboard still shows real numbers rather than all zeros.
    """
    session_id = str(session.id)
    try:
        from apps.results_manager.models import ProcessedResult
        from apps.review_results.api import get_review_progress_stats

        total_results = ProcessedResult.objects.filter(session=session).count()
        review_stats = get_review_progress_stats(session_id)

        prisma_flow_data.update(
            {
                "raw_search_results": total_results,
                "processed_results": total_results,
                "results_included": review_stats.get("included_results", 0),
                "results_excluded": review_stats.get("excluded_results", 0),
                "results_maybe": review_stats.get("maybe_results", 0),
                "results_pending": review_stats.get("pending_results", total_results),
            }
        )
        prisma_flow_data["identification"]["total"] = total_results
        prisma_flow_data["identification"]["websites"] = total_results

        logger.info(
            "Using fallback PRISMA data for session %s: %s total results",
            session_id,
            total_results,
        )
    except (DatabaseError, ImportError, KeyError, AttributeError) as fallback_error:
        logger.error(
            "Failed to get even basic stats for session %s: %s",
            session_id,
            fallback_error,
        )


class ReportDashboardAssemblyService:
    """Builds the data-heavy parts of the reporting dashboard context."""

    def get_prisma_flow_data(self, session) -> dict:
        """Return PRISMA flow data for the session (cached, with fallback)."""
        session_id = str(session.id)
        prisma_flow_data = _default_prisma_flow_data()

        try:
            cache_key = f"prisma_flow:{session_id}"
            cached_data = cache.get(cache_key)

            if cached_data is None:
                prisma_service = PrismaReportingService()
                generated_data = prisma_service.generate_prisma_flow_data(session_id)

                if generated_data and isinstance(generated_data, dict):
                    prisma_flow_data.update(generated_data)
                    logger.info(
                        "Successfully generated PRISMA data for session %s: %s fields",
                        session_id,
                        len(generated_data),
                    )
                else:
                    logger.warning(
                        "PrismaReportingService returned invalid data for session %s: %s",
                        session_id,
                        type(generated_data),
                    )

                cache.set(cache_key, prisma_flow_data, PRISMA_FLOW_CACHE_TIMEOUT)
            else:
                prisma_flow_data = cached_data
        except ImportError as e:
            logger.error(
                "Import error in PRISMA flow generation for session %s: %s",
                session_id,
                e,
                exc_info=True,
            )
            _apply_basic_stats_fallback(session, prisma_flow_data)
        except (DatabaseError, ValueError, KeyError, AttributeError) as e:
            logger.error(
                "Error generating PRISMA flow data for session %s: %s",
                session_id,
                e,
                exc_info=True,
            )
            _apply_basic_stats_fallback(session, prisma_flow_data)

        return prisma_flow_data

    def get_other_methods_context(self, session) -> dict:
        """Return the PRISMA 'other methods' form context for the session."""
        session_id = str(session.id)
        try:
            prisma_service = PrismaReportingService()
            other_methods_auto = prisma_service.auto_populate_other_methods(session_id)
            exclusion_reasons = prisma_service.get_exclusion_reasons(session_id)

            # Saved overrides take precedence over auto-populated defaults.
            saved = session.prisma_other_methods or {}
            form_initial = {**other_methods_auto}
            for key in PrismaOtherMethodsForm.base_fields:
                if key in saved:
                    form_initial[key] = saved[key]

            return {
                "other_methods_form": PrismaOtherMethodsForm(initial=form_initial),
                "has_other_methods": bool(saved),
                "other_methods_auto": other_methods_auto,
                "exclusion_reasons": exclusion_reasons,
            }
        except (DatabaseError, ValueError, KeyError, AttributeError) as e:
            logger.warning(
                "Failed to load other methods context for session %s: %s",
                session_id,
                e,
                exc_info=True,
            )
            return {
                "other_methods_form": PrismaOtherMethodsForm(),
                "has_other_methods": False,
                "other_methods_auto": {},
                "exclusion_reasons": {},
            }
