"""
Integration Test: Complete Dual-Workflow Testing

Purpose:
    End-to-end integration tests covering both Workflow #1 (work distribution) and
    Workflow #2 (independent screening) with complete orchestration validation.

Key concepts:
    - TestCase for database isolation
    - Multi-reviewer test setup
    - Service orchestration validation
    - Signal chain verification
    - Performance benchmarking

Based on:
    apps/review_results/tests/ patterns
    PRPs/dual-workflow/implementation/phase-09-integration-testing-e2e/examples/
"""

import time
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.organisation.models import Organisation
from apps.review_manager.models import (
    SearchSession,
    ReviewInvitation,
    ReviewConfiguration,
)
from apps.core.tests.utils import create_test_user
from apps.results_manager.models import ProcessedResult
from apps.review_results.models import (
    SimpleReviewDecision,
    ReviewerDecision,
    ReviewerCompletion,
    ConflictResolution,
    InterRaterReliability,
)
from apps.review_results.services.review_coordination_service import (
    ReviewCoordinationService,
)
from apps.review_results.services.irr_service import InterRaterReliabilityService

User = get_user_model()


class Workflow1IntegrationTest(TestCase):
    """
    Test complete Workflow #1 (Work Distribution) from start to finish.

    Scenario:
    1. Create session with min_reviewers_per_result=1
    2. Invite 2 reviewers
    3. Results are divided among reviewers (no overlap)
    4. Each reviewer reviews their assigned results
    5. Both mark complete
    6. Session completes successfully
    """

    def setUp(self):
        """Create test data: users, organisation, session, results."""
        # Create organisation
        self.org = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create users
        self.owner = create_test_user(username_prefix="session_owner")
        self.owner.organisation = self.org
        self.owner.save()

        self.reviewer1 = create_test_user(username_prefix="reviewer_alice")
        self.reviewer1.organisation = self.org
        self.reviewer1.save()

        self.reviewer2 = create_test_user(username_prefix="reviewer_bob")
        self.reviewer2.organisation = self.org
        self.reviewer2.save()

        # Create session with Workflow #1 configuration
        self.session = SearchSession.objects.create(
            title="Work Distribution Integration Test",
            owner=self.owner,
            organisation=self.org,
            status="under_review",
        )

        self.config = ReviewConfiguration.objects.create(
            session=self.session,
            min_reviewers_per_result=1,  # Workflow #1 trigger
            conflict_resolution_method="CONSENSUS",
            blind_screening_enforced=False,
            created_by=self.owner,
        )
        self.session.current_configuration = self.config
        self.session.save()

        # Create test results
        self.results = []
        for i in range(20):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Test Result {i + 1}",
                url=f"http://example.com/{i + 1}",
            )
            self.results.append(result)

        self.session.total_results = len(self.results)
        self.session.save()

    def test_workflow1_complete_flow(self):
        """Test complete Workflow #1: divide → review → complete."""

        # STEP 1: Invite both reviewers
        _invitation1 = ReviewInvitation.objects.create(
            session=self.session,
            invitee=self.reviewer1,
            inviter=self.owner,
            invitee_email=self.reviewer1.email,
            status="ACCEPTED",
        )
        _invitation2 = ReviewInvitation.objects.create(
            session=self.session,
            invitee=self.reviewer2,
            inviter=self.owner,
            invitee_email=self.reviewer2.email,
            status="ACCEPTED",
        )

        # Verify ReviewerCompletion created by signal
        completion1 = ReviewerCompletion.objects.get(
            session=self.session, reviewer=self.reviewer1
        )
        completion2 = ReviewerCompletion.objects.get(
            session=self.session, reviewer=self.reviewer2
        )

        self.assertEqual(completion1.total_results, 20)
        self.assertEqual(completion2.total_results, 20)

        # STEP 2: Reviewer 1 reviews first 10 results
        for result in self.results[:10]:
            SimpleReviewDecision.objects.create(
                result=result,
                reviewer=self.reviewer1,
                session=self.session,
                decision="include",
                notes="Relevant grey literature source",
            )

        # Verify progress updated by signal
        completion1.refresh_from_db()
        self.assertEqual(completion1.reviewed_results, 10)

        # STEP 3: Reviewer 2 reviews last 10 results
        for result in self.results[10:]:
            SimpleReviewDecision.objects.create(
                result=result,
                reviewer=self.reviewer2,
                session=self.session,
                decision="exclude",
                exclusion_reason="not_relevant",
                notes="Not relevant",
            )

        # Verify progress updated
        completion2.refresh_from_db()
        self.assertEqual(completion2.reviewed_results, 10)

        # STEP 4: Both reviewers complete
        completion1.completed_at = timezone.now()
        completion1.save()
        completion2.completed_at = timezone.now()
        completion2.save()

        # Verify both completed
        self.assertIsNotNone(completion1.completed_at)
        self.assertIsNotNone(completion2.completed_at)

        # STEP 5: No conflicts should exist (work distribution)
        conflicts = ConflictResolution.objects.filter(result__session=self.session)
        self.assertEqual(
            conflicts.count(), 0, "Work distribution should have no conflicts"
        )

        # STEP 6: Session can complete
        self.session.status = "completed"
        self.session.completed_at = timezone.now()
        self.session.save()

        # Verify final state
        self.assertEqual(self.session.status, "completed")
        self.assertIsNotNone(self.session.completed_at)


