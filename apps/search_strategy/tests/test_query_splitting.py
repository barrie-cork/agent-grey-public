"""
Comprehensive test suite for query splitting functionality.

This test module validates all aspects of the query splitting feature including:
- Query length checking
- Various splitting strategies (by_pic_terms, by_interest, by_domains)
- File type preservation in split queries
- Edge cases and metadata validation
- Integration with SearchStrategyService
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchStrategy
from apps.search_strategy.services.search_strategy_service import SearchStrategyService
from apps.core.tests.utils import create_test_user

User = get_user_model()


class TestQueryLengthChecking(TestCase):
    """Test the query length checking functionality."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()

        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="defining_search"
        )

        # Create a strategy with terms that will generate long queries
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=[
                "elderly",
                "seniors",
                "older adults",
                "geriatric patients",
                "aged population",
            ],
            interest_terms=[
                "obesity",
                "overweight",
                "weight management",
                "body mass index",
                "adiposity",
            ],
            context_terms=[
                "primary care",
                "general practice",
                "community health",
                "family medicine",
                "outpatient",
            ],
            search_config={
                "domains": ["nice.org.uk", "who.int"],
                "include_general_search": True,
                "file_types": ["pdf", "doc"],
                "query_splitting": {
                    "enabled": False,
                    "strategy": "by_pic_terms",
                    "max_query_length": 200,  # Low threshold for testing
                },
            },
        )

    def test_check_query_lengths_identifies_long_queries(self):
        """Test that check_query_lengths correctly identifies queries exceeding threshold."""
        issues = self.strategy.check_query_lengths(max_length=200)

        # Should have issues since we have many terms
        self.assertGreater(len(issues), 0, "Should identify long queries")

        # Check issue structure
        for issue in issues:
            self.assertIn("index", issue)
            self.assertIn("query", issue)
            self.assertIn("length", issue)
            self.assertIn("excess", issue)
            self.assertIn("type", issue)

            # Verify excess calculation
            self.assertEqual(issue["excess"], issue["length"] - 200)

            # Verify query truncation
            self.assertTrue(issue["query"].endswith("..."))

    def test_check_query_lengths_respects_custom_threshold(self):
        """Test that custom max_length parameter is respected."""
        # Check with very high threshold
        issues_high = self.strategy.check_query_lengths(max_length=5000)
        self.assertEqual(
            len(issues_high), 0, "Should have no issues with high threshold"
        )

        # Check with very low threshold
        issues_low = self.strategy.check_query_lengths(max_length=50)
        queries = self.strategy.generate_queries()
        self.assertEqual(
            len(issues_low), len(queries), "All queries should exceed low threshold"
        )

    def test_check_query_lengths_with_no_issues(self):
        """Test check_query_lengths returns empty list when no issues."""
        # Create a separate session to avoid unique constraint on strategy.session
        simple_session = SearchSession.objects.create(
            title="Simple Session", owner=self.user, status="defining_search"
        )
        simple_strategy = SearchStrategy.objects.create(
            session=simple_session,
            user=self.user,
            population_terms=["adult"],
            interest_terms=["obesity"],
            context_terms=["care"],
            search_config={"domains": ["who.int"], "file_types": ["pdf"]},
        )

        issues = simple_strategy.check_query_lengths(max_length=500)
        self.assertEqual(len(issues), 0, "Should have no issues with short queries")


