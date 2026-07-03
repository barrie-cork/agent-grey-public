"""
Tests for review_results internal_api.get_review_progress_stats.

Covers the WF2 (ReviewerDecision) branch added in #181, plus a WF1 sanity check.
"""

from django.test import TestCase

from apps.core.tests.utils import DisablePersonalOrgSignalMixin, create_test_user
from apps.organisation.models import Organisation, OrganisationMembership
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import ReviewConfiguration, SearchSession
from apps.review_results.internal_api import get_review_progress_stats
from apps.review_results.models import (
    ConflictResolution,
    ReviewerDecision,
    SimpleReviewDecision,
)


class TestGetReviewProgressStatsWF2(DisablePersonalOrgSignalMixin, TestCase):
    """
    WF2 sessions must aggregate ReviewerDecision per-result (with consensus +
    conflict resolution) rather than returning all-zeros from SimpleReviewDecision.
    """

    def setUp(self):
        self.org = Organisation.objects.create(
            name="Test Org", slug="test-org-internal-api-wf2"
        )
        self.reviewer1 = create_test_user(
            username_prefix="iapi_r1", email="iapi_r1@test.com"
        )
        self.reviewer2 = create_test_user(
            username_prefix="iapi_r2", email="iapi_r2@test.com"
        )
        OrganisationMembership.objects.create(
            organisation=self.org, user=self.reviewer1, role="REVIEWER"
        )
        OrganisationMembership.objects.create(
            organisation=self.org, user=self.reviewer2, role="REVIEWER"
        )

        self.session = SearchSession.objects.create(
            organisation=self.org,
            title="WF2 Stats Test",
            owner=self.reviewer1,
            status="under_review",
        )
        self.config = ReviewConfiguration.objects.create(
            session=self.session,
            min_reviewers_per_result=2,
            version=1,
            organisation=self.org,
            created_by=self.reviewer1,
        )
        self.session.current_configuration = self.config
        self.session.save()

        # Result 1: unanimous INCLUDE
        result_include = ProcessedResult.objects.create(
            session=self.session,
            title="Unanimous Include",
            url="https://example.com/include",
            snippet="test",
        )
        ReviewerDecision.objects.create(
            organisation=self.org,
            result=result_include,
            reviewer=self.reviewer1,
            decision="INCLUDE",
            screening_stage="SCREENING",
        )
        ReviewerDecision.objects.create(
            organisation=self.org,
            result=result_include,
            reviewer=self.reviewer2,
            decision="INCLUDE",
            screening_stage="SCREENING",
        )

        # Result 2: unanimous EXCLUDE
        result_exclude = ProcessedResult.objects.create(
            session=self.session,
            title="Unanimous Exclude",
            url="https://example.com/exclude",
            snippet="test",
        )
        ReviewerDecision.objects.create(
            organisation=self.org,
            result=result_exclude,
            reviewer=self.reviewer1,
            decision="EXCLUDE",
            screening_stage="SCREENING",
            exclusion_reason="Not relevant",
        )
        ReviewerDecision.objects.create(
            organisation=self.org,
            result=result_exclude,
            reviewer=self.reviewer2,
            decision="EXCLUDE",
            screening_stage="SCREENING",
            exclusion_reason="Not relevant",
        )

        # Result 3: conflict, resolved to INCLUDE
        result_conflict = ProcessedResult.objects.create(
            session=self.session,
            title="Conflict Resolved Include",
            url="https://example.com/conflict",
            snippet="test",
        )
        d_r1_include = ReviewerDecision.objects.create(
            organisation=self.org,
            result=result_conflict,
            reviewer=self.reviewer1,
            decision="INCLUDE",
            screening_stage="SCREENING",
        )
        d_r2_exclude = ReviewerDecision.objects.create(
            organisation=self.org,
            result=result_conflict,
            reviewer=self.reviewer2,
            decision="EXCLUDE",
            screening_stage="SCREENING",
            exclusion_reason="Not relevant",
        )
        conflict = ConflictResolution.objects.create(
            organisation=self.org,
            result=result_conflict,
            status=ConflictResolution.STATUS_RESOLVED,
            final_decision=d_r1_include,
            conflict_type="INCLUDE_EXCLUDE",
        )
        conflict.conflicting_decisions.add(d_r1_include, d_r2_exclude)

        # Result 4: only ABSTAIN -- not counted as reviewed
        result_abstain = ProcessedResult.objects.create(
            session=self.session,
            title="Abstain Only",
            url="https://example.com/abstain",
            snippet="test",
        )
        ReviewerDecision.objects.create(
            organisation=self.org,
            result=result_abstain,
            reviewer=self.reviewer1,
            decision="ABSTAIN",
            screening_stage="SCREENING",
        )

        self.session_id = str(self.session.id)

    def test_not_all_zero(self):
        stats = get_review_progress_stats(self.session_id)
        self.assertNotEqual(stats["included_results"], 0)
        self.assertNotEqual(stats["excluded_results"], 0)
        self.assertNotEqual(stats["reviewed_results"], 0)

    def test_total_results(self):
        stats = get_review_progress_stats(self.session_id)
        self.assertEqual(stats["total_results"], 4)

    def test_reviewed_excludes_abstain_only(self):
        # Results 1, 2, 3 have at least one non-ABSTAIN decision; result 4 does not.
        stats = get_review_progress_stats(self.session_id)
        self.assertEqual(stats["reviewed_results"], 3)

    def test_included_unanimous_plus_resolved_conflict(self):
        # Result 1 (unanimous INCLUDE) + Result 3 (conflict resolved to INCLUDE)
        stats = get_review_progress_stats(self.session_id)
        self.assertEqual(stats["included_results"], 2)

    def test_excluded_unanimous(self):
        stats = get_review_progress_stats(self.session_id)
        self.assertEqual(stats["excluded_results"], 1)

    def test_maybe_zero(self):
        stats = get_review_progress_stats(self.session_id)
        self.assertEqual(stats["maybe_results"], 0)

    def test_pending_count(self):
        # 4 total - 3 reviewed = 1 pending (the ABSTAIN-only result)
        stats = get_review_progress_stats(self.session_id)
        self.assertEqual(stats["pending_results"], 1)

    def test_completion_percentage(self):
        stats = get_review_progress_stats(self.session_id)
        self.assertEqual(stats["completion_percentage"], 75.0)


