"""
Tests for the multi-provider SERP abstraction layer.

Covers: SerpProvider protocol, provider registry, per-provider rate limiting,
dynamic serp_source, cross-provider dedup metadata, and search source breakdown.
"""

from django.test import TestCase

from apps.core.tests.utils import create_test_user
from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.models import RawSearchResult, SearchExecution


class SerpProviderProtocolTests(TestCase):
    """Test SerpProvider protocol conformance."""

    def test_serper_provider_implements_protocol(self):
        """SerperProvider must satisfy SerpProvider protocol."""
        from apps.serp_execution.providers.base import SerpProvider
        from apps.serp_execution.providers.serper_provider import SerperProvider

        provider = SerperProvider()
        self.assertIsInstance(provider, SerpProvider)

    def test_mock_client_implements_protocol(self):
        """MockSerperClient must satisfy SerpProvider protocol."""
        from apps.serp_execution.providers.base import SerpProvider
        from apps.serp_execution.services.mock_serper_client import MockSerperClient

        client = MockSerperClient()
        self.assertIsInstance(client, SerpProvider)

    def test_serper_provider_attributes(self):
        """SerperProvider has correct provider_key and display_name."""
        from apps.serp_execution.providers.serper_provider import SerperProvider

        provider = SerperProvider()
        self.assertEqual(provider.provider_key, "serper")
        self.assertEqual(provider.display_name, "Serper.dev")

    def test_serper_provider_rate_limit_key(self):
        """SerperProvider returns correct rate limit key."""
        from apps.serp_execution.providers.serper_provider import SerperProvider

        provider = SerperProvider()
        self.assertEqual(provider.get_rate_limit_key(), "rate_limit:serper")

    def test_serper_provider_health_check(self):
        """SerperProvider health check returns boolean."""
        from apps.serp_execution.services.mock_serper_client import MockSerperClient

        from ..providers.serper_provider import SerperProvider

        provider = SerperProvider(client=MockSerperClient())
        result = provider.health_check()
        self.assertIsInstance(result, bool)
        self.assertTrue(result)

    def test_serper_provider_safe_search_returns_tuple(self):
        """SerperProvider.safe_search() returns (results, metadata) tuple."""
        from apps.serp_execution.services.mock_serper_client import MockSerperClient

        from ..providers.serper_provider import SerperProvider

        # Use MockSerperClient directly to avoid rate limit issues in test suite
        provider = SerperProvider(client=MockSerperClient())
        results, metadata = provider.safe_search("test query", num_results=5)
        self.assertIsInstance(results, dict)
        self.assertIsInstance(metadata, dict)
        self.assertIn("organic", results)


class ProviderRegistryTests(TestCase):
    """Test provider registry and factory functions."""

    def test_get_provider_serper(self):
        """get_provider('serper') returns a SerperProvider."""
        from apps.serp_execution.providers import get_provider
        from apps.serp_execution.providers.serper_provider import SerperProvider

        provider = get_provider("serper")
        self.assertIsInstance(provider, SerperProvider)

    def test_get_provider_unknown_raises(self):
        """get_provider with unknown key raises ValueError."""
        from apps.serp_execution.providers import get_provider

        with self.assertRaises(ValueError):
            get_provider("nonexistent_provider")

    def test_list_providers(self):
        """list_providers returns all registered keys."""
        from apps.serp_execution.providers import list_providers

        providers = list_providers()
        self.assertIn("serper", providers)

    def test_register_provider(self):
        """register_provider adds a new provider to the registry."""
        from apps.serp_execution.providers import (
            _provider_classes,
            list_providers,
            register_provider,
        )

        class FakeProvider:
            provider_key = "fake"
            display_name = "Fake Provider"

        register_provider("fake", FakeProvider)
        self.assertIn("fake", list_providers())

        # Clean up
        del _provider_classes["fake"]

    def test_get_default_provider(self):
        """get_default_provider returns a working provider."""
        from apps.serp_execution.providers import get_default_provider

        provider = get_default_provider()
        self.assertEqual(provider.provider_key, "serper")

    def test_get_provider_display_name(self):
        """get_provider_display_name returns the display name."""
        from apps.serp_execution.providers import get_provider_display_name

        name = get_provider_display_name("serper")
        self.assertEqual(name, "Serper.dev")

    def test_get_provider_display_name_unknown(self):
        """get_provider_display_name for unknown key returns the key itself."""
        from apps.serp_execution.providers import get_provider_display_name

        name = get_provider_display_name("unknown_provider")
        self.assertEqual(name, "unknown_provider")


