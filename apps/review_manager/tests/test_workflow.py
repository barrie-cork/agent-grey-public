"""
Tests for the 9-state workflow implementation as defined in the PRD.
Validates all status transitions and business rules.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.review_manager.models import SearchSession, SessionActivity
from apps.core.tests.utils import create_test_user

User = get_user_model()


class WorkflowTransitionTests(TestCase):
    """Test the 9-state workflow transitions"""

    def setUp(self):
        self.user = create_test_user(username_prefix="researcher")

    def test_complete_workflow_happy_path(self):
        """Test complete workflow from draft to archived"""
        session = SearchSession.objects.create(
            title="Complete Workflow Test", owner=self.user, status="draft"
        )

        # Define the happy path through all states
        workflow_path = [
            ("draft", "defining_search"),
            ("defining_search", "ready_to_execute"),
            ("ready_to_execute", "executing"),
            ("executing", "processing_results"),
            ("processing_results", "ready_for_review"),
            ("ready_for_review", "under_review"),
            ("under_review", "completed"),
            ("completed", "archived"),
        ]

        for current_status, next_status in workflow_path:
            # Verify current status
            self.assertEqual(session.status, current_status)

            # Verify transition is allowed
            self.assertTrue(
                session.can_transition_to(next_status),
                f"Should be able to transition from {current_status} to {next_status}",
            )

            # Make the transition
            session.status = next_status
            session.save()

            # Log activity
            SessionActivity.log_activity(
                session=session,
                activity_type="status_changed",
                description=f"Status changed from {current_status} to {next_status}",
                user=self.user,
                metadata={"old_status": current_status, "new_status": next_status},
            )

        # Verify we reached the end
        self.assertEqual(session.status, "archived")

        # Verify activity log
        activities = SessionActivity.objects.filter(session=session)
        self.assertEqual(activities.count(), len(workflow_path))

    def test_allowed_transitions_from_each_state(self):
        """Test all allowed transitions as defined in PRD"""
        allowed_transitions = {
            "draft": ["defining_search", "archived"],
            "defining_search": ["ready_to_execute", "draft", "archived"],
            "ready_to_execute": ["executing", "defining_search", "archived"],
            "executing": [
                "processing_results",
                "ready_to_execute",
                "defining_search",
                "archived",
            ],
            "processing_results": [
                "ready_for_review",
                "executing",
                "defining_search",
                "completed",
                "archived",
            ],
            "ready_for_review": [
                "under_review",
                "processing_results",
                "defining_search",
                "archived",
            ],
            "under_review": [
                "completed",
                "ready_for_review",
                "defining_search",
                "archived",
            ],
            "completed": ["archived", "under_review"],
            "archived": ["draft"],
        }

        for from_status, allowed_to_statuses in allowed_transitions.items():
            session = SearchSession.objects.create(
                title=f"Test from {from_status}", owner=self.user, status=from_status
            )

            # Test allowed transitions
            for to_status in allowed_to_statuses:
                self.assertTrue(
                    session.can_transition_to(to_status),
                    f"Should allow {from_status} -> {to_status}",
                )

            # Test some disallowed transitions
            all_statuses = set(dict(SearchSession.STATUS_CHOICES).keys())
            disallowed = all_statuses - set(allowed_to_statuses) - {from_status}

            for to_status in list(disallowed)[:3]:  # Test a few disallowed
                self.assertFalse(
                    session.can_transition_to(to_status),
                    f"Should NOT allow {from_status} -> {to_status}",
                )

    def test_backward_transitions(self):
        """Test that certain backward transitions are allowed"""
        session = SearchSession.objects.create(
            title="Backward Transition Test", owner=self.user, status="under_review"
        )

        # Should be able to go back to ready_for_review
        self.assertTrue(session.can_transition_to("ready_for_review"))
        session.status = "ready_for_review"
        session.save()

        # Should be able to go back to processing_results
        self.assertTrue(session.can_transition_to("processing_results"))
        session.status = "processing_results"
        session.save()

        # Should be able to go back to executing
        self.assertTrue(session.can_transition_to("executing"))

    def test_archive_from_any_state(self):
        """Test that sessions can be archived from most states"""
        archivable_states = [
            "draft",
            "defining_search",
            "ready_to_execute",
            "executing",
            "processing_results",
            "ready_for_review",
            "under_review",
            "completed",
        ]

        for status in archivable_states:
            session = SearchSession.objects.create(
                title=f"Archive from {status}", owner=self.user, status=status
            )

            self.assertTrue(
                session.can_transition_to("archived"),
                f"Should be able to archive from {status}",
            )

    def test_unarchive_to_draft_only(self):
        """Test that archived sessions can only go back to draft"""
        session = SearchSession.objects.create(
            title="Unarchive Test", owner=self.user, status="archived"
        )

        # Can only go to draft
        self.assertTrue(session.can_transition_to("draft"))

        # Cannot go to other states
        other_states = [
            "defining_search",
            "ready_to_execute",
            "executing",
            "processing_results",
            "ready_for_review",
            "under_review",
            "completed",
        ]

        for status in other_states:
            self.assertFalse(
                session.can_transition_to(status),
                f"Should NOT be able to go from archived to {status}",
            )

    def test_validation_on_invalid_transition(self):
        """Test that can_transition_to prevents invalid transitions"""
        session = SearchSession.objects.create(
            title="Invalid Transition Test", owner=self.user, status="draft"
        )

        # Draft -> completed should not be allowed
        self.assertFalse(
            session.can_transition_to("completed"),
            "Should NOT allow draft -> completed",
        )

        # Draft -> executing should not be allowed (must go through defining_search first)
        self.assertFalse(
            session.can_transition_to("executing"),
            "Should NOT allow draft -> executing",
        )

    def test_automatic_timestamp_updates(self):
        """Test that timestamps are set automatically on status changes"""
        session = SearchSession.objects.create(
            title="Timestamp Test", owner=self.user, status="ready_to_execute"
        )

        # Transition to executing should set started_at
        self.assertIsNone(session.started_at)
        session.status = "executing"
        session.save()
        self.assertIsNotNone(session.started_at)

        # Continue through workflow
        session.status = "processing_results"
        session.save()
        session.status = "ready_for_review"
        session.save()
        session.status = "under_review"
        session.save()

        # Transition to completed should set completed_at
        self.assertIsNone(session.completed_at)
        session.status = "completed"
        session.save()
        self.assertIsNotNone(session.completed_at)


class StatusPropertyTests(TestCase):
    """Test status-related properties and business logic"""

    def setUp(self):
        self.user = create_test_user(username_prefix="researcher")

    def test_is_active_property(self):
        """Test is_active property for different statuses"""
        # Active statuses
        active_statuses = [
            "draft",
            "defining_search",
            "ready_to_execute",
            "executing",
            "processing_results",
            "ready_for_review",
            "under_review",
        ]

        for status in active_statuses:
            session = SearchSession.objects.create(
                title=f"Active {status}", owner=self.user, status=status
            )
            self.assertTrue(session.is_active, f"{status} should be active")

        # Inactive statuses
        inactive_statuses = ["completed", "archived"]

        for status in inactive_statuses:
            session = SearchSession.objects.create(
                title=f"Inactive {status}", owner=self.user, status=status
            )
            self.assertFalse(session.is_active, f"{status} should be inactive")

    def test_can_edit_property(self):
        """Test can_edit property for different statuses"""
        # Editable statuses
        editable_statuses = ["draft", "defining_search"]

        for status in editable_statuses:
            session = SearchSession.objects.create(
                title=f"Editable {status}", owner=self.user, status=status
            )
            self.assertTrue(session.can_edit, f"{status} should be editable")

        # Non-editable statuses
        non_editable_statuses = [
            "ready_to_execute",
            "executing",
            "processing_results",
            "ready_for_review",
            "under_review",
            "completed",
            "archived",
        ]

        for status in non_editable_statuses:
            session = SearchSession.objects.create(
                title=f"Non-editable {status}", owner=self.user, status=status
            )
            self.assertFalse(session.can_edit, f"{status} should not be editable")

    def test_can_delete_property(self):
        """Test can_delete property - only draft can be deleted"""
        # Only draft can be deleted
        draft_session = SearchSession.objects.create(
            title="Draft for deletion", owner=self.user, status="draft"
        )
        self.assertTrue(draft_session.can_delete)

        # All other statuses cannot be deleted
        other_statuses = [
            "defining_search",
            "ready_to_execute",
            "executing",
            "processing_results",
            "ready_for_review",
            "under_review",
            "completed",
            "archived",
        ]

        for status in other_statuses:
            session = SearchSession.objects.create(
                title=f"No delete {status}", owner=self.user, status=status
            )
            self.assertFalse(session.can_delete, f"{status} should not be deletable")


class ActivityLoggingTests(TestCase):
    """Test activity logging functionality"""

    def setUp(self):
        self.user = create_test_user(username_prefix="researcher")
        self.session = SearchSession.objects.create(
            title="Activity Test Session", owner=self.user, status="draft"
        )

    def test_log_activity_method(self):
        """Test the log_activity convenience method"""
        activity = SessionActivity.log_activity(
            session=self.session,
            activity_type="created",
            description="Test activity",
            user=self.user,
            metadata={"key": "value"},
        )

        self.assertEqual(activity.session, self.session)
        self.assertEqual(activity.activity_type, "created")
        self.assertEqual(activity.description, "Test activity")
        self.assertEqual(activity.user, self.user)
        self.assertEqual(activity.metadata["key"], "value")

    def test_activity_types(self):
        """Test all activity types can be logged"""
        activity_types = [
            "created",
            "status_changed",
            "search_defined",
            "search_executed",
            "results_processed",
            "review_started",
            "review_completed",
            "exported",
            "shared",
            "note_added",
            "settings_changed",
        ]

        for activity_type in activity_types:
            activity = SessionActivity.log_activity(
                session=self.session,
                activity_type=activity_type,
                description=f"Testing {activity_type}",
                user=self.user,
            )
            self.assertEqual(activity.activity_type, activity_type)

    def test_activity_ordering(self):
        """Test activities are ordered by creation time (newest first)"""
        # Create activities with slight delays
        activities = []
        for i in range(3):
            activity = SessionActivity.log_activity(
                session=self.session,
                activity_type="note_added",
                description=f"Activity {i}",
                user=self.user,
            )
            activities.append(activity)

        # Get activities from database
        db_activities = list(self.session.activities.all())

        # Should be in reverse order (newest first)
        self.assertEqual(db_activities[0].description, "Activity 2")
        self.assertEqual(db_activities[1].description, "Activity 1")
        self.assertEqual(db_activities[2].description, "Activity 0")

    def test_activity_with_null_user(self):
        """Test that activities can handle null user (system actions)"""
        activity = SessionActivity.log_activity(
            session=self.session,
            activity_type="status_changed",
            description="Automatic status change",
            user=None,
            metadata={"triggered_by": "system"},
        )

        self.assertIsNone(activity.user)
        self.assertEqual(activity.metadata["triggered_by"], "system")
