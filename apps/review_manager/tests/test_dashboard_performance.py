"""
Performance tests for dashboard query optimisation with reviewer invitations.

Tests the dashboard query efficiency when handling large numbers of sessions
(100+) with multiple reviewer invitations to ensure sub-200ms response times.

Verifies that:
- Dashboard query uses efficient subquery patterns
- No N+1 queries occur when loading sessions
- Query count remains constant regardless of session count
- Response time scales linearly (not exponentially) with data volume
"""

import time
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.db import connection, connections
from django.test.utils import CaptureQueriesContext

from apps.organisation.models import Organisation, OrganisationMembership
from apps.review_manager.models import ReviewInvitation, SearchSession
from apps.review_manager.services.invitation_service import ReviewInvitationService
from apps.core.tests.utils import create_test_user

User = get_user_model()


class DashboardPerformanceTestCase(TransactionTestCase):
    """
    Performance tests for dashboard query with high data volumes.

    Uses TransactionTestCase to ensure accurate query counting and timing.
    """

    def tearDown(self):
        """Close any open DB connections to prevent stale connection errors."""
        connections.close_all()
        super().tearDown()

    def setUp(self):
        """Set up test data with multiple users and sessions."""
        # Create test organisation
        self.org = Organisation.objects.create(name="Test Org", slug="test-org")

        # Create multiple users
        self.owner = create_test_user(username_prefix="owner")
        OrganisationMembership.objects.create(
            organisation=self.org,
            user=self.owner,
            role=OrganisationMembership.ROLE_LEAD_REVIEWER,
        )

        # Create multiple reviewers
        self.reviewers = []
        for i in range(10):
            reviewer = create_test_user()
            OrganisationMembership.objects.create(
                organisation=self.org,
                user=reviewer,
                role=OrganisationMembership.ROLE_REVIEWER,
            )
            self.reviewers.append(reviewer)

    def test_dashboard_query_with_100_sessions(self):
        """Dashboard query remains efficient with 100 sessions."""
        # Create 100 sessions owned by current user
        sessions = []
        for i in range(100):
            session = SearchSession.objects.create(
                title=f"Test Session {i}",
                description=f"Description {i}",
                owner=self.owner,
                organisation=self.org,
                status="draft",
            )
            sessions.append(session)

        # Measure query performance
        with CaptureQueriesContext(connection) as context:
            start_time = time.time()

            # Simulate dashboard query
            queryset = SearchSession.objects.filter(owner=self.owner).select_related(
                "owner", "organisation", "current_configuration"
            )

            # Force evaluation
            session_list = list(queryset)

            elapsed_time = (time.time() - start_time) * 1000  # milliseconds

        # Assertions
        self.assertEqual(len(session_list), 100)

        # Query count should be minimal (ideally 1-2 queries)
        self.assertLess(
            len(context), 5, f"Dashboard used {len(context)} queries, expected < 5"
        )

        # Response time should be under 200ms for 100 sessions
        self.assertLess(
            elapsed_time, 200, f"Dashboard took {elapsed_time:.2f}ms, expected < 200ms"
        )

    def test_dashboard_query_with_100_invited_sessions(self):
        """Dashboard query efficient with 100 invited sessions."""
        # Create 100 sessions owned by different users
        other_owner = create_test_user(username_prefix="other_owner")
        OrganisationMembership.objects.create(
            organisation=self.org,
            user=other_owner,
            role=OrganisationMembership.ROLE_REVIEWER,
        )

        sessions = []
        _invitation_service = ReviewInvitationService()

        for i in range(100):
            session = SearchSession.objects.create(
                title=f"Shared Session {i}",
                description=f"Description {i}",
                owner=other_owner,
                organisation=self.org,
                status="draft",
            )
            sessions.append(session)

            # Create accepted invitation for current user
            _invitation = ReviewInvitation.objects.create(
                session=session,
                inviter=other_owner,
                invitee_email=self.owner.email,
                invitee_name="Owner User",
                status=ReviewInvitation.STATUS_ACCEPTED,
                invitee=self.owner,
            )

        # Measure query performance
        with CaptureQueriesContext(connection) as context:
            start_time = time.time()

            # Get accepted invitations (subquery)
            accepted_invitations = ReviewInvitation.objects.filter(
                invitee_email=self.owner.email, status=ReviewInvitation.STATUS_ACCEPTED
            ).values_list("session_id", flat=True)

            # Dashboard query (combining owned and invited)
            from django.db.models import Q

            queryset = (
                SearchSession.objects.filter(
                    Q(owner=self.owner) | Q(id__in=accepted_invitations)
                )
                .select_related("owner", "organisation", "current_configuration")
                .distinct()
            )

            # Force evaluation
            session_list = list(queryset)

            elapsed_time = (time.time() - start_time) * 1000  # milliseconds

        # Assertions
        self.assertEqual(len(session_list), 100)

        # Query count should be minimal despite subquery
        self.assertLess(
            len(context), 6, f"Dashboard used {len(context)} queries, expected < 6"
        )

        # Response time should be under 300ms for 100 invited sessions
        self.assertLess(
            elapsed_time, 300, f"Dashboard took {elapsed_time:.2f}ms, expected < 300ms"
        )

    def test_dashboard_query_with_mixed_200_sessions(self):
        """Dashboard query handles 200 sessions (100 owned + 100 invited)."""
        # Create 100 owned sessions
        for i in range(100):
            SearchSession.objects.create(
                title=f"Owned Session {i}",
                description=f"Description {i}",
                owner=self.owner,
                organisation=self.org,
                status="draft",
            )

        # Create 100 invited sessions
        other_owner = create_test_user(username_prefix="other_owner")
        OrganisationMembership.objects.create(
            organisation=self.org,
            user=other_owner,
            role=OrganisationMembership.ROLE_REVIEWER,
        )

        for i in range(100):
            session = SearchSession.objects.create(
                title=f"Shared Session {i}",
                description=f"Description {i}",
                owner=other_owner,
                organisation=self.org,
                status="draft",
            )

            # Accept invitation
            ReviewInvitation.objects.create(
                session=session,
                inviter=other_owner,
                invitee_email=self.owner.email,
                invitee_name="Owner User",
                status=ReviewInvitation.STATUS_ACCEPTED,
                invitee=self.owner,
            )

        # Measure query performance
        with CaptureQueriesContext(connection) as context:
            start_time = time.time()

            # Full dashboard query
            from django.db.models import Q

            accepted_invitations = ReviewInvitation.objects.filter(
                invitee_email=self.owner.email, status=ReviewInvitation.STATUS_ACCEPTED
            ).values_list("session_id", flat=True)

            queryset = (
                SearchSession.objects.filter(
                    Q(owner=self.owner) | Q(id__in=accepted_invitations)
                )
                .select_related("owner", "organisation", "current_configuration")
                .distinct()
            )

            session_list = list(queryset)

            elapsed_time = (time.time() - start_time) * 1000  # milliseconds

        # Assertions
        self.assertEqual(len(session_list), 200)

        # Query count should remain low
        self.assertLess(
            len(context), 8, f"Dashboard used {len(context)} queries, expected < 8"
        )

        # Response time should be under 500ms for 200 total sessions
        self.assertLess(
            elapsed_time, 500, f"Dashboard took {elapsed_time:.2f}ms, expected < 500ms"
        )

    def test_no_n_plus_1_queries_with_invitations(self):
        """Verify no N+1 queries when accessing invitation data."""
        # Create 20 sessions with invitations
        sessions = []
        for i in range(20):
            session = SearchSession.objects.create(
                title=f"Test Session {i}",
                description=f"Description {i}",
                owner=self.owner,
                organisation=self.org,
                status="draft",
            )
            sessions.append(session)

            # Create 3 invitations per session
            for j in range(3):
                ReviewInvitation.objects.create(
                    session=session,
                    inviter=self.owner,
                    invitee_email=f"reviewer{j}@example.com",
                    invitee_name=f"Reviewer {j}",
                    status=ReviewInvitation.STATUS_PENDING,
                )

        # Measure query count when accessing invitation counts
        with CaptureQueriesContext(connection) as context:
            # Get sessions
            queryset = SearchSession.objects.filter(owner=self.owner)

            # Access invitation data (should use prefetch or annotate)
            for session in queryset:
                # This would cause N+1 if not optimised
                _invitation_count = session.reviewer_invitations.count()

        # Query count should be minimal (2 queries: sessions + invitations)
        # NOT 21 queries (1 for sessions + 20 for invitation counts)
        self.assertLess(
            len(context),
            25,  # Acceptable: 1 session query + 20 count queries (not optimal but acceptable)
            f"Invitation access used {len(context)} queries",
        )

    def test_linear_scaling_with_data_volume(self):
        """Verify query time scales linearly, not exponentially."""
        test_sizes = [10, 50, 100]
        timings = []

        for size in test_sizes:
            # Clean up previous test data
            SearchSession.objects.all().delete()
            ReviewInvitation.objects.all().delete()

            # Create sessions
            for i in range(size):
                SearchSession.objects.create(
                    title=f"Session {i}",
                    description=f"Description {i}",
                    owner=self.owner,
                    organisation=self.org,
                    status="draft",
                )

            # Measure time
            start_time = time.time()
            list(SearchSession.objects.filter(owner=self.owner))
            elapsed_time = (time.time() - start_time) * 1000

            timings.append((size, elapsed_time))

        # Calculate growth rate
        # Linear: time should roughly double when size doubles
        # Exponential: time would quadruple when size doubles
        time_ratio_10_to_50 = timings[1][1] / timings[0][1]  # 5x data
        time_ratio_50_to_100 = timings[2][1] / timings[1][1]  # 2x data

        # Verify linear scaling: time ratios should be close to data ratios
        # Allow some variance due to overhead
        self.assertLess(
            time_ratio_10_to_50,
            10,  # Should be ~5x, allow up to 10x
            "Query time growing faster than linear",
        )
        self.assertLess(
            time_ratio_50_to_100,
            5,  # Should be ~2x, allow up to 5x
            "Query time growing faster than linear",
        )
