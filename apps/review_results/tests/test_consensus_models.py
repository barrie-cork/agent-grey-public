"""
Unit tests for consensus discussion models.

Tests ConflictComment, RevoteProposal, and ConflictResolution helper methods.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.organisation.models import Organisation
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.review_results.models import (
    ConflictComment,
    ConflictResolution,
    ReviewerDecision,
    RevoteProposal,
)
from apps.core.tests.utils import create_test_user

User = get_user_model()


class ConflictCommentModelTest(TestCase):
    """Test the ConflictComment model."""

    def setUp(self):
        """Set up test data."""
        # Create organisation
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create users
        self.user1 = create_test_user(username_prefix="reviewer1")
        self.user2 = create_test_user(username_prefix="reviewer2")

        # Create session
        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.user1,
            organisation=self.organisation,
            status="draft",
        )

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
            reviewer=self.user1,
            decision="INCLUDE",
            screening_stage="INITIAL",
            organisation=self.organisation,
        )
        self.decision2 = ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.user2,
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

    def test_create_simple_comment(self):
        """Test creating a simple comment."""
        comment = ConflictComment.objects.create(
            conflict=self.conflict, author=self.user1, content="This is a test comment"
        )

        self.assertEqual(comment.conflict, self.conflict)
        self.assertEqual(comment.author, self.user1)
        self.assertEqual(comment.content, "This is a test comment")
        self.assertFalse(comment.is_deleted)
        self.assertFalse(comment.is_system_message)
        self.assertFalse(comment.is_edited)

    def test_markdown_rendering(self):
        """Test that markdown is rendered to HTML on save."""
        comment = ConflictComment.objects.create(
            conflict=self.conflict,
            author=self.user1,
            content="**Bold text** and *italic text*",
        )

        # Check that HTML was generated
        self.assertIn("<strong>Bold text</strong>", comment.content_html)
        self.assertIn("<em>italic text</em>", comment.content_html)

    def test_markdown_code_blocks(self):
        """Test markdown fenced code blocks."""
        comment = ConflictComment.objects.create(
            conflict=self.conflict,
            author=self.user1,
            content="```python\nprint('hello')\n```",
        )

        # Check that code block was rendered with language class
        self.assertIn('<code class="language-python">', comment.content_html)
        self.assertIn("print('hello')", comment.content_html)

    def test_threaded_comments(self):
        """Test parent/child relationship for threading."""
        # Create parent comment
        parent = ConflictComment.objects.create(
            conflict=self.conflict, author=self.user1, content="Parent comment"
        )

        # Create child comments
        child1 = ConflictComment.objects.create(
            conflict=self.conflict,
            author=self.user2,
            content="First reply",
            parent=parent,
        )
        child2 = ConflictComment.objects.create(
            conflict=self.conflict,
            author=self.user1,
            content="Second reply",
            parent=parent,
        )

        # Test relationships
        self.assertEqual(parent.replies.count(), 2)
        self.assertIn(child1, parent.replies.all())
        self.assertIn(child2, parent.replies.all())
        self.assertEqual(child1.parent, parent)
        self.assertEqual(child2.parent, parent)

    def test_soft_delete_flag(self):
        """Test soft delete functionality."""
        comment = ConflictComment.objects.create(
            conflict=self.conflict, author=self.user1, content="This will be deleted"
        )

        # Soft delete
        comment.is_deleted = True
        comment.save()

        # Comment still exists in database
        self.assertTrue(ConflictComment.objects.filter(id=comment.id).exists())
        # But is marked as deleted
        comment.refresh_from_db()
        self.assertTrue(comment.is_deleted)

    def test_system_message_flag(self):
        """Test system message flag."""
        comment = ConflictComment.objects.create(
            conflict=self.conflict,
            author=None,  # System messages have no author
            content="Re-vote proposal accepted",
            is_system_message=True,
        )

        self.assertTrue(comment.is_system_message)
        self.assertIsNone(comment.author)

    def test_str_representation(self):
        """Test string representation."""
        comment = ConflictComment.objects.create(
            conflict=self.conflict, author=self.user1, content="Test comment"
        )

        expected = f"Comment by {self.user1.username} on conflict {self.conflict.id}"
        self.assertEqual(str(comment), expected)

    def test_str_representation_no_author(self):
        """Test string representation with no author."""
        comment = ConflictComment.objects.create(
            conflict=self.conflict,
            author=None,
            content="System message",
            is_system_message=True,
        )

        self.assertIn("Unknown", str(comment))

    def test_ordering(self):
        """Test comments are ordered by created_at."""
        # Create comments at different times
        comment1 = ConflictComment.objects.create(
            conflict=self.conflict, author=self.user1, content="First comment"
        )
        comment2 = ConflictComment.objects.create(
            conflict=self.conflict, author=self.user2, content="Second comment"
        )
        comment3 = ConflictComment.objects.create(
            conflict=self.conflict, author=self.user1, content="Third comment"
        )

        # Get all comments
        comments = list(self.conflict.comments.all())

        # Verify chronological order
        self.assertEqual(comments[0], comment1)
        self.assertEqual(comments[1], comment2)
        self.assertEqual(comments[2], comment3)

    def test_cascade_delete_conflict(self):
        """Test comments are deleted when conflict is deleted."""
        comment = ConflictComment.objects.create(
            conflict=self.conflict, author=self.user1, content="Test comment"
        )

        comment_id = comment.id
        self.conflict.delete()

        # Comment should be deleted
        self.assertFalse(ConflictComment.objects.filter(id=comment_id).exists())

    def test_set_null_on_author_delete(self):
        """Test author is set to NULL when user is deleted."""
        # Create a separate user with no ReviewerDecision records (which have PROTECT FK)
        deletable_user = create_test_user(username_prefix="deletable")
        comment = ConflictComment.objects.create(
            conflict=self.conflict, author=deletable_user, content="Test comment"
        )

        deletable_user.delete()
        comment.refresh_from_db()

        # Comment preserved but author is None
        self.assertIsNone(comment.author)

    def test_cascade_delete_parent(self):
        """Test replies are deleted when parent is deleted."""
        parent = ConflictComment.objects.create(
            conflict=self.conflict, author=self.user1, content="Parent"
        )
        child = ConflictComment.objects.create(
            conflict=self.conflict, author=self.user2, content="Child", parent=parent
        )

        child_id = child.id
        parent.delete()

        # Child should be deleted
        self.assertFalse(ConflictComment.objects.filter(id=child_id).exists())


class RevoteProposalModelTest(TestCase):
    """Test the RevoteProposal model."""

    def setUp(self):
        """Set up test data."""
        # Create organisation
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create users
        self.user1 = create_test_user(username_prefix="reviewer1")
        self.user2 = create_test_user(username_prefix="reviewer2")

        # Create session
        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.user1,
            organisation=self.organisation,
            status="draft",
        )

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
            reviewer=self.user1,
            decision="INCLUDE",
            screening_stage="INITIAL",
            organisation=self.organisation,
        )
        self.decision2 = ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.user2,
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

    def test_create_proposal(self):
        """Test creating a re-vote proposal."""
        expires_at = timezone.now() + timedelta(hours=48)
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user1,
            rationale="We need to re-evaluate this result",
            expires_at=expires_at,
        )

        self.assertEqual(proposal.conflict, self.conflict)
        self.assertEqual(proposal.proposed_by, self.user1)
        self.assertEqual(proposal.status, "PROPOSED")
        self.assertFalse(proposal.resulted_in_consensus)
        self.assertEqual(proposal.rationale, "We need to re-evaluate this result")

    def test_status_choices(self):
        """Test all status choices work."""
        expires_at = timezone.now() + timedelta(hours=48)
        statuses = ["PROPOSED", "ACCEPTED", "IN_PROGRESS", "COMPLETED", "EXPIRED"]

        for status in statuses:
            with self.subTest(status=status):
                proposal = RevoteProposal.objects.create(
                    conflict=self.conflict,
                    proposed_by=self.user1,
                    rationale=f"Test {status}",
                    status=status,
                    expires_at=expires_at,
                )
                self.assertEqual(proposal.status, status)

    def test_is_expired_method(self):
        """Test is_expired() method."""
        # Create expired proposal
        past_time = timezone.now() - timedelta(hours=1)
        expired_proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user1,
            rationale="Old proposal",
            status="PROPOSED",
            expires_at=past_time,
        )

        # Create active proposal
        future_time = timezone.now() + timedelta(hours=48)
        active_proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user1,
            rationale="Active proposal",
            status="PROPOSED",
            expires_at=future_time,
        )

        self.assertTrue(expired_proposal.is_expired())
        self.assertFalse(active_proposal.is_expired())

    def test_is_expired_only_for_proposed_status(self):
        """Test that is_expired() only returns True for PROPOSED status."""
        past_time = timezone.now() - timedelta(hours=1)

        # Accepted proposal past expiry time shouldn't be considered expired
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user1,
            rationale="Accepted proposal",
            status="ACCEPTED",
            expires_at=past_time,
        )

        self.assertFalse(proposal.is_expired())

    def test_can_accept_method_valid_reviewer(self):
        """Test can_accept() returns True for conflicting reviewer."""
        expires_at = timezone.now() + timedelta(hours=48)
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user1,
            rationale="Test proposal",
            expires_at=expires_at,
        )

        # Both conflicting reviewers can accept
        self.assertTrue(proposal.can_accept(self.user1))
        self.assertTrue(proposal.can_accept(self.user2))

    def test_can_accept_method_invalid_reviewer(self):
        """Test can_accept() returns False for non-conflicting reviewer."""
        user3 = create_test_user(username_prefix="reviewer3")

        expires_at = timezone.now() + timedelta(hours=48)
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user1,
            rationale="Test proposal",
            expires_at=expires_at,
        )

        # User3 is not involved in the conflict
        self.assertFalse(proposal.can_accept(user3))

    def test_can_accept_method_expired_proposal(self):
        """Test can_accept() returns False for expired proposal."""
        past_time = timezone.now() - timedelta(hours=1)
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user1,
            rationale="Expired proposal",
            expires_at=past_time,
        )

        self.assertFalse(proposal.can_accept(self.user1))

    def test_can_accept_method_non_proposed_status(self):
        """Test can_accept() returns False for non-PROPOSED status."""
        expires_at = timezone.now() + timedelta(hours=48)
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user1,
            rationale="Completed proposal",
            status="COMPLETED",
            expires_at=expires_at,
        )

        self.assertFalse(proposal.can_accept(self.user1))

    def test_all_accepted_method(self):
        """Test all_accepted() method."""
        expires_at = timezone.now() + timedelta(hours=48)
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user1,
            rationale="Test proposal",
            expires_at=expires_at,
        )

        # Initially, no one has accepted
        self.assertFalse(proposal.all_accepted())

        # User1 accepts
        proposal.accepted_by.add(self.user1)
        self.assertFalse(proposal.all_accepted())

        # User2 accepts
        proposal.accepted_by.add(self.user2)
        self.assertTrue(proposal.all_accepted())

    def test_many_to_many_accepted_by(self):
        """Test ManyToMany relationship for accepted_by."""
        expires_at = timezone.now() + timedelta(hours=48)
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user1,
            rationale="Test proposal",
            expires_at=expires_at,
        )

        # Add reviewers who accepted
        proposal.accepted_by.add(self.user1, self.user2)

        # Verify relationship
        self.assertEqual(proposal.accepted_by.count(), 2)
        self.assertIn(self.user1, proposal.accepted_by.all())
        self.assertIn(self.user2, proposal.accepted_by.all())

    def test_str_representation(self):
        """Test string representation."""
        expires_at = timezone.now() + timedelta(hours=48)
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user1,
            rationale="Test proposal",
            expires_at=expires_at,
        )

        expected = f"Re-vote proposal for conflict {self.conflict.id} (PROPOSED)"
        self.assertEqual(str(proposal), expected)

    def test_ordering(self):
        """Test proposals are ordered by -proposed_at."""
        expires_at = timezone.now() + timedelta(hours=48)

        proposal1 = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user1,
            rationale="First proposal",
            expires_at=expires_at,
        )
        proposal2 = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user2,
            rationale="Second proposal",
            expires_at=expires_at,
        )

        # Get all proposals
        proposals = list(self.conflict.revote_proposals.all())

        # Verify reverse chronological order
        self.assertEqual(proposals[0], proposal2)
        self.assertEqual(proposals[1], proposal1)


class ConflictResolutionHelperMethodsTest(TestCase):
    """Test the ConflictResolution helper methods."""

    def setUp(self):
        """Set up test data."""
        # Create organisation
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create users
        self.user1 = create_test_user(username_prefix="reviewer1")
        self.user2 = create_test_user(username_prefix="reviewer2")

        # Create session
        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.user1,
            organisation=self.organisation,
            status="draft",
        )

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
            reviewer=self.user1,
            decision="INCLUDE",
            screening_stage="INITIAL",
            organisation=self.organisation,
        )
        self.decision2 = ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.user2,
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

    def test_get_discussion_summary_no_activity(self):
        """Test get_discussion_summary() with no comments."""
        summary = self.conflict.get_discussion_summary()

        self.assertEqual(summary["comment_count"], 0)
        self.assertEqual(summary["participant_count"], 0)
        self.assertEqual(summary["revote_count"], 0)
        self.assertIsNone(summary["last_activity"])

    def test_get_discussion_summary_with_comments(self):
        """Test get_discussion_summary() with comments."""
        # Create comments
        ConflictComment.objects.create(
            conflict=self.conflict, author=self.user1, content="First comment"
        )
        ConflictComment.objects.create(
            conflict=self.conflict, author=self.user2, content="Second comment"
        )
        ConflictComment.objects.create(
            conflict=self.conflict, author=self.user1, content="Third comment"
        )

        summary = self.conflict.get_discussion_summary()

        self.assertEqual(summary["comment_count"], 3)
        self.assertEqual(summary["participant_count"], 2)  # 2 unique authors
        self.assertIsNotNone(summary["last_activity"])

    def test_get_discussion_summary_excludes_deleted_comments(self):
        """Test that deleted comments are excluded from summary."""
        ConflictComment.objects.create(
            conflict=self.conflict, author=self.user1, content="Active comment"
        )
        ConflictComment.objects.create(
            conflict=self.conflict,
            author=self.user2,
            content="Deleted comment",
            is_deleted=True,
        )

        summary = self.conflict.get_discussion_summary()

        self.assertEqual(summary["comment_count"], 1)

    def test_get_discussion_summary_with_revote_proposals(self):
        """Test get_discussion_summary() includes revote count."""
        expires_at = timezone.now() + timedelta(hours=48)
        RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user1,
            rationale="First proposal",
            expires_at=expires_at,
        )
        RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user2,
            rationale="Second proposal",
            expires_at=expires_at,
        )

        summary = self.conflict.get_discussion_summary()

        self.assertEqual(summary["revote_count"], 2)

    def test_has_active_revote_proposal_false(self):
        """Test has_active_revote_proposal() returns False when no active proposals."""
        self.assertFalse(self.conflict.has_active_revote_proposal())

    def test_has_active_revote_proposal_proposed_status(self):
        """Test has_active_revote_proposal() returns True for PROPOSED status."""
        expires_at = timezone.now() + timedelta(hours=48)
        RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user1,
            rationale="Test",
            status="PROPOSED",
            expires_at=expires_at,
        )

        self.assertTrue(self.conflict.has_active_revote_proposal())

    def test_has_active_revote_proposal_accepted_status(self):
        """Test has_active_revote_proposal() returns True for ACCEPTED status."""
        expires_at = timezone.now() + timedelta(hours=48)
        RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user1,
            rationale="Test",
            status="ACCEPTED",
            expires_at=expires_at,
        )

        self.assertTrue(self.conflict.has_active_revote_proposal())

    def test_has_active_revote_proposal_in_progress_status(self):
        """Test has_active_revote_proposal() returns True for IN_PROGRESS status."""
        expires_at = timezone.now() + timedelta(hours=48)
        RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user1,
            rationale="Test",
            status="IN_PROGRESS",
            expires_at=expires_at,
        )

        self.assertTrue(self.conflict.has_active_revote_proposal())

    def test_has_active_revote_proposal_completed_status(self):
        """Test has_active_revote_proposal() returns False for COMPLETED status."""
        expires_at = timezone.now() + timedelta(hours=48)
        RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user1,
            rationale="Test",
            status="COMPLETED",
            expires_at=expires_at,
        )

        self.assertFalse(self.conflict.has_active_revote_proposal())

    def test_has_active_revote_proposal_expired_status(self):
        """Test has_active_revote_proposal() returns False for EXPIRED status."""
        expires_at = timezone.now() + timedelta(hours=48)
        RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user1,
            rationale="Test",
            status="EXPIRED",
            expires_at=expires_at,
        )

        self.assertFalse(self.conflict.has_active_revote_proposal())

    def test_can_propose_revote_authorized_user(self):
        """Test can_propose_revote() returns True for conflicting reviewer."""
        self.assertTrue(self.conflict.can_propose_revote(self.user1))
        self.assertTrue(self.conflict.can_propose_revote(self.user2))

    def test_can_propose_revote_unauthorized_user(self):
        """Test can_propose_revote() returns False for non-conflicting reviewer."""
        user3 = create_test_user(username_prefix="reviewer3")

        self.assertFalse(self.conflict.can_propose_revote(user3))

    def test_can_propose_revote_with_active_proposal(self):
        """Test can_propose_revote() returns False when active proposal exists."""
        expires_at = timezone.now() + timedelta(hours=48)
        RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user1,
            rationale="Active proposal",
            status="PROPOSED",
            expires_at=expires_at,
        )

        self.assertFalse(self.conflict.can_propose_revote(self.user2))

    def test_can_propose_revote_resolved_conflict(self):
        """Test can_propose_revote() returns False for resolved conflict."""
        self.conflict.status = "RESOLVED"
        self.conflict.save()

        self.assertFalse(self.conflict.can_propose_revote(self.user1))

    def test_get_active_revote_proposal_none(self):
        """Test get_active_revote_proposal() returns None when no active proposals."""
        self.assertIsNone(self.conflict.get_active_revote_proposal())

    def test_get_active_revote_proposal_returns_proposal(self):
        """Test get_active_revote_proposal() returns active proposal."""
        expires_at = timezone.now() + timedelta(hours=48)
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user1,
            rationale="Active proposal",
            status="PROPOSED",
            expires_at=expires_at,
        )

        active_proposal = self.conflict.get_active_revote_proposal()
        self.assertEqual(active_proposal, proposal)

    def test_get_active_revote_proposal_returns_first_if_multiple(self):
        """Test get_active_revote_proposal() returns first active proposal."""
        expires_at = timezone.now() + timedelta(hours=48)

        # Create two active proposals (shouldn't happen in practice, but test edge case)
        proposal1 = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user1,
            rationale="First proposal",
            status="PROPOSED",
            expires_at=expires_at,
        )
        RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user2,
            rationale="Second proposal",
            status="PROPOSED",
            expires_at=expires_at,
        )

        # Should return the most recent one (newest first ordering)
        active_proposal = self.conflict.get_active_revote_proposal()
        self.assertIsNotNone(active_proposal)
        # Will return the second one due to -proposed_at ordering
        self.assertNotEqual(active_proposal, proposal1)
