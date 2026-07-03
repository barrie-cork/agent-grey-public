"""
Integration tests for Consensus Discussion API endpoints.

Tests the full workflow from conflict creation through comment posting,
re-vote proposals, and consensus resolution.
"""

from datetime import timedelta
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.organisation.models import Organisation, OrganisationMembership
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.review_results.models import (
    ConflictComment,
    ConflictResolution,
    ReviewerDecision,
    RevoteProposal,
)
from apps.core.tests.utils import create_test_user, make_session_participant

User = get_user_model()


class ConflictDetailAPITest(TestCase):
    """Test ConflictDetailView API endpoint."""

    def setUp(self):
        """Set up test data."""
        # Create organisation
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create users
        self.reviewer1 = create_test_user(username_prefix="reviewer1")
        self.reviewer2 = create_test_user(username_prefix="reviewer2")

        # Create organisation memberships (required for middleware)
        OrganisationMembership.objects.create(
            user=self.reviewer1, organisation=self.organisation, role="REVIEWER"
        )
        OrganisationMembership.objects.create(
            user=self.reviewer2, organisation=self.organisation, role="REVIEWER"
        )

        # Create session
        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.reviewer1,
            organisation=self.organisation,
            status="draft",
        )
        # reviewer1 owns the session; reviewer2 gains access as an accepted
        # reviewer (org membership alone no longer grants access -- GH #230).
        make_session_participant(self.session, self.reviewer2)

        # Create result
        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result for Consensus Discussion",
            url="https://example.com/test-consensus",
            snippet="This is a test result for consensus discussion testing",
        )

        # Create conflicting decisions
        self.decision1 = ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.reviewer1,
            decision="INCLUDE",
            screening_stage="INITIAL",
            organisation=self.organisation,
        )
        self.decision2 = ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.reviewer2,
            decision="EXCLUDE",
            screening_stage="INITIAL",
            organisation=self.organisation,
        )

        # Create conflict
        self.conflict = ConflictResolution.objects.create(
            organisation=self.organisation,
            result=self.result,
            conflict_type="INCLUDE_EXCLUDE",
            status="PENDING",
        )
        self.conflict.conflicting_decisions.add(self.decision1, self.decision2)

    def test_get_conflict_details_authenticated_reviewer(self):
        """Test that conflicting reviewers can access conflict details."""
        self.client.force_login(self.reviewer1)
        url = reverse("review_results_api:conflict-details", args=[self.conflict.id])

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        # Verify basic conflict data
        self.assertEqual(data["conflict"]["id"], str(self.conflict.id))
        self.assertEqual(data["conflict"]["status"], "PENDING")

        # Verify result data (nested in conflict)
        self.assertEqual(
            data["conflict"]["result"]["title"], "Test Result for Consensus Discussion"
        )

        # Verify conflicting decisions (nested in conflict)
        self.assertEqual(len(data["conflict"]["conflicting_decisions"]), 2)

        # Verify permissions
        self.assertTrue(data["permissions"]["can_comment"])
        self.assertTrue(data["permissions"]["can_propose_revote"])

    def test_get_conflict_details_non_reviewer_blocked(self):
        """Test that non-conflicting reviewers cannot access conflict details."""
        non_reviewer = create_test_user(username_prefix="non_reviewer")
        # Create organisation membership (but not involved in this conflict)
        OrganisationMembership.objects.create(
            user=non_reviewer, organisation=self.organisation, role="REVIEWER"
        )
        # Participant, but not a conflicting reviewer -> blocked by the secondary
        # permission gate (403), not by session access.
        make_session_participant(self.session, non_reviewer)
        self.client.force_login(non_reviewer)
        url = reverse("review_results_api:conflict-details", args=[self.conflict.id])

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_conflict_details_invalid_uuid(self):
        """Test that invalid conflict UUID returns 404."""
        self.client.force_login(self.reviewer1)
        import uuid

        invalid_id = uuid.uuid4()
        url = reverse("review_results_api:conflict-details", args=[invalid_id])

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        data = response.json()
        self.assertEqual(data["error"], "not_found")

    def test_get_conflict_details_wrong_organisation(self):
        """Test that conflict from different organisation returns 404 for non-owner."""
        # Create another organisation with a different owner
        other_org = Organisation.objects.create(
            name="Other Organisation", slug="other-org"
        )
        other_owner = create_test_user(username_prefix="other_owner")
        OrganisationMembership.objects.create(
            user=other_owner, organisation=other_org, role="LEAD_REVIEWER"
        )

        # Create conflict in other organisation (owned by different user)
        other_session = SearchSession.objects.create(
            title="Other Session",
            owner=other_owner,
            organisation=other_org,
            status="draft",
        )
        other_result = ProcessedResult.objects.create(
            session=other_session,
            title="Other Result",
            url="https://example.com/other",
            snippet="Other snippet",
        )
        other_conflict = ConflictResolution.objects.create(
            organisation=other_org,
            result=other_result,
            conflict_type="INCLUDE_EXCLUDE",
            status="PENDING",
        )

        # Try to access from user in different organisation (not owner, not invited)
        self.client.force_login(self.reviewer1)
        url = reverse("review_results_api:conflict-details", args=[other_conflict.id])

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_conflict_details_admin_access(self):
        """Test that admin users can access conflict details."""
        # Create admin user
        admin_user = create_test_user(username_prefix="admin")
        OrganisationMembership.objects.create(
            user=admin_user, organisation=self.organisation, role="SENIOR_RESEARCHER"
        )

        self.client.force_login(admin_user)
        url = reverse("review_results_api:conflict-details", args=[self.conflict.id])

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        # Admin should be able to resolve conflicts
        self.assertTrue(data["permissions"]["can_resolve"])