class TestGetReviewProgressStatsWF1(DisablePersonalOrgSignalMixin, TestCase):
    """WF1 path must remain unchanged (SimpleReviewDecision, lowercase decisions)."""

    def setUp(self):
        self.org = Organisation.objects.create(
            name="Test Org WF1", slug="test-org-internal-api-wf1"
        )
        self.reviewer = create_test_user(
            username_prefix="iapi_wf1", email="iapi_wf1@test.com"
        )
        OrganisationMembership.objects.create(
            organisation=self.org, user=self.reviewer, role="REVIEWER"
        )

        self.session = SearchSession.objects.create(
            organisation=self.org,
            title="WF1 Stats Test",
            owner=self.reviewer,
            status="under_review",
        )
        config = ReviewConfiguration.objects.create(
            session=self.session,
            min_reviewers_per_result=1,
            version=1,
            organisation=self.org,
            created_by=self.reviewer,
        )
        self.session.current_configuration = config
        self.session.save()

        # Create 5 results with decisions
        for i in range(5):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"WF1 Result {i}",
                url=f"https://example.com/wf1/{i}",
                snippet="test",
            )
            decision = ["include", "include", "exclude", "maybe", "pending"][i]
            exclusion_reason = "not_relevant" if decision == "exclude" else ""
            SimpleReviewDecision.objects.create(
                result=result,
                session=self.session,
                reviewer=self.reviewer,
                decision=decision,
                exclusion_reason=exclusion_reason,
            )

        self.session_id = str(self.session.id)

    def test_total_results(self):
        stats = get_review_progress_stats(self.session_id)
        self.assertEqual(stats["total_results"], 5)

    def test_reviewed_excludes_pending(self):
        stats = get_review_progress_stats(self.session_id)
        self.assertEqual(stats["reviewed_results"], 4)

    def test_included_count(self):
        stats = get_review_progress_stats(self.session_id)
        self.assertEqual(stats["included_results"], 2)

    def test_excluded_count(self):
        stats = get_review_progress_stats(self.session_id)
        self.assertEqual(stats["excluded_results"], 1)

    def test_maybe_count(self):
        stats = get_review_progress_stats(self.session_id)
        self.assertEqual(stats["maybe_results"], 1)

    def test_pending_count(self):
        stats = get_review_progress_stats(self.session_id)
        self.assertEqual(stats["pending_results"], 1)


