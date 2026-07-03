"""
Tests for search_strategy models.

Tests for SearchStrategy model including
PIC framework validation and query generation.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.review_manager.models import SearchSession

from ..models import SearchStrategy
from apps.core.tests.utils import create_test_user

User = get_user_model()


class SearchQueryModelTests(TestCase):
    """Test cases for SearchStrategy model (legacy SearchQuery tests)."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user(username_prefix="test@example.com")
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user
        )

    def test_strategy_creation(self):
        """Test creating a search strategy."""
        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["elderly adults"],
            interest_terms=["digital health interventions"],
            context_terms=["healthcare settings"],
            search_config={
                "domains": [],
                "include_general_search": True,
                "search_type": "google",
            },
        )

        self.assertEqual(strategy.population_terms, ["elderly adults"])
        self.assertEqual(strategy.interest_terms, ["digital health interventions"])
        self.assertEqual(strategy.context_terms, ["healthcare settings"])
        self.assertTrue(strategy.search_config["include_general_search"])

    def test_query_string_generation(self):
        """Test automatic query string generation."""
        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["students"],
            interest_terms=["online learning"],
            context_terms=["higher education"],
            search_config={"include_general_search": True},
        )

        # Check that query string was auto-generated
        base_query = strategy.generate_base_query()
        self.assertIn("students", base_query)
        self.assertIn("online learning", base_query)
        self.assertIn("higher education", base_query)
        self.assertIn("AND", base_query)

    def test_pic_validation(self):
        """Test PIC framework validation."""
        strategy = SearchStrategy(
            session=self.session,
            user=self.user,
            population_terms=[],
            interest_terms=[],
            context_terms=[],
            search_config={},
        )

        # New validation logic: validate_completeness method
        is_valid = strategy.validate_completeness()
        self.assertFalse(is_valid)
        self.assertIn("pic_terms", strategy.validation_errors)

    def test_empty_strategy_validation(self):
        """Test that a completely empty strategy is invalid."""
        strategy = SearchStrategy(
            session=self.session,
            user=self.user,
            population_terms=[],
            interest_terms=[],
            context_terms=[],
            search_config={},
        )

        # Should be invalid with empty PIC terms
        is_valid = strategy.validate_completeness()
        self.assertFalse(is_valid)