class CommentPostingAPITest(TestCase):
    """Test ConflictCommentCreateView API endpoint."""

    def setUp(self):
        """Set up test data."""
        # Create organisation
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create users
        self.reviewer1 = create_test_user(username_prefix="reviewer1")
        self.reviewer2 = create_test_user(username_prefix="reviewer2")

        # Create organisation memberships (required for middleware)
        OrganisationMembership.objects.create(
            user=self.reviewer1, organisation=self.organisation, role="REVIEWER"
        )
        OrganisationMembership.objects.create(
            user=self.reviewer2, organisation=self.organisation, role="REVIEWER"
        )

        # Create session
        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.reviewer1,
            organisation=self.organisation,
            status="draft",
        )
        # reviewer1 owns the session; reviewer2 gains access as an accepted
        # reviewer (org membership alone no longer grants access -- GH #230).
        make_session_participant(self.session, self.reviewer2)

        # Create result
        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            url="https://example.com/test",
            snippet="Test snippet",
        )

        # Create conflicting decisions
        self.decision1 = ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.reviewer1,
            decision="INCLUDE",
            screening_stage="INITIAL",
            organisation=self.organisation,
        )
        self.decision2 = ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.reviewer2,
            decision="EXCLUDE",
            screening_stage="INITIAL",
            organisation=self.organisation,
        )

        # Create conflict
        self.conflict = ConflictResolution.objects.create(
            organisation=self.organisation,
            result=self.result,
            conflict_type="INCLUDE_EXCLUDE",
            status="PENDING",
        )
        self.conflict.conflicting_decisions.add(self.decision1, self.decision2)

    def test_post_comment_success(self):
        """Test successfully posting a comment."""
        self.client.force_login(self.reviewer1)
        url = reverse("review_results_api:create-comment", args=[self.conflict.id])

        payload = {
            "content": "I think we should include this result because it contains relevant data."
        }

        response = self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()

        # Verify comment was created
        self.assertEqual(data["content"], payload["content"])
        self.assertEqual(data["author"]["username"], self.reviewer1.username)

        # Verify comment exists in database
        comment = ConflictComment.objects.get(id=data["id"])
        self.assertEqual(comment.content, payload["content"])
        self.assertEqual(comment.author, self.reviewer1)

    def test_post_comment_with_markdown(self):
        """Test posting comment with markdown formatting."""
        self.client.force_login(self.reviewer1)
        url = reverse("review_results_api:create-comment", args=[self.conflict.id])

        payload = {
            "content": "## Reasons to Include\n\n1. Strong evidence\n2. Relevant to research question\n\n**Important:** Check methodology section."
        }

        response = self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()

        # Verify markdown is preserved
        self.assertIn("## Reasons to Include", data["content"])
        self.assertIn("**Important:**", data["content"])

    def test_post_reply_to_comment(self):
        """Test posting a reply to existing comment."""
        # Create parent comment
        parent_comment = ConflictComment.objects.create(
            conflict=self.conflict, author=self.reviewer1, content="Original comment"
        )

        self.client.force_login(self.reviewer2)
        url = reverse("review_results_api:create-comment", args=[self.conflict.id])

        payload = {
            "content": "I disagree with this assessment.",
            "parent_id": str(parent_comment.id),
        }

        response = self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()

        # Verify reply relationship
        self.assertEqual(data["parent"], str(parent_comment.id))

        # Verify in database
        reply = ConflictComment.objects.get(id=data["id"])
        self.assertEqual(reply.parent, parent_comment)

    def test_post_comment_empty_content(self):
        """Test that empty comment content returns validation error."""
        self.client.force_login(self.reviewer1)
        url = reverse("review_results_api:create-comment", args=[self.conflict.id])

        payload = {"content": ""}

        response = self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertEqual(data["error"], "validation_error")

    def test_post_comment_invalid_parent_id(self):
        """Test that invalid parent_id returns validation error."""
        self.client.force_login(self.reviewer1)
        url = reverse("review_results_api:create-comment", args=[self.conflict.id])

        import uuid

        invalid_parent_id = uuid.uuid4()
        payload = {
            "content": "This is a reply to non-existent comment",
            "parent_id": str(invalid_parent_id),
        }

        response = self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertEqual(data["error"], "validation_error")

    def test_post_comment_conflict_not_found(self):
        """Test that posting comment to non-existent conflict returns 404."""
        self.client.force_login(self.reviewer1)

        import uuid

        invalid_conflict_id = uuid.uuid4()
        url = reverse("review_results_api:create-comment", args=[invalid_conflict_id])

        payload = {"content": "This comment should fail"}

        response = self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        data = response.json()
        self.assertEqual(data["error"], "not_found")

    def test_post_comment_non_reviewer_blocked(self):
        """Test that non-conflicting reviewers cannot post comments."""
        non_reviewer = create_test_user(username_prefix="non_reviewer")
        OrganisationMembership.objects.create(
            user=non_reviewer, organisation=self.organisation, role="REVIEWER"
        )

        # Participant, but not a conflicting reviewer and lacks CONFLICT_COMMENT ->
        # blocked by the secondary permission gate (403), not by session access.
        make_session_participant(self.session, non_reviewer)
        self.client.force_login(non_reviewer)
        url = reverse("review_results_api:create-comment", args=[self.conflict.id])

        payload = {"content": "I should not be able to post this"}

        response = self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        data = response.json()
        self.assertEqual(data["error"], "permission_denied")