class TestWF2ProgressCountsMajorityCriteria(DisablePersonalOrgSignalMixin, TestCase):
    """
    T11: _wf2_progress_counts must bucket non-unanimous MAJORITY results correctly.

    N=3 MAJORITY session with INCLUDE/INCLUDE/EXCLUDE (no conflict) must count
    as 1 included result, not 0 (which the old unanimity logic would give).
    """

    def setUp(self):
        self.org = Organisation.objects.create(
            name="Majority Test Org", slug="majority-test-org"
        )
        self.reviewer1 = create_test_user(
            username_prefix="maj_r1", email="maj_r1@test.com"
        )
        self.reviewer2 = create_test_user(
            username_prefix="maj_r2", email="maj_r2@test.com"
        )
        self.reviewer3 = create_test_user(
            username_prefix="maj_r3", email="maj_r3@test.com"
        )
        for rv in [self.reviewer1, self.reviewer2, self.reviewer3]:
            OrganisationMembership.objects.create(
                organisation=self.org, user=rv, role="REVIEWER"
            )

        self.session = SearchSession.objects.create(
            organisation=self.org,
            title="Majority Criteria Test",
            owner=self.reviewer1,
            status="under_review",
        )
        self.config = ReviewConfiguration.objects.create(
            session=self.session,
            min_reviewers_per_result=3,
            consensus_criteria="MAJORITY",
            version=1,
            organisation=self.org,
            created_by=self.reviewer1,
        )
        self.session.current_configuration = self.config
        self.session.save()

        # Result 1: 2-of-3 INCLUDE (MAJORITY consensus, not unanimous)
        self.result_majority_include = ProcessedResult.objects.create(
            session=self.session,
            title="Majority Include",
            url="https://example.com/majority-include",
            snippet="test",
            min_reviewers_required=3,
        )
        ReviewerDecision.objects.create(
            organisation=self.org,
            result=self.result_majority_include,
            reviewer=self.reviewer1,
            decision="INCLUDE",
            screening_stage="SCREENING",
        )
        ReviewerDecision.objects.create(
            organisation=self.org,
            result=self.result_majority_include,
            reviewer=self.reviewer2,
            decision="INCLUDE",
            screening_stage="SCREENING",
        )
        ReviewerDecision.objects.create(
            organisation=self.org,
            result=self.result_majority_include,
            reviewer=self.reviewer3,
            decision="EXCLUDE",
            screening_stage="SCREENING",
        )

        # Result 2: all three unanimous EXCLUDE (for baseline)
        self.result_unanimous_exclude = ProcessedResult.objects.create(
            session=self.session,
            title="Unanimous Exclude",
            url="https://example.com/unanimous-exclude",
            snippet="test",
            min_reviewers_required=3,
        )
        for rv in [self.reviewer1, self.reviewer2, self.reviewer3]:
            ReviewerDecision.objects.create(
                organisation=self.org,
                result=self.result_unanimous_exclude,
                reviewer=rv,
                decision="EXCLUDE",
                screening_stage="SCREENING",
                exclusion_reason="Not relevant",
            )

        self.session_id = str(self.session.id)

    def test_majority_include_counted_as_included(self):
        """2-of-3 INCLUDE under MAJORITY criteria must appear in included_results."""
        stats = get_review_progress_stats(self.session_id)
        self.assertEqual(stats["included_results"], 1)

    def test_unanimous_exclude_counted_as_excluded(self):
        stats = get_review_progress_stats(self.session_id)
        self.assertEqual(stats["excluded_results"], 1)

    def test_majority_include_not_in_excluded(self):
        """The INCLUDE-majority result must not be double-counted as excluded."""
        stats = get_review_progress_stats(self.session_id)
        # excluded = 1 (unanimous exclude only)
        self.assertEqual(stats["excluded_results"], 1)

    def test_reviewed_count(self):
        stats = get_review_progress_stats(self.session_id)
        self.assertEqual(stats["reviewed_results"], 2)