class SearchStrategyModelTests(TestCase):
    """Test cases for SearchStrategy model caching and optimization."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user(username_prefix="strategy@example.com")
        self.session = SearchSession.objects.create(
            title="Strategy Test Session", owner=self.user
        )

    def create_test_strategy(self):
        """Create a test strategy with sample data."""
        from ..models import SearchStrategy

        return SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["elderly", "seniors"],
            interest_terms=["telehealth", "remote care"],
            context_terms=["rural", "remote"],
            search_config={
                "domains": ["who.int", "nice.org.uk"],
                "include_general_search": True,
                "file_types": ["pdf"],
            },
        )

    def test_count_queries_method(self):
        """Test efficient query counting without generation."""
        from unittest.mock import patch

        strategy = self.create_test_strategy()

        # Should count 3 queries (2 domains + 1 general)
        self.assertEqual(strategy.count_queries(), 3)

        # Verify it doesn't call generate_queries
        with patch.object(strategy, "generate_queries") as mock_generate:
            count = strategy.count_queries()
            mock_generate.assert_not_called()
            self.assertEqual(count, 3)

    def test_query_caching(self):
        """Test that queries are cached during request lifecycle."""
        from unittest.mock import patch

        strategy = self.create_test_strategy()

        # First call generates
        queries1 = strategy.generate_queries()
        self.assertIsNotNone(queries1)
        self.assertEqual(len(queries1), 3)  # 2 domains + 1 general

        # Second call should return cached
        with patch.object(strategy, "generate_base_query") as mock_base:
            queries2 = strategy.generate_queries()
            mock_base.assert_not_called()  # Should use cache

        self.assertEqual(queries1, queries2)

        # After save, cache should be invalidated
        strategy.save()
        with patch.object(
            strategy, "generate_base_query", return_value="(test)"
        ) as mock_base:
            _queries3 = strategy.generate_queries()
            # This should call generate_base_query since cache was cleared
            mock_base.assert_called_once()


class GuidelinesFilterTests(TestCase):
    """Test cases for the guidelines filter functionality."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user(username_prefix="guidelines@example.com")
        self.session = SearchSession.objects.create(
            title="Guidelines Filter Test Session", owner=self.user
        )

    def test_default_search_config_includes_guidelines_filter(self):
        """Test that default search config includes guidelines filter set to False."""
        from ..models import default_search_config

        config = default_search_config()
        self.assertIn("include_guidelines_filter", config)
        self.assertFalse(config["include_guidelines_filter"])

    def test_guidelines_filter_disabled_by_default(self):
        """Test that guidelines filter is disabled by default."""
        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["healthcare workers"],
            interest_terms=["training"],
            context_terms=["hospitals"],
        )

        base_query = strategy.generate_base_query()

        # Should not contain guideline terms when filter is disabled
        self.assertNotIn("guideline", base_query.lower())
        self.assertNotIn("guidance", base_query.lower())
        self.assertNotIn("recommendation", base_query.lower())
        self.assertNotIn("CPG", base_query)

    def test_guidelines_filter_when_enabled(self):
        """Test that guideline terms are added when filter is enabled."""
        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["healthcare workers"],
            interest_terms=["training"],
            context_terms=["hospitals"],
            search_config={
                "include_guidelines_filter": True,
                "include_general_search": True,
            },
        )

        base_query = strategy.generate_base_query()

        # Should contain all expected terms (multi-word terms are quoted)
        self.assertIn('("healthcare workers")', base_query)
        self.assertIn("(training)", base_query)
        self.assertIn("(hospitals)", base_query)
        self.assertIn(
            "(guideline* OR guidance OR statement* OR recommendation* OR CPG)",
            base_query,
        )

        # Should be connected with AND
        and_count = base_query.count(" AND ")
        self.assertEqual(
            and_count, 3
        )  # 3 PIC terms + 1 guidelines term = 3 AND operators

    def test_guidelines_filter_with_partial_pic_terms(self):
        """Test guidelines filter when only some PIC categories have terms."""
        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=[],  # Empty
            interest_terms=["training"],
            context_terms=["hospitals"],
            search_config={
                "include_guidelines_filter": True,
                "include_general_search": True,
            },
        )

        base_query = strategy.generate_base_query()

        # Should contain interest, context, and guidelines terms
        self.assertIn("(training)", base_query)
        self.assertIn("(hospitals)", base_query)
        self.assertIn(
            "(guideline* OR guidance OR statement* OR recommendation* OR CPG)",
            base_query,
        )

        # Should have 2 AND operators (interest + context + guidelines = 2 AND)
        and_count = base_query.count(" AND ")
        self.assertEqual(and_count, 2)

    def test_guidelines_filter_only_with_no_pic_terms(self):
        """Test guidelines filter when no PIC terms are provided."""
        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=[],
            interest_terms=[],
            context_terms=[],
            search_config={
                "include_guidelines_filter": True,
                "include_general_search": True,
            },
        )

        base_query = strategy.generate_base_query()

        # Should only contain the guidelines terms
        self.assertEqual(
            base_query,
            "(guideline* OR guidance OR statement* OR recommendation* OR CPG)",
        )

    def test_guidelines_filter_in_full_queries(self):
        """Test that guidelines filter appears in complete generated queries."""
        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["patients"],
            interest_terms=["medication"],
            search_config={
                "domains": ["who.int"],
                "include_general_search": True,
                "include_guidelines_filter": True,
                "file_types": ["pdf"],
            },
        )

        queries = strategy.generate_queries()

        self.assertEqual(len(queries), 2)  # 1 domain + 1 general

        # Both queries should contain guidelines terms
        for query_data in queries:
            query_text = query_data["query"]
            self.assertIn("guideline*", query_text)
            self.assertIn("guidance", query_text)
            self.assertIn("recommendation*", query_text)
            self.assertIn("CPG", query_text)
            self.assertIn("patients", query_text)
            self.assertIn("medication", query_text)

    def test_validation_with_guidelines_filter(self):
        """Test that validation works correctly with guidelines filter enabled."""
        # Strategy with only guidelines filter (no PIC terms) should be invalid
        strategy = SearchStrategy(
            session=self.session,
            user=self.user,
            population_terms=[],
            interest_terms=[],
            context_terms=[],
            search_config={
                "include_guidelines_filter": True,
                "include_general_search": True,
            },
        )

        is_valid = strategy.validate_completeness()
        self.assertFalse(is_valid)
        self.assertIn("pic_terms", strategy.validation_errors)

        # Strategy with PIC terms AND guidelines filter should be valid
        strategy.interest_terms = ["training"]
        is_valid = strategy.validate_completeness()
        self.assertTrue(is_valid)
        self.assertEqual(len(strategy.validation_errors), 0)


