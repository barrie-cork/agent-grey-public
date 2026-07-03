"""
Test PRISMA 2020 compliance for exclusion reason reporting.

This test suite validates that the PRISMA diagram generation properly
displays detailed exclusion reasons according to PRISMA 2020 guidelines.
"""

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.reporting.services.prisma_reporting_service import PrismaReportingService
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.review_results.models import SimpleReviewDecision
from apps.core.tests.utils import create_test_user

User = get_user_model()


class PRISMAComplianceTestCase(TestCase):
    """Test PRISMA 2020 compliance for detailed exclusion reporting."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()

        # Create a search session
        self.session = SearchSession.objects.create(
            title="Test Systematic Review",
            description="A test systematic review for PRISMA compliance",
            owner=self.user,
            status="completed",
        )

        # Create test processed results
        self.results = []
        for i in range(10):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Test Result {i + 1}",
                url=f"https://example.com/paper{i + 1}",
                snippet=f"This is a test snippet for result {i + 1}",
            )
            self.results.append(result)

        # Create exclusion decisions with different reasons
        exclusion_data = [
            (0, "not_relevant"),
            (1, "not_relevant"),
            (2, "not_grey_lit"),
            (3, "duplicate"),
            (4, "no_access"),
            (5, "wrong_document_type"),
            (6, "language"),
            (7, "wrong_population"),
            (8, "other"),
        ]

        for result_idx, reason in exclusion_data:
            SimpleReviewDecision.objects.create(
                result=self.results[result_idx],
                session=self.session,
                reviewer=self.user,
                decision="exclude",
                exclusion_reason=reason,
                notes=f"Test exclusion for {reason}",
            )

        # Create one inclusion decision
        SimpleReviewDecision.objects.create(
            result=self.results[9],
            session=self.session,
            reviewer=self.user,
            decision="include",
            notes="This result meets inclusion criteria",
        )

        self.service = PrismaReportingService()

    def test_exclusion_reasons_aggregation(self):
        """Test that exclusion reasons are properly aggregated."""
        exclusion_reasons = self.service.get_exclusion_reasons(str(self.session.id))

        # Verify all exclusion categories are present
        expected_reasons = {
            "Not relevant to research question": 2,
            "Not grey literature": 1,
            "Duplicate result": 1,
            "Full text unavailable": 1,
            "Inappropriate document type": 1,
            "Language other than English": 1,
            "Wrong population": 1,
            "Other reason": 1,
        }

        self.assertEqual(exclusion_reasons, expected_reasons)
        self.assertEqual(sum(exclusion_reasons.values()), 9)  # Total exclusions

    def test_prisma_flow_data_includes_exclusion_reasons(self):
        """Test that PRISMA flow data includes detailed exclusion reasons."""
        with patch(
            "apps.reporting.services.prisma_reporting_service.get_session_data"
        ) as mock_session:
            mock_session.return_value = {
                "id": str(self.session.id),
                "title": self.session.title,
                "created_at": self.session.created_at.isoformat(),
            }

            flow_data = self.service.generate_prisma_flow_data(str(self.session.id))

            # Verify exclusion reasons are included
            self.assertIn("eligibility", flow_data)
            self.assertIn("exclusion_reasons", flow_data["eligibility"])

            exclusion_reasons = flow_data["eligibility"]["exclusion_reasons"]
            self.assertIsInstance(exclusion_reasons, dict)
            self.assertGreater(len(exclusion_reasons), 0)

            # Verify specific exclusion categories
            self.assertIn("Not relevant to research question", exclusion_reasons)
            self.assertEqual(exclusion_reasons["Not relevant to research question"], 2)

    def test_prisma_2020_structure_compliance(self):
        """Test that flow data follows PRISMA 2020 structure."""
        with patch(
            "apps.reporting.services.prisma_reporting_service.get_session_data"
        ) as mock_session:
            mock_session.return_value = {
                "id": str(self.session.id),
                "title": self.session.title,
                "created_at": self.session.created_at.isoformat(),
            }

            flow_data = self.service.generate_prisma_flow_data(str(self.session.id))

            # Verify PRISMA 2020 nested structure
            required_sections = [
                "identification",
                "screening",
                "retrieval",
                "eligibility",
                "included",
            ]
            for section in required_sections:
                self.assertIn(
                    section, flow_data, f"Missing required PRISMA section: {section}"
                )

            # Verify eligibility section has exclusion details
            eligibility = flow_data["eligibility"]
            self.assertIn("exclusion_reasons", eligibility)
            self.assertIn("excluded", eligibility)

            # Verify exclusion count matches
            total_excluded = sum(eligibility["exclusion_reasons"].values())
            self.assertEqual(total_excluded, eligibility["excluded"])

    def test_exclusion_reason_mapping_from_notes(self):
        """Test that exclusion reasons are properly mapped from free-text notes."""
        # Create additional result with reason in notes instead of choice field
        result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result with Notes",
            url="https://example.com/notes-test",
            snippet="Test snippet",
        )

        # Create decision with reason in notes
        SimpleReviewDecision.objects.create(
            result=result,
            session=self.session,
            reviewer=self.user,
            decision="exclude",
            exclusion_reason="not_relevant",
            notes="This paper is not relevant to our research question",
        )

        # Test exclusion reason extraction
        exclusion_reasons = self.service.get_exclusion_reasons(str(self.session.id))

        # Verify the notes-based exclusion was mapped correctly
        self.assertIn("Not relevant to research question", exclusion_reasons)
        # Should now be 3 (2 from choice field + 1 from notes)
        self.assertEqual(exclusion_reasons["Not relevant to research question"], 3)

    def test_empty_exclusion_reasons_handling(self):
        """Test handling of sessions with no exclusions."""
        # Create a new session with no exclusions
        empty_session = SearchSession.objects.create(
            title="Empty Review",
            description="A review with no exclusions",
            owner=self.user,
            status="under_review",
        )

        exclusion_reasons = self.service.get_exclusion_reasons(str(empty_session.id))
        self.assertEqual(exclusion_reasons, {})

        # Test flow data generation
        with patch(
            "apps.reporting.services.prisma_reporting_service.get_session_data"
        ) as mock_session:
            mock_session.return_value = {
                "id": str(empty_session.id),
                "title": empty_session.title,
                "created_at": empty_session.created_at.isoformat(),
            }

            flow_data = self.service.generate_prisma_flow_data(str(empty_session.id))
            self.assertEqual(flow_data["eligibility"]["exclusion_reasons"], {})

    def test_prisma_diagram_data_format(self):
        """Test that data format is compatible with frontend canvas rendering."""
        with patch(
            "apps.reporting.services.prisma_reporting_service.get_session_data"
        ) as mock_session:
            mock_session.return_value = {
                "id": str(self.session.id),
                "title": self.session.title,
                "created_at": self.session.created_at.isoformat(),
            }

            flow_data = self.service.generate_prisma_flow_data(str(self.session.id))

            # Test that data can be serialized to JSON (required for template rendering)
            try:
                json_data = json.dumps(flow_data)
                self.assertIsNotNone(json_data)
            except TypeError as e:
                self.fail(f"Flow data is not JSON serializable: {e}")

            # Verify exclusion_reasons is a dictionary of strings to integers
            exclusion_reasons = flow_data["eligibility"]["exclusion_reasons"]
            for reason, count in exclusion_reasons.items():
                self.assertIsInstance(reason, str)
                self.assertIsInstance(count, int)
                self.assertGreater(count, 0)

    def test_prisma_compliance_standards(self):
        """Test compliance with PRISMA 2020 reporting standards."""
        exclusion_reasons = self.service.get_exclusion_reasons(str(self.session.id))

        # PRISMA requires specific categories of exclusion reasons
        # Verify we have clear, standardized reason names
        for reason_name in exclusion_reasons.keys():
            self.assertIsInstance(reason_name, str)
            self.assertGreater(len(reason_name), 5)  # Meaningful description
            self.assertNotIn("unknown", reason_name.lower())  # No vague reasons

        # Verify exclusion counts are reasonable
        total_exclusions = sum(exclusion_reasons.values())
        self.assertGreater(total_exclusions, 0)
        self.assertLessEqual(total_exclusions, 20)  # Reasonable upper bound for test

        # Verify most common exclusion reason tracking
        analysis = self.service.analyze_exclusion_reasons(str(self.session.id))
        self.assertIn("most_common_reason", analysis)
        self.assertIn("total_exclusions", analysis)
        self.assertEqual(analysis["total_exclusions"], total_exclusions)
