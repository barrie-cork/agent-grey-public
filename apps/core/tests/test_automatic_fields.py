from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.review_manager.models import SearchSession
from apps.core.tests.utils import create_test_user

User = get_user_model()


class AutomaticFieldsTest(TestCase):
    """Test Django automatic fields work correctly."""

    def setUp(self):
        """Create test data."""
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="draft"
        )

    def test_pk_field_in_get(self):
        """Test that pk field works in get queries."""
        # Should work with pk
        found = SearchSession.objects.get(pk=self.session.pk)
        self.assertEqual(found.id, self.session.id)

        # pk and id should be the same for default primary key
        self.assertEqual(self.session.pk, self.session.id)

    def test_pk_field_in_filter(self):
        """Test that pk field works in filter queries."""
        # Filter by pk
        results = SearchSession.objects.filter(pk=self.session.pk)
        self.assertEqual(results.count(), 1)

        # Filter by pk__in
        results = SearchSession.objects.filter(pk__in=[self.session.pk])
        self.assertEqual(results.count(), 1)

    def test_pk_field_in_related_queries(self):
        """Test that pk field works in related queries."""
        # Filter by related object's pk
        sessions = SearchSession.objects.filter(owner__pk=self.user.pk)
        self.assertEqual(sessions.count(), 1)

        # Reverse relationship with pk
        users = User.objects.filter(search_sessions__pk=self.session.pk)
        self.assertEqual(users.count(), 1)

    def test_pk_field_ordering(self):
        """Test that pk field works in ordering."""
        # Create another session
        _session2 = SearchSession.objects.create(
            title="Test Session 2", owner=self.user, status="draft"
        )

        # Order by pk should work without errors
        sessions = SearchSession.objects.order_by("pk")
        self.assertEqual(sessions.count(), 2)

        # Order by -pk should also work
        sessions_desc = SearchSession.objects.order_by("-pk")
        self.assertEqual(sessions_desc.count(), 2)

        # The order should be opposite
        self.assertEqual(sessions[0].pk, sessions_desc[1].pk)
        self.assertEqual(sessions[1].pk, sessions_desc[0].pk)
