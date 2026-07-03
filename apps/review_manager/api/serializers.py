from rest_framework import serializers

from ..models import SearchSession, SessionActivity


class SearchSessionSerializer(serializers.ModelSerializer):
    """Basic session serializer for list views."""

    owner_username = serializers.CharField(source="owner.username", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    progress_percentage = serializers.FloatField(read_only=True)
    next_action = serializers.SerializerMethodField()

    class Meta:
        model = SearchSession
        fields = [
            "id",
            "title",
            "description",
            "status",
            "status_display",
            "owner",
            "owner_username",
            "created_at",
            "updated_at",
            "total_queries",
            "total_results",
            "reviewed_results",
            "included_results",
            "progress_percentage",
            "next_action",
        ]
        read_only_fields = ["id", "owner", "created_at", "updated_at"]

    def get_next_action(self, obj):
        from ..mixins import SessionNavigationMixin

        mixin = SessionNavigationMixin()
        return mixin.get_session_next_url(obj)


class SearchSessionDetailSerializer(SearchSessionSerializer):
    """Detailed session serializer with related data."""

    recent_activities = serializers.SerializerMethodField()
    allowed_transitions = serializers.ListField(read_only=True)
    inclusion_rate = serializers.FloatField(read_only=True)

    class Meta(SearchSessionSerializer.Meta):
        fields = SearchSessionSerializer.Meta.fields + [
            "notes",
            "started_at",
            "completed_at",
            "recent_activities",
            "allowed_transitions",
            "inclusion_rate",
        ]

    def get_recent_activities(self, obj):
        activities = obj.activities.select_related("user").order_by("-created_at")[:5]
        return SessionActivitySerializer(activities, many=True).data


class SessionActivitySerializer(serializers.ModelSerializer):
    """Activity log serializer."""

    user_username = serializers.CharField(source="user.username", read_only=True)
    activity_type_display = serializers.CharField(
        source="get_activity_type_display", read_only=True
    )

    class Meta:
        model = SessionActivity
        fields = [
            "id",
            "activity_type",
            "activity_type_display",
            "description",
            "user",
            "user_username",
            "created_at",
            "metadata",
        ]
