"""
Unit tests for search_strategy signal handlers.

Tests check_strategy_completion and get_query_count directly.
"""

import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.core.tests.utils import DisablePersonalOrgSignalMixin, create_test_user
from apps.organisation.models import Organisation, OrganisationMembership
from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchQuery
from apps.search_strategy.signals import check_strategy_completion, get_query_count


class CheckStrategyCompletionSignalTest(DisablePersonalOrgSignalMixin, TestCase):
    """Tests for check_strategy_completion signal handler."""

    def setUp(self):
        self.user = create_test_user(username_prefix="strat_signal")
        self.org = Organisation.objects.create(
            name="Strategy Signal Org", slug="strat-signal-org"
        )
        OrganisationMembership.objects.create(
            user=self.user,
            organisation=self.org,
            role="INFORMATION_SPECIALIST",
            is_active=True,
        )
        self.session = SearchSession.objects.create(
            title="Strategy Signal Test",
            owner=self.user,
            organisation=self.org,
            status="defining_search",
        )

    def _create_strategy_and_query(self, query_text="test query"):
        """Helper to create a strategy with one active query."""
        from apps.search_strategy.models import SearchStrategy

        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test pop"],
            interest_terms=["test interest"],
            context_terms=["test context"],
            search_config={
                "domains": ["example.com"],
                "include_general_search": False,
                "file_types": [],
            },
        )
        query = SearchQuery(
            strategy=strategy,
            session=self.session,
            query_text=query_text,
            query_type="boolean",
            is_active=True,
        )
        return strategy, query

    @patch("apps.search_strategy.signals.session_status_changed")
    def test_skips_without_strategy(self, mock_signal):
        """Exits early when instance has no strategy."""
        instance = MagicMock()
        instance.strategy = None
        instance.session = self.session

        check_strategy_completion(sender=SearchQuery, instance=instance, created=True)
        mock_signal.send.assert_not_called()

    @patch("apps.search_strategy.signals.session_status_changed")
    def test_skips_wrong_session_status(self, mock_signal):
        """Exits early when session is not in draft/defining_search."""
        self.session.status = "under_review"
        self.session.save(update_fields=["status"])

        strategy, query = self._create_strategy_and_query()

        check_strategy_completion(sender=SearchQuery, instance=query, created=True)
        mock_signal.send.assert_not_called()

    @patch("apps.search_strategy.signals.session_status_changed")
    def test_skips_incomplete_strategy(self, mock_signal):
        """Exits early when strategy validate_completeness returns False."""
        from apps.search_strategy.models import SearchStrategy

        # Create strategy with no terms and no domains - will fail validation
        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=[],
            interest_terms=[],
            context_terms=[],
            search_config={
                "domains": [],
                "include_general_search": False,
            },
        )
        query = SearchQuery(
            strategy=strategy,
            session=self.session,
            query_text="test",
            query_type="boolean",
            is_active=True,
        )

        check_strategy_completion(sender=SearchQuery, instance=query, created=True)
        mock_signal.send.assert_not_called()

    @patch("apps.search_strategy.signals.session_status_changed")
    def test_skips_no_active_queries(self, mock_signal):
        """Exits early when no active queries exist."""
        strategy, _ = self._create_strategy_and_query()

        # Create only an inactive query (don't save the active one from helper)
        query = SearchQuery.objects.create(
            strategy=strategy,
            session=self.session,
            query_text="inactive query",
            query_type="boolean",
            is_active=False,
        )

        check_strategy_completion(sender=SearchQuery, instance=query, created=True)
        mock_signal.send.assert_not_called()

    @patch("apps.search_strategy.signals.session_status_changed")
    def test_emits_status_change_signal(self, mock_signal):
        """Emits session_status_changed when strategy is complete with active queries."""
        strategy, _ = self._create_strategy_and_query()

        # post_save on SearchQuery triggers check_strategy_completion automatically
        SearchQuery.objects.create(
            strategy=strategy,
            session=self.session,
            query_text="complete query",
            query_type="boolean",
            is_active=True,
        )

        mock_signal.send.assert_called()
        call_kwargs = mock_signal.send.call_args.kwargs
        self.assertEqual(call_kwargs["session_id"], str(self.session.id))
        self.assertEqual(call_kwargs["requested_status"], "ready_to_execute")

    @patch("apps.search_strategy.signals.session_status_changed")
    def test_skips_when_no_search_strategy(self, mock_signal):
        """Exits early when session has no search strategy."""
        # Create a session without a strategy, then a query referencing it
        other_session = SearchSession.objects.create(
            title="No Strategy",
            owner=self.user,
            organisation=self.org,
            status="defining_search",
        )
        instance = MagicMock()
        instance.strategy = MagicMock()
        instance.session = other_session

        check_strategy_completion(sender=SearchQuery, instance=instance, created=True)
        mock_signal.send.assert_not_called()


class GetQueryCountTest(DisablePersonalOrgSignalMixin, TestCase):
    """Tests for get_query_count function."""

    def setUp(self):
        self.user = create_test_user(username_prefix="qcount")
        self.org = Organisation.objects.create(
            name="Query Count Org", slug="query-count-org"
        )
        OrganisationMembership.objects.create(
            user=self.user,
            organisation=self.org,
            role="INFORMATION_SPECIALIST",
            is_active=True,
        )

    def test_returns_count_for_valid_session(self):
        """Returns count of active queries for a session."""
        from apps.search_strategy.models import SearchStrategy

        session = SearchSession.objects.create(
            title="Count Test",
            owner=self.user,
            organisation=self.org,
            status="defining_search",
        )
        strategy = SearchStrategy.objects.create(
            session=session,
            user=self.user,
            population_terms=["pop"],
            interest_terms=["interest"],
            context_terms=["context"],
        )
        for i in range(3):
            SearchQuery.objects.create(
                strategy=strategy,
                session=session,
                query_text=f"query {i}",
                query_type="boolean",
                is_active=True,
            )
        # One inactive query should not be counted
        SearchQuery.objects.create(
            strategy=strategy,
            session=session,
            query_text="inactive",
            query_type="boolean",
            is_active=False,
        )

        self.assertEqual(get_query_count(str(session.id)), 3)

    def test_returns_zero_for_nonexistent_session(self):
        """Returns 0 for an invalid session_id."""
        self.assertEqual(get_query_count(str(uuid.uuid4())), 0)
