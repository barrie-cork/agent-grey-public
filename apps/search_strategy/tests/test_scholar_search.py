"""Tests for Google Scholar search execution and search_types config.

Covers:
- Form stores search_types as a list (both Google and Scholar can be selected)
- Backward compatibility with legacy search_type string
- Execution task iterates over search_types
- SerperClient uses correct API endpoint per search_type
- max_results enforcement through pagination config forwarding
"""

from unittest.mock import Mock, patch

from django.test import TestCase

from apps.core.tests.utils import create_test_user
from apps.review_manager.models import SearchSession
from apps.search_strategy.forms import SearchStrategyForm
from apps.search_strategy.models import SearchStrategy


class SearchTypesFormTests(TestCase):
    """Test that the form stores search_types as a list."""

    def setUp(self):
        self.user = create_test_user(username_prefix="scholar_test")
        self.session = SearchSession.objects.create(
            title="Scholar Test", owner=self.user
        )

    def _base_form_data(self, **overrides):
        data = {
            "population_terms_text": "healthcare workers",
            "interest_terms_text": "training",
            "context_terms_text": "",
            "organization_domains": "",
            "include_general_search": True,
            "include_guidelines_filter": False,
            "search_pdf": False,
            "search_doc": False,
            "use_google_search": True,
            "use_google_scholar": False,
            "max_results_per_query": 20,
            "enable_query_splitting": False,
            "splitting_strategy": "by_pic_terms",
            "max_query_length": 2000,
            "serp_providers": ["serper"],
        }
        data.update(overrides)
        return data

    def test_google_only_stores_search_types_list(self):
        """When only Google is checked, search_types is ['google']."""
        form = SearchStrategyForm(data=self._base_form_data())
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        config = form.cleaned_data["search_config"]
        self.assertEqual(config["search_types"], ["google"])
        self.assertNotIn("search_type", config)

    def test_scholar_only_stores_search_types_list(self):
        """When only Scholar is checked, search_types is ['scholar']."""
        form = SearchStrategyForm(
            data=self._base_form_data(use_google_search=False, use_google_scholar=True)
        )
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        config = form.cleaned_data["search_config"]
        self.assertEqual(config["search_types"], ["scholar"])

    def test_both_google_and_scholar_stores_both(self):
        """When both are checked, search_types contains both."""
        form = SearchStrategyForm(
            data=self._base_form_data(use_google_search=True, use_google_scholar=True)
        )
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        config = form.cleaned_data["search_config"]
        self.assertEqual(config["search_types"], ["google", "scholar"])

    def test_neither_checked_defaults_to_google(self):
        """When neither is checked, defaults to ['google']."""
        form = SearchStrategyForm(
            data=self._base_form_data(use_google_search=False, use_google_scholar=False)
        )
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        config = form.cleaned_data["search_config"]
        self.assertEqual(config["search_types"], ["google"])

    def test_max_results_stored_correctly(self):
        """max_results from form input is stored in search_config."""
        form = SearchStrategyForm(data=self._base_form_data(max_results_per_query=20))
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        config = form.cleaned_data["search_config"]
        self.assertEqual(config["max_results"], 20)

    def test_backward_compat_legacy_search_type_in_init(self):
        """Form init reads legacy search_type string into checkboxes."""
        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            search_config={"search_type": "scholar", "domains": [], "file_types": []},
        )
        form = SearchStrategyForm(instance=strategy)
        self.assertTrue(form.fields["use_google_scholar"].initial)
        self.assertFalse(form.fields["use_google_search"].initial)

    def test_backward_compat_search_types_list_in_init(self):
        """Form init reads search_types list into checkboxes."""
        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            search_config={
                "search_types": ["google", "scholar"],
                "domains": [],
                "file_types": [],
            },
        )
        form = SearchStrategyForm(instance=strategy)
        self.assertTrue(form.fields["use_google_search"].initial)
        self.assertTrue(form.fields["use_google_scholar"].initial)