class TestQuerySplittingByPICTerms(TestCase):
    """Test the by_pic_terms splitting strategy."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()

        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="defining_search"
        )

        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["children", "adolescents", "youth"],
            interest_terms=["diabetes", "hyperglycemia", "insulin resistance"],
            context_terms=["school health", "educational settings", "classroom"],
            search_config={
                "domains": ["nice.org.uk"],
                "file_types": ["pdf", "doc"],
                "query_splitting": {
                    "enabled": True,
                    "strategy": "by_pic_terms",
                    "max_query_length": 150,  # Force splitting
                },
            },
        )

    def test_split_by_pic_terms_creates_three_combinations(self):
        """Test that PIC splitting creates three query combinations."""
        split_queries = self.strategy.generate_split_queries()

        # Count splits for the domain-specific query
        domain_splits = [q for q in split_queries if q["domain"] == "nice.org.uk"]

        # Should have 3 combinations: pop+int, pop+ctx, int+ctx
        split_strategies = [
            q.get("split_info", {}).get("split_strategy") for q in domain_splits
        ]
        self.assertIn("population_interest", split_strategies)
        self.assertIn("population_context", split_strategies)
        self.assertIn("interest_context", split_strategies)

    def test_split_queries_preserve_file_types(self):
        """Test that file type filters are preserved in split queries."""
        split_queries = self.strategy.generate_split_queries()

        for query in split_queries:
            query_text = query["query"]
            if query.get("domain"):  # Domain-specific queries have file types
                # Check for proper grouping with parentheses
                self.assertIn(
                    " (filetype:pdf OR filetype:doc OR filetype:docx)", query_text
                )

                # Verify file types are grouped, not loose at the end
                self.assertNotIn("site:" + query["domain"] + " filetype:", query_text)

    def test_split_info_metadata_structure(self):
        """Test that split_info metadata has correct structure."""
        split_queries = self.strategy.generate_split_queries()

        # Find a split query
        split_query = next((q for q in split_queries if "split_info" in q), None)
        self.assertIsNotNone(split_query, "Should have at least one split query")

        assert split_query is not None
        split_info = split_query["split_info"]

        # Check required fields
        self.assertIn("population", split_info)
        self.assertIn("interest", split_info)
        self.assertIn("context", split_info)
        self.assertIn("original_index", split_info)
        self.assertIn("split_index", split_info)
        self.assertIn("split_strategy", split_info)

        # Check data types
        self.assertIsInstance(split_info["population"], list)
        self.assertIsInstance(split_info["interest"], list)
        self.assertIsInstance(split_info["context"], list)
        self.assertIsInstance(split_info["original_index"], int)
        self.assertIsInstance(split_info["split_index"], int)
        self.assertIsInstance(split_info["split_strategy"], str)

    def test_split_queries_maintain_domain_prefix(self):
        """Test that domain-specific queries maintain site: prefix."""
        split_queries = self.strategy.generate_split_queries()

        domain_queries = [q for q in split_queries if q.get("domain") == "nice.org.uk"]

        for query in domain_queries:
            self.assertTrue(query["query"].startswith("site:nice.org.uk "))

    def test_multi_word_terms_are_quoted(self):
        """Test that multi-word terms are properly quoted in split queries."""
        # Create a separate session to avoid unique constraint on strategy.session
        multi_word_session = SearchSession.objects.create(
            title="Multi Word Session", owner=self.user, status="defining_search"
        )
        strategy = SearchStrategy.objects.create(
            session=multi_word_session,
            user=self.user,
            population_terms=["young adults", "college students"],
            interest_terms=["mental health", "anxiety disorders"],
            context_terms=["university counseling", "campus services"],
            search_config={
                "domains": ["who.int"],
                "query_splitting": {
                    "enabled": True,
                    "strategy": "by_pic_terms",
                    "max_query_length": 100,
                },
            },
        )

        split_queries = strategy.generate_split_queries()

        for query in split_queries:
            query_text = query["query"]
            # Check that multi-word terms are quoted
            if "young adults" in query.get("split_info", {}).get("population", []):
                self.assertIn('"young adults"', query_text)
            if "mental health" in query.get("split_info", {}).get("interest", []):
                self.assertIn('"mental health"', query_text)


class TestQuerySplittingByInterest(TestCase):
    """Test the by_interest splitting strategy."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()

        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="defining_search"
        )

        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["adults", "patients"],
            interest_terms=[
                "hypertension",
                "blood pressure",
                "cardiovascular disease",
                "heart disease",
            ],
            context_terms=["emergency", "acute care"],
            search_config={
                "domains": ["nice.org.uk"],
                "file_types": ["pdf"],
                "query_splitting": {
                    "enabled": True,
                    "strategy": "by_interest",
                    "max_query_length": 150,
                },
            },
        )

    def test_split_by_interest_creates_one_query_per_interest_term(self):
        """Test that by_interest strategy creates one query per interest term."""
        split_queries = self.strategy.generate_split_queries()

        # Find split queries for domain
        domain_splits = [
            q
            for q in split_queries
            if q.get("domain") == "nice.org.uk" and "split_info" in q
        ]

        # Should have one query per interest term
        self.assertEqual(len(domain_splits), len(self.strategy.interest_terms))

        # Each query should have only one interest term
        for query in domain_splits:
            split_info = query["split_info"]
            self.assertEqual(len(split_info["interest"]), 1)

            # But should have all population and context terms
            self.assertEqual(
                len(split_info["population"]), len(self.strategy.population_terms)
            )
            self.assertEqual(
                len(split_info["context"]), len(self.strategy.context_terms)
            )

    def test_split_by_interest_query_structure(self):
        """Test the query structure when splitting by interest terms."""
        split_queries = self.strategy.generate_split_queries()

        # Find a split query
        split_query = next((q for q in split_queries if "split_info" in q), None)
        self.assertIsNotNone(split_query)

        assert split_query is not None
        query_text = split_query["query"]
        interest_term = split_query["split_info"]["interest"][0]

        # Interest term should not be in an OR group (single term)
        if " " in interest_term:
            self.assertIn(f'"{interest_term}"', query_text)
        else:
            self.assertIn(interest_term, query_text)

        # Population terms should be in OR group
        self.assertIn("(adults OR patients)", query_text)

        # Context terms should be in OR group
        self.assertIn('(emergency OR "acute care")', query_text)