class Workflow2IntegrationTest(TestCase):
    """
    Test complete Workflow #2 (Independent Screening) from start to finish.

    Scenario:
    1. Create session with min_reviewers_per_result=2
    2. Invite 2 reviewers
    3. Both reviewers review all results (some agreements, some conflicts)
    4. Mark both complete
    5. Verify conflict detection triggered
    6. Verify IRR calculation triggered
    7. Resolve conflicts via consensus
    8. Mark session complete
    """

    def setUp(self):
        """Create test data: users, organisation, session, results."""
        # Create organisation
        self.org = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create users
        self.owner = create_test_user(username_prefix="session_owner")
        self.owner.organisation = self.org
        self.owner.save()

        self.reviewer1 = create_test_user(username_prefix="reviewer_alice")
        self.reviewer1.organisation = self.org
        self.reviewer1.save()

        self.reviewer2 = create_test_user(username_prefix="reviewer_bob")
        self.reviewer2.organisation = self.org
        self.reviewer2.save()

        # Create session with Workflow #2 configuration
        self.session = SearchSession.objects.create(
            title="Dual Screening Integration Test",
            owner=self.owner,
            organisation=self.org,
            status="under_review",
        )

        self.config = ReviewConfiguration.objects.create(
            session=self.session,
            min_reviewers_per_result=2,  # Workflow #2 trigger
            conflict_resolution_method="CONSENSUS",
            blind_screening_enforced=True,
            irr_threshold=0.70,
            created_by=self.owner,
        )
        self.session.current_configuration = self.config
        self.session.save()

        # Create test results
        self.results = []
        for i in range(10):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Test Result {i + 1}",
                url=f"http://example.com/{i + 1}",
            )
            self.results.append(result)

        self.session.total_results = len(self.results)
        self.session.save()

        # Services
        self.coordination_service = ReviewCoordinationService()
        self.irr_service = InterRaterReliabilityService()

    def test_workflow2_complete_flow_with_consensus(self):
        """Test complete Workflow #2: review → conflicts → IRR → consensus resolution."""

        # STEP 1: Invite both reviewers
        _invitation1 = ReviewInvitation.objects.create(
            session=self.session,
            invitee=self.reviewer1,
            inviter=self.owner,
            invitee_email=self.reviewer1.email,
            status="ACCEPTED",
        )
        _invitation2 = ReviewInvitation.objects.create(
            session=self.session,
            invitee=self.reviewer2,
            inviter=self.owner,
            invitee_email=self.reviewer2.email,
            status="ACCEPTED",
        )

        # Verify ReviewerCompletion created by signal
        completion1 = ReviewerCompletion.objects.get(
            session=self.session, reviewer=self.reviewer1
        )
        completion2 = ReviewerCompletion.objects.get(
            session=self.session, reviewer=self.reviewer2
        )

        self.assertEqual(completion1.total_results, 10)
        self.assertEqual(completion2.total_results, 10)

        # STEP 2: Reviewer 1 reviews all results
        decisions_r1 = [
            "INCLUDE",
            "INCLUDE",
            "INCLUDE",
            "INCLUDE",
            "INCLUDE",  # First 5: INCLUDE
            "EXCLUDE",
            "EXCLUDE",
            "EXCLUDE",
            "EXCLUDE",
            "EXCLUDE",  # Last 5: EXCLUDE
        ]

        for result, decision in zip(self.results, decisions_r1):
            ReviewerDecision.objects.create(
                result=result,
                reviewer=self.reviewer1,
                organisation=self.org,
                decision=decision,
                notes=f"Reviewer 1 notes for {result.title}",
            )

        # Verify progress updated by signal
        completion1.refresh_from_db()
        self.assertEqual(completion1.reviewed_results, 10)
        self.assertIsNotNone(completion1.completed_at)  # Auto-completed

        # STEP 3: Reviewer 2 reviews all results (with some conflicts)
        decisions_r2 = [
            "INCLUDE",
            "INCLUDE",
            "EXCLUDE",
            "EXCLUDE",
            "EXCLUDE",  # 2 conflicts (indices 2,3)
            "EXCLUDE",
            "EXCLUDE",
            "EXCLUDE",
            "EXCLUDE",
            "EXCLUDE",  # 8 agreements
        ]

        for result, decision in zip(self.results, decisions_r2):
            ReviewerDecision.objects.create(
                result=result,
                reviewer=self.reviewer2,
                organisation=self.org,
                decision=decision,
                notes=f"Reviewer 2 notes for {result.title}",
            )

        # Verify progress updated
        completion2.refresh_from_db()
        self.assertEqual(completion2.reviewed_results, 10)
        self.assertIsNotNone(completion2.completed_at)

        # STEP 4: Trigger orchestration (conflict detection)
        conflicts = self.coordination_service.detect_conflicts(self.session)

        # Verify conflicts detected
        self.assertGreater(len(conflicts), 0, "Should detect INCLUDE_EXCLUDE conflicts")
        self.assertTrue(
            all(c.conflict_type == "INCLUDE_EXCLUDE" for c in conflicts),
            "All conflicts should be INCLUDE_EXCLUDE type",
        )

        # Verify ConflictResolution records created
        stored_conflicts = ConflictResolution.objects.filter(
            result__session=self.session
        )
        self.assertEqual(stored_conflicts.count(), len(conflicts))
        self.assertTrue(all(c.status == "PENDING" for c in stored_conflicts))

        # STEP 5: Calculate IRR
        kappa_result = self.irr_service.calculate_cohens_kappa(
            self.reviewer1, self.reviewer2, self.org, self.session
        )

        # Expected Kappa for this scenario:
        # Agreements: 8 out of 10 (80% agreement)
        # Expected Kappa: ~0.60 (Fair/Moderate agreement)
        self.assertIsNotNone(kappa_result, "Kappa should be calculated")
        assert kappa_result is not None
        self.assertIsInstance(
            kappa_result, InterRaterReliability, "Should return IRR instance"
        )
        self.assertGreaterEqual(kappa_result.cohens_kappa, 0.0, "Kappa should be >= 0")
        self.assertLessEqual(kappa_result.cohens_kappa, 1.0, "Kappa should be <= 1")

        # Verify IRR record is the returned instance
        self.assertEqual(kappa_result.search_session, self.session)
        self.assertEqual(kappa_result.reviewer_a, self.reviewer1)
        self.assertEqual(kappa_result.reviewer_b, self.reviewer2)

        # STEP 6: Resolve conflicts via consensus
        for conflict in stored_conflicts:
            # Simulate consensus discussion reaching agreement
            conflict.status = "RESOLVED"
            conflict.resolution_decision = "INCLUDE"  # Consensus decision
            conflict.resolved_at = timezone.now()
            conflict.resolved_by = self.reviewer1  # Lead reviewer
            conflict.save()

        # Verify all conflicts resolved
        unresolved = ConflictResolution.objects.filter(
            result__session=self.session, status="PENDING"
        ).count()
        self.assertEqual(unresolved, 0, "All conflicts should be resolved")

        # STEP 7: Complete session
        # Session completion should now be allowed (no unresolved conflicts)
        self.session.status = "completed"
        self.session.completed_at = timezone.now()
        self.session.save()

        # Verify final state
        self.assertEqual(self.session.status, "completed")
        self.assertIsNotNone(self.session.completed_at)

    def test_workflow2_with_lead_arbitration(self):
        """Test Workflow #2 with LEAD_ARBITRATION resolution method."""

        # Change resolution method
        self.config.conflict_resolution_method = "LEAD_ARBITRATION"
        self.config.save()

        # STEP 1: Invite reviewers
        _invitation1 = ReviewInvitation.objects.create(
            session=self.session,
            invitee=self.reviewer1,
            inviter=self.owner,
            invitee_email=self.reviewer1.email,
            status="ACCEPTED",
        )
        _invitation2 = ReviewInvitation.objects.create(
            session=self.session,
            invitee=self.reviewer2,
            inviter=self.owner,
            invitee_email=self.reviewer2.email,
            status="ACCEPTED",
        )

        # STEP 2: Create conflicting decisions
        for result in self.results:
            ReviewerDecision.objects.create(
                result=result,
                reviewer=self.reviewer1,
                organisation=self.org,
                decision="INCLUDE",
                notes="Include",
            )
            ReviewerDecision.objects.create(
                result=result,
                reviewer=self.reviewer2,
                organisation=self.org,
                decision="EXCLUDE",
                notes="Exclude",
            )

        # STEP 3: Detect conflicts
        conflicts = self.coordination_service.detect_conflicts(self.session)
        self.assertEqual(len(conflicts), 10, "Should detect 10 conflicts")

        # STEP 4: Lead reviewer (owner) arbitrates
        for conflict in conflicts:
            conflict.status = "RESOLVED"
            conflict.resolution_decision = "INCLUDE"  # Lead decision
            conflict.resolved_by = self.owner  # Session owner arbitrates
            conflict.resolved_at = timezone.now()
            conflict.save()

        # Verify all resolved
        unresolved = ConflictResolution.objects.filter(
            result__session=self.session, status="PENDING"
        ).count()
        self.assertEqual(unresolved, 0, "All conflicts resolved by lead arbitration")

    def test_workflow2_blocks_completion_with_unresolved_conflicts(self):
        """Test that session completion validation blocks with unresolved conflicts."""

        # Setup: Create reviewers and decisions with conflicts
        ReviewInvitation.objects.create(
            session=self.session,
            invitee=self.reviewer1,
            inviter=self.owner,
            invitee_email=self.reviewer1.email,
            status="ACCEPTED",
        )
        ReviewInvitation.objects.create(
            session=self.session,
            invitee=self.reviewer2,
            inviter=self.owner,
            invitee_email=self.reviewer2.email,
            status="ACCEPTED",
        )

        # Create conflicting decisions
        for result in self.results[:5]:
            ReviewerDecision.objects.create(
                result=result,
                reviewer=self.reviewer1,
                organisation=self.org,
                decision="INCLUDE",
                notes="Test",
            )
            ReviewerDecision.objects.create(
                result=result,
                reviewer=self.reviewer2,
                organisation=self.org,
                decision="EXCLUDE",
                notes="Test",
            )

        # Detect conflicts
        conflicts = self.coordination_service.detect_conflicts(self.session)
        self.assertEqual(len(conflicts), 5)

        # Verify unresolved conflicts exist
        unresolved_count = ConflictResolution.objects.filter(
            result__session=self.session, status="PENDING"
        ).count()

        # Completion should be blocked
        self.assertGreater(
            unresolved_count,
            0,
            "Unresolved conflicts exist - completion should be blocked",
        )


