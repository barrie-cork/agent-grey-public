"""
Unit tests for consensus discussion serializers (Phase 2).

Tests all serializers for the consensus discussion feature:
- ConflictCommentSerializer (read-only with nested replies)
- ConflictCommentCreateSerializer (write with validation)
- RevoteProposalSerializer (read-only with acceptance tracking)
- ReviewerDecisionCreateSerializer (write for re-vote decisions)
- ConflictResolutionDetailSerializer (extended with discussion data)
"""

import uuid
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.review_results.models import (
    ConflictResolution,
    ConflictComment,
    RevoteProposal,
)
from apps.core.tests.utils import create_test_user
from apps.review_results.serializers import (
    ConflictCommentSerializer,
    ConflictCommentCreateSerializer,
    RevoteProposalSerializer,
    ReviewerDecisionCreateSerializer,
    ConflictResolutionDetailSerializer,
)
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.organisation.models import Organisation

User = get_user_model()


class ConflictCommentSerializerTests(TestCase):
    """Test ConflictCommentSerializer (read-only)."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all tests."""
        # Create organisation
        cls.org = Organisation.objects.create(
            name="Test Organisation",
            slug="test-org",
        )

        # Create users
        cls.user1 = create_test_user(
            username_prefix="reviewer1", first_name="John", last_name="Doe"
        )
        cls.user2 = create_test_user(
            username_prefix="reviewer2", first_name="Jane", last_name="Smith"
        )

        # Create session and result
        cls.session = SearchSession.objects.create(
            title="Test Session",
            organisation=cls.org,
            owner=cls.user1,
            status="draft",
        )
        cls.result = ProcessedResult.objects.create(
            session=cls.session,
            title="Test Result",
            snippet="Test snippet",
            url="https://example.com",
        )

        # Create conflict
        cls.conflict = ConflictResolution.objects.create(
            result=cls.result,
            conflict_type="INCLUDE_EXCLUDE",
            status="PENDING",
            organisation=cls.org,
        )

    def test_serialize_simple_comment(self):
        """Test serializing a comment without replies."""
        comment = ConflictComment.objects.create(
            conflict=self.conflict,
            author=self.user1,
            content="**This** is a test comment",
        )

        serializer = ConflictCommentSerializer(comment)
        data = serializer.data

        # Verify basic fields
        self.assertEqual(data["id"], str(comment.id))
        self.assertEqual(data["content"], "**This** is a test comment")
        self.assertIn("<strong>This</strong>", data["content_html"])
        self.assertEqual(data["is_deleted"], False)
        self.assertEqual(data["is_system_message"], False)

        # Verify author nested serialization
        self.assertEqual(data["author"]["username"], self.user1.username)
        self.assertEqual(data["author"]["first_name"], "John")
        self.assertEqual(data["author"]["last_name"], "Doe")

        # Verify no replies
        self.assertEqual(data["replies"], [])

    def test_serialize_threaded_comments(self):
        """Test serializing comments with nested replies."""
        # Create parent comment
        parent = ConflictComment.objects.create(
            conflict=self.conflict,
            author=self.user1,
            content="Parent comment",
        )

        # Create child comments
        child1 = ConflictComment.objects.create(
            conflict=self.conflict,
            author=self.user2,
            parent=parent,
            content="Child 1",
        )
        ConflictComment.objects.create(
            conflict=self.conflict,
            author=self.user1,
            parent=parent,
            content="Child 2",
        )

        # Create grandchild comment
        ConflictComment.objects.create(
            conflict=self.conflict,
            author=self.user2,
            parent=child1,
            content="Grandchild",
        )

        serializer = ConflictCommentSerializer(parent)
        data = serializer.data

        # Verify parent has 2 replies
        self.assertEqual(len(data["replies"]), 2)

        # Verify child1 has 1 reply (grandchild)
        child1_data = next(r for r in data["replies"] if r["content"] == "Child 1")
        self.assertEqual(len(child1_data["replies"]), 1)
        self.assertEqual(child1_data["replies"][0]["content"], "Grandchild")

        # Verify child2 has no replies
        child2_data = next(r for r in data["replies"] if r["content"] == "Child 2")
        self.assertEqual(len(child2_data["replies"]), 0)

    def test_exclude_deleted_comments_from_replies(self):
        """Test that soft-deleted comments are excluded from replies."""
        parent = ConflictComment.objects.create(
            conflict=self.conflict,
            author=self.user1,
            content="Parent",
        )

        # Create active and deleted replies
        ConflictComment.objects.create(
            conflict=self.conflict,
            author=self.user2,
            parent=parent,
            content="Active reply",
        )
        ConflictComment.objects.create(
            conflict=self.conflict,
            author=self.user2,
            parent=parent,
            content="Deleted reply",
            is_deleted=True,
        )

        serializer = ConflictCommentSerializer(parent)
        data = serializer.data

        # Should only show active reply
        self.assertEqual(len(data["replies"]), 1)
        self.assertEqual(data["replies"][0]["content"], "Active reply")

    def test_serialize_system_message(self):
        """Test serializing system-generated messages."""
        comment = ConflictComment.objects.create(
            conflict=self.conflict,
            author=None,  # System messages have no author
            content="System: Re-vote proposal accepted",
            is_system_message=True,
        )

        serializer = ConflictCommentSerializer(comment)
        data = serializer.data

        self.assertTrue(data["is_system_message"])
        self.assertIsNone(data["author"])

    def test_serialize_edited_comment(self):
        """Test serializing edited comments."""
        comment = ConflictComment.objects.create(
            conflict=self.conflict,
            author=self.user1,
            content="Original content",
        )

        # Simulate editing
        comment.content = "Edited content"
        comment.is_edited = True
        comment.edited_at = timezone.now()
        comment.save()

        serializer = ConflictCommentSerializer(comment)
        data = serializer.data

        self.assertTrue(data["is_edited"])
        self.assertIsNotNone(data["edited_at"])
        self.assertEqual(data["content"], "Edited content")


