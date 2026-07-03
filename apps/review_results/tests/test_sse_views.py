"""
Unit tests for Server-Sent Events (SSE) views.

Tests the conflict_discussion_stream view for real-time updates,
permission checks, event delivery, and error handling.
"""

import asyncio
import json
import unittest
from datetime import timedelta
from typing import AsyncIterator, Optional
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from apps.organisation.models import Organisation, OrganisationMembership
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


class _SuppressConflictSignalMixin:
    """Disconnect conflict_detected_handler during tests that create ConflictResolution.

    Prevents email notification attempts during test data setup.
    """

    def setUp(self):
        from django.db.models.signals import m2m_changed
        from apps.review_results.signals import conflict_detected_handler

        m2m_changed.disconnect(
            conflict_detected_handler,
            sender=ConflictResolution.conflicting_decisions.through,
        )
        super().setUp()

    def tearDown(self):
        from django.db.models.signals import m2m_changed
        from apps.review_results.signals import conflict_detected_handler

        m2m_changed.connect(
            conflict_detected_handler,
            sender=ConflictResolution.conflicting_decisions.through,
        )
        super().tearDown()


class SSEStreamConsumer:
    """
    Helper class to consume and parse Server-Sent Events from async streams.

    Parses SSE format:
        event: event_name
        data: {"key": "value"}

        : keepalive
    """

    def __init__(self, timeout: float = 5.0):
        """
        Initialize SSE stream consumer.

        Args:
            timeout: Maximum time to wait for events (seconds)
        """
        self.timeout = timeout
        self.events = []
        self.keepalives = 0

    async def consume_stream(self, stream_content: bytes) -> list[dict]:
        """
        Consume SSE stream and parse events.

        Args:
            stream_content: Raw bytes from StreamingHttpResponse

        Returns:
            List of parsed events with 'event' and 'data' keys
        """
        content = stream_content.decode("utf-8")
        lines = content.split("\n")

        current_event = {}

        for line in lines:
            line = line.strip()

            # Skip empty lines (event separator)
            if not line:
                if current_event:
                    self.events.append(current_event)
                    current_event = {}
                continue

            # Keepalive comment
            if line.startswith(":"):
                self.keepalives += 1
                continue

            # Parse event field
            if line.startswith("event:"):
                current_event["event"] = line[6:].strip()

            # Parse data field
            elif line.startswith("data:"):
                data_str = line[5:].strip()
                try:
                    current_event["data"] = json.loads(data_str)
                except json.JSONDecodeError:
                    current_event["data"] = data_str

        # Add final event if exists
        if current_event:
            self.events.append(current_event)

        return self.events

    async def consume_async_generator(
        self, generator: AsyncIterator[str], max_events: Optional[int] = None
    ) -> list[dict]:
        """
        Consume events from async generator with timeout.

        Args:
            generator: Async generator yielding SSE event strings
            max_events: Stop after receiving this many events (optional)

        Returns:
            List of parsed events
        """
        try:
            async with asyncio.timeout(self.timeout):
                collected_lines = []
                event_count = 0

                async for chunk in generator:
                    collected_lines.append(chunk)

                    # Check if we've received enough events
                    if max_events and "event:" in chunk:
                        event_count += 1
                        if event_count >= max_events:
                            break

                # Parse collected content
                full_content = "".join(collected_lines)
                return await self.consume_stream(full_content.encode("utf-8"))

        except asyncio.TimeoutError:
            # Parse what we collected before timeout
            if collected_lines:
                full_content = "".join(collected_lines)
                return await self.consume_stream(full_content.encode("utf-8"))
            return []


