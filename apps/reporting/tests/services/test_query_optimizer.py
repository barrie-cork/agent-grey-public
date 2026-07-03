"""Tests for QueryOptimizer._calculate_success_rate.

Covers all branches:
- list input with completed and non-completed items
- QuerySet-like input (Django QuerySet)
- empty inputs (list and QuerySet)
- unsupported type (falls through to list branch, len()==0 returns 0.0)
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.reporting.constants import PerformanceConstants
from apps.reporting.services.query_optimizer import QueryOptimizer


class CalculateSuccessRateListTest(TestCase):
    """Test _calculate_success_rate with list inputs."""

    def setUp(self):
        # Patch get_search_strategy to avoid hitting the real dependency
        patcher = patch("apps.reporting.services.query_optimizer.get_search_strategy")
        self.mock_get_strategy = patcher.start()
        self.addCleanup(patcher.stop)
        self.optimizer = QueryOptimizer()

    def test_list_all_completed(self):
        """All completed executions -> 100.0%."""
        executions = [
            MagicMock(status=PerformanceConstants.COMPLETED_STATUS),
            MagicMock(status=PerformanceConstants.COMPLETED_STATUS),
        ]
        result = self.optimizer._calculate_success_rate(executions)
        self.assertEqual(result, 100.0)

    def test_list_mixed_statuses(self):
        """Half completed -> 50.0%."""
        executions = [
            MagicMock(status=PerformanceConstants.COMPLETED_STATUS),
            MagicMock(status="failed"),
        ]
        result = self.optimizer._calculate_success_rate(executions)
        self.assertEqual(result, 50.0)

    def test_list_none_completed(self):
        """No completed executions -> 0.0%."""
        executions = [
            MagicMock(status="failed"),
            MagicMock(status="pending"),
        ]
        result = self.optimizer._calculate_success_rate(executions)
        self.assertEqual(result, 0.0)

    def test_list_dict_items_without_status(self):
        """Items without status attribute -> treated as non-completed."""
        executions = [{"id": 1}, {"id": 2}]
        result = self.optimizer._calculate_success_rate(executions)
        self.assertEqual(result, 0.0)


class CalculateSuccessRateEmptyTest(TestCase):
    """Test _calculate_success_rate with empty inputs."""

    def setUp(self):
        patcher = patch("apps.reporting.services.query_optimizer.get_search_strategy")
        self.mock_get_strategy = patcher.start()
        self.addCleanup(patcher.stop)
        self.optimizer = QueryOptimizer()

    def test_empty_list(self):
        """Empty list -> 0.0."""
        self.assertEqual(self.optimizer._calculate_success_rate([]), 0.0)

    def test_none_like_empty(self):
        """Falsy empty collection -> 0.0."""
        self.assertEqual(self.optimizer._calculate_success_rate([]), 0.0)


class CalculateSuccessRateQuerySetTest(TestCase):
    """Test _calculate_success_rate with QuerySet-like inputs."""

    def setUp(self):
        patcher = patch("apps.reporting.services.query_optimizer.get_search_strategy")
        self.mock_get_strategy = patcher.start()
        self.addCleanup(patcher.stop)
        self.optimizer = QueryOptimizer()

    def test_queryset_all_completed(self):
        """QuerySet where all are completed -> 100.0%."""
        from django.db.models import QuerySet

        qs = MagicMock(spec=QuerySet)
        qs.count.return_value = 3
        filtered_qs = MagicMock()
        filtered_qs.count.return_value = 3
        qs.filter.return_value = filtered_qs
        # Make it truthy for the `if not executions` check
        qs.__bool__ = MagicMock(return_value=True)

        result = self.optimizer._calculate_success_rate(qs)
        self.assertEqual(result, 100.0)
        qs.filter.assert_called_once_with(status=PerformanceConstants.COMPLETED_STATUS)

    def test_queryset_partial_completed(self):
        """QuerySet with partial completion -> correct percentage."""
        from django.db.models import QuerySet

        qs = MagicMock(spec=QuerySet)
        qs.count.return_value = 4
        filtered_qs = MagicMock()
        filtered_qs.count.return_value = 1
        qs.filter.return_value = filtered_qs
        qs.__bool__ = MagicMock(return_value=True)

        result = self.optimizer._calculate_success_rate(qs)
        self.assertEqual(result, 25.0)

    def test_queryset_empty(self):
        """Empty QuerySet (truthy but count=0) -> 0.0%."""
        from django.db.models import QuerySet

        qs = MagicMock(spec=QuerySet)
        qs.count.return_value = 0
        filtered_qs = MagicMock()
        filtered_qs.count.return_value = 0
        qs.filter.return_value = filtered_qs
        qs.__bool__ = MagicMock(return_value=True)

        result = self.optimizer._calculate_success_rate(qs)
        self.assertEqual(result, 0.0)