class ConflictCommentCreateSerializerTests(TestCase):
    """Test ConflictCommentCreateSerializer (write)."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all tests."""
        cls.org = Organisation.objects.create(
            name="Test Organisation",
            slug="test-org",
        )
        cls.user = create_test_user(username_prefix="reviewer")
        cls.session = SearchSession.objects.create(
            title="Test Session",
            organisation=cls.org,
            owner=cls.user,
            status="draft",
        )
        cls.result = ProcessedResult.objects.create(
            session=cls.session,
            title="Test Result",
            snippet="Test snippet",
            url="https://example.com",
        )
        cls.conflict = ConflictResolution.objects.create(
            result=cls.result,
            conflict_type="INCLUDE_EXCLUDE",
            status="PENDING",
            organisation=cls.org,
        )

    def test_valid_simple_comment(self):
        """Test creating a simple comment without parent."""
        data = {
            "content": "This is a test comment",
        }

        serializer = ConflictCommentCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["content"], "This is a test comment")

    def test_valid_reply_comment(self):
        """Test creating a reply to another comment."""
        parent = ConflictComment.objects.create(
            conflict=self.conflict,
            author=self.user,
            content="Parent comment",
        )

        data = {
            "content": "This is a reply",
            "parent_id": str(parent.id),
        }

        serializer = ConflictCommentCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_empty_content_validation(self):
        """Test that empty content is rejected."""
        data = {
            "content": "",
        }

        serializer = ConflictCommentCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("content", serializer.errors)

    def test_whitespace_only_content_validation(self):
        """Test that whitespace-only content is rejected."""
        data = {
            "content": "   \n\t  ",
        }

        serializer = ConflictCommentCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("content", serializer.errors)

    def test_content_too_long_validation(self):
        """Test that content exceeding max length is rejected."""
        data = {
            "content": "x" * 5001,  # Max is 5000
        }

        serializer = ConflictCommentCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("content", serializer.errors)

    def test_invalid_parent_id_validation(self):
        """Test that invalid parent_id is rejected."""
        data = {
            "content": "Test comment",
            "parent_id": str(uuid.uuid4()),  # Non-existent UUID
        }

        serializer = ConflictCommentCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("parent_id", serializer.errors)

    def test_parent_from_different_conflict_validation(self):
        """Test that parent from different conflict is rejected."""
        # Create another conflict
        other_result = ProcessedResult.objects.create(
            session=self.session,
            title="Other Result",
            snippet="Other snippet",
            url="https://example.com/other",
        )
        other_conflict = ConflictResolution.objects.create(
            result=other_result,
            conflict_type="INCLUDE_EXCLUDE",
            status="PENDING",
            organisation=self.org,
        )

        parent = ConflictComment.objects.create(
            conflict=other_conflict,
            author=self.user,
            content="Parent in different conflict",
        )

        data = {
            "content": "Reply to parent",
            "parent_id": str(parent.id),
        }

        serializer = ConflictCommentCreateSerializer(data=data)
        serializer.conflict = self.conflict  # Set conflict context

        self.assertFalse(serializer.is_valid())
        self.assertIn("parent_id", serializer.errors)

    def test_content_whitespace_stripping(self):
        """Test that content whitespace is stripped."""
        data = {
            "content": "   Test comment   ",
        }

        serializer = ConflictCommentCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["content"], "Test comment")