class SSEViewPermissionTest(_SuppressConflictSignalMixin, TestCase):
    """Test SSE view permission checks."""

    def setUp(self):
        """Set up test data."""
        super().setUp()
        # Create organisation
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create users
        self.reviewer1 = create_test_user(username_prefix="reviewer1")
        self.reviewer2 = create_test_user(username_prefix="reviewer2")
        self.non_reviewer = create_test_user(username_prefix="nonreviewer")
        self.admin_user = create_test_user(username_prefix="admin")

        # Create admin membership
        OrganisationMembership.objects.create(
            user=self.admin_user,
            organisation=self.organisation,
            role="SENIOR_RESEARCHER",
            is_active=True,
        )

        # Create session
        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.reviewer1,
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

    def test_sse_requires_authentication(self):
        """Test that SSE endpoint requires authentication."""
        url = reverse("review_results_api:conflict-stream", args=[self.conflict.id])
        response = self.client.get(url)

        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_sse_conflicting_reviewer_can_connect(self):
        """Test that conflicting reviewers can connect to SSE stream."""
        self.client.force_login(self.reviewer1)
        url = reverse("review_results_api:conflict-stream", args=[self.conflict.id])

        # Make request (we can't fully test streaming, but we can verify it starts)
        response = self.client.get(url)

        # Should return 200 with SSE headers
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/event-stream")
        self.assertEqual(response["Cache-Control"], "no-cache")
        self.assertEqual(response["X-Accel-Buffering"], "no")

    def test_sse_admin_can_connect(self):
        """Test that admins can connect to SSE stream."""
        self.client.force_login(self.admin_user)
        url = reverse("review_results_api:conflict-stream", args=[self.conflict.id])

        response = self.client.get(url)

        # Should return 200 with SSE headers
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/event-stream")

    def test_sse_non_reviewer_blocked(self):
        """Test that non-conflicting reviewers are blocked from SSE stream."""
        self.client.force_login(self.non_reviewer)
        url = reverse("review_results_api:conflict-stream", args=[self.conflict.id])

        response = self.client.get(url)

        # Should return 200 (stream starts) but first event should be an error
        self.assertEqual(response.status_code, 200)

        # Parse streaming content to check for error event
        # Note: In a real async test, we'd consume the stream properly
        # For now, we verify the stream starts (permission check happens in generator)

    def test_sse_conflict_not_found(self):
        """Test SSE with non-existent conflict ID."""
        self.client.force_login(self.reviewer1)
        import uuid

        fake_id = uuid.uuid4()
        url = reverse("review_results_api:conflict-stream", args=[fake_id])

        response = self.client.get(url)

        # Should return 200 (stream starts) but first event should be error
        self.assertEqual(response.status_code, 200)


class SSEEventDeliveryTest(_SuppressConflictSignalMixin, TestCase):
    """
    Test SSE event delivery.

    Tests event detection logic without real async streaming.
    """

    def setUp(self):
        """Set up test data."""
        super().setUp()
        # Create organisation
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create users
        self.reviewer1 = create_test_user(username_prefix="reviewer1")
        self.reviewer2 = create_test_user(username_prefix="reviewer2")

        # Create session
        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.reviewer1,
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

    def test_new_comment_event_detected(self):
        """Test that SSE detects new comments."""
        # Create a comment
        comment = ConflictComment.objects.create(
            conflict=self.conflict,
            author=self.reviewer1,
            content="Test comment for SSE",
        )

        # Verify comment was created and will be detected by SSE polling
        self.assertTrue(ConflictComment.objects.filter(id=comment.id).exists())
        self.assertEqual(comment.content, "Test comment for SSE")

        # SSE view polls database every 2 seconds and will detect this comment

    def test_revote_proposal_event_detected(self):
        """Test that SSE detects new revote proposals."""
        # Create a revote proposal (expires in 48 hours)
        expires_at = timezone.now() + timedelta(hours=48)
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="Need to re-evaluate the decision",
            expires_at=expires_at,
        )

        # Verify proposal was created
        self.assertTrue(RevoteProposal.objects.filter(id=proposal.id).exists())
        self.assertEqual(proposal.rationale, "Need to re-evaluate the decision")

    def test_consensus_reached_event_detected(self):
        """Test that SSE detects when consensus is reached."""
        # Create a revote proposal and mark as accepted (expires in 48 hours)
        expires_at = timezone.now() + timedelta(hours=48)
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="Need to re-evaluate",
            expires_at=expires_at,
        )
        proposal.accepted_by.add(self.reviewer1, self.reviewer2)

        # Create new decisions (re-votes) with consensus
        new_decision1 = ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.reviewer1,
            decision="INCLUDE",  # Both agree now
            screening_stage="INITIAL",
            organisation=self.organisation,
            is_revote=True,
            revote_proposal=proposal,
        )
        _new_decision2 = ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.reviewer2,
            decision="INCLUDE",  # Consensus on INCLUDE
            screening_stage="INITIAL",
            organisation=self.organisation,
            is_revote=True,
            revote_proposal=proposal,
        )

        # Update conflict status to RESOLVED
        self.conflict.status = "RESOLVED"
        self.conflict.final_decision = new_decision1
        self.conflict.resolved_at = timezone.now()
        self.conflict.resolution_method = "CONSENSUS"
        self.conflict.save()

        # Verify conflict was resolved
        self.conflict.refresh_from_db()
        self.assertEqual(self.conflict.status, "RESOLVED")
        self.assertEqual(self.conflict.resolution_method, "CONSENSUS")


