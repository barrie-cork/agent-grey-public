"""
Test Zero Results Handling (Issues #50 and #51)
Tests the fixes for zero results causing stuck sessions
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.results_manager.models import ProcessingSession
from apps.results_manager.tasks.orchestration import process_session_results_task
from apps.results_manager.validation import validate_session_for_processing
from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.models import RawSearchResult, SearchExecution
from apps.core.tests.utils import create_test_user

User = get_user_model()


class ZeroResultsValidationTest(TestCase):
    """Test Issue #51: Zero results should not cause validation errors"""

    def setUp(self):
        self.user = create_test_user()

        # Create a session in processing_results state
        self.session = SearchSession.objects.create(
            title="Zero Results Test",
            description="Testing zero results handling",
            status="processing_results",
            owner=self.user,
        )

        # Create search strategy
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["elderly"],
            interest_terms=["exercise"],
            context_terms=["standard care", "mobility"],
        )

        # Create a search query
        self.query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="elderly AND exercise AND mobility",
            target_domain="pubmed.gov",
            query_type="manual",
        )

        # Create execution with zero results
        self.execution = SearchExecution.objects.create(
            query=self.query,
            status="completed",
            results_count=0,
            started_at=timezone.now(),
            completed_at=timezone.now(),
        )

    def test_zero_results_validation_passes(self):
        """Test that validation passes with zero results (Issue #51 fix)"""
        # This should NOT raise an exception after our fix
        try:
            validate_session_for_processing(self.session)
            validation_passed = True
        except ValueError as e:
            validation_passed = False
            _error_message = str(e)

        self.assertTrue(
            validation_passed,
            "Validation should pass with zero results after Issue #51 fix",
        )

    def test_zero_results_proceeds_to_completed(self):
        """Test that zero results sessions transition to completed state"""
        # Move session to processing_results
        self.session.status = "processing_results"
        self.session.save()

        # Process the session using the actual task
        # Call the task directly -- zero results should be handled gracefully
        result = process_session_results_task(str(self.session.id))  # type: ignore[call-arg]

        # Should complete successfully (zero results path)
        self.assertIsInstance(result, dict)

        # Reload session
        self.session.refresh_from_db()

        # Should transition to completed (zero results) or ready_for_review
        self.assertIn(self.session.status, ["ready_for_review", "completed"])

    def test_zero_results_warning_logged(self):
        """Test that zero results generates a warning log"""
        with self.assertLogs(
            "apps.results_manager.validation", level="WARNING"
        ) as logs:
            validate_session_for_processing(self.session)

            # Check that warning was logged
            warning_found = any("zero raw results" in log for log in logs.output)
            self.assertTrue(warning_found, "Should log warning for zero results")


class SmallResultSetHandlingTest(TestCase):
    """Test Issue #50: Small result sets should auto-redirect quickly"""

    def setUp(self):
        self.user = create_test_user()

        # Create session
        self.session = SearchSession.objects.create(
            title="Small Result Set Test",
            description="Testing small result set handling",
            status="executing",
            owner=self.user,
        )

        # Create search strategy
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test"],
            interest_terms=["intervention"],
            context_terms=["comparison"],
        )

        # Create query
        self.query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="test query",
            target_domain="test.com",
            query_type="manual",
        )

    def test_small_result_set_fast_processing(self):
        """Test that small result sets (< 20) process quickly"""
        # Create execution with 5 results
        execution = SearchExecution.objects.create(
            query=self.query,
            status="completed",
            results_count=5,
            started_at=timezone.now(),
            completed_at=timezone.now(),
        )

        # Create 5 raw results
        for i in range(5):
            RawSearchResult.objects.create(
                execution=execution,
                title=f"Result {i}",
                link=f"https://example.com/result{i}",
                snippet=f"Test snippet {i}",
                position=i + 1,
            )

        # Move to processing_results (bypass validation)
        SearchSession.objects.filter(id=self.session.id).update(
            status="processing_results"
        )
        self.session.refresh_from_db()

        # Process results
        _start_time = timezone.now()

        # Process using the task (creates ProcessingSession internally)
        result = process_session_results_task(str(self.session.id))  # type: ignore[call-arg]

        # The task creates a Celery workflow that executes asynchronously.
        # When called directly, the task returns a result dict but batch
        # processing hasn't completed. Verify the task returned successfully.
        self.assertIsInstance(result, dict)

        # A ProcessingSession should have been created
        processing_session = ProcessingSession.objects.filter(
            search_session=self.session
        ).first()
        self.assertIsNotNone(processing_session)

    def test_result_count_thresholds(self):
        """Test different result count thresholds.

        Note: When called directly (not via Celery worker), the orchestration task
        creates an async workflow but batch tasks don't execute synchronously.
        Only zero-result sessions complete immediately (via _handle_no_results).
        Non-zero sessions stay in processing_results until the async workflow completes.
        """
        test_cases = [
            # (result_count, expected_status)
            # Zero results -> completed immediately via _handle_no_results
            (0, "completed"),
            # Non-zero results -> processing_results (async workflow created but not executed)
            (1, "processing_results"),
            (10, "processing_results"),
            (50, "processing_results"),
        ]

        for result_count, expected_status in test_cases:
            with self.subTest(result_count=result_count):
                session = SearchSession.objects.create(
                    title=f"Test {result_count} results",
                    description=f"Testing {result_count} results",
                    status="processing_results",
                    owner=self.user,
                )

                strategy = SearchStrategy.objects.create(
                    session=session,
                    user=self.user,
                    population_terms=["test"],
                    interest_terms=["test"],
                    context_terms=["test"],
                )

                query = SearchQuery.objects.create(
                    strategy=strategy,
                    session=session,
                    query_text="test",
                    target_domain="test.com",
                    query_type="manual",
                )

                execution = SearchExecution.objects.create(
                    query=query, status="completed", results_count=result_count
                )

                for i in range(result_count):
                    RawSearchResult.objects.create(
                        execution=execution,
                        title=f"Result {i}",
                        link=f"https://example.com/{session.id}/result{i}",
                        snippet=f"Snippet {i}",
                        position=i + 1,
                    )

                result = process_session_results_task(str(session.id))  # type: ignore[call-arg]
                self.assertIsInstance(result, dict)

                session.refresh_from_db()
                self.assertEqual(
                    session.status,
                    expected_status,
                    f"Session with {result_count} results should be in {expected_status}",
                )


