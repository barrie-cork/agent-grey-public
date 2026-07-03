"""
Extension ingestion API (Phase 1 – S4).

Endpoints consumed exclusively by the Agent Grey browser extension.
Authentication: Knox per-device token (Authorization: Token ag_ext_<token>).
CORS:           Allowed for chrome-extension:// origins on /api/extension/* paths.

Routes (registered in grey_lit_project/urls.py):
    GET  /api/extension/sessions/      -- list active sessions for user/orgs
    POST /api/extension/visits/        -- batch ingest BrowsingVisit records
    POST /api/extension/add-result/    -- promote URL to screening queue
"""

import logging

from knox.auth import TokenAuthentication
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.review_manager.models import SearchSession
from apps.review_results.services.browsing_import_service import BrowsingImportService
from apps.review_results.services.manual_result_service import ManualResultService

logger = logging.getLogger(__name__)

_REVIEWABLE_STATES = ("ready_for_review", "under_review")


# ---------------------------------------------------------------------------
# Sessions endpoint
# ---------------------------------------------------------------------------


class ExtensionSessionListView(APIView):
    """
    List the user's active sessions suitable for capture.

    Returns sessions in ready_for_review or under_review state that the
    user owns or is a reviewer in.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        sessions = (
            SearchSession.objects.filter(
                owner=request.user,
                status__in=_REVIEWABLE_STATES,
            )
            .order_by("-updated_at")
            .values("id", "title", "status", "updated_at")
        )
        data = [
            {
                "id": str(s["id"]),
                "title": s["title"],
                "status": s["status"],
                "updated_at": s["updated_at"].isoformat(),
            }
            for s in sessions
        ]
        return Response(data)


# ---------------------------------------------------------------------------
# Visits batch ingest endpoint
# ---------------------------------------------------------------------------


class BatchVisitSerializer(serializers.Serializer):
    """Validate the /visits/ request body."""

    session_id = serializers.UUIDField()
    visits = serializers.ListField(
        child=serializers.DictField(), allow_empty=True, max_length=500
    )


class ExtensionVisitIngestView(APIView):
    """
    Batch-ingest browsing visits from the extension.

    Expects: {"session_id": "<uuid>", "visits": [...]}
    Each visit dict follows the BrowsingImportService schema.
    Returns import result counts plus any per-visit error messages.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        ser = BatchVisitSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            session = SearchSession.objects.get(
                id=ser.validated_data["session_id"],
                owner=request.user,
            )
        except SearchSession.DoesNotExist:
            return Response(
                {"error": "Session not found or not owned by you."},
                status=status.HTTP_404_NOT_FOUND,
            )

        data = {"visits": ser.validated_data["visits"]}
        result = BrowsingImportService.import_from_json(session, request.user, data)

        if (
            result.errors
            and result.visits_created == 0
            and result.queue_items_added == 0
        ):
            return Response(
                {"errors": result.errors}, status=status.HTTP_400_BAD_REQUEST
            )

        http_status = (
            status.HTTP_201_CREATED
            if (result.visits_created or result.queue_items_added)
            else status.HTTP_200_OK
        )
        return Response(
            {
                "visits_created": result.visits_created,
                "visits_skipped": result.visits_skipped,
                "queue_items_added": result.queue_items_added,
                "errors": result.errors,
            },
            status=http_status,
        )


# ---------------------------------------------------------------------------
# Add-result (Stream-2 promotion) endpoint
# ---------------------------------------------------------------------------


class AddResultSerializer(serializers.Serializer):
    """Validate the /add-result/ request body."""

    session_id = serializers.UUIDField()
    url = serializers.URLField(max_length=2048)
    title = serializers.CharField(max_length=512, allow_blank=True, default="")
    justification = serializers.CharField(
        max_length=1000, allow_blank=True, default="Added via browser extension"
    )
    metadata = serializers.DictField(required=False, default=dict)


class ExtensionAddResultView(APIView):
    """
    Promote a URL to the session's screening queue (Stream-2 one-click add).

    Wraps ManualResultService.add_manual_result with metadata support.
    Returns 201 with the new ProcessedResult id, or 409 for duplicate URL.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        ser = AddResultSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            session = SearchSession.objects.get(
                id=ser.validated_data["session_id"],
                owner=request.user,
            )
        except SearchSession.DoesNotExist:
            return Response(
                {"error": "Session not found or not owned by you."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            result = ManualResultService.add_manual_result(
                session=session,
                user=request.user,
                url=ser.validated_data["url"],
                title=ser.validated_data["title"] or ser.validated_data["url"],
                justification=ser.validated_data["justification"],
                metadata=ser.validated_data["metadata"] or None,
            )
        except ValueError as exc:
            http_status = (
                status.HTTP_409_CONFLICT
                if "already exists" in str(exc)
                else status.HTTP_400_BAD_REQUEST
            )
            return Response({"error": str(exc)}, status=http_status)

        return Response(
            {"result_id": str(result.pk), "url": result.url},
            status=status.HTTP_201_CREATED,
        )