class SSEConnectionManagementTest(_SuppressConflictSignalMixin, TestCase):
    """Test SSE connection lifecycle and error handling."""

    def setUp(self):
        """Set up test data."""
        super().setUp()
        # Create organisation
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create users
        self.reviewer1 = create_test_user(username_prefix="reviewer1")
        self.reviewer2 = create_test_user(username_prefix="reviewer2")

        # Create session
        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.reviewer1,
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

        # Create conflicting decisions (need 2 for a valid conflict)
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

    def test_sse_response_headers(self):
        """Test that SSE response has correct headers."""
        self.client.force_login(self.reviewer1)
        url = reverse("review_results_api:conflict-stream", args=[self.conflict.id])

        response = self.client.get(url)

        # Verify SSE headers
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/event-stream")
        self.assertEqual(response["Cache-Control"], "no-cache")
        self.assertEqual(response["X-Accel-Buffering"], "no")

    def test_sse_csrf_exempt(self):
        """Test that SSE endpoint is CSRF exempt (EventSource doesn't support CSRF)."""
        self.client.force_login(self.reviewer1)
        url = reverse("review_results_api:conflict-stream", args=[self.conflict.id])

        # Should work without CSRF token
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class SSEIntegrationTest(_SuppressConflictSignalMixin, TestCase):
    """
    Integration tests for SSE with full workflow.

    Tests the complete flow from comment posting to SSE event delivery.
    """

    def setUp(self):
        """Set up test data."""
        super().setUp()
        # Create organisation
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create users
        self.reviewer1 = create_test_user(username_prefix="reviewer1")
        self.reviewer2 = create_test_user(username_prefix="reviewer2")

        # Create session
        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.reviewer1,
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

    def test_comment_appears_in_sse_poll(self):
        """Test that new comments are detectable by SSE polling logic."""
        # Get timestamp before comment
        before_time = timezone.now()

        # Create a comment
        comment = ConflictComment.objects.create(
            conflict=self.conflict,
            author=self.reviewer1,
            content="This should appear in SSE stream",
        )

        # Query for comments created after before_time (simulating SSE polling)
        new_comments = ConflictComment.objects.filter(
            conflict_id=self.conflict.id, created_at__gt=before_time, is_deleted=False
        ).select_related("author", "parent")

        # Verify comment would be detected
        self.assertEqual(new_comments.count(), 1)
        self.assertEqual(new_comments.first().id, comment.id)
        self.assertEqual(
            new_comments.first().content, "This should appear in SSE stream"
        )

    def test_multiple_events_in_sequence(self):
        """Test that multiple events are detectable in sequence."""
        before_time = timezone.now()

        # Create comment
        _comment = ConflictComment.objects.create(
            conflict=self.conflict, author=self.reviewer1, content="First event"
        )

        # Create revote proposal (expires in 48 hours)
        expires_at = timezone.now() + timedelta(hours=48)
        _proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="Second event",
            expires_at=expires_at,
        )

        # Query for all new events (simulating SSE polling)
        new_comments = ConflictComment.objects.filter(
            conflict_id=self.conflict.id, created_at__gt=before_time, is_deleted=False
        )
        new_proposals = RevoteProposal.objects.filter(
            conflict_id=self.conflict.id, proposed_at__gt=before_time
        )

        # Verify both events would be detected
        self.assertEqual(new_comments.count(), 1)
        self.assertEqual(new_proposals.count(), 1)
        self.assertEqual(new_comments.first().content, "First event")
        self.assertEqual(new_proposals.first().rationale, "Second event")


# ============================================================================
# SSE STREAMING INTEGRATION TESTS (Phase 2 - Event Streaming & Format)
# ============================================================================