class TestQuerySplittingEdgeCases(TestCase):
    """Test edge cases and error conditions for query splitting."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()

        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="defining_search"
        )

    def test_splitting_with_empty_category(self):
        """Test splitting behavior when one PIC category is empty."""
        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["adults"],
            interest_terms=[],  # Empty interest
            context_terms=["hospital"],
            search_config={
                "domains": ["who.int"],
                "query_splitting": {
                    "enabled": True,
                    "strategy": "by_pic_terms",
                    "max_query_length": 50,
                },
            },
        )

        # Should handle gracefully without errors
        split_queries = strategy.generate_split_queries()
        self.assertIsInstance(split_queries, list)

        # With empty interest, PIC combinations might not make sense
        # Check that it doesn't crash
        for query in split_queries:
            self.assertIn("query", query)

    def test_splitting_with_single_term_per_category(self):
        """Test splitting with only one term in each category."""
        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["adults"],
            interest_terms=["obesity"],
            context_terms=["hospital"],
            search_config={
                "domains": ["nice.org.uk"],
                "query_splitting": {
                    "enabled": True,
                    "strategy": "by_pic_terms",
                    "max_query_length": 50,
                },
            },
        )

        split_queries = strategy.generate_split_queries()

        # Should still create splits
        splits_with_info = [q for q in split_queries if "split_info" in q]
        self.assertGreater(len(splits_with_info), 0)

        # Single terms should not have OR grouping
        for query in splits_with_info:
            query_text = query["query"]
            # Single terms should appear without parentheses for OR grouping
            self.assertNotIn("(adults OR", query_text)
            self.assertNotIn("(obesity OR", query_text)
            self.assertNotIn("(hospital OR", query_text)

    def test_splitting_disabled_returns_original_queries(self):
        """Test that disabling splitting returns original queries."""
        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["elderly"] * 10,  # Many terms to force length
            interest_terms=["obesity"] * 10,
            context_terms=["care"] * 10,
            search_config={
                "domains": ["who.int"],
                "query_splitting": {
                    "enabled": False,  # Disabled
                    "strategy": "by_pic_terms",
                    "max_query_length": 50,
                },
            },
        )

        original_queries = strategy.generate_queries()
        split_queries = strategy.generate_split_queries()

        # Should be identical when splitting is disabled
        self.assertEqual(len(original_queries), len(split_queries))

        # No split_info should be present
        for query in split_queries:
            self.assertNotIn("split_info", query)

    def test_unknown_splitting_strategy_returns_original(self):
        """Test that unknown splitting strategy returns original query."""
        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["adults"] * 10,
            interest_terms=["obesity"] * 10,
            context_terms=["care"] * 10,
            search_config={
                "domains": ["who.int"],
                "query_splitting": {
                    "enabled": True,
                    "strategy": "unknown_strategy",  # Invalid strategy
                    "max_query_length": 50,
                },
            },
        )

        split_queries = strategy.generate_split_queries()

        # Should return queries but without splitting
        self.assertGreater(len(split_queries), 0)

        # No split_info should be added for unknown strategy
        for query in split_queries:
            self.assertNotIn("split_info", query)

    def test_queries_under_threshold_not_split(self):
        """Test that queries under the threshold are not split."""
        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["adults", "elderly"],
            interest_terms=["obesity", "diabetes"],
            context_terms=["care", "hospital"],
            search_config={
                "domains": ["who.int"],
                "query_splitting": {
                    "enabled": True,
                    "strategy": "by_pic_terms",
                    "max_query_length": 5000,  # Very high threshold
                },
            },
        )

        split_queries = strategy.generate_split_queries()

        # Should not have any split_info since queries are under threshold
        for query in split_queries:
            self.assertNotIn("split_info", query)


class TestSearchStrategyServiceIntegration(TestCase):
    """Test integration with SearchStrategyService for split queries."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()

        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="defining_search"
        )

        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["adults", "elderly", "seniors"],
            interest_terms=["obesity", "overweight", "adiposity"],
            context_terms=["primary care", "community", "outpatient"],
            search_config={
                "domains": ["nice.org.uk"],
                "file_types": ["pdf"],
                "query_splitting": {
                    "enabled": True,
                    "strategy": "by_pic_terms",
                    "max_query_length": 100,
                },
            },
        )

        self.service = SearchStrategyService()

    @patch("apps.search_strategy.services.search_strategy_service.logger")
    def test_service_uses_split_queries_when_enabled(self, mock_logger):
        """Test that service uses generate_split_queries when splitting is enabled."""
        # Update search queries
        _result = self.service.update_search_queries(self.strategy)

        # Check that splitting was logged
        mock_logger.info.assert_any_call(
            f"[Query Splitting] Generating split queries for session {self.strategy.session.id}"
        )

        # Check that SearchQuery objects were created
        from apps.search_strategy.models import SearchQuery

        queries = SearchQuery.objects.filter(strategy=self.strategy)
        self.assertGreater(queries.count(), 0)

        # Check for split query logging
        split_log_calls = [
            call
            for call in mock_logger.info.call_args_list
            if "[Query Splitting] Creating split query" in str(call)
        ]
        self.assertGreater(len(split_log_calls), 0, "Should log split query creation")

    @patch("apps.search_strategy.services.search_strategy_service.logger")
    def test_service_uses_regular_queries_when_disabled(self, mock_logger):
        """Test that service uses generate_queries when splitting is disabled."""
        # Disable splitting
        self.strategy.search_config["query_splitting"]["enabled"] = False
        self.strategy.save()

        # Update search queries
        _result = self.service.update_search_queries(self.strategy)

        # Should not log splitting
        split_log_calls = [
            call
            for call in mock_logger.info.call_args_list
            if "[Query Splitting]" in str(call)
        ]
        self.assertEqual(
            len(split_log_calls), 0, "Should not log query splitting when disabled"
        )

        # Note: Regular query creation logging has been removed for performance
        # The update_search_queries will still be called successfully without logging