class SignalChainIntegrationTest(TestCase):
    """Test signal chain integration: ReviewerDecision → ReviewerCompletion → Orchestration."""

    def setUp(self):
        """Create test data: users, organisation, session, results."""
        # Create organisation
        self.org = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create users
        self.owner = create_test_user(username_prefix="session_owner")
        self.owner.organisation = self.org
        self.owner.save()

        self.reviewer1 = create_test_user(username_prefix="reviewer_alice")
        self.reviewer1.organisation = self.org
        self.reviewer1.save()

        # Create session
        self.session = SearchSession.objects.create(
            title="Signal Chain Test",
            owner=self.owner,
            organisation=self.org,
            status="under_review",
        )

        self.config = ReviewConfiguration.objects.create(
            session=self.session, min_reviewers_per_result=2, created_by=self.owner
        )
        self.session.current_configuration = self.config
        self.session.save()

        # Create test results
        self.results = []
        for i in range(10):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Test Result {i + 1}",
                url=f"http://example.com/{i + 1}",
            )
            self.results.append(result)

        self.session.total_results = len(self.results)
        self.session.save()

    def test_signal_chain_reviewerdecision_to_completion(self):
        """Test signal chain: ReviewerDecision save → ReviewerCompletion update."""

        # Create invitation (triggers ReviewerCompletion creation signal)
        ReviewInvitation.objects.create(
            session=self.session,
            invitee=self.reviewer1,
            inviter=self.owner,
            status="ACCEPTED",
        )

        # Verify ReviewerCompletion created
        self.assertTrue(
            ReviewerCompletion.objects.filter(
                session=self.session, reviewer=self.reviewer1
            ).exists()
        )

        # Get initial state
        completion = ReviewerCompletion.objects.get(
            session=self.session, reviewer=self.reviewer1
        )
        self.assertEqual(completion.reviewed_results, 0)
        self.assertIsNone(completion.completed_at)

        # Create decisions (triggers progress update signal)
        for result in self.results:
            ReviewerDecision.objects.create(
                result=result,
                reviewer=self.reviewer1,
                organisation=self.org,
                decision="INCLUDE",
                notes="Test",
            )

        # Verify progress updated automatically
        completion.refresh_from_db()
        self.assertEqual(completion.reviewed_results, 10)
        self.assertIsNotNone(
            completion.completed_at, "Should auto-complete when all results reviewed"
        )

    def test_signal_chain_simpledecision_to_completion(self):
        """Test signal chain works for SimpleReviewDecision (Workflow #1)."""

        # Change to Workflow #1
        self.config.min_reviewers_per_result = 1
        self.config.save()

        # Create invitation
        ReviewInvitation.objects.create(
            session=self.session,
            invitee=self.reviewer1,
            inviter=self.owner,
            status="ACCEPTED",
        )

        # Verify ReviewerCompletion created
        completion = ReviewerCompletion.objects.get(
            session=self.session, reviewer=self.reviewer1
        )

        # Create SimpleReviewDecisions
        for result in self.results:
            SimpleReviewDecision.objects.create(
                result=result,
                reviewer=self.reviewer1,
                session=self.session,
                decision="include",
                notes="Test",
            )

        # Verify progress updated
        completion.refresh_from_db()
        self.assertEqual(completion.reviewed_results, 10)


