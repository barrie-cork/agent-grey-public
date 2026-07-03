"""
Mock Serper API client for testing purposes.
Returns realistic but fake search results to enable E2E testing without API credentials.
"""

import logging
import time
import uuid

logger = logging.getLogger(__name__)


class MockSerperClient:
    """
    Mock implementation of SerperClient for testing.
    Returns realistic fake data that matches the expected API response format.
    Implements the SerpProvider protocol.
    """

    provider_key: str = "serper"
    display_name: str = "Serper.dev"

    def __init__(self, *args, **kwargs):
        """Initialize mock client - ignores all parameters."""
        self.api_key = "mock-key-for-testing"
        logger.warning(
            "MockSerperClient initialised. This client returns FAKE search results. "
            "If this appears in production logs, investigate immediately."
        )

    def execute_with_retry(self, query: str, api_params: dict, execution, retry_func):
        """
        Mock implementation of execute_with_retry that returns (results, metadata) tuple.
        This matches the expected interface from the real SerpQueryExecutor.
        """
        # Get search results (returns Dict)
        results = self.search(query, api_params.get("num", 10))

        # Build metadata from response
        metadata = {
            "credits_used": 1,
            "total_results": str(len(results.get("organic", [])) * 100),
            "time_taken": 0.5,
            "request_id": f"mock-{int(time.time())}-{hash(query) % 10000}",
            "response_warnings": [],
            "mock_client": True,
            "api_params": api_params.copy(),
            "query": query,
            "timestamp": time.time(),
        }

        logger.info(
            f"MockSerperClient execute_with_retry returned {len(results.get('organic', []))} results"
        )
        return results, metadata

    def safe_search(
        self, query: str, num_results: int = 10, **kwargs
    ) -> tuple[dict, dict]:
        """
        Mock safe_search method that matches the real SerperClient interface.

        Args:
            query: Search query string
            num_results: Number of results to return
            **kwargs: Additional parameters

        Returns:
            Tuple of (results, metadata)
        """
        result = self.search(query, num_results, **kwargs)
        metadata = {
            "credits_used": 1,
            "total_results": str(len(result.get("organic", [])) * 100),
            "time_taken": 0.5,
            "request_id": f"mock-{int(time.time())}-{hash(query) % 10000}",
            "response_warnings": [],
            "mock_client": True,
        }
        return result, metadata

    def search(self, query: str, num_results: int = 10, **kwargs) -> dict:
        """
        Mock search method that returns realistic fake results.

        Args:
            query: Search query string
            num_results: Number of results to return (max 10 for mock)
            **kwargs: Additional parameters (ignored in mock)

        Returns:
            Dictionary with search results (matches real SerperClient.search interface)
        """
        # Simulate API delay
        time.sleep(0.5)

        # Limit results for mock data
        actual_results = min(num_results, 10)

        # Generate mock results based on query
        mock_results = self._generate_mock_results(query, actual_results)

        response = {
            "organic": mock_results,
            "peopleAlsoAsk": self._generate_mock_paa(query),
            "relatedSearches": self._generate_mock_related(query),
            "searchParameters": {
                "q": query,
                "gl": "us",
                "hl": "en",
                "num": actual_results,
                "type": "search",
            },
        }

        logger.warning(
            f"MockSerperClient returned {len(mock_results)} FAKE results for query: {query[:50]}..."
        )
        return response

    def _generate_mock_results(self, query: str, num_results: int) -> list:
        """Generate realistic mock search results."""
        results = []

        # Keywords to customize results based on query
        is_healthcare = any(
            term in query.lower()
            for term in ["healthcare", "medical", "hospital", "covid", "ppe"]
        )
        is_academic = "filetype:pdf" in query.lower() or any(
            term in query.lower() for term in ["research", "study", "systematic review"]
        )

        base_titles = (
            [
                "Systematic Review of Healthcare Worker Safety During COVID-19",
                "Personal Protective Equipment Guidelines for Healthcare Settings",
                "Hospital Safety Protocols: A Comprehensive Analysis",
                "Healthcare Worker Mental Health During Pandemic Conditions",
                "Evidence-Based Approaches to Healthcare Safety Management",
                "Infection Control Measures in Healthcare Environments",
                "Healthcare Quality Improvement: Current Best Practices",
                "Safety Culture in Healthcare Organizations: A Meta-Analysis",
                "Healthcare Worker Training and Safety Outcomes",
                "Pandemic Preparedness in Healthcare Systems",
            ]
            if is_healthcare
            else [
                "Research Methodology in Social Sciences",
                "Data Analysis Techniques for Academic Research",
                "Systematic Literature Review Best Practices",
                "Academic Writing and Publication Guidelines",
                "Research Ethics and Methodology Standards",
                "Qualitative Research Methods Overview",
                "Statistical Analysis in Academic Research",
                "Citation Analysis and Reference Management",
                "Academic Research Database Usage",
                "Research Design and Implementation",
            ]
        )

        domains = (
            [
                "pubmed.ncbi.nlm.nih.gov",
                "scholar.google.com",
                "researchgate.net",
                "ncbi.nlm.nih.gov",
                "academic.oup.com",
                "sciencedirect.com",
                "journals.lww.com",
                "bmj.com",
                "nejm.org",
                "cochranelibrary.com",
            ]
            if is_academic
            else [
                "example-journal.com",
                "research-institute.org",
                "academic-publisher.edu",
                "university-repository.ac.uk",
                "professional-org.net",
            ]
        )

        for i in range(num_results):
            title = base_titles[i % len(base_titles)]
            domain = domains[i % len(domains)]

            result = {
                "title": title,
                "link": f"https://{domain}/article/{uuid.uuid4().hex[:8]}",
                "snippet": self._generate_snippet(query, title),
                "position": i + 1,
                "date": f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",  # Mock recent dates
            }

            # Add PDF indication for academic searches
            if is_academic and i < 3:
                result["title"] += " [PDF]"
                result["link"] = result["link"].replace(".com/", ".com/pdfs/") + ".pdf"

            results.append(result)

        return results

    def _generate_snippet(self, query: str, title: str) -> str:
        """Generate realistic snippet text."""
        query_terms = (
            query.replace('"', "")
            .replace("(", "")
            .replace(")", "")
            .replace("filetype:pdf", "")
            .split()
        )
        key_terms = [
            term
            for term in query_terms
            if len(term) > 3 and term.upper() not in ["AND", "OR"]
        ][:3]

        if key_terms:
            focus_term = key_terms[-1] if len(key_terms) > 2 else "best practices"
            return (
                f"This study examines {' and '.join(key_terms[:2])} with focus on {focus_term}. "
                "The research provides comprehensive analysis and evidence-based recommendations for implementation."
            )
        else:
            return (
                "Comprehensive research analysis providing evidence-based insights "
                "and practical recommendations for implementation in professional settings."
            )

    def _generate_mock_paa(self, query: str) -> list:
        """Generate mock People Also Ask questions."""
        return [
            {
                "question": f"What are the best practices for {query.split()[0].lower()}?"
            },
            {"question": f"How does {query.split()[0].lower()} impact outcomes?"},
            {"question": f"What research exists on {query.split()[0].lower()}?"},
        ]

    def _generate_mock_related(self, query: str) -> list:
        """Generate mock related searches."""
        base_term = query.split()[0].lower() if query.split() else "research"
        return [
            {"query": f"{base_term} best practices"},
            {"query": f"{base_term} systematic review"},
            {"query": f"{base_term} evidence based"},
            {"query": f"{base_term} guidelines"},
        ]

    def health_check(self) -> bool:
        """Mock health check always returns True."""
        return True

    def get_rate_limit_key(self) -> str:
        """Return Redis key prefix for mock rate limiting."""
        return f"rate_limit:{self.provider_key}"


