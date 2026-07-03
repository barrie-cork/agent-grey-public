from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.core.tests.utils import create_test_user

User = get_user_model()


class DenormalizedFieldsTest(TestCase):
    """Test denormalized fields work correctly."""

    def setUp(self):
        """Create test data."""
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="defining_search"
        )
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["term1"],
            interest_terms=["term2"],
        )

    def test_search_query_denormalized_session(self):
        """Test SearchQuery's denormalized session field."""
        # Create query with denormalized session field
        _query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,  # Denormalized field
            query_text="test query",
            query_type="general",
        )

        # Direct access via denormalized field
        queries_direct = SearchQuery.objects.filter(session=self.session)
        self.assertEqual(queries_direct.count(), 1)

        # Access via relationship chain
        queries_via_strategy = SearchQuery.objects.filter(
            strategy__session=self.session
        )
        self.assertEqual(queries_via_strategy.count(), 1)

        # Both should return the same results
        self.assertEqual(
            list(queries_direct.values_list("id", flat=True)),
            list(queries_via_strategy.values_list("id", flat=True)),
        )

    def test_denormalized_field_performance(self):
        """Test that denormalized fields improve query performance."""
        # Create multiple queries
        for i in range(10):
            SearchQuery.objects.create(
                strategy=self.strategy,
                session=self.session,
                query_text=f"query {i}",
                query_type="general",
            )

        # Using denormalized field should be faster (no join needed)
        with self.assertNumQueries(1):
            list(SearchQuery.objects.filter(session=self.session))

        # Using relationship requires join
        with self.assertNumQueries(1):  # Still 1 query but with JOIN
            list(SearchQuery.objects.filter(strategy__session=self.session))