class TestWF2ProgressCountsUnanimousCriteria(DisablePersonalOrgSignalMixin, TestCase):
    """
    T11 continuation: UNANIMOUS criteria must NOT count 2-of-3 INCLUDE as included
    (it would be a conflict under UNANIMOUS, but here no ConflictResolution exists
    so consensus_value returns None → not included).
    """

    def setUp(self):
        self.org = Organisation.objects.create(
            name="Unanimous Test Org", slug="unanimous-test-org"
        )
        self.reviewer1 = create_test_user(
            username_prefix="unm_r1", email="unm_r1@test.com"
        )
        self.reviewer2 = create_test_user(
            username_prefix="unm_r2", email="unm_r2@test.com"
        )
        self.reviewer3 = create_test_user(
            username_prefix="unm_r3", email="unm_r3@test.com"
        )
        for rv in [self.reviewer1, self.reviewer2, self.reviewer3]:
            OrganisationMembership.objects.create(
                organisation=self.org, user=rv, role="REVIEWER"
            )

        self.session = SearchSession.objects.create(
            organisation=self.org,
            title="Unanimous Criteria Test",
            owner=self.reviewer1,
            status="under_review",
        )
        self.config = ReviewConfiguration.objects.create(
            session=self.session,
            min_reviewers_per_result=3,
            consensus_criteria="UNANIMOUS",
            version=1,
            organisation=self.org,
            created_by=self.reviewer1,
        )
        self.session.current_configuration = self.config
        self.session.save()

        # 2-of-3 INCLUDE (not unanimous) — no ConflictResolution created
        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="Non-Unanimous Include",
            url="https://example.com/non-unanimous",
            snippet="test",
            min_reviewers_required=3,
        )
        ReviewerDecision.objects.create(
            organisation=self.org,
            result=self.result,
            reviewer=self.reviewer1,
            decision="INCLUDE",
            screening_stage="SCREENING",
        )
        ReviewerDecision.objects.create(
            organisation=self.org,
            result=self.result,
            reviewer=self.reviewer2,
            decision="INCLUDE",
            screening_stage="SCREENING",
        )
        ReviewerDecision.objects.create(
            organisation=self.org,
            result=self.result,
            reviewer=self.reviewer3,
            decision="EXCLUDE",
            screening_stage="SCREENING",
        )

        self.session_id = str(self.session.id)

    def test_non_unanimous_not_counted_as_included(self):
        """Under UNANIMOUS criteria, 2-of-3 INCLUDE must not appear in included_results."""
        stats = get_review_progress_stats(self.session_id)
        self.assertEqual(stats["included_results"], 0)

    def test_non_unanimous_not_counted_as_excluded(self):
        """The minority EXCLUDE vote must not make the result appear as excluded."""
        stats = get_review_progress_stats(self.session_id)
        self.assertEqual(stats["excluded_results"], 0)