class TestFileTypePreservationInSplits(TestCase):
    """Test that file type filters are correctly preserved in all splitting scenarios."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()

        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="defining_search"
        )

    def test_multiple_file_types_with_pic_splitting(self):
        """Test multiple file types are preserved with PIC splitting.

        Note: The model only recognises 'pdf' and 'doc' file types.
        'doc' auto-expands to filetype:doc OR filetype:docx.
        """
        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["adults", "elderly"],
            interest_terms=["diabetes", "insulin"],
            context_terms=["hospital", "clinic"],
            search_config={
                "domains": ["who.int"],
                "file_types": ["pdf", "doc"],
                "query_splitting": {
                    "enabled": True,
                    "strategy": "by_pic_terms",
                    "max_query_length": 100,
                },
            },
        )

        split_queries = strategy.generate_split_queries()

        for query in split_queries:
            if query.get("domain"):  # Domain-specific queries
                query_text = query["query"]

                # Check for recognised file types (pdf, doc, docx)
                self.assertIn("filetype:pdf", query_text)
                self.assertIn("filetype:doc", query_text)
                self.assertIn("filetype:docx", query_text)

                # Check for proper grouping
                self.assertIn(" (filetype:", query_text)

    def test_file_types_with_interest_splitting(self):
        """Test file types are preserved with by_interest splitting.

        Note: The model only recognises 'pdf' and 'doc' file types.
        """
        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["children"],
            interest_terms=["asthma", "bronchitis", "pneumonia"],
            context_terms=["school"],
            search_config={
                "domains": ["nice.org.uk"],
                "file_types": ["pdf", "doc"],
                "query_splitting": {
                    "enabled": True,
                    "strategy": "by_interest",
                    "max_query_length": 80,
                },
            },
        )

        split_queries = strategy.generate_split_queries()

        # Find split queries
        split_with_info = [q for q in split_queries if "split_info" in q]
        self.assertGreater(len(split_with_info), 0)

        for query in split_with_info:
            if query.get("domain"):
                query_text = query["query"]

                # Check file types are present
                self.assertIn("filetype:pdf", query_text)
                self.assertIn("filetype:doc", query_text)
                self.assertIn("filetype:docx", query_text)

                # Check grouping
                self.assertIn(
                    " (filetype:pdf OR filetype:doc OR filetype:docx)", query_text
                )

    def test_general_search_includes_file_type_filters(self):
        """Test that general search queries include file type filters when configured.

        The model applies file type filters to both domain-specific and general
        search queries, using AND grouping to maintain proper Boolean precedence.
        """
        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["adults"],
            interest_terms=["obesity"],
            context_terms=["care"],
            search_config={
                "domains": ["who.int"],
                "include_general_search": True,
                "file_types": ["pdf"],
                "query_splitting": {
                    "enabled": True,
                    "strategy": "by_pic_terms",
                    "max_query_length": 50,
                },
            },
        )

        split_queries = strategy.generate_split_queries()

        # Find general search query
        general_query = next((q for q in split_queries if q["type"] == "general"), None)
        self.assertIsNotNone(general_query)

        # General search includes file type filters with grouping
        assert general_query is not None
        self.assertIn("(filetype:pdf)", general_query["query"])

    def test_empty_file_types_no_filter(self):
        """Test that empty file types list doesn't add filters."""
        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["adults"],
            interest_terms=["obesity"],
            context_terms=["care"],
            search_config={
                "domains": ["who.int"],
                "file_types": [],  # Empty file types
                "query_splitting": {
                    "enabled": True,
                    "strategy": "by_pic_terms",
                    "max_query_length": 50,
                },
            },
        )

        split_queries = strategy.generate_split_queries()

        for query in split_queries:
            self.assertNotIn("filetype:", query["query"])