def get_serper_client(*args, **kwargs):
    """
    Factory function that returns either real or mock client.

    In production/staging: Always returns real SerperClient.
    Raises ImproperlyConfigured if SERPER_API_KEY is missing.

    In local/test: Returns MockSerperClient when API key is
    missing, contains 'development'/'test', or ENABLE_SERPER_MOCKING is True.
    """
    from django.conf import settings
    from django.core.exceptions import ImproperlyConfigured

    environment = getattr(settings, "ENVIRONMENT", "")
    api_key = getattr(settings, "SERPER_API_KEY", "")
    enable_mocking = getattr(settings, "ENABLE_SERPER_MOCKING", False)

    is_prod = environment in ("production", "staging")

    # Production/staging: never allow mock client, require an API key
    if is_prod and not api_key:
        raise ImproperlyConfigured(
            f"SERPER_API_KEY is required in {environment} but is empty or missing. "
            "Configure it in DigitalOcean App Platform environment variables."
        )

    # Local/test only: allow mock when appropriate
    should_mock = not is_prod and (
        enable_mocking
        or not api_key
        or "development" in api_key.lower()
        or "test" in api_key.lower()
        or api_key == "development-test-key-replace-with-real-key"
    )

    if should_mock:
        logger.warning(
            "Using MockSerperClient for API calls (environment=%s). "
            "Set SERPER_API_KEY to use real search results.",
            environment or "unknown",
        )
        return MockSerperClient(*args, **kwargs)

    from apps.core.services.serper_client import SerperClient

    logger.info(
        "Using real SerperClient for API calls (environment=%s)",
        environment or "unknown",
    )
    return SerperClient(*args, **kwargs)