class RevoteProposalSerializerTests(TestCase):
    """Test RevoteProposalSerializer (read-only)."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all tests."""
        cls.org = Organisation.objects.create(
            name="Test Organisation",
            slug="test-org",
        )
        cls.user1 = create_test_user(
            username_prefix="reviewer1", first_name="John", last_name="Doe"
        )
        cls.user2 = create_test_user(
            username_prefix="reviewer2", first_name="Jane", last_name="Smith"
        )
        cls.session = SearchSession.objects.create(
            title="Test Session",
            organisation=cls.org,
            owner=cls.user1,
            status="draft",
        )
        cls.result = ProcessedResult.objects.create(
            session=cls.session,
            title="Test Result",
            snippet="Test snippet",
            url="https://example.com",
        )
        cls.conflict = ConflictResolution.objects.create(
            result=cls.result,
            conflict_type="INCLUDE_EXCLUDE",
            status="PENDING",
            organisation=cls.org,
        )

    def test_serialize_proposed_proposal(self):
        """Test serializing a PROPOSED proposal."""
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user1,
            rationale="Let's review this again",
            expires_at=timezone.now() + timedelta(hours=48),
        )

        serializer = RevoteProposalSerializer(proposal)
        data = serializer.data

        # Verify basic fields
        self.assertEqual(data["id"], str(proposal.id))
        self.assertEqual(data["rationale"], "Let's review this again")
        self.assertEqual(data["status"], "PROPOSED")
        self.assertEqual(data["status_display"], "Proposed")

        # Verify proposed_by nested serialization
        self.assertEqual(data["proposed_by"]["username"], self.user1.username)
        self.assertEqual(data["proposed_by"]["first_name"], "John")

        # Verify empty accepted_by
        self.assertEqual(data["accepted_by"], [])

        # Verify not expired
        self.assertFalse(data["is_expired"])

    def test_serialize_accepted_proposal(self):
        """Test serializing an ACCEPTED proposal with multiple acceptors."""
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user1,
            rationale="Re-vote needed",
            status="ACCEPTED",
            accepted_at=timezone.now(),
            expires_at=timezone.now() + timedelta(hours=48),
        )
        proposal.accepted_by.add(self.user1, self.user2)

        serializer = RevoteProposalSerializer(proposal)
        data = serializer.data

        # Verify status
        self.assertEqual(data["status"], "ACCEPTED")
        self.assertEqual(data["status_display"], "Accepted")

        # Verify accepted_by includes both users
        self.assertEqual(len(data["accepted_by"]), 2)
        usernames = {u["username"] for u in data["accepted_by"]}
        self.assertEqual(usernames, {self.user1.username, self.user2.username})

        # Verify accepted_at timestamp
        self.assertIsNotNone(data["accepted_at"])

    def test_serialize_completed_proposal(self):
        """Test serializing a COMPLETED proposal."""
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user1,
            rationale="Re-vote needed",
            status="COMPLETED",
            accepted_at=timezone.now() - timedelta(hours=24),
            completed_at=timezone.now(),
            resulted_in_consensus=True,
            expires_at=timezone.now() + timedelta(hours=24),
        )
        proposal.accepted_by.add(self.user1, self.user2)

        serializer = RevoteProposalSerializer(proposal)
        data = serializer.data

        # Verify completion fields
        self.assertEqual(data["status"], "COMPLETED")
        self.assertIsNotNone(data["completed_at"])
        self.assertTrue(data["resulted_in_consensus"])

    def test_is_expired_computed_field(self):
        """Test is_expired computed field."""
        # Create expired proposal
        expired_proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user1,
            rationale="Expired proposal",
            expires_at=timezone.now() - timedelta(hours=1),
        )

        serializer = RevoteProposalSerializer(expired_proposal)
        data = serializer.data

        self.assertTrue(data["is_expired"])

    def test_proposal_with_no_acceptors(self):
        """Test proposal with no accepted_by users."""
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.user1,
            rationale="New proposal",
            expires_at=timezone.now() + timedelta(hours=48),
        )

        serializer = RevoteProposalSerializer(proposal)
        data = serializer.data

        self.assertEqual(data["accepted_by"], [])