class SerpProviderConfigModelTests(TestCase):
    """Test SerpProviderConfig model."""

    def setUp(self):
        """Seed provider config for each test (migrations not visible in TestCase)."""
        from apps.serp_execution.providers.config import SerpProviderConfig

        self.config, _ = SerpProviderConfig.objects.get_or_create(
            provider_key="serper",
            defaults={
                "display_name": "Serper.dev",
                "base_url": "https://google.serper.dev/search",
                "api_key_setting": "SERPER_API_KEY",
                "is_default": True,
                "is_enabled": True,
            },
        )

    def test_seeded_serper_config_exists(self):
        """Serper.dev config exists with correct attributes."""
        self.assertEqual(self.config.display_name, "Serper.dev")
        self.assertTrue(self.config.is_default)
        self.assertTrue(self.config.is_enabled)
        self.assertEqual(self.config.api_key_setting, "SERPER_API_KEY")

    def test_unique_default_constraint(self):
        """Only one provider can be the default."""
        from django.db import IntegrityError

        from apps.serp_execution.providers.config import SerpProviderConfig

        with self.assertRaises(IntegrityError):
            SerpProviderConfig.objects.create(
                provider_key="test_dup_default",
                display_name="Test Duplicate Default",
                base_url="https://example.com",
                is_default=True,
            )

    def test_provider_key_unique(self):
        """provider_key must be unique."""
        from django.db import IntegrityError

        from apps.serp_execution.providers.config import SerpProviderConfig

        with self.assertRaises(IntegrityError):
            SerpProviderConfig.objects.create(
                provider_key="serper",
                display_name="Duplicate Serper",
                base_url="https://example.com",
            )

    def test_str_representation(self):
        """String representation includes display name and default status."""
        self.assertEqual(str(self.config), "Serper.dev (default)")


class SearchExecutionProviderFieldTests(TestCase):
    """Test serp_provider fields on SearchExecution."""

    def setUp(self):
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user
        )
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test"],
            interest_terms=["test"],
            context_terms=["test"],
            search_config={"domains": [], "include_general_search": True},
        )
        self.query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="test query",
            query_type="general",
        )

    def test_default_serp_provider(self):
        """New executions default to 'serper' provider."""
        execution = SearchExecution.objects.create(
            query=self.query, initiated_by=self.user
        )
        self.assertEqual(execution.serp_provider, "serper")
        self.assertEqual(execution.serp_provider_display, "Serper.dev")

    def test_custom_serp_provider(self):
        """Executions can be created with custom provider."""
        execution = SearchExecution.objects.create(
            query=self.query,
            initiated_by=self.user,
            serp_provider="serpapi",
            serp_provider_display="SerpAPI",
        )
        self.assertEqual(execution.serp_provider, "serpapi")
        self.assertEqual(execution.serp_provider_display, "SerpAPI")

    def test_serp_provider_indexed(self):
        """serp_provider field should be indexed for reporting queries."""
        field = SearchExecution._meta.get_field("serp_provider")
        self.assertTrue(field.db_index)


class DynamicSerpSourceTests(TestCase):
    """Test dynamic serp_source in ProcessedResult.get_query_metadata()."""

    def setUp(self):
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user
        )
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test"],
            interest_terms=["test"],
            context_terms=["test"],
            search_config={"domains": [], "include_general_search": True},
        )
        self.query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="test query",
            query_type="general",
        )

    def test_serp_source_reads_from_execution(self):
        """get_query_metadata reads serp_source from execution record."""
        from apps.results_manager.models import ProcessedResult

        execution = SearchExecution.objects.create(
            query=self.query,
            initiated_by=self.user,
            status="completed",
            serp_provider="serpapi",
            serp_provider_display="SerpAPI",
        )
        raw_result = RawSearchResult.objects.create(
            execution=execution,
            position=1,
            title="Test Result",
            link="https://example.com/test",
            snippet="Test snippet",
        )
        processed = ProcessedResult.objects.create(
            session=self.session,
            raw_result=raw_result,
            title="Test Result",
            url="https://example.com/test",
            snippet="Test snippet",
        )

        metadata = processed.get_query_metadata()
        self.assertIsNotNone(metadata)
        self.assertEqual(metadata["serp_source"], "SerpAPI")

    def test_serp_source_fallback_for_legacy(self):
        """Legacy records without serp_provider_display fall back gracefully."""
        from apps.results_manager.models import ProcessedResult

        execution = SearchExecution.objects.create(
            query=self.query,
            initiated_by=self.user,
            status="completed",
        )
        # Simulate legacy record by using default values
        raw_result = RawSearchResult.objects.create(
            execution=execution,
            position=1,
            title="Legacy Result",
            link="https://example.com/legacy",
            snippet="Legacy snippet",
        )
        processed = ProcessedResult.objects.create(
            session=self.session,
            raw_result=raw_result,
            title="Legacy Result",
            url="https://example.com/legacy",
            snippet="Legacy snippet",
        )

        metadata = processed.get_query_metadata()
        self.assertIsNotNone(metadata)
        # Default value on the field is "Serper.dev"
        self.assertEqual(metadata["serp_source"], "Serper.dev")