class TestQuerySplittingValidation(TestCase):
    """Validation tests to ensure split queries are valid and executable."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()

        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="defining_search"
        )

    def test_split_queries_are_shorter_than_original(self):
        """Test that split queries are actually shorter than originals."""
        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["adults", "elderly", "seniors", "aged", "geriatric"],
            interest_terms=["obesity", "overweight", "adiposity", "weight", "BMI"],
            context_terms=["primary", "community", "outpatient", "clinic", "practice"],
            search_config={
                "domains": ["who.int"],
                "file_types": ["pdf", "doc"],
                "query_splitting": {
                    "enabled": True,
                    "strategy": "by_pic_terms",
                    "max_query_length": 150,
                },
            },
        )

        # Get original queries
        original_queries = strategy.generate_queries()

        # Get split queries
        split_queries = strategy.generate_split_queries()

        # Find the original long query
        long_original = next(
            (q for q in original_queries if len(q["query"]) > 150), None
        )
        self.assertIsNotNone(long_original)
        assert long_original is not None

        # Find corresponding splits
        splits = [
            q
            for q in split_queries
            if "split_info" in q
            and q["split_info"]["original_index"]
            == original_queries.index(long_original)
        ]

        # Each split should be shorter than the original
        for split in splits:
            assert split is not None
            self.assertLess(len(split["query"]), len(long_original["query"]))

    def test_split_queries_have_valid_boolean_operators(self):
        """Test that split queries have valid Boolean operators."""
        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["adults", "elderly"],
            interest_terms=["obesity", "diabetes"],
            context_terms=["hospital", "clinic"],
            search_config={
                "domains": ["nice.org.uk"],
                "file_types": ["pdf"],
                "query_splitting": {
                    "enabled": True,
                    "strategy": "by_pic_terms",
                    "max_query_length": 100,
                },
            },
        )

        split_queries = strategy.generate_split_queries()

        for query in split_queries:
            query_text = query["query"]

            # Check for balanced parentheses
            self.assertEqual(query_text.count("("), query_text.count(")"))

            # Check for proper AND/OR usage
            if " AND " in query_text:
                # Should have terms on both sides of AND
                parts = query_text.split(" AND ")
                for part in parts:
                    self.assertTrue(len(part.strip()) > 0)

            if " OR " in query_text:
                # Should have terms on both sides of OR
                parts = query_text.split(" OR ")
                for part in parts:
                    self.assertTrue(len(part.strip()) > 0)

    def test_split_queries_preserve_search_intent(self):
        """Test that split queries maintain the original search intent."""
        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["teenagers", "adolescents", "young adults"],
            interest_terms=["depression", "anxiety", "mental health disorders"],
            context_terms=["school", "education", "educational settings"],
            search_config={
                "domains": ["who.int"],
                "file_types": ["pdf", "doc"],
                "query_splitting": {
                    "enabled": True,
                    "strategy": "by_pic_terms",
                    "max_query_length": 50,  # Low threshold to force splitting
                },
            },
        )

        split_queries = strategy.generate_split_queries()

        # Collect all terms from splits
        all_pop_terms = set()
        all_int_terms = set()
        all_ctx_terms = set()

        for query in split_queries:
            if "split_info" in query:
                all_pop_terms.update(query["split_info"]["population"])
                all_int_terms.update(query["split_info"]["interest"])
                all_ctx_terms.update(query["split_info"]["context"])

        # All original terms should appear in splits
        self.assertEqual(set(strategy.population_terms), all_pop_terms)
        self.assertEqual(set(strategy.interest_terms), all_int_terms)
        self.assertEqual(set(strategy.context_terms), all_ctx_terms)