class ReviewerDecisionCreateSerializerTests(TestCase):
    """Test ReviewerDecisionCreateSerializer (write)."""

    def test_valid_include_decision(self):
        """Test valid INCLUDE decision."""
        data = {
            "decision": "INCLUDE",
            "notes": "Relevant to the review",
        }

        serializer = ReviewerDecisionCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_valid_exclude_decision_with_reason(self):
        """Test valid EXCLUDE decision with exclusion_reason."""
        data = {
            "decision": "EXCLUDE",
            "exclusion_reason": "Not relevant",
            "notes": "Does not meet criteria",
        }

        serializer = ReviewerDecisionCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_valid_maybe_decision(self):
        """Test valid MAYBE decision."""
        data = {
            "decision": "MAYBE",
            "notes": "Need more information",
        }

        serializer = ReviewerDecisionCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_exclude_without_reason_validation(self):
        """Test that EXCLUDE without exclusion_reason is rejected."""
        data = {
            "decision": "EXCLUDE",
            "notes": "Some notes",
        }

        serializer = ReviewerDecisionCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("exclusion_reason", serializer.errors)

    def test_include_with_reason_validation(self):
        """Test that INCLUDE with exclusion_reason is rejected."""
        data = {
            "decision": "INCLUDE",
            "exclusion_reason": "Should not have this",
        }

        serializer = ReviewerDecisionCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("exclusion_reason", serializer.errors)

    def test_maybe_with_reason_validation(self):
        """Test that MAYBE with exclusion_reason is rejected."""
        data = {
            "decision": "MAYBE",
            "exclusion_reason": "Should not have this",
        }

        serializer = ReviewerDecisionCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("exclusion_reason", serializer.errors)

    def test_notes_max_length_validation(self):
        """Test that notes exceeding max length is rejected."""
        data = {
            "decision": "INCLUDE",
            "notes": "x" * 1001,  # Max is 1000
        }

        serializer = ReviewerDecisionCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("notes", serializer.errors)

    def test_exclusion_reason_max_length_validation(self):
        """Test that exclusion_reason exceeding max length is rejected."""
        data = {
            "decision": "EXCLUDE",
            "exclusion_reason": "x" * 101,  # Max is 100
        }

        serializer = ReviewerDecisionCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("exclusion_reason", serializer.errors)

    def test_optional_notes_field(self):
        """Test that notes field is optional."""
        data = {
            "decision": "INCLUDE",
        }

        serializer = ReviewerDecisionCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid())