class RevoteProposalAPITest(TestCase):
    """Test re-vote proposal workflow API endpoints."""

    def setUp(self):
        """Set up test data."""
        # Create organisation
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create users
        self.reviewer1 = create_test_user(username_prefix="reviewer1")
        self.reviewer2 = create_test_user(username_prefix="reviewer2")

        # Create organisation memberships (required for middleware)
        OrganisationMembership.objects.create(
            user=self.reviewer1, organisation=self.organisation, role="REVIEWER"
        )
        OrganisationMembership.objects.create(
            user=self.reviewer2, organisation=self.organisation, role="REVIEWER"
        )

        # Create session
        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.reviewer1,
            organisation=self.organisation,
            status="draft",
        )
        # reviewer1 owns the session; reviewer2 gains access as an accepted
        # reviewer (org membership alone no longer grants access -- GH #230).
        make_session_participant(self.session, self.reviewer2)

        # Create result
        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            url="https://example.com/test",
            snippet="Test snippet",
        )

        # Create conflicting decisions
        self.decision1 = ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.reviewer1,
            decision="INCLUDE",
            screening_stage="INITIAL",
            organisation=self.organisation,
        )
        self.decision2 = ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.reviewer2,
            decision="EXCLUDE",
            screening_stage="INITIAL",
            organisation=self.organisation,
        )

        # Create conflict
        self.conflict = ConflictResolution.objects.create(
            organisation=self.organisation,
            result=self.result,
            conflict_type="INCLUDE_EXCLUDE",
            status="PENDING",
        )
        self.conflict.conflicting_decisions.add(self.decision1, self.decision2)

    def test_propose_revote_success(self):
        """Test successfully proposing a re-vote."""
        self.client.force_login(self.reviewer1)
        url = reverse("review_results_api:propose-revote", args=[self.conflict.id])

        payload = {
            "rationale": "After reviewing the methodology, I think we should reconsider our initial decisions."
        }

        response = self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()

        # Verify proposal was created
        self.assertEqual(data["rationale"], payload["rationale"])
        self.assertEqual(data["status"], "PROPOSED")
        self.assertEqual(data["proposed_by"]["username"], self.reviewer1.username)

        # Verify in database
        proposal = RevoteProposal.objects.get(id=data["id"])
        self.assertEqual(proposal.conflict, self.conflict)
        self.assertEqual(proposal.proposed_by, self.reviewer1)

    def test_accept_revote_proposal_success(self):
        """Test successfully accepting a re-vote proposal."""
        # Create proposal first
        expires_at = timezone.now() + timedelta(hours=48)
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="We need to re-vote",
            expires_at=expires_at,
        )
        # Proposer auto-accepts (mimic API behavior)
        proposal.accepted_by.add(self.reviewer1)

        # Accept as reviewer2
        self.client.force_login(self.reviewer2)
        url = reverse(
            "review_results_api:accept-revote", args=[self.conflict.id, proposal.id]
        )

        response = self.client.post(url, content_type="application/json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        # Verify acceptance
        self.assertEqual(data["status"], "ACCEPTED")
        self.assertEqual(len(data["accepted_by"]), 2)  # Both reviewers accepted

        # Verify in database
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, "ACCEPTED")
        self.assertTrue(proposal.accepted_by.filter(id=self.reviewer2.id).exists())

    def test_submit_revote_decision_success(self):
        """Test successfully submitting a re-vote decision."""
        # Create and accept proposal
        expires_at = timezone.now() + timedelta(hours=48)
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="Re-vote needed",
            status="ACCEPTED",
            expires_at=expires_at,
        )
        proposal.accepted_by.add(self.reviewer1, self.reviewer2)

        # Submit re-vote decision
        self.client.force_login(self.reviewer1)
        url = reverse(
            "review_results_api:submit-revote-decision",
            args=[self.conflict.id, proposal.id],
        )

        payload = {
            "decision": "EXCLUDE",  # Changed from INCLUDE
            "exclusion_reason": "METHODOLOGY",  # Required for EXCLUDE decisions
            "notes": "After reconsidering, I think we should exclude this result.",
        }

        response = self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()

        # Verify re-vote decision was created
        self.assertEqual(data["decision"], "EXCLUDE")
        self.assertTrue(data["is_revote"])

        # Verify in database
        revote_decision = ReviewerDecision.objects.get(id=data["id"])
        self.assertEqual(revote_decision.decision, "EXCLUDE")
        self.assertTrue(revote_decision.is_revote)
        self.assertEqual(revote_decision.revote_proposal, proposal)

    def test_propose_revote_duplicate_prevention(self):
        """Test that proposing re-vote when active proposal exists is rejected."""
        # Create existing active proposal
        expires_at = timezone.now() + timedelta(hours=48)
        RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="First proposal",
            status="PROPOSED",
            expires_at=expires_at,
        )

        # Try to create second proposal
        self.client.force_login(self.reviewer2)
        url = reverse("review_results_api:propose-revote", args=[self.conflict.id])

        payload = {"rationale": "Second proposal attempt"}

        response = self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertEqual(data["error"], "proposal_not_allowed")

    def test_propose_revote_on_resolved_conflict(self):
        """Test that proposing re-vote on resolved conflict is rejected."""
        # Resolve the conflict first
        self.conflict.status = "RESOLVED"
        self.conflict.save()

        self.client.force_login(self.reviewer1)
        url = reverse("review_results_api:propose-revote", args=[self.conflict.id])

        payload = {"rationale": "Trying to re-vote resolved conflict"}

        response = self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertEqual(data["error"], "proposal_not_allowed")

    def test_propose_revote_missing_rationale(self):
        """Test that proposing re-vote without rationale is rejected."""
        self.client.force_login(self.reviewer1)
        url = reverse("review_results_api:propose-revote", args=[self.conflict.id])

        payload = {"rationale": ""}

        response = self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertEqual(data["error"], "validation_error")

    def test_accept_expired_proposal(self):
        """Test that accepting expired proposal is rejected."""
        # Create expired proposal
        expires_at = timezone.now() - timedelta(hours=1)  # Expired 1 hour ago
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="This proposal has expired",
            status="PROPOSED",
            expires_at=expires_at,
        )
        proposal.accepted_by.add(self.reviewer1)

        self.client.force_login(self.reviewer2)
        url = reverse(
            "review_results_api:accept-revote", args=[self.conflict.id, proposal.id]
        )

        response = self.client.post(url, content_type="application/json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertEqual(data["error"], "cannot_accept")

    def test_accept_proposal_already_accepted_status(self):
        """Test accepting proposal when status is already ACCEPTED."""
        # Create proposal that's already accepted
        expires_at = timezone.now() + timedelta(hours=48)
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="Already accepted proposal",
            status="ACCEPTED",
            expires_at=expires_at,
        )
        proposal.accepted_by.add(self.reviewer1, self.reviewer2)

        # Try to accept again (shouldn't cause error, but shouldn't change anything)
        self.client.force_login(self.reviewer1)
        url = reverse(
            "review_results_api:accept-revote", args=[self.conflict.id, proposal.id]
        )

        response = self.client.post(url, content_type="application/json")

        # Should be rejected since status is not PROPOSED
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ConsensusWorkflowIntegrationTest(TestCase):
    """Test complete consensus workflow from conflict to resolution."""

    def setUp(self):
        """Set up test data."""
        # Create organisation
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create users
        self.reviewer1 = create_test_user(username_prefix="reviewer1")
        self.reviewer2 = create_test_user(username_prefix="reviewer2")

        # Create organisation memberships (required for middleware)
        OrganisationMembership.objects.create(
            user=self.reviewer1, organisation=self.organisation, role="REVIEWER"
        )
        OrganisationMembership.objects.create(
            user=self.reviewer2, organisation=self.organisation, role="REVIEWER"
        )

        # Create session
        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.reviewer1,
            organisation=self.organisation,
            status="draft",
        )
        # reviewer1 owns the session; reviewer2 gains access as an accepted
        # reviewer (org membership alone no longer grants access -- GH #230).
        make_session_participant(self.session, self.reviewer2)

        # Create result
        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            url="https://example.com/test",
            snippet="Test snippet",
        )

        # Create conflicting decisions
        self.decision1 = ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.reviewer1,
            decision="INCLUDE",
            screening_stage="INITIAL",
            organisation=self.organisation,
        )
        self.decision2 = ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.reviewer2,
            decision="EXCLUDE",
            screening_stage="INITIAL",
            organisation=self.organisation,
        )

        # Create conflict
        self.conflict = ConflictResolution.objects.create(
            organisation=self.organisation,
            result=self.result,
            conflict_type="INCLUDE_EXCLUDE",
            status="PENDING",
        )
        self.conflict.conflicting_decisions.add(self.decision1, self.decision2)

    def test_complete_consensus_workflow(self):
        """
        Test complete workflow: conflict → discussion → re-vote → consensus.

        Steps:
        1. Post discussion comments
        2. Propose re-vote
        3. Accept re-vote proposal
        4. Submit re-vote decisions
        5. Verify consensus reached
        """
        # Step 1: Post discussion comments
        self.client.force_login(self.reviewer1)
        comment_url = reverse(
            "review_results_api:create-comment", args=[self.conflict.id]
        )

        comment_response = self.client.post(
            comment_url,
            data=json.dumps({"content": "I think we should discuss this further."}),
            content_type="application/json",
        )
        self.assertEqual(comment_response.status_code, status.HTTP_201_CREATED)

        # Step 2: Propose re-vote
        proposal_url = reverse(
            "review_results_api:propose-revote", args=[self.conflict.id]
        )

        proposal_response = self.client.post(
            proposal_url,
            data=json.dumps({"rationale": "After discussion, let's re-vote."}),
            content_type="application/json",
        )
        self.assertEqual(proposal_response.status_code, status.HTTP_201_CREATED)
        proposal_id = proposal_response.json()["id"]

        # Step 3: Accept re-vote proposal (as reviewer2)
        self.client.force_login(self.reviewer2)
        accept_url = reverse(
            "review_results_api:accept-revote", args=[self.conflict.id, proposal_id]
        )

        accept_response = self.client.post(accept_url, content_type="application/json")
        self.assertEqual(accept_response.status_code, status.HTTP_200_OK)
        self.assertEqual(accept_response.json()["status"], "ACCEPTED")

        # Step 4: Submit re-vote decisions (both agree on EXCLUDE)
        # Reviewer 1 changes to EXCLUDE
        self.client.force_login(self.reviewer1)
        decision_url = reverse(
            "review_results_api:submit-revote-decision",
            args=[self.conflict.id, proposal_id],
        )

        decision1_response = self.client.post(
            decision_url,
            data=json.dumps({"decision": "EXCLUDE", "exclusion_reason": "METHODOLOGY"}),
            content_type="application/json",
        )
        self.assertEqual(decision1_response.status_code, status.HTTP_201_CREATED)

        # Reviewer 2 confirms EXCLUDE
        self.client.force_login(self.reviewer2)

        decision2_response = self.client.post(
            decision_url,
            data=json.dumps({"decision": "EXCLUDE", "exclusion_reason": "METHODOLOGY"}),
            content_type="application/json",
        )
        self.assertEqual(decision2_response.status_code, status.HTTP_201_CREATED)

        # Step 5: Verify consensus reached
        self.conflict.refresh_from_db()
        self.assertEqual(self.conflict.status, "RESOLVED")
        self.assertEqual(self.conflict.resolution_method, "CONSENSUS")
        self.assertEqual(self.conflict.final_decision.decision, "EXCLUDE")


