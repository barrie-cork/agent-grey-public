"""
Tests for ReviewConfiguration model - Workflow #2 support.

Tests validation, workflow detection helpers, and dual-screening configuration
for PRISMA 2020 compliant independent screening.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.review_manager.models import ReviewConfiguration, SearchSession
from apps.organisation.models import Organisation
from apps.core.tests.utils import create_test_user

User = get_user_model()


class ReviewConfigurationWorkflow2TestCase(TestCase):
    """Test ReviewConfiguration for Workflow #2 support."""

    def setUp(self):
        """Create test fixtures."""
        # Create organization
        self.organisation = Organisation.objects.create(name="Test Organisation")

        # Create test user
        self.user = create_test_user(first_name="Test", last_name="User")

        # Create test sessions
        self.session1 = SearchSession.objects.create(
            title="Test Session 1",
            description="Test description",
            owner=self.user,
            organisation=self.organisation,
        )

        self.session2 = SearchSession.objects.create(
            title="Test Session 2",
            description="Test description",
            owner=self.user,
            organisation=self.organisation,
        )

    def test_workflow1_config_valid(self):
        """Workflow #1: min_reviewers=1, no resolution method required."""
        config = ReviewConfiguration.objects.create(
            session=self.session1,
            min_reviewers_per_result=1,
            created_by=self.user,
            organisation=self.organisation,
            # conflict_resolution_method has default value
        )
        # Should not raise ValidationError
        config.full_clean()
        self.assertEqual(config.min_reviewers_per_result, 1)

    def test_workflow2_config_valid(self):
        """Workflow #2: Complete configuration valid."""
        config = ReviewConfiguration.objects.create(
            session=self.session1,
            min_reviewers_per_result=2,
            conflict_resolution_method="CONSENSUS",
            blind_screening_enforced=True,
            irr_threshold=0.70,
            created_by=self.user,
            organisation=self.organisation,
        )
        config.full_clean()  # Should not raise
        self.assertEqual(config.conflict_resolution_method, "CONSENSUS")
        self.assertTrue(config.blind_screening_enforced)
        self.assertEqual(config.irr_threshold, 0.70)

    def test_irr_threshold_range_validation(self):
        """IRR threshold must be between 0.0 and 1.0."""
        config = ReviewConfiguration(
            session=self.session1,
            min_reviewers_per_result=2,
            conflict_resolution_method="CONSENSUS",
            irr_threshold=1.5,  # Invalid: > 1.0
            created_by=self.user,
            organisation=self.organisation,
        )
        with self.assertRaises(ValidationError):
            config.full_clean()

    def test_irr_threshold_negative_invalid(self):
        """IRR threshold cannot be negative."""
        config = ReviewConfiguration(
            session=self.session1,
            min_reviewers_per_result=2,
            conflict_resolution_method="CONSENSUS",
            irr_threshold=-0.1,  # Invalid: < 0.0
            created_by=self.user,
            organisation=self.organisation,
        )
        with self.assertRaises(ValidationError):
            config.full_clean()

    def test_default_values(self):
        """Test default values for new fields."""
        config = ReviewConfiguration.objects.create(
            session=self.session1,
            min_reviewers_per_result=1,
            created_by=self.user,
            organisation=self.organisation,
        )
        # Default values from model definition
        self.assertEqual(
            config.conflict_resolution_method, "LEAD_ARBITRATION"
        )  # Default
        self.assertTrue(
            config.blind_screening_enforced
        )  # Default True for PRISMA compliance
        self.assertEqual(config.irr_threshold, 0.70)  # Default PRISMA threshold

    def test_workflow_detection_workflow1(self):
        """Test workflow detection for Workflow #1."""
        config = ReviewConfiguration.objects.create(
            session=self.session1,
            min_reviewers_per_result=1,
            created_by=self.user,
            organisation=self.organisation,
        )
        self.assertFalse(config.is_workflow_2)
        self.assertEqual(config.workflow_name, "Work Distribution")

    def test_workflow_detection_workflow2(self):
        """Test workflow detection for Workflow #2."""
        config = ReviewConfiguration.objects.create(
            session=self.session1,
            min_reviewers_per_result=2,
            conflict_resolution_method="CONSENSUS",
            created_by=self.user,
            organisation=self.organisation,
        )
        self.assertTrue(config.is_workflow_2)
        self.assertEqual(config.workflow_name, "Independent Screening")

    def test_workflow_detection_triple_screening(self):
        """Test workflow detection for 3+ reviewers (also Workflow #2)."""
        config = ReviewConfiguration.objects.create(
            session=self.session1,
            min_reviewers_per_result=3,
            conflict_resolution_method="MAJORITY",
            created_by=self.user,
            organisation=self.organisation,
        )
        self.assertTrue(config.is_workflow_2)
        self.assertEqual(config.workflow_name, "Independent Screening")

    def test_resolution_method_choices(self):
        """Test all resolution method choices are valid."""
        methods = ["CONSENSUS", "LEAD_ARBITRATION", "DESIGNATED_ARBITRATOR", "MAJORITY"]

        for i, method in enumerate(methods):
            # Create a unique session for each method to avoid unique constraint violation
            session = SearchSession.objects.create(
                title=f"Test Session for {method}",
                description="Test description",
                owner=self.user,
                organisation=self.organisation,
            )
            # MAJORITY requires 3+ reviewers
            min_reviewers = 3 if method == "MAJORITY" else 2
            config = ReviewConfiguration.objects.create(
                session=session,
                min_reviewers_per_result=min_reviewers,
                conflict_resolution_method=method,
                created_by=self.user,
                organisation=self.organisation,
                # Add required fields for DESIGNATED_ARBITRATOR
                designated_arbitrator_email="arbitrator@example.com"
                if method == "DESIGNATED_ARBITRATOR"
                else "",
                designated_arbitrator_name="Dr. Arbitrator"
                if method == "DESIGNATED_ARBITRATOR"
                else "",
            )
            config.full_clean()  # Should not raise
            self.assertEqual(config.conflict_resolution_method, method)

    def test_designated_arbitrator_validation(self):
        """Test that DESIGNATED_ARBITRATOR method requires arbitrator details."""
        config = ReviewConfiguration(
            session=self.session1,
            min_reviewers_per_result=2,
            conflict_resolution_method="DESIGNATED_ARBITRATOR",
            # Missing designated_arbitrator_email and designated_arbitrator_name
            created_by=self.user,
            organisation=self.organisation,
        )
        with self.assertRaises(ValidationError) as cm:
            config.clean()
        self.assertIn("designated_arbitrator_email", str(cm.exception))

    def test_majority_resolution_validation(self):
        """Test that MAJORITY resolution method works with 3+ reviewers."""
        config = ReviewConfiguration.objects.create(
            session=self.session1,
            min_reviewers_per_result=3,
            conflict_resolution_method="MAJORITY",
            created_by=self.user,
            organisation=self.organisation,
        )
        config.full_clean()  # Should not raise
        self.assertEqual(config.conflict_resolution_method, "MAJORITY")
        self.assertEqual(config.min_reviewers_per_result, 3)

    def test_str_representation(self):
        """Test string representation includes workflow info."""
        config = ReviewConfiguration.objects.create(
            session=self.session1,
            min_reviewers_per_result=2,
            conflict_resolution_method="CONSENSUS",
            created_by=self.user,
            organisation=self.organisation,
        )
        str_repr = str(config)
        self.assertIn("Test Session 1", str_repr)
        self.assertIn("2 reviewers", str_repr)