class ConflictResolutionDetailSerializerTests(TestCase):
    """Test ConflictResolutionDetailSerializer (extended in Phase 2)."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all tests."""
        cls.org = Organisation.objects.create(
            name="Test Organisation",
            slug="test-org",
        )
        cls.user1 = create_test_user(username_prefix="reviewer1")
        cls.user2 = create_test_user(username_prefix="reviewer2")
        cls.session = SearchSession.objects.create(
            title="Test Session",
            organisation=cls.org,
            owner=cls.user1,
            status="draft",
        )
        cls.result = ProcessedResult.objects.create(
            session=cls.session,
            title="Test Result",
            snippet="Test snippet",
            url="https://example.com",
        )

    def test_discussion_summary_with_comments(self):
        """Test discussion_summary field with comments."""
        conflict = ConflictResolution.objects.create(
            result=self.result,
            conflict_type="INCLUDE_EXCLUDE",
            status="PENDING",
            organisation=self.org,
        )

        # Create some comments
        ConflictComment.objects.create(
            conflict=conflict,
            author=self.user1,
            content="Comment 1",
        )
        ConflictComment.objects.create(
            conflict=conflict,
            author=self.user2,
            content="Comment 2",
        )
        ConflictComment.objects.create(
            conflict=conflict,
            author=self.user1,
            content="Comment 3",
        )

        serializer = ConflictResolutionDetailSerializer(conflict)
        data = serializer.data

        # Verify discussion summary
        summary = data["discussion_summary"]
        self.assertEqual(summary["comment_count"], 3)
        self.assertEqual(summary["participant_count"], 2)
        self.assertEqual(summary["revote_count"], 0)
        self.assertIsNotNone(summary["last_activity"])

    def test_discussion_summary_without_comments(self):
        """Test discussion_summary field without comments."""
        conflict = ConflictResolution.objects.create(
            result=self.result,
            conflict_type="INCLUDE_EXCLUDE",
            status="PENDING",
            organisation=self.org,
        )

        serializer = ConflictResolutionDetailSerializer(conflict)
        data = serializer.data

        # Verify empty summary
        summary = data["discussion_summary"]
        self.assertEqual(summary["comment_count"], 0)
        self.assertEqual(summary["participant_count"], 0)
        self.assertEqual(summary["revote_count"], 0)
        self.assertIsNone(summary["last_activity"])

    def test_active_revote_proposal(self):
        """Test active_revote_proposal field with active proposal."""
        conflict = ConflictResolution.objects.create(
            result=self.result,
            conflict_type="INCLUDE_EXCLUDE",
            status="PENDING",
            organisation=self.org,
        )

        # Create active proposal
        proposal = RevoteProposal.objects.create(
            conflict=conflict,
            proposed_by=self.user1,
            rationale="Re-vote needed",
            expires_at=timezone.now() + timedelta(hours=48),
        )

        serializer = ConflictResolutionDetailSerializer(conflict)
        data = serializer.data

        # Verify active proposal is included
        self.assertIsNotNone(data["active_revote_proposal"])
        self.assertEqual(data["active_revote_proposal"]["id"], str(proposal.id))
        self.assertEqual(data["active_revote_proposal"]["status"], "PROPOSED")

    def test_no_active_revote_proposal(self):
        """Test active_revote_proposal field without active proposal."""
        conflict = ConflictResolution.objects.create(
            result=self.result,
            conflict_type="INCLUDE_EXCLUDE",
            status="PENDING",
            organisation=self.org,
        )

        serializer = ConflictResolutionDetailSerializer(conflict)
        data = serializer.data

        # Verify no active proposal
        self.assertIsNone(data["active_revote_proposal"])

    def test_completed_proposal_not_active(self):
        """Test that completed proposals are not shown as active."""
        conflict = ConflictResolution.objects.create(
            result=self.result,
            conflict_type="INCLUDE_EXCLUDE",
            status="PENDING",
            organisation=self.org,
        )

        # Create completed proposal (should not be active)
        RevoteProposal.objects.create(
            conflict=conflict,
            proposed_by=self.user1,
            rationale="Re-vote completed",
            status="COMPLETED",
            completed_at=timezone.now(),
            expires_at=timezone.now() + timedelta(hours=48),
        )

        serializer = ConflictResolutionDetailSerializer(conflict)
        data = serializer.data

        # Completed proposal should not be shown as active
        self.assertIsNone(data["active_revote_proposal"])

    def test_discussion_summary_excludes_deleted_comments(self):
        """Test that discussion summary excludes soft-deleted comments."""
        conflict = ConflictResolution.objects.create(
            result=self.result,
            conflict_type="INCLUDE_EXCLUDE",
            status="PENDING",
            organisation=self.org,
        )

        # Create active and deleted comments
        ConflictComment.objects.create(
            conflict=conflict,
            author=self.user1,
            content="Active comment",
        )
        ConflictComment.objects.create(
            conflict=conflict,
            author=self.user2,
            content="Deleted comment",
            is_deleted=True,
        )

        serializer = ConflictResolutionDetailSerializer(conflict)
        data = serializer.data

        # Should only count active comment
        summary = data["discussion_summary"]
        self.assertEqual(summary["comment_count"], 1)