class RevoteDecisionEdgeCasesTest(TestCase):
    """Test edge cases for re-vote decision submission."""

    def setUp(self):
        """Set up test data."""
        # Create organisation
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create users
        self.reviewer1 = create_test_user(username_prefix="reviewer1")
        self.reviewer2 = create_test_user(username_prefix="reviewer2")

        # Create organisation memberships
        OrganisationMembership.objects.create(
            user=self.reviewer1, organisation=self.organisation, role="REVIEWER"
        )
        OrganisationMembership.objects.create(
            user=self.reviewer2, organisation=self.organisation, role="REVIEWER"
        )

        # Create session
        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.reviewer1,
            organisation=self.organisation,
            status="draft",
        )
        # reviewer1 owns the session; reviewer2 gains access as an accepted
        # reviewer (org membership alone no longer grants access -- GH #230).
        make_session_participant(self.session, self.reviewer2)

        # Create result
        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            url="https://example.com/test",
            snippet="Test snippet",
        )

        # Create conflicting decisions
        self.decision1 = ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.reviewer1,
            decision="INCLUDE",
            screening_stage="INITIAL",
            organisation=self.organisation,
        )
        self.decision2 = ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.reviewer2,
            decision="EXCLUDE",
            screening_stage="INITIAL",
            organisation=self.organisation,
        )

        # Create conflict
        self.conflict = ConflictResolution.objects.create(
            organisation=self.organisation,
            result=self.result,
            conflict_type="INCLUDE_EXCLUDE",
            status="PENDING",
        )
        self.conflict.conflicting_decisions.add(self.decision1, self.decision2)

    def test_submit_decision_before_proposal_acceptance(self):
        """Test that submitting decision before proposal is accepted is rejected."""
        # Create proposal that's still in PROPOSED status
        expires_at = timezone.now() + timedelta(hours=48)
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="Need re-vote",
            status="PROPOSED",  # Not yet accepted
            expires_at=expires_at,
        )
        proposal.accepted_by.add(self.reviewer1)

        self.client.force_login(self.reviewer2)
        url = reverse(
            "review_results_api:submit-revote-decision",
            args=[self.conflict.id, proposal.id],
        )

        payload = {"decision": "EXCLUDE", "exclusion_reason": "METHODOLOGY"}

        response = self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertEqual(data["error"], "proposal_not_accepted")

    def test_submit_duplicate_revote_decision(self):
        """Test that submitting duplicate re-vote decision is rejected."""
        # Create and accept proposal
        expires_at = timezone.now() + timedelta(hours=48)
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="Re-vote needed",
            status="ACCEPTED",
            expires_at=expires_at,
        )
        proposal.accepted_by.add(self.reviewer1, self.reviewer2)

        # Submit first decision
        ReviewerDecision.objects.create(
            organisation=self.organisation,
            result=self.result,
            reviewer=self.reviewer1,
            decision="EXCLUDE",
            exclusion_reason="METHODOLOGY",
            is_revote=True,
            revote_proposal=proposal,
            screening_stage="SCREENING",
            confidence_level=2,
        )

        # Try to submit second decision for same reviewer
        self.client.force_login(self.reviewer1)
        url = reverse(
            "review_results_api:submit-revote-decision",
            args=[self.conflict.id, proposal.id],
        )

        payload = {
            "decision": "INCLUDE",  # Different decision
            "notes": "Changed my mind again",
        }

        response = self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertEqual(data["error"], "already_voted")

    def test_submit_revote_decision_missing_exclusion_reason(self):
        """Test that EXCLUDE decision without exclusion_reason is rejected."""
        # Create and accept proposal
        expires_at = timezone.now() + timedelta(hours=48)
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="Re-vote needed",
            status="ACCEPTED",
            expires_at=expires_at,
        )
        proposal.accepted_by.add(self.reviewer1, self.reviewer2)

        self.client.force_login(self.reviewer1)
        url = reverse(
            "review_results_api:submit-revote-decision",
            args=[self.conflict.id, proposal.id],
        )

        payload = {
            "decision": "EXCLUDE",
            # Missing exclusion_reason
            "notes": "Should be excluded",
        }

        response = self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertEqual(data["error"], "validation_error")

    def test_submit_revote_decision_invalid_choice(self):
        """Test that invalid decision choice is rejected."""
        # Create and accept proposal
        expires_at = timezone.now() + timedelta(hours=48)
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="Re-vote needed",
            status="ACCEPTED",
            expires_at=expires_at,
        )
        proposal.accepted_by.add(self.reviewer1, self.reviewer2)

        self.client.force_login(self.reviewer1)
        url = reverse(
            "review_results_api:submit-revote-decision",
            args=[self.conflict.id, proposal.id],
        )

        payload = {
            "decision": "INVALID_DECISION",  # Invalid choice
            "notes": "This should fail",
        }

        response = self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertEqual(data["error"], "validation_error")

    def test_submit_revote_non_conflicting_reviewer(self):
        """Test that non-conflicting reviewer cannot submit re-vote decision."""
        # Create third reviewer who is a participant but not part of this conflict
        reviewer3 = create_test_user(username_prefix="reviewer3")
        OrganisationMembership.objects.create(
            user=reviewer3, organisation=self.organisation, role="REVIEWER"
        )
        make_session_participant(self.session, reviewer3)

        # Create and accept proposal
        expires_at = timezone.now() + timedelta(hours=48)
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="Re-vote needed",
            status="ACCEPTED",
            expires_at=expires_at,
        )
        proposal.accepted_by.add(self.reviewer1, self.reviewer2)

        self.client.force_login(reviewer3)
        url = reverse(
            "review_results_api:submit-revote-decision",
            args=[self.conflict.id, proposal.id],
        )

        payload = {"decision": "EXCLUDE", "exclusion_reason": "METHODOLOGY"}

        response = self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        data = response.json()
        self.assertEqual(data["error"], "permission_denied")