class SerperClientSearchTypeTests(TestCase):
    """Test that the SerperClient uses the correct API endpoint per search_type."""

    def setUp(self):
        mock_rate_limiter = Mock()
        mock_rate_limiter.can_proceed.return_value = True

        from apps.core.services.serper_client import SerperClient

        self.client_instance = SerperClient(
            config={
                "api_key": "test-key",
                "timeout": 30,
                "base_url": "https://google.serper.dev/search",
                "cache_timeout": 3600,
                "enable_caching": False,
            },
            rate_limiter=mock_rate_limiter,
            cache_manager=Mock(),
        )

    @patch("apps.core.services.serper_client.requests.post")
    def test_default_search_type_uses_search_endpoint(self, mock_post):
        """Without search_type, requests go to /search endpoint."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"organic": []}
        mock_response.headers = {}
        mock_post.return_value = mock_response

        self.client_instance._search_single_page("test query", 10, None, page=1)

        call_url = mock_post.call_args[0][0]
        self.assertEqual(call_url, "https://google.serper.dev/search")

    @patch("apps.core.services.serper_client.requests.post")
    def test_scholar_search_type_uses_scholar_endpoint(self, mock_post):
        """search_type='scholar' routes to /scholar endpoint."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"organic": []}
        mock_response.headers = {}
        mock_post.return_value = mock_response

        self.client_instance._search_single_page(
            "test query", 10, None, page=1, search_type="scholar"
        )

        call_url = mock_post.call_args[0][0]
        self.assertEqual(call_url, "https://google.serper.dev/scholar")

    @patch("apps.core.services.serper_client.requests.post")
    def test_search_type_preserved_across_pagination(self, mock_post):
        """search_type kwarg is preserved across multiple pages."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "organic": [
                {"title": f"Result {i}", "link": f"https://example.com/{i}"}
                for i in range(10)
            ],
            "searchInformation": {"totalResults": "100"},
        }
        mock_response.headers = {}
        mock_post.return_value = mock_response

        pagination_config = {
            "enabled": True,
            "results_per_page": 10,
            "max_pages": 2,
            "delay_between_pages": 0,
        }
        self.client_instance.search(
            "test query",
            num_results=20,
            pagination_config=pagination_config,
            search_type="scholar",
        )

        # All API calls should go to /scholar
        for call in mock_post.call_args_list:
            self.assertEqual(call[0][0], "https://google.serper.dev/scholar")


class ExecutionTaskSearchTypesTests(TestCase):
    """Test that execution task iterates over search_types."""

    def setUp(self):
        self.user = create_test_user(username_prefix="exec_test")
        self.session = SearchSession.objects.create(
            title="Execution Test", owner=self.user, status="ready_to_execute"
        )

    def test_search_types_backward_compat_from_legacy_config(self):
        """Execution reads search_types from legacy search_type string."""
        from apps.serp_execution.tasks.simple_tasks import (
            execute_search_session_simple,
        )

        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["elderly"],
            interest_terms=["care"],
            search_config={
                "search_type": "scholar",
                "domains": [],
                "include_general_search": True,
                "file_types": [],
                "max_results": 20,
                "serp_providers": ["serper"],
            },
        )

        from apps.search_strategy.models import SearchQuery

        SearchQuery.objects.create(
            strategy=strategy,
            session=self.session,
            query_text="test query",
            is_active=True,
        )

        # Patch the provider to capture the search_type kwarg
        mock_provider = Mock()
        mock_provider.provider_key = "serper"
        mock_provider.safe_search.return_value = (
            {"organic": []},
            {"total_results": "0"},
        )

        with (
            patch(
                "apps.serp_execution.providers.get_provider",
                return_value=mock_provider,
            ),
            patch(
                "apps.serp_execution.providers.get_provider_display_name",
                return_value="Serper.dev",
            ),
        ):
            result = execute_search_session_simple(str(self.session.id))

        # Verify safe_search was called with search_type="scholar"
        self.assertTrue(result["success"])
        call_kwargs = mock_provider.safe_search.call_args[1]
        self.assertEqual(call_kwargs["search_type"], "scholar")

    def test_both_search_types_executes_twice_per_query(self):
        """Both Google and Scholar selected = 2x executions per query."""
        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["elderly"],
            interest_terms=["care"],
            search_config={
                "search_types": ["google", "scholar"],
                "domains": [],
                "include_general_search": True,
                "file_types": [],
                "max_results": 20,
                "serp_providers": ["serper"],
            },
        )

        from apps.search_strategy.models import SearchQuery

        SearchQuery.objects.create(
            strategy=strategy,
            session=self.session,
            query_text="test query",
            is_active=True,
        )

        mock_provider = Mock()
        mock_provider.provider_key = "serper"
        mock_provider.safe_search.return_value = (
            {"organic": []},
            {"total_results": "0"},
        )

        with (
            patch(
                "apps.serp_execution.providers.get_provider",
                return_value=mock_provider,
            ),
            patch(
                "apps.serp_execution.providers.get_provider_display_name",
                return_value="Serper.dev",
            ),
            patch(
                "apps.serp_execution.tasks.simple_tasks.process_session_results_simple"
            ),
        ):
            from apps.serp_execution.tasks.simple_tasks import (
                execute_search_session_simple,
            )

            result = execute_search_session_simple(str(self.session.id))

        # Should have been called twice: once for google, once for scholar
        self.assertEqual(mock_provider.safe_search.call_count, 2)

        # Check search_type values
        search_types_used = [
            call[1]["search_type"] for call in mock_provider.safe_search.call_args_list
        ]
        self.assertEqual(search_types_used, ["search", "scholar"])
        self.assertEqual(result["queries_executed"], 2)