class GuidelinesFilterFormTests(TestCase):
    """Test cases for guidelines filter in the form."""

    def setUp(self):
        """Set up test data."""
        from apps.serp_execution.providers.config import SerpProviderConfig

        self.user = create_test_user(username_prefix="form@example.com")
        self.session = SearchSession.objects.create(
            title="Form Test Session", owner=self.user
        )
        SerpProviderConfig.objects.get_or_create(
            provider_key="serper",
            defaults={
                "display_name": "Serper.dev (Google)",
                "is_enabled": True,
                "is_default": True,
            },
        )

    def test_form_includes_guidelines_filter_field(self):
        """Test that the form includes the guidelines filter checkbox."""
        from ..forms import SearchStrategyForm

        form = SearchStrategyForm()

        # Check that the field exists
        self.assertIn("include_guidelines_filter", form.fields)

        # Check field properties
        field = form.fields["include_guidelines_filter"]
        self.assertEqual(field.label, "Guidelines filter")
        self.assertFalse(field.initial)  # Should be False by default
        self.assertFalse(field.required)  # Should be optional

    def test_form_processes_guidelines_filter_correctly(self):
        """Test that the form correctly processes guidelines filter data."""
        from ..forms import SearchStrategyForm

        # Create form data with guidelines filter enabled
        form_data = {
            "population_terms_text": "healthcare workers",
            "interest_terms_text": "training",
            "context_terms_text": "",
            "organization_domains": "",
            "include_general_search": True,
            "include_guidelines_filter": True,
            "search_pdf": True,
            "search_doc": False,
            "use_google_search": True,
            "use_google_scholar": False,
            "max_results_per_query": 50,
            "enable_query_splitting": False,
            "splitting_strategy": "by_pic_terms",
            "max_query_length": 2000,
            "serp_providers": ["serper"],
        }

        form = SearchStrategyForm(data=form_data)

        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

        # Check that search_config includes guidelines filter
        search_config = form.cleaned_data["search_config"]
        self.assertTrue(search_config["include_guidelines_filter"])
        self.assertEqual(search_config["serp_providers"], ["serper"])

    def test_form_saves_strategy_with_guidelines_filter(self):
        """Test that the form saves strategy with correct guidelines filter setting."""
        from ..forms import SearchStrategyForm

        # Create a strategy first
        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
        )

        form_data = {
            "population_terms_text": "patients",
            "interest_terms_text": "medication",
            "context_terms_text": "",
            "organization_domains": "who.int",
            "include_general_search": False,
            "include_guidelines_filter": True,
            "search_pdf": True,
            "search_doc": False,
            "use_google_search": True,
            "use_google_scholar": False,
            "max_results_per_query": 50,
            "enable_query_splitting": False,
            "splitting_strategy": "by_pic_terms",
            "max_query_length": 2000,
            "serp_providers": ["serper"],
        }

        form = SearchStrategyForm(data=form_data, instance=strategy)

        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

        saved_strategy = form.save()

        # Verify the strategy was saved with correct settings
        self.assertTrue(saved_strategy.search_config["include_guidelines_filter"])
        self.assertEqual(saved_strategy.population_terms, ["patients"])
        self.assertEqual(saved_strategy.interest_terms, ["medication"])

        # Verify the generated query includes guidelines terms
        base_query = saved_strategy.generate_base_query()
        self.assertIn(
            "(guideline* OR guidance OR statement* OR recommendation* OR CPG)",
            base_query,
        )