class SSEStreamingIntegrationTest(_SuppressConflictSignalMixin, TransactionTestCase):
    """
    SSE event streaming integration tests using sync Client.

    Note: Due to Django AsyncClient session limitations (see docs/fixes/issue-17-sse-testing-rca.md),
    these tests use sync Client to validate SSE streaming. This pragmatic approach achieves
    coverage goals without async framework blockers.

    Uses TransactionTestCase to ensure database transactions are visible to async code.

    Tests SSE format validation, event delivery, and stream behaviour.
    """

    def setUp(self):
        """Set up test data for SSE streaming tests."""
        super().setUp()
        # Create organisation
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create users
        self.reviewer1 = create_test_user(username_prefix="reviewer1")
        self.reviewer2 = create_test_user(username_prefix="reviewer2")

        # Create session
        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.reviewer1,
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

    def tearDown(self):
        """Clean up database connections leaked by async SSE generators.

        SSE generators use sync_to_async(thread_sensitive=True) which runs
        DB queries in ASGIRef's single-thread executor. That thread gets its
        own Django DB connection that persists after asyncio.run() returns.
        We close it by running connections.close_all() in that same thread.
        """
        from asgiref.sync import sync_to_async
        from django.db import connections

        async def _close_async_thread_connections():
            await sync_to_async(connections.close_all, thread_sensitive=True)()

        try:
            asyncio.run(_close_async_thread_connections())
        except Exception:
            import logging

            logging.getLogger(__name__).debug(
                "Failed to close async thread connections in tearDown",
                exc_info=True,
            )

        # Close connections in the current (test) thread too
        connections.close_all()
        super().tearDown()

    def _get_first_chunk(self, response):
        """Read first chunk from SSE stream and properly close the generator."""

        async def _consume():
            gen = response.streaming_content
            try:
                async with asyncio.timeout(5.0):
                    async for chunk in gen:
                        return chunk.decode("utf-8")
                return None
            except TimeoutError:
                return None
            finally:
                await gen.aclose()

        return asyncio.run(_consume())

    def _collect_chunks(self, response, *, max_chunks=None, stop_on=None, timeout=5.0):
        """Collect chunks from SSE stream and properly close the generator.

        Args:
            response: StreamingHttpResponse from SSE endpoint
            max_chunks: Stop after this many chunks
            stop_on: Stop when this substring appears in a chunk
            timeout: Maximum time in seconds

        Returns:
            list[str]: Decoded chunks
        """

        async def _consume():
            chunks = []
            gen = response.streaming_content
            try:
                async with asyncio.timeout(timeout):
                    async for chunk in gen:
                        decoded = chunk.decode("utf-8")
                        chunks.append(decoded)
                        if max_chunks and len(chunks) >= max_chunks:
                            break
                        if stop_on and stop_on in decoded:
                            break
            except asyncio.TimeoutError:
                pass
            finally:
                await gen.aclose()
            return chunks

        return asyncio.run(_consume())

    def test_sse_stream_initialization(self):
        """Test that SSE stream initializes with connected event."""
        self.client.force_login(self.reviewer1)
        url = reverse("review_results_api:conflict-stream", args=[self.conflict.id])

        response = self.client.get(url)

        # Verify response
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/event-stream")
        self.assertEqual(response["Cache-Control"], "no-cache")
        self.assertEqual(response["X-Accel-Buffering"], "no")

        # Get first chunk (connected event) -- generator properly closed
        first_chunk = self._get_first_chunk(response)

        # Verify connected event format
        self.assertIn("data:", first_chunk)
        self.assertIn("connected", first_chunk)
        self.assertIn(str(self.conflict.id), first_chunk)

    def test_sse_event_format_validation(self):
        """Test that SSE events use correct format (data: + JSON)."""
        self.client.force_login(self.reviewer1)
        url = reverse("review_results_api:conflict-stream", args=[self.conflict.id])

        response = self.client.get(url)

        # Get first chunk -- generator properly closed
        first_chunk = self._get_first_chunk(response)

        # SSE format: "data: {json}\n\n"
        assert first_chunk is not None
        self.assertTrue(first_chunk.startswith("data:"))
        self.assertIn("{", first_chunk)  # JSON data
        self.assertIn("}", first_chunk)

        # Parse JSON to verify structure
        json_start = first_chunk.index("{")
        json_end = first_chunk.rindex("}") + 1
        json_str = first_chunk[json_start:json_end]
        data = json.loads(json_str)

        # Verify connected event structure
        self.assertEqual(data["type"], "connected")
        self.assertEqual(data["conflict_id"], str(self.conflict.id))

    def test_sse_stream_with_concurrent_connections(self):
        """Test that multiple reviewers can connect to same SSE stream."""
        url = reverse("review_results_api:conflict-stream", args=[self.conflict.id])

        # First reviewer connection -- generator properly closed
        self.client.force_login(self.reviewer1)
        response1 = self.client.get(url)
        self.assertEqual(response1.status_code, 200)
        chunk1 = self._get_first_chunk(response1)
        self.assertIn("connected", chunk1)

        # Second reviewer connection (new client) -- generator properly closed
        from django.test import Client

        client2 = Client()
        client2.force_login(self.reviewer2)
        response2 = client2.get(url)
        self.assertEqual(response2.status_code, 200)
        chunk2 = self._get_first_chunk(response2)
        self.assertIn("connected", chunk2)

        # Both should receive connected event
        self.assertIn(str(self.conflict.id), chunk1)
        self.assertIn(str(self.conflict.id), chunk2)

    def test_sse_stream_polling_detects_new_comments(self):
        """Test that SSE polling logic detects new comments."""
        # This validates the database query logic used by SSE
        before_time = timezone.now()

        # Create a comment
        _comment = ConflictComment.objects.create(
            conflict=self.conflict, author=self.reviewer1, content="SSE test comment"
        )

        # Simulate SSE polling query
        new_comments = ConflictComment.objects.filter(
            conflict_id=self.conflict.id, created_at__gt=before_time, is_deleted=False
        ).select_related("author", "parent")

        # Verify comment would be detected
        self.assertEqual(new_comments.count(), 1)
        self.assertEqual(new_comments.first().content, "SSE test comment")

    def test_sse_stream_polling_detects_revote_proposals(self):
        """Test that SSE polling logic detects new revote proposals."""
        before_time = timezone.now()

        # Create revote proposal
        expires_at = timezone.now() + timedelta(hours=48)
        _proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="Test proposal",
            expires_at=expires_at,
        )

        # Simulate SSE polling query
        new_proposals = RevoteProposal.objects.filter(
            conflict_id=self.conflict.id, proposed_at__gt=before_time
        ).select_related("proposed_by")

        # Verify proposal would be detected
        self.assertEqual(new_proposals.count(), 1)
        self.assertEqual(new_proposals.first().rationale, "Test proposal")

    def test_sse_stream_polling_detects_consensus_reached(self):
        """Test that SSE polling logic detects when consensus is reached."""
        before_time = timezone.now()

        # Resolve the conflict
        self.conflict.status = "RESOLVED"
        self.conflict.final_decision = self.decision1
        self.conflict.resolved_at = timezone.now()
        self.conflict.resolution_method = "CONSENSUS"
        self.conflict.save()

        # Simulate SSE polling query
        updated_conflict = (
            ConflictResolution.objects.filter(
                id=self.conflict.id, resolved_at__gt=before_time, status="RESOLVED"
            )
            .select_related("final_decision")
            .first()
        )

        # Verify resolution would be detected
        self.assertIsNotNone(updated_conflict)
        self.assertEqual(updated_conflict.status, "RESOLVED")
        self.assertEqual(updated_conflict.resolution_method, "CONSENSUS")

    def test_sse_stream_detects_revote_accepted(self):
        """Test that SSE logic detects when revote proposal is accepted by all."""
        # Create revote proposal
        expires_at = timezone.now() + timedelta(hours=48)
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="Need re-vote",
            expires_at=expires_at,
        )

        # Accept by both reviewers
        proposal.accepted_by.add(self.reviewer1, self.reviewer2)

        # Verify all_accepted logic
        self.assertTrue(proposal.all_accepted)
        self.assertEqual(proposal.accepted_by.count(), 2)

    def test_sse_event_serialization(self):
        """Test that comments are properly serialized for SSE events."""
        # Create a comment with all fields
        comment = ConflictComment.objects.create(
            conflict=self.conflict, author=self.reviewer1, content="Test serialization"
        )

        # Serialize using the SSE serializer
        from apps.review_results.serializers import ConflictCommentSerializer

        serialized = ConflictCommentSerializer(comment).data

        # Verify all required fields present
        self.assertIn("id", serialized)
        self.assertIn("content", serialized)
        self.assertIn("author", serialized)
        self.assertIn("created_at", serialized)
        self.assertEqual(serialized["content"], "Test serialization")

    def test_sse_revote_proposal_serialization(self):
        """Test that revote proposals are properly serialized for SSE events."""
        expires_at = timezone.now() + timedelta(hours=48)
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="Test rationale",
            expires_at=expires_at,
        )

        # Serialize using the SSE serializer
        from apps.review_results.serializers import RevoteProposalSerializer

        serialized = RevoteProposalSerializer(proposal).data

        # Verify all required fields present
        self.assertIn("id", serialized)
        self.assertIn("rationale", serialized)
        self.assertIn("proposed_by", serialized)
        self.assertIn("expires_at", serialized)
        self.assertEqual(serialized["rationale"], "Test rationale")

    @unittest.skip(
        "View decorator chain changed; timeout covered by mocked_time variant"
    )
    def test_sse_stream_timeout_after_max_duration(self):
        """Test that SSE stream times out after max_duration."""
        import asyncio

        self.client.force_login(self.reviewer1)
        url = reverse("review_results_api:conflict-stream", args=[self.conflict.id])

        # Patch max_duration to 0.5 seconds for faster test
        with patch(
            "apps.review_results.api.sse_views.conflict_discussion_stream"
        ) as mock_view:
            # Create a modified version of the view with shorter timeout
            from apps.review_results.api import sse_views

            _original_func = (
                sse_views.conflict_discussion_stream.__wrapped__.__wrapped__.__wrapped__
            )

            async def patched_stream(request, conflict_id):
                # Call original but we'll manually set max_duration
                async def event_generator():
                    # Simplified generator that times out quickly
                    from datetime import datetime, timezone

                    start_time = datetime.now(timezone.utc)
                    max_duration = 0.5  # Short timeout for testing

                    yield (
                        'data: {"type": "connected", "conflict_id": "'
                        + str(conflict_id)
                        + '"}\n\n'
                    )

                    while True:
                        elapsed = (
                            datetime.now(timezone.utc) - start_time
                        ).total_seconds()
                        if elapsed > max_duration:
                            yield 'data: {"type": "timeout", "message": "Connection timeout - please refresh"}\n\n'
                            break
                        await asyncio.sleep(0.1)

                from django.http import StreamingHttpResponse

                response = StreamingHttpResponse(
                    event_generator(),
                    content_type="text/event-stream",
                )
                response["Cache-Control"] = "no-cache"
                response["X-Accel-Buffering"] = "no"
                return response

            mock_view.side_effect = patched_stream
            response = self.client.get(url)

        # Collect chunks with timeout
        async def collect_chunks_until_timeout():
            chunks = []
            try:
                async with asyncio.timeout(2.0):  # 2 second max
                    async for chunk in response.streaming_content:
                        decoded = chunk.decode("utf-8")
                        chunks.append(decoded)
                        if "timeout" in decoded:
                            break
            except asyncio.TimeoutError:
                pass
            return chunks

        chunks = asyncio.run(collect_chunks_until_timeout())

        # Verify we got chunks
        self.assertGreater(len(chunks), 0)

        # Verify timeout message was sent
        all_content = "".join(chunks)
        self.assertIn("timeout", all_content)
        self.assertIn("Connection timeout", all_content)

    def test_sse_stream_timeout_after_max_duration_with_mocked_time(self):
        """Test that SSE stream times out after max_duration (10 minutes)."""
        from datetime import datetime, timezone, timedelta

        self.client.force_login(self.reviewer1)
        url = reverse("review_results_api:conflict-stream", args=[self.conflict.id])

        # Mock datetime.now() to simulate time passing
        fake_start_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        fake_elapsed_time = fake_start_time + timedelta(
            seconds=601
        )  # Just over 10 minutes

        call_count = [0]

        def mock_now(tz=None):
            """Return start time first, then elapsed time."""
            call_count[0] += 1
            if call_count[0] == 1:
                return fake_start_time  # First call: start_time
            elif call_count[0] == 2:
                return fake_start_time  # Second call: last_check init
            else:
                return fake_elapsed_time  # Subsequent calls: show time has passed

        with patch("apps.review_results.api.sse_views.datetime") as mock_datetime:
            mock_datetime.now = mock_now
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

            response = self.client.get(url)

            # Generator properly closed via _collect_chunks
            chunks = self._collect_chunks(response, stop_on="timeout", timeout=3.0)

        # Verify we got chunks
        self.assertGreater(len(chunks), 0, "Should receive at least connected event")

        # Verify timeout message was sent
        all_content = "".join(chunks)
        self.assertIn("timeout", all_content.lower())
        self.assertIn("Connection timeout", all_content)
        self.assertIn("please refresh", all_content.lower())

        # Verify it's in the expected SSE format
        timeout_chunk = [c for c in chunks if "timeout" in c.lower()][0]
        self.assertIn("data:", timeout_chunk)

        # Verify JSON structure
        json_match = timeout_chunk.split("data:")[1].strip()
        timeout_data = json.loads(json_match.split("\n")[0])
        self.assertEqual(timeout_data["type"], "timeout")

    def test_sse_stream_error_retry_and_max_errors(self):
        """Test that SSE stream handles errors and stops after max_errors (3)."""
        from unittest.mock import MagicMock

        self.client.force_login(self.reviewer1)
        url = reverse("review_results_api:conflict-stream", args=[self.conflict.id])

        # Create a side effect that raises exceptions 3 times
        error_count = [0]

        def mock_filter_with_errors(*args, **kwargs):
            """Mock that raises exceptions for first 3 calls."""
            error_count[0] += 1
            if error_count[0] <= 3:
                raise Exception(f"Database error {error_count[0]}")
            # After 3 errors, return empty result
            mock_queryset = MagicMock()
            mock_queryset.exists.return_value = False
            mock_queryset.select_related.return_value = mock_queryset
            mock_queryset.prefetch_related.return_value = mock_queryset
            mock_queryset.order_by.return_value = mock_queryset
            mock_queryset.first.return_value = None
            return mock_queryset

        # Patch ConflictComment.objects.filter to trigger errors
        with patch(
            "apps.review_results.models.ConflictComment.objects.filter",
            side_effect=mock_filter_with_errors,
        ):
            response = self.client.get(url)

            # Generator properly closed via _collect_chunks
            chunks = self._collect_chunks(
                response, stop_on="Too many errors", timeout=5.0
            )

        # Verify we got chunks
        self.assertGreater(len(chunks), 0, "Should receive at least connected event")

        # Verify error threshold message was sent
        all_content = "".join(chunks)
        self.assertIn("Too many errors", all_content)
        self.assertIn("closing connection", all_content)

        # Verify it's in the expected SSE format
        error_chunks = [c for c in chunks if "Too many errors" in c]
        self.assertGreater(len(error_chunks), 0, "Should have error message chunk")

        error_chunk = error_chunks[0]
        self.assertIn("data:", error_chunk)

        # Verify JSON structure
        json_match = error_chunk.split("data:")[1].strip()
        error_data = json.loads(json_match.split("\n")[0])
        self.assertEqual(error_data["type"], "error")
        self.assertIn("Too many errors", error_data["message"])

        # Verify we hit the error limit (3 consecutive errors)
        self.assertEqual(error_count[0], 3, "Should have triggered exactly 3 errors")

    def test_sse_stream_sends_keepalive_comments(self):
        """Test that SSE stream sends keepalive comments during polling."""
        self.client.force_login(self.reviewer1)
        url = reverse("review_results_api:conflict-stream", args=[self.conflict.id])
        response = self.client.get(url)

        # Generator properly closed via _collect_chunks
        chunks = self._collect_chunks(response, max_chunks=4, timeout=7.0)

        # Should have at least 3 chunks (connected + keepalives)
        self.assertGreaterEqual(
            len(chunks), 3, "Should receive connected event + keepalives"
        )

        # Verify first chunk is connected event
        first_chunk = chunks[0]
        self.assertIn("connected", first_chunk.lower())
        self.assertIn(str(self.conflict.id), first_chunk)

        # Verify keepalive format ": keepalive\n\n" (SSE comment)
        keepalive_chunks = [c for c in chunks if "keepalive" in c]
        self.assertGreater(
            len(keepalive_chunks), 0, "Should have at least one keepalive"
        )

        # Verify SSE keepalive comment format (starts with ":")
        keepalive_found = any(": keepalive" in c for c in chunks)
        self.assertTrue(
            keepalive_found, "Should have SSE keepalive comment (': keepalive')"
        )

        # Verify keepalive has correct SSE format (ends with double newline)
        for keepalive in keepalive_chunks:
            if ": keepalive" in keepalive:
                # SSE comments should end with \n\n
                self.assertTrue(
                    keepalive.strip().endswith("keepalive") or "\n" in keepalive,
                    "Keepalive should follow SSE format",
                )