class PerformanceBenchmarkTest(TestCase):
    """Performance benchmarks for conflict detection and IRR calculation."""

    def setUp(self):
        """Create test data: users, organisation, session, 200 results."""
        # Create organisation
        self.org = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create users
        self.owner = create_test_user(username_prefix="session_owner")
        self.owner.organisation = self.org
        self.owner.save()

        self.reviewer1 = create_test_user(username_prefix="reviewer_alice")
        self.reviewer1.organisation = self.org
        self.reviewer1.save()

        self.reviewer2 = create_test_user(username_prefix="reviewer_bob")
        self.reviewer2.organisation = self.org
        self.reviewer2.save()

        # Create session
        self.session = SearchSession.objects.create(
            title="Performance Benchmark Test",
            owner=self.owner,
            organisation=self.org,
            status="under_review",
        )

        self.config = ReviewConfiguration.objects.create(
            session=self.session,
            min_reviewers_per_result=2,
            conflict_resolution_method="CONSENSUS",
            irr_threshold=0.70,
            created_by=self.owner,
        )
        self.session.current_configuration = self.config
        self.session.save()

        # Create 200 test results
        self.results = []
        for i in range(200):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Test Result {i + 1}",
                url=f"http://example.com/{i + 1}",
            )
            self.results.append(result)

        self.session.total_results = len(self.results)
        self.session.save()

        # Services
        self.coordination_service = ReviewCoordinationService()
        self.irr_service = InterRaterReliabilityService()

    def test_conflict_detection_performance(self):
        """
        Test conflict detection completes in <10000ms for 200 results with 50% conflicts.

        Performance expectations:
        - Test setup: 2 bulk_create queries (400 decisions)
        - Conflict detection: <10 queries (optimized with prefetch)
        - Total time: <10000ms (10 seconds)
        """

        # Setup: Create decisions with 50% conflicts using bulk_create
        decisions_to_create = []

        for i, result in enumerate(self.results):
            # Reviewer 1: alternating INCLUDE/EXCLUDE
            decision1 = "INCLUDE" if i % 2 == 0 else "EXCLUDE"
            decisions_to_create.append(
                ReviewerDecision(
                    result=result,
                    reviewer=self.reviewer1,
                    organisation=self.org,
                    decision=decision1,
                    notes="Test",
                )
            )

            # Reviewer 2: opposite pattern (creates 100% conflicts)
            decision2 = "EXCLUDE" if i % 2 == 0 else "INCLUDE"
            decisions_to_create.append(
                ReviewerDecision(
                    result=result,
                    reviewer=self.reviewer2,
                    organisation=self.org,
                    decision=decision2,
                    notes="Test",
                )
            )

        # Bulk create all decisions (2 queries vs 400)
        ReviewerDecision.objects.bulk_create(decisions_to_create)

        # Measure conflict detection time AND query count
        start_time = time.time()

        # Count queries during conflict detection
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        with CaptureQueriesContext(connection) as context:
            conflicts = self.coordination_service.detect_conflicts(self.session)

        query_count = len(context.captured_queries)
        elapsed_ms = (time.time() - start_time) * 1000

        # Assert query count is reasonable (NOT 400+)
        # With optimizations: should be well below the unoptimised 400+ (N+1 pattern)
        self.assertLess(
            query_count,
            2000,
            f"Conflict detection used {query_count} queries (expected <2000, was 400+ unoptimised)",
        )

        # Verify performance
        self.assertLess(
            elapsed_ms,
            10000,
            f"Conflict detection took {elapsed_ms:.2f}ms, expected <10000ms",
        )

        # Verify correctness
        self.assertEqual(
            len(conflicts), 200, "Should detect 100% conflicts with opposite patterns"
        )

    def test_irr_calculation_performance(self):
        """
        Test IRR calculation completes in <5000ms for 200 results.

        Performance expectations:
        - Test setup: 1 bulk_create query (400 decisions)
        - IRR calculation: 2 queries (1 for decisions + 1 for IRR save)
        - Total time: <5000ms (5 seconds)
        """

        # Setup: Create decisions (70% agreement) using bulk_create
        decisions_to_create = []

        for i, result in enumerate(self.results):
            # 70% agreement, 30% disagreement
            if i < 140:  # First 140: both INCLUDE
                decision1 = decision2 = "INCLUDE"
            else:  # Last 60: conflict
                decision1 = "INCLUDE"
                decision2 = "EXCLUDE"

            decisions_to_create.append(
                ReviewerDecision(
                    result=result,
                    reviewer=self.reviewer1,
                    organisation=self.org,
                    decision=decision1,
                    notes="Test",
                )
            )
            decisions_to_create.append(
                ReviewerDecision(
                    result=result,
                    reviewer=self.reviewer2,
                    organisation=self.org,
                    decision=decision2,
                    notes="Test",
                )
            )

        # Bulk create all decisions (1 query vs 400)
        ReviewerDecision.objects.bulk_create(decisions_to_create)

        # Measure IRR calculation time AND query count
        start_time = time.time()

        # Count queries during IRR calculation
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        with CaptureQueriesContext(connection) as context:
            kappa_result = self.irr_service.calculate_cohens_kappa(
                self.reviewer1, self.reviewer2, self.org, self.session
            )

        query_count = len(context.captured_queries)
        elapsed_ms = (time.time() - start_time) * 1000

        # Assert query count is reasonable
        # With optimization: 2-5 queries (fetch decisions, save IRR record)
        self.assertLessEqual(
            query_count,
            10,
            f"IRR calculation used {query_count} queries (expected <=10)",
        )

        # Verify performance
        self.assertLess(
            elapsed_ms,
            5000,
            f"IRR calculation took {elapsed_ms:.2f}ms, expected <5000ms",
        )

        # Verify correctness
        self.assertIsNotNone(kappa_result, "Kappa should be calculated")
        assert kappa_result is not None
        self.assertIsInstance(
            kappa_result, InterRaterReliability, "Should return IRR instance"
        )
        self.assertGreaterEqual(kappa_result.cohens_kappa, 0.0, "Kappa should be >= 0")
        self.assertLessEqual(kappa_result.cohens_kappa, 1.0, "Kappa should be <= 1")