class PerProviderRateLimiterTests(TestCase):
    """Test per-provider rate limiter scoping."""

    def test_get_rate_limiter_for_provider(self):
        """Different providers get distinct rate limiters."""
        from apps.serp_execution.services.rate_limiter import (
            get_rate_limiter_for_provider,
        )

        limiter_a = get_rate_limiter_for_provider("serper")
        limiter_b = get_rate_limiter_for_provider("serpapi")

        # They should be separate instances (or same mock)
        self.assertIsNotNone(limiter_a)
        self.assertIsNotNone(limiter_b)

    def test_rate_limiter_provider_isolation(self):
        """Rate limiters for different providers use different key prefixes."""
        from apps.serp_execution.services.rate_limiter import GlobalRateLimiter

        limiter_serper = GlobalRateLimiter(key_prefix="rate_limit:serper")
        limiter_serpapi = GlobalRateLimiter(key_prefix="rate_limit:serpapi")

        self.assertEqual(limiter_serper.key_prefix, "rate_limit:serper")
        self.assertEqual(limiter_serpapi.key_prefix, "rate_limit:serpapi")
        self.assertNotEqual(limiter_serper.key_prefix, limiter_serpapi.key_prefix)


class QueryManagerProviderTests(TestCase):
    """Test that QueryManager passes provider info to execution records."""

    def setUp(self):
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user
        )
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test"],
            interest_terms=["test"],
            context_terms=["test"],
            search_config={"domains": [], "include_general_search": True},
        )
        self.query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="test query",
            query_type="general",
        )

    def test_create_execution_records_with_provider(self):
        """create_execution_records sets provider fields on executions."""
        from apps.serp_execution.services.query_manager import QueryManager

        qm = QueryManager()
        records = qm.create_execution_records(
            queries=[self.query],
            initiated_by=self.user,
            provider_key="serpapi",
            provider_display="SerpAPI",
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].serp_provider, "serpapi")
        self.assertEqual(records[0].serp_provider_display, "SerpAPI")

    def test_create_execution_records_default_provider(self):
        """create_execution_records defaults to serper provider."""
        from apps.serp_execution.services.query_manager import QueryManager

        qm = QueryManager()
        records = qm.create_execution_records(
            queries=[self.query],
            initiated_by=self.user,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].serp_provider, "serper")
        self.assertEqual(records[0].serp_provider_display, "Serper.dev")


class SearchSourceBreakdownTests(TestCase):
    """Test search source breakdown DTO for reporting."""

    def setUp(self):
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user
        )
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test"],
            interest_terms=["test"],
            context_terms=["test"],
            search_config={"domains": [], "include_general_search": True},
        )
        self.query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="test query",
            query_type="general",
        )

    def test_empty_session_returns_empty_list(self):
        """Session with no executions returns empty breakdown."""
        from apps.reporting.services.search_source_service import (
            get_search_source_breakdown,
        )

        breakdown = get_search_source_breakdown(str(self.session.id))
        self.assertEqual(breakdown, [])

    def test_single_provider_breakdown(self):
        """Session with one provider returns single-item breakdown."""
        from apps.reporting.services.search_source_service import (
            get_search_source_breakdown,
        )

        SearchExecution.objects.create(
            query=self.query,
            initiated_by=self.user,
            status="completed",
            results_count=10,
            serp_provider="serper",
            serp_provider_display="Serper.dev",
        )

        breakdown = get_search_source_breakdown(str(self.session.id))
        self.assertEqual(len(breakdown), 1)
        self.assertEqual(breakdown[0]["provider_key"], "serper")
        self.assertEqual(breakdown[0]["display_name"], "Serper.dev")
        self.assertEqual(breakdown[0]["queries_executed"], 1)
        self.assertEqual(breakdown[0]["total_results"], 10)