class ConsensusDetectionTest(TestCase):
    """Test consensus detection and resolution scenarios."""

    def setUp(self):
        """Set up test data."""
        # Create organisation
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create users
        self.reviewer1 = create_test_user(username_prefix="reviewer1")
        self.reviewer2 = create_test_user(username_prefix="reviewer2")

        # Create organisation memberships
        OrganisationMembership.objects.create(
            user=self.reviewer1, organisation=self.organisation, role="REVIEWER"
        )
        OrganisationMembership.objects.create(
            user=self.reviewer2, organisation=self.organisation, role="REVIEWER"
        )

        # Create session
        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.reviewer1,
            organisation=self.organisation,
            status="draft",
        )
        # reviewer1 owns the session; reviewer2 gains access as an accepted
        # reviewer (org membership alone no longer grants access -- GH #230).
        make_session_participant(self.session, self.reviewer2)

        # Create result
        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            url="https://example.com/test",
            snippet="Test snippet",
        )

        # Create conflicting decisions
        self.decision1 = ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.reviewer1,
            decision="INCLUDE",
            screening_stage="INITIAL",
            organisation=self.organisation,
        )
        self.decision2 = ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.reviewer2,
            decision="EXCLUDE",
            screening_stage="INITIAL",
            organisation=self.organisation,
        )

        # Create conflict
        self.conflict = ConflictResolution.objects.create(
            organisation=self.organisation,
            result=self.result,
            conflict_type="INCLUDE_EXCLUDE",
            status="PENDING",
        )
        self.conflict.conflicting_decisions.add(self.decision1, self.decision2)

    def test_no_consensus_scenario(self):
        """Test that when re-vote results in no consensus, conflict requires arbitration."""
        # Create and accept proposal
        expires_at = timezone.now() + timedelta(hours=48)
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="Re-vote needed",
            status="ACCEPTED",
            expires_at=expires_at,
        )
        proposal.accepted_by.add(self.reviewer1, self.reviewer2)

        # Submit conflicting re-vote decisions
        self.client.force_login(self.reviewer1)
        url = reverse(
            "review_results_api:submit-revote-decision",
            args=[self.conflict.id, proposal.id],
        )

        # Reviewer 1: INCLUDE
        payload1 = {"decision": "INCLUDE", "notes": "Still think it should be included"}
        response1 = self.client.post(
            url, data=json.dumps(payload1), content_type="application/json"
        )
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)

        # Reviewer 2: EXCLUDE
        self.client.force_login(self.reviewer2)
        payload2 = {
            "decision": "EXCLUDE",
            "exclusion_reason": "METHODOLOGY",
            "notes": "Still think it should be excluded",
        }
        response2 = self.client.post(
            url, data=json.dumps(payload2), content_type="application/json"
        )
        self.assertEqual(response2.status_code, status.HTTP_201_CREATED)

        # Verify proposal completed without consensus
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, "COMPLETED")
        self.assertFalse(proposal.resulted_in_consensus)

        # Verify conflict is NOT resolved
        self.conflict.refresh_from_db()
        self.assertNotEqual(self.conflict.status, "RESOLVED")

    def test_consensus_with_include_decision(self):
        """Test consensus reached with INCLUDE decision."""
        # Create and accept proposal
        expires_at = timezone.now() + timedelta(hours=48)
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="Re-vote needed",
            status="ACCEPTED",
            expires_at=expires_at,
        )
        proposal.accepted_by.add(self.reviewer1, self.reviewer2)

        # Submit matching INCLUDE re-vote decisions
        self.client.force_login(self.reviewer1)
        url = reverse(
            "review_results_api:submit-revote-decision",
            args=[self.conflict.id, proposal.id],
        )

        # Reviewer 1: INCLUDE
        payload1 = {"decision": "INCLUDE", "notes": "Agree on inclusion"}
        response1 = self.client.post(
            url, data=json.dumps(payload1), content_type="application/json"
        )
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)

        # Reviewer 2: INCLUDE
        self.client.force_login(self.reviewer2)
        payload2 = {"decision": "INCLUDE", "notes": "Agree on inclusion"}
        response2 = self.client.post(
            url, data=json.dumps(payload2), content_type="application/json"
        )
        self.assertEqual(response2.status_code, status.HTTP_201_CREATED)

        # Verify proposal completed with consensus
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, "COMPLETED")
        self.assertTrue(proposal.resulted_in_consensus)

        # Verify conflict is resolved
        self.conflict.refresh_from_db()
        self.assertEqual(self.conflict.status, "RESOLVED")
        self.assertEqual(self.conflict.resolution_method, "CONSENSUS")
        self.assertEqual(self.conflict.final_decision.decision, "INCLUDE")
