"""Regression test for plan 002.

`handle_complete_execution_error` must pass a real session-id *string* (derived
from the execution) into `handle_execution_error_with_progress`, not the
`QueryProgressService` object it used to forward in the `session_id` slot.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.tests.utils import create_test_user
from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.models import SearchExecution
from apps.serp_execution.tasks import execution_helpers

User = get_user_model()


class _FakeRequest:
    id = "task-1"


class HandleCompleteExecutionErrorTest(TestCase):
    def setUp(self):
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            owner=self.user, title="Err Session", status="executing"
        )
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["elderly"],
            interest_terms=["telehealth"],
            context_terms=["rural"],
            search_config={"include_general_search": True},
            is_complete=True,
        )
        self.query = SearchQuery.objects.create(
            session=self.session,
            strategy=self.strategy,
            query_text="test query",
            is_active=True,
        )
        self.execution = SearchExecution.objects.create(
            query=self.query, initiated_by=self.user, search_engine="google"
        )

    # _handle_execution_error is imported inside the function from the execution
    # module, so it must be patched at its source, not on execution_helpers.
    @patch("apps.serp_execution.tasks.execution._handle_execution_error")
    @patch.object(execution_helpers, "handle_execution_error_with_progress")
    def test_passes_real_session_id_not_service_object(
        self, mock_progress, _mock_handle
    ):
        execution_helpers.handle_complete_execution_error(
            execution_id=str(self.execution.id),
            error=ValueError("boom"),
            request=_FakeRequest(),
            max_retries=3,
            progress_service=object(),  # non-string sentinel (the old bug forwarded this)
            execution=self.execution,
        )

        # 3rd positional arg (session_id) must be the real session id string.
        args, kwargs = mock_progress.call_args
        session_id_arg = args[2] if len(args) > 2 else kwargs.get("session_id")
        self.assertEqual(session_id_arg, str(self.execution.query.session_id))
        self.assertIsInstance(session_id_arg, str)