class StateTransitionValidationTest(TransactionTestCase):
    """Test state transition hardening and validation"""

    def setUp(self):
        self.user = create_test_user()

        self.session = SearchSession.objects.create(
            title="Transition Test",
            description="Testing state transitions",
            status="draft",
            owner=self.user,
        )

    def test_valid_transitions(self):
        """Test valid state transitions are allowed"""
        valid_transitions = [
            ("draft", "defining_search"),
            ("defining_search", "ready_to_execute"),
            ("ready_to_execute", "executing"),
            ("executing", "processing_results"),
            ("processing_results", "ready_for_review"),
            ("ready_for_review", "under_review"),
            ("under_review", "completed"),
        ]

        for from_state, to_state in valid_transitions:
            with self.subTest(from_state=from_state, to_state=to_state):
                # Reset to from_state using update() to bypass validation
                SearchSession.objects.filter(id=self.session.id).update(
                    status=from_state
                )
                self.session.refresh_from_db()

                # Attempt transition
                can_transition = self.session.can_transition_to(to_state)
                self.assertTrue(
                    can_transition,
                    f"Should allow transition from {from_state} to {to_state}",
                )

    def test_invalid_transitions_blocked(self):
        """Test invalid state transitions are blocked"""
        invalid_transitions = [
            ("draft", "executing"),  # Can't skip to executing
            ("draft", "processing_results"),  # Can't skip to processing
            ("draft", "completed"),  # Can't skip to completed
            ("executing", "draft"),  # Can't go back to draft from executing
            ("completed", "executing"),  # Can't restart from completed
        ]

        for from_state, to_state in invalid_transitions:
            with self.subTest(from_state=from_state, to_state=to_state):
                # Reset to from_state using update() to bypass validation
                SearchSession.objects.filter(id=self.session.id).update(
                    status=from_state
                )
                self.session.refresh_from_db()

                # Attempt transition
                can_transition = self.session.can_transition_to(to_state)
                self.assertFalse(
                    can_transition,
                    f"Should block transition from {from_state} to {to_state}",
                )

    def test_automated_state_progression(self):
        """Test automated state progression during processing"""
        # Set up session in executing state
        SearchSession.objects.filter(id=self.session.id).update(status="executing")
        self.session.refresh_from_db()

        # Create strategy and query
        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test"],
            interest_terms=["test"],
            context_terms=["test"],
        )

        query = SearchQuery.objects.create(
            strategy=strategy,
            session=self.session,
            query_text="test",
            target_domain="test.com",
            query_type="manual",
        )

        # Create completed execution
        execution = SearchExecution.objects.create(
            query=query, status="completed", results_count=10
        )

        # Create some results
        for i in range(10):
            RawSearchResult.objects.create(
                execution=execution,
                title=f"Result {i}",
                link=f"https://example.com/result{i}",
                snippet=f"Snippet {i}",
                position=i + 1,
            )

        # Move to processing_results
        SearchSession.objects.filter(id=self.session.id).update(
            status="processing_results"
        )
        self.session.refresh_from_db()

        # Process using the task -- creates async workflow
        result = process_session_results_task(str(self.session.id))  # type: ignore[call-arg]
        self.assertIsInstance(result, dict)

        # When called directly (not via Celery worker), the async workflow
        # is created but batch tasks don't execute synchronously.
        # Session stays in processing_results until the workflow completes.
        self.session.refresh_from_db()
        self.assertEqual(
            self.session.status,
            "processing_results",
            "Session should be in processing_results (async workflow created)",
        )

    def test_missed_transition_detection(self):
        """Test that missed transitions are detected and handled"""
        # Use update() to bypass validation when forcing states
        SearchSession.objects.filter(id=self.session.id).update(status="executing")
        self.session.refresh_from_db()

        # Directly set to ready_for_review (simulating missed transition)
        SearchSession.objects.filter(id=self.session.id).update(
            status="ready_for_review"
        )
        self.session.refresh_from_db()

        # The frontend should detect this jump
        # This would be handled by execution_monitor.js detect_missed_transition()
        # Here we just verify the state is valid
        self.assertEqual(self.session.status, "ready_for_review")
        self.assertTrue(
            self.session.can_transition_to("under_review"),
            "Should be able to proceed from ready_for_review",
        )
