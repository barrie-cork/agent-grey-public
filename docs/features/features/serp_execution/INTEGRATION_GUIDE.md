# SERP Execution Integration Guide

## Table of Contents
1. [Overview](#overview)
2. [Workflow Integration](#workflow-integration)
3. [Session Handoff](#session-handoff)
4. [Results Processing Integration](#results-processing-integration)
5. [Error State Management](#error-state-management)
6. [Frontend Integration](#frontend-integration)
7. [API Integration Patterns](#api-integration-patterns)
8. [Testing Integration](#testing-integration)

## Overview

This guide covers how the SERP Execution module integrates with other components of Agent Grey's 9-state workflow system. It details the handoff mechanisms, state transitions, and integration patterns necessary for seamless operation.

## Workflow Integration

### Position in 9-State Workflow

The SERP Execution module handles the **"executing"** state, which is the fourth state in the workflow:

```
1. draft
2. defining_search
3. ready_to_execute
4. executing ← SERP Execution Active
5. processing_results
6. ready_for_review
7. under_review
8. completed
9. archived
```

### State Transition Flow

```python
# Incoming transition (from search_strategy)
ready_to_execute → executing

# Outgoing transitions
executing → processing_results  # Success path
executing → ready_to_execute   # Retry/recovery path
executing → failed             # Terminal failure
```

## Session Handoff

### From Search Strategy to SERP Execution

#### 1. Trigger Point

The handoff occurs when a user clicks "Execute Search" in the search strategy interface:

```python
# apps/search_strategy/views.py
class ExecuteSearchView(LoginRequiredMixin, View):
    def post(self, request, session_id):
        session = get_object_or_404(SearchSession, id=session_id)

        # Validate session is ready
        if session.status != 'ready_to_execute':
            return JsonResponse({'error': 'Invalid state'}, status=400)

        # Transition to executing
        state_manager = SessionStateManager(session)
        if state_manager.transition_to('executing'):
            # Launch SERP execution
            from apps.serp_execution.tasks import initiate_search_session_execution_task
            task = initiate_search_session_execution_task.delay(str(session.id))

            # Store task ID for tracking
            session.current_task_id = task.id
            session.save()

            return JsonResponse({
                'success': True,
                'task_id': task.id,
                'redirect_url': reverse('serp_execution:progress', args=[session.id])
            })
```

#### 2. Data Transfer

The following data is passed from search_strategy to serp_execution:

```python
# Data structure passed via session relationship
{
    'session': {
        'id': UUID,
        'status': 'executing',
        'owner': User,
        'search_strategy': SearchStrategy
    },
    'queries': [
        {
            'id': UUID,
            'query_string': str,  # e.g., "machine learning filetype:pdf"
            'search_type': str,   # 'primary', 'expanded', 'filtered'
            'parameters': {
                'num_results': int,
                'date_from': str,
                'language': str,
                'file_types': list
            }
        }
    ]
}
```

#### 3. Validation Requirements

Before accepting the handoff, SERP execution validates:

```python
class SessionValidator:
    def validate_session(self, session_id: UUID) -> SessionValidationResult:
        """
        Validate session can be executed.

        Checks:
        1. Session exists and is in correct state
        2. User has permission
        3. Queries are defined
        4. API credentials are valid
        5. Rate limits allow execution
        """
        session = SearchSession.objects.get(id=session_id)

        # State validation
        if session.status != 'ready_to_execute':
            return SessionValidationResult(
                can_execute=False,
                error_message=f"Invalid state: {session.status}"
            )

        # Query validation
        queries = session.search_strategy.queries.filter(is_active=True)
        if not queries.exists():
            return SessionValidationResult(
                can_execute=False,
                error_message="No active queries defined"
            )

        # API validation
        if not self._validate_api_access():
            return SessionValidationResult(
                can_execute=False,
                error_message="API access not configured"
            )

        return SessionValidationResult(can_execute=True)
```

### To Results Processing

#### 1. Completion Trigger

When all queries are executed, SERP execution automatically transitions to results processing:

```python
# apps/serp_execution/services/execution_orchestrator.py
def _complete_execution(self, session: SearchSession):
    """
    Complete execution and trigger results processing.
    """
    # Check all executions complete
    executions = SearchExecution.objects.filter(
        query__session=session
    )

    if executions.filter(status__in=['pending', 'running']).exists():
        return  # Still executing

    # Calculate totals
    total_results = RawSearchResult.objects.filter(
        execution__query__session=session
    ).count()

    # Update session
    session.total_raw_results = total_results
    session.execution_completed_at = timezone.now()
    session.save()

    # Transition to processing
    state_manager = SessionStateManager(session)
    if state_manager.transition_to('processing_results'):
        # Launch results processing
        from apps.results_manager.tasks import process_session_results_task
        process_session_results_task.delay(str(session.id))
```

#### 2. Data Handoff Structure

```python
# Data passed to results_manager
{
    'session_id': UUID,
    'raw_results': [
        {
            'id': UUID,
            'execution_id': UUID,
            'position': int,
            'title': str,
            'link': str,
            'snippet': str,
            'source': str,
            'has_pdf': bool,
            'detected_date': date,
            'raw_data': dict
        }
    ],
    'execution_metadata': {
        'total_queries': int,
        'successful_queries': int,
        'failed_queries': int,
        'total_api_calls': int,
        'credits_used': int,
        'duration_seconds': float
    }
}
```

## Results Processing Integration

### Raw Results to Processed Results

The integration between SERP execution and results processing involves:

1. **Data Transformation**
```python
# Transform raw results to processing queue
class ResultsProcessor:
    def process_raw_results(self, session_id: UUID):
        raw_results = RawSearchResult.objects.filter(
            execution__query__session_id=session_id,
            is_processed=False
        )

        for raw_result in raw_results:
            processed = ProcessedResult.objects.create(
                session_id=session_id,
                title=self._normalize_title(raw_result.title),
                url=raw_result.link,
                snippet=self._clean_snippet(raw_result.snippet),
                source_domain=raw_result.get_domain(),
                document_type=self._detect_document_type(raw_result),
                publication_date=raw_result.detected_date,
                relevance_score=self._calculate_relevance(raw_result),
                raw_result=raw_result
            )

            raw_result.is_processed = True
            raw_result.save()
```

2. **Deduplication**
```python
def deduplicate_results(self, session_id: UUID):
    """
    Identify and mark duplicate results.
    """
    results = ProcessedResult.objects.filter(session_id=session_id)

    # Group by URL
    url_groups = results.values('url').annotate(
        count=Count('id'),
        ids=ArrayAgg('id')
    ).filter(count__gt=1)

    for group in url_groups:
        # Keep highest relevance score
        duplicates = ProcessedResult.objects.filter(
            id__in=group['ids']
        ).order_by('-relevance_score')

        primary = duplicates.first()
        for duplicate in duplicates[1:]:
            duplicate.is_duplicate = True
            duplicate.duplicate_of = primary
            duplicate.save()
```

## Error State Management

### Error Recovery Patterns

#### 1. Transient Error Recovery

```python
class ExecutionErrorHandler:
    def handle_transient_error(self, execution: SearchExecution, error: Exception):
        """
        Handle recoverable errors with retry.
        """
        if execution.retry_count < 3:
            execution.retry_count += 1
            execution.status = 'pending'
            execution.error_message = f"Retry {execution.retry_count}: {str(error)}"
            execution.save()

            # Schedule retry with backoff
            retry_delay = 60 * (2 ** execution.retry_count)
            execute_single_query_task.apply_async(
                args=[execution.id],
                countdown=retry_delay
            )
        else:
            self.handle_permanent_failure(execution, error)
```

#### 2. Session Recovery

```python
class SessionRecoveryService:
    def recover_stuck_session(self, session_id: UUID):
        """
        Recover session stuck in executing state.
        """
        session = SearchSession.objects.get(id=session_id)

        # Check if genuinely stuck
        time_in_state = timezone.now() - session.last_updated
        if time_in_state.total_seconds() < 300:  # 5 minutes
            return  # Still processing

        # Check execution status
        executions = SearchExecution.objects.filter(
            query__session=session
        )

        pending = executions.filter(status='pending').count()
        running = executions.filter(status='running').count()
        completed = executions.filter(status='completed').count()
        failed = executions.filter(status='failed').count()

        if running > 0:
            # Check Celery tasks
            for exec in executions.filter(status='running'):
                if not self._is_task_active(exec.celery_task_id):
                    # Task died, mark as failed
                    exec.status = 'failed'
                    exec.error_message = 'Task terminated unexpectedly'
                    exec.save()

        if pending == 0 and running == 0:
            # All done, transition
            if failed > 0 and completed == 0:
                # Total failure
                state_manager = SessionStateManager(session)
                state_manager.transition_to('failed')
            else:
                # Partial or complete success
                state_manager = SessionStateManager(session)
                state_manager.transition_to('processing_results')
```

#### 3. Circuit Breaker Integration

```python
from apps.serp_execution.services.circuit_breaker import serper_circuit_breaker

class CircuitBreakerIntegration:
    def check_circuit_state(self):
        """
        Check if API calls should proceed.
        """
        if serper_circuit_breaker.current_state == 'open':
            # Circuit is open, API is down
            return {
                'can_proceed': False,
                'reason': 'API circuit breaker is open',
                'retry_after': serper_circuit_breaker.time_until_half_open()
            }

        return {'can_proceed': True}

    def handle_circuit_open(self, session: SearchSession):
        """
        Handle open circuit breaker.
        """
        # Pause all pending executions
        SearchExecution.objects.filter(
            query__session=session,
            status='pending'
        ).update(
            status='paused',
            error_message='API temporarily unavailable'
        )

        # Notify user
        from apps.core.notifications import notify_user
        notify_user(
            session.owner,
            'Search execution paused',
            'The search service is temporarily unavailable. Will retry automatically.'
        )
```

## Frontend Integration

### Progress Monitoring

#### 1. JavaScript Polling

```javascript
// static/js/serp_execution/progress_monitor.js
class ExecutionProgressMonitor {
    constructor(sessionId) {
        this.sessionId = sessionId;
        this.pollInterval = 2000; // 2 seconds
        this.pollTimer = null;
    }

    start() {
        this.poll();
        this.pollTimer = setInterval(() => this.poll(), this.pollInterval);
    }

    async poll() {
        try {
            const response = await fetch(`/api/serp-execution/status/${this.sessionId}/`);
            const data = await response.json();

            this.updateUI(data);

            // Check for completion
            if (data.status === 'completed' || data.status === 'processing_results') {
                this.stop();
                if (data.next_url) {
                    window.location.href = data.next_url;
                }
            }
        } catch (error) {
            console.error('Polling error:', error);
        }
    }

    updateUI(data) {
        // Update progress bar
        const progressBar = document.getElementById('execution-progress');
        progressBar.style.width = `${data.progress * 100}%`;
        progressBar.textContent = `${Math.round(data.progress * 100)}%`;

        // Update counters
        document.getElementById('completed-queries').textContent = data.completed_queries;
        document.getElementById('total-queries').textContent = data.total_queries;
        document.getElementById('results-count').textContent = data.results_count;

        // Update status
        document.getElementById('execution-status').textContent = data.status;
        document.getElementById('execution-status').className = `status-${data.status}`;
    }

    stop() {
        if (this.pollTimer) {
            clearInterval(this.pollTimer);
            this.pollTimer = null;
        }
    }
}
```

#### 2. WebSocket Alternative

```python
# apps/serp_execution/consumers.py
from channels.generic.websocket import AsyncJsonWebsocketConsumer

class ExecutionProgressConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.room_group_name = f'execution_{self.session_id}'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def execution_update(self, event):
        """
        Send execution updates to WebSocket.
        """
        await self.send_json({
            'type': 'execution.update',
            'data': event['data']
        })
```

### Status API Endpoint

```python
# apps/serp_execution/views.py
class ExecutionStatusAPI(LoginRequiredMixin, View):
    def get(self, request, session_id):
        """
        Get current execution status for frontend.
        """
        session = get_object_or_404(
            SearchSession,
            id=session_id,
            owner=request.user
        )

        # Get execution statistics
        executions = SearchExecution.objects.filter(
            query__session=session
        )

        total = executions.count()
        completed = executions.filter(status='completed').count()
        failed = executions.filter(status='failed').count()
        running = executions.filter(status='running').count()

        # Calculate progress
        progress = completed / total if total > 0 else 0

        # Get result count
        results_count = RawSearchResult.objects.filter(
            execution__query__session=session
        ).count()

        # Determine next URL
        next_url = None
        if session.status == 'processing_results':
            next_url = reverse('results_manager:processing', args=[session.id])
        elif session.status == 'ready_for_review':
            next_url = reverse('review_results:review', args=[session.id])

        return JsonResponse({
            'status': session.status,
            'progress': progress,
            'completed_queries': completed,
            'failed_queries': failed,
            'running_queries': running,
            'total_queries': total,
            'results_count': results_count,
            'next_url': next_url,
            'errors': list(
                executions.filter(status='failed').values_list(
                    'error_message', flat=True
                )[:5]
            )
        })
```

## API Integration Patterns

### Async Task Pattern

```python
# Pattern for launching async execution
def execute_async(session_id: UUID) -> str:
    """
    Launch async execution and return task ID.
    """
    from apps.serp_execution.tasks import initiate_search_session_execution_task

    # Launch task
    task = initiate_search_session_execution_task.delay(str(session_id))

    # Store task ID for tracking
    SearchSession.objects.filter(id=session_id).update(
        current_task_id=task.id,
        execution_started_at=timezone.now()
    )

    return task.id
```

### Synchronous Wrapper

```python
# Pattern for synchronous execution (testing/admin)
def execute_sync(session_id: UUID, timeout: int = 300) -> dict:
    """
    Execute synchronously with timeout.
    """
    from apps.serp_execution.services.execution_orchestrator import ExecutionOrchestrator

    orchestrator = ExecutionOrchestrator()

    try:
        result = orchestrator.execute_session(session_id)
        return result.model_dump()
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }
```

### Batch Processing Pattern

```python
class BatchExecutor:
    """
    Execute multiple sessions in batch.
    """

    def execute_batch(self, session_ids: List[UUID]):
        from celery import group
        from apps.serp_execution.tasks import initiate_search_session_execution_task

        # Create task group
        job = group(
            initiate_search_session_execution_task.s(str(sid))
            for sid in session_ids
        )

        # Execute in parallel
        result = job.apply_async()

        return {
            'group_id': result.id,
            'task_ids': [r.id for r in result.results],
            'session_ids': session_ids
        }
```

## Testing Integration

### Integration Test Pattern

```python
from django.test import TransactionTestCase
from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchQuery
from apps.serp_execution.services.execution_orchestrator import ExecutionOrchestrator

class TestSerpExecutionIntegration(TransactionTestCase):
    def test_complete_execution_flow(self):
        """
        Test complete execution from handoff to results.
        """
        # Setup
        session = self.create_test_session(status='ready_to_execute')
        queries = self.create_test_queries(session, count=3)

        # Execute
        orchestrator = ExecutionOrchestrator()
        result = orchestrator.execute_session(session.id)

        # Verify execution
        self.assertTrue(result.success)
        self.assertEqual(result.queries_count, 3)

        # Verify state transition
        session.refresh_from_db()
        self.assertEqual(session.status, 'executing')

        # Verify results created
        from apps.serp_execution.models import RawSearchResult
        results = RawSearchResult.objects.filter(
            execution__query__session=session
        )
        self.assertTrue(results.exists())

    def test_error_recovery_flow(self):
        """
        Test error recovery integration.
        """
        session = self.create_test_session()

        # Simulate API error
        with patch('apps.core.services.serper_client.SerperClient.search') as mock:
            mock.side_effect = ConnectionError("Network error")

            orchestrator = ExecutionOrchestrator()
            result = orchestrator.execute_session(session.id)

            # Should handle gracefully
            self.assertFalse(result.success)
            self.assertIn('Network error', result.error)
```

### Mock Integration

```python
# Use mock client for integration testing
from apps.serp_execution.services.mock_serper_client import MockSerperClient

@override_settings(SERP_EXECUTION_CONFIG={'enable_mock_mode': True})
class TestWithMockAPI(TestCase):
    def test_execution_with_mock(self):
        """
        Test execution with mock API.
        """
        # Mock client automatically used when enable_mock_mode=True
        session = create_test_session()

        # Execute
        from apps.serp_execution.tasks import initiate_search_session_execution_task
        result = initiate_search_session_execution_task(str(session.id))

        # Verify mock results
        self.assertTrue(result['success'])
        self.assertEqual(result['api_calls'], 0)  # No real API calls
```

## Best Practices

### 1. State Management
- Always use SessionStateManager for transitions
- Never manually update session status
- Handle all state transitions atomically

### 2. Error Handling
- Classify errors as transient or permanent
- Implement exponential backoff for retries
- Log all errors with context

### 3. Resource Management
- Use connection pooling
- Implement circuit breakers
- Monitor rate limits proactively

### 4. Testing
- Test all integration points
- Use mocks for external services
- Verify state transitions

### 5. Monitoring
- Log all handoffs
- Track execution metrics
- Monitor error rates

## Troubleshooting Integration Issues

### Common Integration Problems

| Issue | Symptoms | Solution |
|-------|----------|----------|
| State mismatch | Execution fails to start | Verify session is in 'ready_to_execute' state |
| Missing queries | No queries to execute | Check search_strategy created queries |
| Task not starting | Status stuck in 'executing' | Verify Celery workers are running |
| Results not processing | Stuck after execution | Check transition to 'processing_results' |
| Frontend not updating | Progress bar static | Verify polling/WebSocket connection |

### Debug Commands

```bash
# Check session state
dc run --rm web python manage.py shell
>>> from apps.review_manager.models import SearchSession
>>> session = SearchSession.objects.get(id='...')
>>> print(f"Status: {session.status}")
>>> print(f"Task ID: {session.current_task_id}")

# Check execution status
>>> from apps.serp_execution.models import SearchExecution
>>> executions = SearchExecution.objects.filter(query__session=session)
>>> for e in executions:
...     print(f"{e.id}: {e.status} - {e.error_message}")

# Force state transition (recovery)
>>> from apps.review_manager.services.state_manager import SessionStateManager
>>> manager = SessionStateManager(session)
>>> manager.transition_to('processing_results')
```

## Summary

The SERP Execution module integrates seamlessly with Agent Grey's workflow through:
- Well-defined state transitions
- Clear data handoff structures
- Robust error recovery mechanisms
- Real-time progress monitoring
- Comprehensive testing patterns

This integration ensures reliable, scalable search execution within the larger grey literature review system.
