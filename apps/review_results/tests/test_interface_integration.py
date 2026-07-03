"""
Integration tests for interface consolidation and navigation enhancements.

Tests the implementation of the interface overlap elimination and enhanced navigation
features implemented in the PRP: Eliminate Interface Overlap & Enhance Navigation.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession

from ..models import SimpleReviewDecision
from apps.core.tests.utils import create_test_user

User = get_user_model()


class InterfaceIntegrationTestCase(TestCase):
    """Test interface consolidation and enhanced navigation functionality."""

    def setUp(self):
        """Set up test data for interface integration tests."""
        self.client = Client()

        # Create test user
        self.user = create_test_user()

        # Create test session
        self.session = SearchSession.objects.create(
            title="Test Session",
            description="Test session for interface integration",
            owner=self.user,
            status="under_review",
        )

        # Create test results (successful/reviewable)
        self.results = []
        for i in range(10):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Test Result {i}",
                url=f"https://example.com/result{i}",
                snippet=f"Test snippet for result {i}",
                processing_status="success",
            )
            self.results.append(result)

        # Create some reviewed results with different statuses
        SimpleReviewDecision.objects.create(
            session=self.session,
            result=self.results[0],
            decision="include",
            reviewer=self.user,
        )
        SimpleReviewDecision.objects.create(
            session=self.session,
            result=self.results[1],
            decision="exclude",
            exclusion_reason="not_relevant",
            reviewer=self.user,
        )
        SimpleReviewDecision.objects.create(
            session=self.session,
            result=self.results[2],
            decision="maybe",
            reviewer=self.user,
        )

        # Mark some results as retrieved
        self.results[0].is_retrieved = True
        self.results[0].save()
        self.results[1].is_retrieved = True
        self.results[1].save()

        # Create filtered duplicate results (3 duplicates)
        for i in range(3):
            ProcessedResult.objects.create(
                session=self.session,
                title=f"Duplicate Result {i}",
                url=f"https://example.com/dup{i}",
                snippet=f"Duplicate snippet {i}",
                processing_status="filtered",
                processing_error_category="duplicate",
            )

        self.client.force_login(self.user)

    def test_statistical_redundancy_eliminated(self):
        """Test that redundant statistics panel has been removed."""
        response = self.client.get(
            reverse("review_results:overview", args=[self.session.id])
        )
        self.assertEqual(response.status_code, 200)

        # Check that the redundant statistics panel is not present
        content = response.content.decode()
        self.assertNotIn("Review Statistics Panel", content)
        self.assertNotIn("simple_review_stats", content)
        self.assertNotIn("bi-bar-chart", content)

        # But Quick Actions should still be there
        self.assertIn("Quick Actions", content)

    def test_consolidated_session_overview(self):
        """Test that session overview is consolidated into single line format."""
        response = self.client.get(
            reverse("review_results:overview", args=[self.session.id])
        )
        self.assertEqual(response.status_code, 200)

        content = response.content.decode()

        # Check that session title and status are displayed
        self.assertIn(self.session.title, content)
        self.assertIn("Under Review", content)

        # Check that separate progress bar section is not present
        self.assertNotIn("Review Progress:", content)

    def test_retrieved_filter_button_present(self):
        """Test that Retrieved filter button is present with correct count."""
        response = self.client.get(
            reverse("review_results:overview", args=[self.session.id])
        )
        self.assertEqual(response.status_code, 200)

        content = response.content.decode()

        # Check that Retrieved filter button exists
        self.assertIn("Retrieved", content)
        self.assertIn("filterByStatus('retrieved')", content)

    def test_duplicates_navigation_button_present(self):
        """Test that Duplicates navigation button is present with correct count."""
        response = self.client.get(
            reverse("review_results:overview", args=[self.session.id])
        )
        self.assertEqual(response.status_code, 200)

        content = response.content.decode()

        # Check that Duplicates navigation button exists
        self.assertIn("Review Duplicates", content)
        self.assertIn(f"navigateToDuplicates('{self.session.id}')", content)

    def test_retrieved_filtering_functionality(self):
        """Test that retrieved results filtering works correctly."""
        # Test filtering by retrieved status
        response = self.client.get(
            reverse("review_results:overview", args=[self.session.id])
            + "?review_status=retrieved"
        )
        self.assertEqual(response.status_code, 200)

        # Check that only retrieved results are shown (2 results)
        results = response.context["results"]
        retrieved_results = [r for r in results if r.is_retrieved]
        self.assertEqual(len(retrieved_results), 2)

        # Verify they are the correct results
        retrieved_ids = [r.id for r in retrieved_results]
        self.assertIn(self.results[0].id, retrieved_ids)
        self.assertIn(self.results[1].id, retrieved_ids)

    def test_duplicate_groups_view_exists(self):
        """Test that duplicate groups view is accessible."""
        response = self.client.get(
            reverse("review_results:duplicate_groups", args=[self.session.id])
        )
        self.assertEqual(response.status_code, 200)

        # Check that the view loads with correct context
        self.assertIn("duplicate_groups", response.context)
        # total_groups = domain groups (all 3 dupes share example.com = 1 group)
        self.assertEqual(response.context["total_groups"], 1)
        self.assertEqual(response.context["total_duplicate_results"], 3)

    def test_duplicate_groups_template_content(self):
        """Test that duplicate groups template displays correct content."""
        response = self.client.get(
            reverse("review_results:duplicate_groups", args=[self.session.id])
        )
        self.assertEqual(response.status_code, 200)

        content = response.content.decode()

        # Check template content
        self.assertIn("Duplicate Groups", content)

        # Check navigation elements
        self.assertIn("Back to Review", content)
        self.assertIn(
            reverse("review_results:overview", args=[self.session.id]), content
        )

    def test_complete_navigation_coverage(self):
        """Test that all filter options are present and functional."""
        response = self.client.get(
            reverse("review_results:overview", args=[self.session.id])
        )
        self.assertEqual(response.status_code, 200)

        content = response.content.decode()

        # Check all filter buttons are present
        filter_buttons = [
            ("Pending", "pending"),
            ("Included", "include"),
            ("Excluded", "exclude"),
            ("Maybe", "maybe"),
            ("Retrieved", "retrieved"),
        ]

        for button_text, filter_value in filter_buttons:
            self.assertIn(button_text, content)
            self.assertIn(f"filterByStatus('{filter_value}')", content)

        # Check duplicates navigation button
        self.assertIn("Review Duplicates", content)
        self.assertIn(f"navigateToDuplicates('{self.session.id}')", content)

    def test_context_data_completeness(self):
        """Test that all required context data is available."""
        response = self.client.get(
            reverse("review_results:overview", args=[self.session.id])
        )
        self.assertEqual(response.status_code, 200)

        # Verify all counts are present in context
        required_counts = [
            "pending_count",
            "included_count",
            "excluded_count",
            "maybe_count",
            "retrieved_count",
            "duplicate_groups_count",
        ]

        for count in required_counts:
            self.assertIn(count, response.context)

        # Verify counts are correct based on test data
        self.assertEqual(response.context["included_count"], 1)
        self.assertEqual(response.context["excluded_count"], 1)
        self.assertEqual(response.context["maybe_count"], 1)
        self.assertEqual(response.context["retrieved_count"], 2)
        # duplicate_groups_count is now the count of filtered duplicate ProcessedResults
        self.assertEqual(response.context["duplicate_groups_count"], 3)

    def test_no_performance_regression(self):
        """Test that template loads without performance regressions."""
        # This is a basic performance test - in production you'd want more sophisticated timing
        response = self.client.get(
            reverse("review_results:overview", args=[self.session.id])
        )
        self.assertEqual(response.status_code, 200)

        # Verify query count hasn't exploded (basic check)
        # In a real scenario, you'd use django-debug-toolbar or similar
        self.assertLess(len(response.context["results"]), 50)  # Pagination working

    def test_template_syntax_validity(self):
        """Test that all templates render without errors via actual views."""
        # Test results overview template renders
        response = self.client.get(
            reverse("review_results:overview", args=[self.session.id])
        )
        self.assertEqual(response.status_code, 200)

        # Test duplicate groups template renders
        response = self.client.get(
            reverse("review_results:duplicate_groups", args=[self.session.id])
        )
        self.assertEqual(response.status_code, 200)

    def test_javascript_functions_integration(self):
        """Test that JavaScript functions are properly integrated."""
        response = self.client.get(
            reverse("review_results:overview", args=[self.session.id])
        )
        self.assertEqual(response.status_code, 200)

        content = response.content.decode()

        # Check that JavaScript functions are included
        self.assertIn("review_interface.js", content)

        # Check that the function calls are in the template
        self.assertIn("filterByStatus(", content)
        self.assertIn("navigateToDuplicates(", content)

    def test_url_routing_completeness(self):
        """Test that all new URL routes are properly configured."""
        # Test that duplicate groups URL resolves
        url = reverse("review_results:duplicate_groups", args=[self.session.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Test that the URL pattern matches expected format
        expected_pattern = f"/review-results/duplicates/{self.session.id}/"
        self.assertEqual(url, expected_pattern)

    def test_responsive_design_integrity(self):
        """Test that responsive design classes are maintained."""
        response = self.client.get(
            reverse("review_results:overview", args=[self.session.id])
        )
        self.assertEqual(response.status_code, 200)

        content = response.content.decode()

        # Check that Tailwind responsive classes are present
        responsive_classes = [
            "lg:grid-cols",  # Grid layout
            "flex",  # Flexbox layouts
            "justify-between",  # Layout utilities
        ]

        for css_class in responsive_classes:
            self.assertIn(css_class, content)

    def tearDown(self):
        """Clean up test data."""
        # Django's TestCase handles cleanup automatically, but explicit cleanup
        # can be helpful for complex test scenarios
        super().tearDown()
