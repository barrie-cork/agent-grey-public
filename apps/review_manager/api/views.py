from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..models import SearchSession, SessionActivity
from .serializers import SearchSessionDetailSerializer, SearchSessionSerializer


class SearchSessionViewSet(viewsets.ModelViewSet):
    """
    API endpoint for search sessions.
    Provides CRUD operations and custom actions.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = SearchSessionSerializer
    lookup_field = "id"

    def get_queryset(self):
        return (
            SearchSession.objects.filter(owner=self.request.user)
            .select_related("owner")
            .prefetch_related("activities")
        )

    def get_serializer_class(self):
        if self.action == "retrieve":
            return SearchSessionDetailSerializer
        return SearchSessionSerializer

    def perform_create(self, serializer):
        session = serializer.save(owner=self.request.user)
        SessionActivity.log_activity(
            session=session,
            activity_type="created",
            description="Session created via API",
            user=self.request.user,
        )

    @action(detail=True, methods=["post"])
    def transition_status(self, request, id=None):
        """Transition session to new status with validation."""
        session = self.get_object()
        new_status = request.data.get("status")

        if not new_status:
            return Response(
                {"error": "Status field is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not session.can_transition_to(new_status):
            return Response(
                {"error": f"Cannot transition from {session.status} to {new_status}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_status = session.status
        session.status = new_status
        session.save()

        SessionActivity.log_activity(
            session=session,
            activity_type="status_changed",
            description=f"Status changed from {old_status} to {new_status}",
            user=request.user,
            metadata={"old_status": old_status, "new_status": new_status},
        )

        serializer = self.get_serializer(session)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def duplicate(self, request, id=None):
        """Create a duplicate of the session."""
        original = self.get_object()

        duplicate = SearchSession.objects.create(
            title=f"{original.title} (Copy)",
            description=original.description,
            owner=request.user,
            status="draft",
            notes=original.notes,
        )

        SessionActivity.log_activity(
            session=duplicate,
            activity_type="created",
            description=f"Duplicated from session {original.id}",
            user=request.user,
            metadata={"original_session_id": str(original.id)},
        )

        serializer = self.get_serializer(duplicate)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False)
    def statistics(self, request):
        """Get user's session statistics."""
        from django.db.models import Case, Count, Q, Sum, When

        sessions = self.get_queryset()

        stats = sessions.aggregate(
            total_sessions=Count("id"),
            active_sessions=Count(
                Case(When(~Q(status__in=["completed", "archived"]), then=1))
            ),
            completed_sessions=Count(Case(When(status="completed", then=1))),
            total_results_reviewed=Sum("reviewed_results", default=0),
            total_results_included=Sum("included_results", default=0),
        )

        return Response(stats)
