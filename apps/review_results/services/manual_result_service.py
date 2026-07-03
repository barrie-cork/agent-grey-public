"""
Service for manually adding results discovered during screening.

Handles provenance tracking, workflow configuration, and reviewer
completion updates when a reviewer adds a result they found while
browsing source URLs.
"""

import logging
from typing import TYPE_CHECKING

from django.db.models import F
from django.utils.dateparse import parse_date

from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SessionActivity
from apps.review_results.models import ReviewerCompletion

if TYPE_CHECKING:
    from datetime import date

    from django.contrib.auth.models import AbstractUser

    from apps.review_manager.models import SearchSession

logger = logging.getLogger(__name__)


class ManualResultService:
    """Service for adding manually discovered results to a review session."""

    ALLOWED_STATES = ("ready_for_review", "under_review")

    @staticmethod
    def add_manual_result(
        session: "SearchSession",
        user: "AbstractUser",
        url: str,
        title: str,
        justification: str,
        snippet: str = "",
        metadata: "dict | None" = None,
    ) -> ProcessedResult:
        """
        Add a manually discovered result to a session's screening queue.

        Args:
            session: The review session to add the result to.
            user: The reviewer who discovered the result.
            url: URL of the discovered resource.
            title: Title of the resource.
            justification: Why this result was added during screening.
            snippet: Optional description/snippet.
            metadata: Optional dict from browser-extension capture with keys
                ``author``, ``published_date`` (ISO string or date),
                ``publisher``, and ``document_type``.

        Returns:
            The created ProcessedResult.

        Raises:
            ValueError: If session is in wrong state or URL is a duplicate.
        """
        if session.status not in ManualResultService.ALLOWED_STATES:
            raise ValueError(
                f"Cannot add results when session is in '{session.status}' state. "
                f"Session must be in 'ready_for_review' or 'under_review'."
            )

        if ProcessedResult.objects.filter(session=session, url=url).exists():
            raise ValueError("A result with this URL already exists in this session.")

        config = session.current_configuration
        review_mode, min_reviewers = (
            config.review_mode_defaults if config else ("SINGLE", 1)
        )

        result = ProcessedResult.objects.create(
            session=session,
            title=title,
            url=url,
            snippet=snippet,
            raw_result=None,
            is_manually_added=True,
            manually_added_by=user,
            manual_addition_justification=justification,
            processing_status="success",
            review_mode=review_mode,
            min_reviewers_required=min_reviewers,
            execution_round=0,
        )

        if metadata:
            ManualResultService._apply_metadata(result, metadata)

        SessionActivity.log_activity(
            session=session,
            activity_type="manual_result_added",
            description=f"{user.username} manually added result: {title[:80]}",
            user=user,
            metadata={
                "result_id": str(result.pk),
                "url": url,
                "justification": justification,
            },
        )

        # Update reviewer completion counts for WF2 (any reviewer count >= 2)
        if config and config.is_workflow_2:
            updated = ReviewerCompletion.objects.filter(session=session).update(
                total_results=F("total_results") + 1
            )
            if updated:
                logger.debug(
                    "Incremented total_results for %d ReviewerCompletion records",
                    updated,
                )

        logger.info(
            "Manual result added to session %s by %s: %s",
            session.pk,
            user.username,
            url,
        )

        return result

    @staticmethod
    def _apply_metadata(result: ProcessedResult, metadata: dict) -> None:
        """Persist browser-captured metadata fields on a ProcessedResult."""
        update_fields: list[str] = []

        if author := metadata.get("author"):
            result.authors = [author]
            update_fields.append("authors")

        if raw_date := metadata.get("published_date"):
            parsed: "date | None" = (
                parse_date(raw_date) if isinstance(raw_date, str) else raw_date
            )
            if parsed:
                result.publication_date = parsed
                result.publication_year = parsed.year
                update_fields.extend(["publication_date", "publication_year"])

        if publisher := metadata.get("publisher"):
            result.source_organization = publisher
            update_fields.append("source_organization")

        if doc_type := metadata.get("document_type"):
            result.document_type = doc_type
            update_fields.append("document_type")

        if update_fields:
            result.save(update_fields=update_fields)
