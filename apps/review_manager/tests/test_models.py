"""
Tests for review_manager models.

Tests for SearchSession and SessionActivity models including
workflow state transitions, validation, and model methods.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from ..models import SearchSession, SessionActivity
from apps.core.tests.utils import create_test_user

User = get_user_model()


class SearchSessionModelTests(TestCase):
    """Test cases for SearchSession model."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()

    def test_session_creation(self):
        """Test creating a search session."""
        session = SearchSession.objects.create(
            title="Test Session", description="Test description", owner=self.user
        )

        self.assertEqual(session.title, "Test Session")
        self.assertEqual(session.status, "draft")
        self.assertEqual(session.owner, self.user)
        self.assertEqual(session.total_results, 0)

    def test_status_transitions(self):
        """Test allowed status transitions."""
        session = SearchSession.objects.create(title="Test Session", owner=self.user)

        # Test valid transition
        self.assertTrue(session.can_transition_to("defining_search"))

        # Test invalid transition
        self.assertFalse(session.can_transition_to("completed"))

    def test_progress_percentage(self):
        """Test progress percentage calculation."""
        session = SearchSession.objects.create(
            title="Test Session",
            owner=self.user,
            total_results=100,
            reviewed_results=25,
        )

        self.assertEqual(session.progress_percentage, 25.0)

    def test_inclusion_rate(self):
        """Test inclusion rate calculation."""
        session = SearchSession.objects.create(
            title="Test Session",
            owner=self.user,
            reviewed_results=100,
            included_results=30,
        )

        self.assertEqual(session.inclusion_rate, 30.0)


class SessionActivityModelTests(TestCase):
    """Test cases for SessionActivity model."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user(username_prefix="activityuser")
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user
        )

    def test_activity_logging(self):
        """Test logging session activities."""
        activity = SessionActivity.log_activity(
            session=self.session,
            activity_type="created",
            description="Session created",
            user=self.user,
        )

        self.assertEqual(activity.session, self.session)
        self.assertEqual(activity.activity_type, "created")
        self.assertEqual(activity.user, self.user)
        self.assertEqual(activity.description, "Session created")
