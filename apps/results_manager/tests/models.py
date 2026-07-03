"""
TypedDict definitions for test data in zero-results tests.
Migrated from Pydantic during Phase 2 TypedDict migration.
"""

from datetime import datetime
from typing import Any, Dict, List, TypedDict


class TestUserData(TypedDict):
    """Model for test user data."""

    username: str
    email: str
    password: str


class TestSessionData(TypedDict):
    """Model for test session data."""

    title: str
    status: str
    owner_email: str
    total_results: int | None


class TestStrategyData(TypedDict):
    """Model for test search strategy data."""

    population_terms: List[str]
    interest_terms: List[str]
    context_terms: List[str]


class TestQueryData(TypedDict):
    """Model for test search query data."""

    query_text: str
    is_active: bool
    execution_order: int


class TestExecutionData(TypedDict):
    """Model for test search execution data."""

    status: str
    results_count: int
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None


class MockAPIResponse(TypedDict):
    """Model for mock API response data."""

    organic: List[Dict[str, Any]]
    search_parameters: Dict[str, Any]
    credits_used: int
    response_time: float


class ZeroResultsTestScenario(TypedDict):
    """Complete test scenario for zero results workflow."""

    user: TestUserData
    session: TestSessionData
    strategy: TestStrategyData
    queries: List[TestQueryData]
    expected_results: int
    expected_final_status: str


def create_zero_results_scenario() -> ZeroResultsTestScenario:
    """Factory function for zero results scenario."""
    return {
        "user": {
            "username": "test@example.com",
            "email": "test@example.com",
            "password": "testpass123",
        },
        "session": {
            "title": "Zero Results Test",
            "status": "ready_to_execute",
            "owner_email": "test@example.com",
            "total_results": None,
        },
        "strategy": {
            "population_terms": ["nonexistentterm123"],
            "interest_terms": ["doesnotexist456"],
            "context_terms": ["invalid789"],
        },
        "queries": [
            {
                "query_text": "nonexistentterm123 filetype:xyz",
                "is_active": True,
                "execution_order": 1,
            }
        ],
        "expected_results": 0,
        "expected_final_status": "completed",
    }