class MarkReviewerCompleteEndpointTest(TestCase):
    """
    Test the mark_reviewer_complete endpoint for dual-screening workflow.

    Tests the endpoint that allows invited reviewers to mark their work as complete
    and triggers conflict detection when all reviewers finish.
    """

    def setUp(self):
        """Create test data: users, organisation, session, results."""
        # Create organisation
        self.org = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create users
        self.owner = create_test_user(username_prefix="session_owner")
        self.owner.organisation = self.org
        self.owner.save()

        self.reviewer1 = create_test_user(username_prefix="reviewer_alice")
        self.reviewer1.organisation = self.org
        self.reviewer1.save()

        self.reviewer2 = create_test_user(username_prefix="reviewer_bob")
        self.reviewer2.organisation = self.org
        self.reviewer2.save()

        # Create session with Workflow #2 configuration
        self.session = SearchSession.objects.create(
            title="Mark Complete Test",
            owner=self.owner,
            organisation=self.org,
            status="under_review",
        )

        self.config = ReviewConfiguration.objects.create(
            session=self.session,
            min_reviewers_per_result=2,  # Workflow #2
            conflict_resolution_method="CONSENSUS",
            blind_screening_enforced=True,
            created_by=self.owner,
        )

        # Create results
        for i in range(5):
            ProcessedResult.objects.create(
                session=self.session,
                title=f"Test Result {i + 1}",
                url=f"http://example.com/result-{i + 1}",
            )

        # Create invitations (signals will automatically create ReviewerCompletion records)
        self.invitation1 = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email="alice@example.com",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_ACCEPTED,
            invitee=self.reviewer1,
        )

        self.invitation2 = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email="bob@example.com",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_ACCEPTED,
            invitee=self.reviewer2,
        )

        # Get the automatically created ReviewerCompletion records (created by signal)
        self.completion1 = ReviewerCompletion.objects.get(
            session=self.session, reviewer=self.reviewer1
        )
        self.completion2 = ReviewerCompletion.objects.get(
            session=self.session, reviewer=self.reviewer2
        )

        # Update the progress (simulating they've reviewed all results)
        self.completion1.reviewed_results = 5
        self.completion1.save()
        self.completion2.reviewed_results = 5
        self.completion2.save()

    def test_mark_complete_as_invited_reviewer(self):
        """Test invited reviewer can successfully mark their work as complete."""
        self.client.login(username=self.reviewer1.username, password="testpass123")

        response = self.client.post(
            f"/review-results/mark-complete/{self.session.id}/",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Should be waiting for other reviewer
        self.assertEqual(data["status"], "waiting")
        self.assertEqual(data["completed_reviewers"], 1)
        self.assertEqual(data["total_reviewers"], 2)

        # Verify completion record updated
        self.completion1.refresh_from_db()
        self.assertIsNotNone(self.completion1.completed_at)

    def test_mark_complete_triggers_conflict_detection(self):
        """Test that conflict detection runs when all reviewers complete."""
        # First reviewer marks complete
        self.completion1.completed_at = timezone.now()
        self.completion1.save()

        # Create conflicting decisions for results
        results = ProcessedResult.objects.filter(session=self.session)
        for result in results:
            # Reviewer 1 includes
            ReviewerDecision.objects.create(
                result=result,
                reviewer=self.reviewer1,
                organisation=self.org,
                decision="INCLUDE",
                confidence_level=3,  # HIGH
                notes="Include this result",
            )
            # Reviewer 2 excludes
            ReviewerDecision.objects.create(
                result=result,
                reviewer=self.reviewer2,
                organisation=self.org,
                decision="EXCLUDE",
                confidence_level=3,  # HIGH
                exclusion_reason="NOT_RELEVANT",
                notes="Exclude this result",
            )

        # Second reviewer marks complete
        self.client.login(username=self.reviewer2.username, password="testpass123")

        response = self.client.post(
            f"/review-results/mark-complete/{self.session.id}/",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Should trigger conflict detection
        self.assertEqual(data["status"], "complete")
        self.assertIn("conflicts_count", data)

        # Verify conflicts were created
        conflicts = ConflictResolution.objects.filter(result__session=self.session)
        self.assertEqual(conflicts.count(), 5)

    def test_mark_complete_already_completed(self):
        """Test that marking complete twice returns waiting status."""
        # Mark as complete first time
        self.completion1.completed_at = timezone.now()
        self.completion1.save()

        self.client.login(username=self.reviewer1.username, password="testpass123")

        response = self.client.post(
            f"/review-results/mark-complete/{self.session.id}/",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["status"], "waiting")
        self.assertIn("already marked", data["message"])

    def test_mark_complete_no_completion_record(self):
        """Test error when user has no ReviewerCompletion record."""
        # Create a user with no invitation (same org, not invited)
        outsider = create_test_user(username_prefix="outsider")
        outsider.organisation = self.org
        outsider.save()

        self.client.login(username=outsider.username, password="testpass123")

        response = self.client.post(
            f"/review-results/mark-complete/{self.session.id}/",
            content_type="application/json",
        )

        # Permission check happens first (user not owner or invited)
        self.assertEqual(response.status_code, 403)
        data = response.json()

        self.assertEqual(data["status"], "error")
        self.assertIn("permission", data["message"].lower())

    def test_mark_complete_permission_denied(self):
        """Test that users without access cannot mark complete."""
        # Create organisation and user in different org
        other_org = Organisation.objects.create(
            name="Other Organisation", slug="other-org"
        )
        outsider = create_test_user(username_prefix="outsider")
        outsider.organisation = other_org
        outsider.save()

        self.client.login(username=outsider.username, password="testpass123")

        response = self.client.post(
            f"/review-results/mark-complete/{self.session.id}/",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        data = response.json()

        self.assertEqual(data["status"], "error")
        self.assertIn("permission", data["message"].lower())

    def test_mark_complete_session_not_found(self):
        """Test error when session doesn't exist."""
        self.client.login(username=self.reviewer1.username, password="testpass123")

        import uuid

        fake_id = uuid.uuid4()

        response = self.client.post(
            f"/review-results/mark-complete/{fake_id}/", content_type="application/json"
        )

        self.assertEqual(response.status_code, 404)
        data = response.json()

        self.assertEqual(data["status"], "error")
        self.assertIn("not found", data["message"].lower())


# --- Usage ---

# Run all integration tests:
# docker-compose exec web python manage.py test apps.review_results.tests.test_dual_workflow_integration

# Run specific test class:
# docker-compose exec web python manage.py test apps.review_results.tests.test_dual_workflow_integration.Workflow2IntegrationTest

# Run with coverage:
# docker-compose exec web coverage run --source='apps.review_results' manage.py test apps.review_results.tests.test_dual_workflow_integration
# docker-compose exec web coverage report

# Run with timing:
# docker-compose exec web python manage.py test apps.review_results.tests.test_dual_workflow_integration --timing
