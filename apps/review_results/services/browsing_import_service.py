"""
Service for importing JSON browsing reports into BrowsingVisit records.

Phase 0 prototype: validates and persists visit data from a JSON export,
optionally promoting flagged visits to the screening queue via ManualResultService.
"""

import logging
from dataclasses import dataclass, field
from urllib.parse import urlparse, urlunparse

from django.utils.dateparse import parse_date, parse_datetime

from apps.review_results.models import BrowsingVisit
from apps.review_results.services.manual_result_service import ManualResultService

logger = logging.getLogger(__name__)


def canonicalize_url(url: str) -> str:
    """Normalize a URL: lowercase scheme/host, strip fragment, strip trailing path slash."""
    try:
        p = urlparse(url.strip())
        path = p.path.rstrip("/") or "/"
        return urlunparse(
            (p.scheme.lower(), p.netloc.lower(), path, p.params, p.query, "")
        )
    except Exception:
        return url


@dataclass
class ImportResult:
    visits_created: int = 0
    visits_skipped: int = 0
    queue_items_added: int = 0
    errors: list[str] = field(default_factory=list)


class BrowsingImportService:
    """Import a JSON browsing report into BrowsingVisit records."""

    ALLOWED_STATES = ("ready_for_review", "under_review")

    @staticmethod
    def import_from_json(session: object, user: object, data: dict) -> ImportResult:
        """
        Parse and persist a browsing report JSON payload.

        Args:
            session: The SearchSession to associate visits with.
            user: The user performing the import.
            data: Parsed JSON dict with a ``visits`` list.

        Returns:
            ImportResult with counts and any per-visit error messages.
        """
        result = ImportResult()

        if session.status not in BrowsingImportService.ALLOWED_STATES:  # type: ignore[union-attr]
            result.errors.append(
                f"Session must be in ready_for_review or under_review "
                f"(currently '{session.status}')."  # type: ignore[union-attr]
            )
            return result

        visits = data.get("visits", [])
        if not isinstance(visits, list):
            result.errors.append("'visits' must be a list.")
            return result

        for i, visit_data in enumerate(visits):
            try:
                BrowsingImportService._import_visit(session, user, visit_data, result)
            except Exception as exc:
                result.errors.append(f"Visit {i}: unexpected error – {exc}")
                logger.exception("Unexpected error importing visit %d", i)

        return result

    @staticmethod
    def _import_visit(
        session: object, user: object, visit_data: dict, result: ImportResult
    ) -> None:
        url = (visit_data.get("url") or "").strip()
        if not url:
            result.errors.append("Visit missing required 'url' field.")
            return

        canonical = canonicalize_url(visit_data.get("canonical_url") or url)
        client_capture_id = visit_data.get("client_capture_id") or None

        # Idempotency: skip if this client_capture_id was already imported
        if (
            client_capture_id
            and BrowsingVisit.objects.filter(
                client_capture_id=client_capture_id
            ).exists()
        ):
            result.visits_skipped += 1
            return

        visit = BrowsingVisit.objects.create(
            session=session,  # type: ignore[misc]
            user=user,  # type: ignore[misc]
            url=url,
            canonical_url=canonical,
            title=(visit_data.get("title") or "")[:512],
            document_type=(visit_data.get("document_type") or "")[:100],
            site_name=(visit_data.get("site_name") or "")[:255],
            author=(visit_data.get("author") or "")[:512],
            published_date=_parse_date_safe(visit_data.get("published_date")),
            access_successful=bool(visit_data.get("access_successful", True)),
            visit_source=visit_data.get("visit_source") or "auto",
            # Strict boolean: a stray string like "false" must not become True
            captured_incognito=visit_data.get("captured_incognito") is True,
            client_capture_id=client_capture_id,
        )

        # Override auto_now_add timestamp when the extension supplies it
        raw_ts = visit_data.get("accessed_at")
        if raw_ts:
            parsed_ts = parse_datetime(raw_ts)
            if parsed_ts:
                BrowsingVisit.objects.filter(pk=visit.pk).update(accessed_at=parsed_ts)

        result.visits_created += 1
        logger.debug("Created BrowsingVisit %s for session %s", visit.pk, session.pk)  # type: ignore[union-attr]

        # Stream-2 promotion: add to screening queue
        if visit_data.get("add_to_queue"):
            BrowsingImportService._promote_visit(
                session, user, visit, visit_data, result
            )

    @staticmethod
    def _promote_visit(
        session: object,
        user: object,
        visit: BrowsingVisit,
        visit_data: dict,
        result: ImportResult,
    ) -> None:
        title = (visit_data.get("title") or "").strip() or visit.url
        justification = visit_data.get("justification") or "Added via browsing import"
        metadata = {
            "author": visit_data.get("author") or "",
            "published_date": visit_data.get("published_date") or "",
            "publisher": visit_data.get("publisher") or "",
            "document_type": visit_data.get("document_type") or "",
        }
        try:
            promoted = ManualResultService.add_manual_result(
                session=session,  # type: ignore[arg-type]
                user=user,  # type: ignore[arg-type]
                url=visit.url,
                title=title,
                justification=justification,
                metadata=metadata,
            )
            # Link the visit back to the ProcessedResult it produced
            BrowsingVisit.objects.filter(pk=visit.pk).update(promoted_result=promoted)
            result.queue_items_added += 1
        except ValueError as exc:
            # Duplicate URL or wrong session state — not fatal
            result.errors.append(f"Queue promotion skipped for {visit.url}: {exc}")


def _parse_date_safe(value: object) -> object:
    """Parse an ISO date string; return None on failure."""
    if not value:
        return None
    return parse_date(str(value))
