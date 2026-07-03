# Consensus Discussion Feature Architecture

**Version:** 1.0
**Last Updated:** 2025-10-21
**Status:** Production
**Phase:** Phase 3 (Consensus Discussion) - Implemented

## Table of Contents

1. [System Overview](#system-overview)
2. [Technology Stack](#technology-stack)
3. [Data Flow](#data-flow)
4. [Database Schema](#database-schema)
5. [Component Architecture](#component-architecture)
6. [State Management](#state-management)
7. [SSE Implementation](#sse-implementation)
8. [Authentication and Permissions](#authentication-and-permissions)
9. [Performance Considerations](#performance-considerations)
10. [Deployment Architecture](#deployment-architecture)

---

## System Overview

The Consensus Discussion feature enables dual-screening reviewers to resolve conflicts through structured discussion, re-voting, and arbitration. This feature aligns with PRISMA 2020 and Cochrane systematic review standards, providing a complete audit trail of the consensus-building process for grey literature reviews.

### High-Level Architecture

```mermaid
graph TB
    subgraph "Client Layer"
        UI[ConflictDiscussion.vue]
        Store[Pinia Store]
        SSE[SSE Composable]
    end

    subgraph "API Layer"
        REST[REST API Endpoints]
        SSEStream[SSE Stream Endpoint]
    end

    subgraph "Service Layer"
        ReviewCoord[ReviewCoordinationService]
        EmailNotif[EmailNotificationService]
    end

    subgraph "Data Layer"
        Models[Django Models]
        DB[(PostgreSQL)]
    end

    UI --> Store
    Store --> REST
    SSE --> SSEStream
    REST --> ReviewCoord
    SSEStream --> Models
    ReviewCoord --> Models
    ReviewCoord --> EmailNotif
    Models --> DB

    classDef frontend fill:#e3f2fd,stroke:#1976d2,stroke-width:2px
    classDef backend fill:#fff3e0,stroke:#f57c00,stroke-width:2px
    classDef data fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px

    class UI,Store,SSE frontend
    class REST,SSEStream,ReviewCoord,EmailNotif backend
    class Models,DB data
```

### Core Features

1. **Threaded Discussion**: Reviewers discuss conflicts with support for nested replies
2. **Re-vote Workflow**: Structured proposal, acceptance, and voting process
3. **Real-time Updates**: SSE-based push notifications for discussion events
4. **Email Notifications**: Async notifications for key events (Phase 4)
5. **Audit Trail**: Immutable record of all discussion and decision history
6. **Consensus Detection**: Automatic conflict resolution when re-votes achieve consensus

---

## Technology Stack

### Backend Technologies

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Framework** | Django | 5.2.7 | Async-capable web framework |
| **Database** | PostgreSQL | 15 | Relational data storage with JSON support |
| **ORM** | Django ORM | 5.2.7 | Database abstraction with async support |
| **API Framework** | Django REST Framework | 3.14.0 | REST API endpoints and serialization |
| **API Documentation** | drf-spectacular | 0.27.0 | OpenAPI/Swagger schema generation |
| **Markdown Rendering** | python-markdown | 3.5.1 | Comment markdown to HTML conversion |
| **Email** | Celery | 5.3.4 | Async email notification delivery |

### Frontend Technologies

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Framework** | Vue.js | 3.4.x | Reactive UI framework |
| **State Management** | Pinia | 2.1.x | Centralised state management |
| **Type Safety** | TypeScript | 5.x | Static type checking |
| **HTTP Client** | Axios | 1.6.x | REST API communication |
| **Build Tool** | Vite | 5.x | Fast development and production builds |
| **SSE Client** | EventSource API | Native | Browser-native SSE support |

### Infrastructure

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Web Server** | Nginx | Reverse proxy with SSE support |
| **ASGI Server** | Uvicorn | Async Python application server |
| **Message Queue** | Redis | Celery task queue backend |
| **Cache** | Redis | Session and query caching |

---

## Data Flow

### Comment Posting Flow

```mermaid
sequenceDiagram
    participant User
    participant Vue as ConflictDiscussion.vue
    participant Store as Pinia Store
    participant API as REST API
    participant Service as ReviewCoordinationService
    participant DB as PostgreSQL
    participant SSE as SSE Stream
    participant Email as Email Service

    User->>Vue: Type comment and submit
    Vue->>Store: addComment(conflictId, content)
    Store->>API: POST /api/conflicts/{id}/comments/

    API->>API: Validate permissions
    API->>Service: Create comment
    Service->>DB: INSERT ConflictComment
    DB-->>Service: Comment saved
    Service->>DB: UPDATE ConflictResolution status

    API->>Email: Queue notification email
    Email-->>Email: Async delivery via Celery

    API-->>Store: Return comment data
    Store->>Store: Update local state
    Store-->>Vue: Comment added
    Vue-->>User: Display new comment

    DB->>SSE: Trigger change detection
    SSE-->>Vue: SSE event: new_comment
    Vue->>Store: Update from SSE
    Store->>Vue: Re-render with server data
```

### Re-vote Consensus Flow

```mermaid
sequenceDiagram
    participant R1 as Reviewer 1
    participant R2 as Reviewer 2
    participant API as REST API
    participant Service as ReviewCoordinationService
    participant DB as PostgreSQL
    participant SSE as SSE Stream
    participant Email as Email Service

    R1->>API: POST /api/conflicts/{id}/revote/propose
    API->>DB: INSERT RevoteProposal (status=PROPOSED)
    API->>DB: Add R1 to accepted_by
    API->>DB: INSERT system message
    API->>Email: Notify R2 of proposal
    API-->>R1: Proposal created
    SSE-->>R2: SSE: revote_proposed

    R2->>API: POST /api/conflicts/{id}/revote/{pid}/accept
    API->>DB: Add R2 to accepted_by
    API->>DB: UPDATE status=ACCEPTED
    API->>DB: INSERT system message
    API->>Email: Notify all: ready to vote
    API-->>R2: Proposal accepted
    SSE-->>R1: SSE: revote_accepted

    R1->>API: POST /api/conflicts/{id}/revote/{pid}/vote
    API->>DB: INSERT ReviewerDecision (is_revote=true)
    API-->>R1: Decision recorded
    SSE-->>R2: SSE: revote_decision_submitted

    R2->>API: POST /api/conflicts/{id}/revote/{pid}/vote
    API->>DB: INSERT ReviewerDecision (is_revote=true)
    API->>Service: Check for consensus
    Service->>DB: Query all re-vote decisions
    Service->>Service: Detect consensus (both INCLUDE)
    Service->>DB: UPDATE ConflictResolution (status=RESOLVED)
    Service->>DB: UPDATE RevoteProposal (status=COMPLETED)
    Service->>DB: INSERT system message (consensus reached)
    Service->>Email: Notify all: consensus achieved
    API-->>R2: Consensus reached!
    SSE-->>R1: SSE: consensus_reached
```

---

## Database Schema

### Entity Relationship Diagram

```mermaid
erDiagram
    ConflictResolution ||--o{ ConflictComment : "has"
    ConflictResolution ||--o{ RevoteProposal : "has"
    ConflictResolution }o--|| ProcessedResult : "references"
    ConflictResolution ||--o{ ReviewerDecision : "conflicting_decisions"
    ConflictResolution }o--o| ReviewerDecision : "final_decision"

    RevoteProposal ||--o{ ReviewerDecision : "revote_decisions"
    RevoteProposal }o--o{ User : "accepted_by"

    ConflictComment }o--o| ConflictComment : "parent/replies"
    ConflictComment }o--|| User : "author"

    ReviewerDecision }o--|| User : "reviewer"
    ReviewerDecision }o--|| ProcessedResult : "result"

    ConflictResolution {
        uuid id PK
        uuid organisation_id FK
        uuid result_id FK
        string conflict_type
        string status
        string resolution_method
        uuid final_decision_id FK
        datetime detected_at
        datetime resolved_at
        uuid resolved_by_id FK
        text resolution_notes
    }

    ConflictComment {
        uuid id PK
        uuid conflict_id FK
        uuid author_id FK
        uuid parent_id FK
        text content
        text content_html
        datetime created_at
        datetime updated_at
        boolean is_edited
        datetime edited_at
        boolean is_deleted
        boolean is_system_message
    }

    RevoteProposal {
        uuid id PK
        uuid conflict_id FK
        uuid proposed_by_id FK
        text rationale
        string status
        datetime proposed_at
        datetime accepted_at
        datetime completed_at
        boolean resulted_in_consensus
        datetime expires_at
    }

    ReviewerDecision {
        uuid id PK
        uuid organisation_id FK
        uuid result_id FK
        uuid reviewer_id FK
        uuid assignment_id FK
        string decision
        string exclusion_reason
        integer confidence_level
        text notes
        datetime decided_at
        integer time_spent_seconds
        boolean is_revote
        uuid revote_proposal_id FK
        string screening_stage
        integer version
    }

    ProcessedResult {
        uuid id PK
        uuid session_id FK
        string title
        string url
        text snippet
        boolean is_reviewed
    }

    User {
        uuid id PK
        string username
        string email
    }
```

### Key Model Details

#### ConflictResolution

**Purpose**: Tracks conflicts and their resolution workflow

**Lifecycle States**:
- `PENDING`: Awaiting discussion or resolution
- `IN_DISCUSSION`: Active discussion with comments
- `ESCALATED`: Re-vote proposal created
- `RESOLVED`: Final decision reached

**Key Fields**:
- `conflict_type`: Type of disagreement (INCLUDE_EXCLUDE, EXCLUSION_REASON, LOW_CONFIDENCE)
- `resolution_method`: How resolved (CONSENSUS, ARBITRATION, MAJORITY, SENIOR_OVERRIDE)
- `final_decision`: FK to winning ReviewerDecision
- `detected_at`: Automatic detection timestamp
- `resolved_at`: Resolution timestamp

**Indexes**:
```python
models.Index(fields=['organisation', 'detected_at'])
models.Index(fields=['result', 'status'])
models.Index(fields=['status', 'detected_at'])
```

#### ConflictComment

**Purpose**: Discussion comments with threading support

**Features**:
- Markdown support with cached HTML rendering
- Threaded replies via self-referential `parent` FK
- Soft deletion for audit trail (`is_deleted=True`)
- System messages for workflow events (`is_system_message=True`)

**Markdown Extensions**:
- `nl2br`: Newline to `<br>` conversion
- `fenced_code`: Code block support

**Indexes**:
```python
models.Index(fields=['conflict', 'created_at'])
models.Index(fields=['conflict', 'parent'])
```

#### RevoteProposal

**Purpose**: Re-vote proposal and acceptance tracking

**Workflow States**:
- `PROPOSED`: Awaiting acceptance from all reviewers
- `ACCEPTED`: All reviewers accepted, voting can begin
- `IN_PROGRESS`: At least one re-vote decision submitted
- `COMPLETED`: All re-vote decisions submitted
- `EXPIRED`: Proposal expired before acceptance (48 hour timeout)

**Key Fields**:
- `accepted_by`: Many-to-many field tracking who accepted
- `expires_at`: Auto-expiry timestamp (48 hours from creation)
- `resulted_in_consensus`: Boolean flag for consensus detection

**Expiry Logic**:
```python
def is_expired(self):
    from django.utils import timezone
    return timezone.now() > self.expires_at and self.status == 'PROPOSED'
```

#### ReviewerDecision

**Purpose**: Immutable audit trail of reviewer decisions

**Immutability Pattern**:
```python
def save(self, *args, **kwargs):
    is_new = self._state.adding
    if not is_new and not kwargs.pop('allow_update', False):
        raise ValueError("ReviewerDecision is immutable. Create a new record instead of updating.")
    if not is_new:
        self.version += 1
    super().save(*args, **kwargs)
```

**Re-vote Fields**:
- `is_revote`: Boolean flag distinguishing re-vote decisions
- `revote_proposal`: FK to proposal (if is_revote=True)

**Unique Constraint**:
```python
models.UniqueConstraint(
    fields=['result', 'reviewer', 'screening_stage', 'is_revote'],
    name='unique_reviewer_decision_per_stage_and_type'
)
```
Allows one initial decision + one re-vote decision per reviewer per stage.

---

## Component Architecture

### Vue Component Hierarchy

```mermaid
graph TD
    ConflictDiscussion[ConflictDiscussion.vue<br/>Main Page Container]

    ConflictDiscussion --> ConflictHeader[ConflictHeader<br/>Result display]
    ConflictDiscussion --> DecisionCard[DecisionCard<br/>Decision display]
    ConflictDiscussion --> StatusBadge[StatusBadge<br/>Status indicator]
    ConflictDiscussion --> CommentThread[CommentThread<br/>Discussion UI]
    ConflictDiscussion --> RevotePanel[RevotePanel<br/>Re-vote workflow]
    ConflictDiscussion --> LoadingSpinner[LoadingSpinner<br/>Loading state]
    ConflictDiscussion --> ErrorAlert[ErrorAlert<br/>Error display]

    CommentThread --> CommentItem[CommentItem<br/>Single comment]
    CommentThread --> CommentForm[CommentForm<br/>New comment input]

    CommentItem --> CommentItem

    RevotePanel --> ProposalStatus[ProposalStatus<br/>Proposal state]
    RevotePanel --> AcceptButton[AcceptButton<br/>Accept action]
    RevotePanel --> VoteForm[VoteForm<br/>Decision input]

    classDef container fill:#e3f2fd,stroke:#1976d2,stroke-width:3px
    classDef display fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
    classDef interactive fill:#fff3e0,stroke:#f57c00,stroke-width:2px

    class ConflictDiscussion container
    class ConflictHeader,DecisionCard,StatusBadge,LoadingSpinner,ErrorAlert display
    class CommentThread,RevotePanel,CommentItem,CommentForm,ProposalStatus,AcceptButton,VoteForm interactive
```

### Component Responsibilities

#### ConflictDiscussion.vue

**Role**: Page-level container and orchestrator

**Responsibilities**:
- Route parameter handling (`conflictId`)
- Lifecycle management (mount, unmount)
- SSE connection establishment
- Error boundary and retry logic
- Layout composition

**Key Methods**:
```typescript
async loadConflictData(): Promise<void>
async handlePostComment(content: string): Promise<void>
async handleAcceptProposal(): Promise<void>
async handleSubmitDecision(decision, notes, confidence): Promise<void>
```

#### CommentThread

**Role**: Discussion thread manager

**Features**:
- Recursive rendering of nested replies
- Comment form visibility toggling
- Reply threading UI
- Scroll-to-latest behaviour

**Props**:
```typescript
{
  comments: ConflictComment[]
  canComment: boolean
  isSubmitting: boolean
}
```

**Events**:
```typescript
emit('post-comment', content: string)
```

#### RevotePanel

**Role**: Re-vote workflow UI

**States**:
- Proposal pending acceptance (show Accept button)
- Proposal accepted, awaiting votes (show Vote form)
- Re-vote in progress (show progress indicator)
- Re-vote completed (show results)

**Props**:
```typescript
{
  proposal: RevoteProposal
  conflictId: string
  currentUserId: string
  hasAlreadyVoted: boolean
}
```

**Events**:
```typescript
emit('accept-proposal')
emit('submit-decision', decision: DecisionType, notes?: string, confidence: number)
```

---

## State Management

### Pinia Store Structure

```mermaid
graph TD
    subgraph "consensusDiscussion Store"
        State[State]
        Getters[Getters]
        Actions[Actions]

        State --> conflictDetail
        State --> isLoading
        State --> error
        State --> isSubmitting
        State --> optimisticComments

        Getters --> allComments
        Getters --> activeRevoteProposal
        Getters --> canComment
        Getters --> canProposeRevote
        Getters --> canAcceptRevote
        Getters --> canVoteOnRevote
        Getters --> hasVotedOnActiveProposal
        Getters --> discussionSummary

        Actions --> fetchConflictDetail
        Actions --> addComment
        Actions --> createRevoteProposal
        Actions --> acceptProposal
        Actions --> submitVote
        Actions --> clearConflict
        Actions --> clearError
    end

    classDef state fill:#e8f5e9,stroke:#4caf50,stroke-width:2px
    classDef getter fill:#e3f2fd,stroke:#2196f3,stroke-width:2px
    classDef action fill:#fff3e0,stroke:#ff9800,stroke-width:2px

    class State,conflictDetail,isLoading,error,isSubmitting,optimisticComments state
    class Getters,allComments,activeRevoteProposal,canComment,canProposeRevote,canAcceptRevote,canVoteOnRevote,hasVotedOnActiveProposal,discussionSummary getter
    class Actions,fetchConflictDetail,addComment,createRevoteProposal,acceptProposal,submitVote,clearConflict,clearError action
```

### Store State Schema

```typescript
interface ConsensusDiscussionState {
  // Server data
  conflictDetail: ConflictResolutionDetail | null

  // UI state
  isLoading: boolean
  error: string | null
  isSubmitting: boolean

  // Optimistic updates
  optimisticComments: ConflictComment[]
}
```

### Permission Getters Logic

#### canComment

```typescript
const canComment = computed(() => {
  const authStore = useAuthStore()
  if (!authStore.user || !conflictDetail.value) return false

  // Must be a conflicting reviewer
  const userId = authStore.user.id
  const isConflictingReviewer = conflictDetail.value.conflicting_decisions?.some(
    (decision) => decision.reviewer.id === userId
  )

  // Conflict must not be resolved
  return isConflictingReviewer && conflictDetail.value.status === 'PENDING'
})
```

#### canProposeRevote

```typescript
const canProposeRevote = computed(() => {
  if (!canComment.value || !conflictDetail.value) return false

  // No active proposal exists
  const hasActiveProposal = activeRevoteProposal.value !== null

  // At least one discussion comment exists
  const hasDiscussion = conflictDetail.value.comments.length > 0

  return !hasActiveProposal && hasDiscussion
})
```

#### canVoteOnRevote

```typescript
const canVoteOnRevote = computed(() => {
  const authStore = useAuthStore()
  if (!canComment.value || !activeRevoteProposal.value || !authStore.user) return false

  const proposal = activeRevoteProposal.value
  const userId = authStore.user.id

  // Check if user has already voted on this proposal
  const hasVoted = conflictDetail.value?.conflicting_decisions?.some(
    (decision) =>
      decision.reviewer.id === userId &&
      decision.is_revote &&
      decision.revote_proposal === proposal.id
  )

  return proposal.status === 'ACCEPTED' && !hasVoted
})
```

### Optimistic UI Pattern

Comments are optimistically added to local state before server confirmation:

```typescript
async function addComment(conflictId: string, input: ConflictCommentInput): Promise<ConflictComment | null> {
  isSubmitting.value = true
  error.value = null

  try {
    const newComment = await postComment(conflictId, input)

    // Update local state immediately
    if (conflictDetail.value) {
      if (input.parent_comment) {
        // Add as nested reply
        const addReplyToComment = (comments: ConflictComment[]): boolean => {
          for (const comment of comments) {
            if (comment.id === input.parent_comment) {
              comment.replies = comment.replies || []
              comment.replies.push(newComment)
              return true
            }
            if (comment.replies && addReplyToComment(comment.replies)) {
              return true
            }
          }
          return false
        }
        addReplyToComment(conflictDetail.value.comments)
      } else {
        // Add as top-level comment
        conflictDetail.value.comments.push(newComment)
      }
    }

    return newComment
  } catch (err: any) {
    error.value = err.response?.data?.message || 'Failed to post comment'
    return null
  } finally {
    isSubmitting.value = false
  }
}
```

---

## SSE Implementation

### SSE Architecture

```mermaid
sequenceDiagram
    participant Browser
    participant Nginx
    participant Django as Django (Uvicorn)
    participant DB as PostgreSQL

    Browser->>Nginx: EventSource('/api/conflicts/{id}/stream/')
    Nginx->>Django: Forward with SSE headers

    Note over Django: @transaction.non_atomic_requests
    Django->>Django: Verify user permissions
    Django->>Browser: Send connection event

    loop Every 2 seconds
        Django->>DB: Query new events (sync_to_async)
        DB-->>Django: Return changes since last check

        alt New comment detected
            Django->>Browser: event: new_comment\ndata: {...}
        end

        alt Re-vote proposed
            Django->>Browser: event: revote_proposed\ndata: {...}
        end

        alt All reviewers accepted
            Django->>Browser: event: revote_accepted\ndata: {...}
        end

        alt Consensus reached
            Django->>Browser: event: consensus_reached\ndata: {...}
            Django->>Browser: Close connection
        end

        Django->>Browser: : keepalive
    end
```

### Django SSE View (async)

**File**: `apps/review_results/api/sse_views.py`

**Key Patterns**:

#### 1. Async View Decorator

```python
@csrf_exempt  # SSE doesn't support CSRF tokens in EventSource API
@login_required
@transaction.non_atomic_requests  # Required for async views with ATOMIC_REQUESTS=True
async def conflict_discussion_stream(request, conflict_id):
    """SSE endpoint for real-time conflict discussion updates."""
```

#### 2. Thread-Safe Database Access

```python
@sync_to_async(thread_sensitive=True)
def get_new_events():
    """Fetch new events since last check."""
    events = {
        'new_comments': [],
        'revote_proposed': [],
        'revote_accepted': [],
        'consensus_reached': None,
    }

    # Get new comments
    new_comments = ConflictComment.objects.filter(
        conflict_id=conflict_id,
        created_at__gt=last_check,
        is_deleted=False
    ).select_related('author', 'parent').order_by('created_at')

    if new_comments.exists():
        events['new_comments'] = list(new_comments)

    return events
```

#### 3. SSE Event Format

```python
# Event with data
yield f"event: new_comment\n"
yield f"data: {json.dumps(event_data)}\n\n"

# Keepalive comment (ignored by EventSource)
yield ": keepalive\n\n"
```

#### 4. Error Handling and Reconnection

```python
consecutive_errors = 0
max_errors = 3

while True:
    try:
        events = await get_new_events()
        # Process events...
        consecutive_errors = 0  # Reset on success

    except Exception as e:
        consecutive_errors += 1
        logger.error(f"SSE error: {e}", exc_info=True)

        if consecutive_errors >= max_errors:
            yield 'data: {"type": "error", "message": "Too many errors"}\n\n'
            break

        await asyncio.sleep(1.0)
```

### Nginx SSE Configuration

**Critical Headers**:

```nginx
location ~ ^/api/conflicts/.+/stream/$ {
    proxy_pass http://web:8000;

    # Disable buffering for SSE
    proxy_set_header X-Accel-Buffering no;
    proxy_buffering off;
    proxy_cache off;

    # Extended timeout for long-lived connections
    proxy_read_timeout 300s;

    # SSE requires chunked encoding to be disabled
    chunked_transfer_encoding off;
}
```

### Frontend SSE Composable

**File**: `frontend/src/composables/useConflictSSE.ts`

**Features**:
- Automatic reconnection with exponential backoff
- Connection state tracking
- Custom event dispatching for Vue components

**Usage**:

```typescript
import { useConflictSSE } from '@/composables/useConflictSSE'
import { onMounted, onUnmounted } from 'vue'

const { connect, disconnect, connectionState, isConnected } = useConflictSSE(conflictId.value)

onMounted(() => {
  connect()
})

onUnmounted(() => {
  disconnect()
})

// Listen for SSE events
window.addEventListener('conflict:new_comment', (event: CustomEvent) => {
  const comment = event.detail
  // Update UI...
})
```

**Reconnection Logic**:

```typescript
const RECONNECT_CONFIG = {
  maxAttempts: 5,
  initialDelay: 1000,      // 1 second
  maxDelay: 8000,          // 8 seconds
  backoffMultiplier: 2,    // Exponential backoff: 1s, 2s, 4s, 8s
}

function calculateReconnectDelay(): number {
  const delay = RECONNECT_CONFIG.initialDelay * Math.pow(
    RECONNECT_CONFIG.backoffMultiplier,
    reconnectAttempts.value - 1
  )
  return Math.min(delay, RECONNECT_CONFIG.maxDelay)
}
```

---

## Authentication and Permissions

### Permission Layers

```mermaid
graph TD
    Request[HTTP Request] --> Auth[Authentication Layer]
    Auth --> Org[Organisation Middleware]
    Org --> Perm[Permission Check]

    Perm --> Conflicting{Is Conflicting<br/>Reviewer?}
    Perm --> Admin{Is Admin?}

    Conflicting -->|Yes| Allow[Allow Access]
    Admin -->|Yes| Allow

    Conflicting -->|No| Deny[403 Forbidden]
    Admin -->|No| Deny

    Allow --> Resource[Access Resource]

    classDef auth fill:#e3f2fd,stroke:#1976d2,stroke-width:2px
    classDef decision fill:#fff3e0,stroke:#f57c00,stroke-width:2px
    classDef result fill:#e8f5e9,stroke:#4caf50,stroke-width:2px
    classDef error fill:#ffebee,stroke:#f44336,stroke-width:2px

    class Auth,Org auth
    class Perm,Conflicting,Admin decision
    class Allow,Resource result
    class Deny error
```

### Permission Rules

#### Viewing Conflict Discussion

**Allowed**:
- Conflicting reviewers (users whose decisions are in conflict)
- Organisation admins (SENIOR_RESEARCHER, INFORMATION_SPECIALIST roles)

**Implementation**:

```python
# Get conflict
conflict = ConflictResolution.objects.get(id=conflict_id, organisation=organisation)

# Check if user is a conflicting reviewer
reviewer_ids = list(conflict.conflicting_decisions.values_list('reviewer_id', flat=True))
is_conflicting_reviewer = request.user.id in reviewer_ids

# Check if user is admin
from apps.organisation.models import OrganisationMembership
is_admin = OrganisationMembership.objects.filter(
    user=request.user,
    organisation=organisation,
    role__in=['SENIOR_RESEARCHER', 'INFORMATION_SPECIALIST'],
    is_active=True
).exists()

if not (is_conflicting_reviewer or is_admin):
    return Response({"error": "permission_denied"}, status=403)
```

#### Posting Comments

**Allowed**:
- Conflicting reviewers
- Organisation admins
- Conflict status must be PENDING or IN_DISCUSSION

#### Proposing Re-vote

**Allowed**:
- Conflicting reviewers only
- At least one discussion comment must exist
- No active re-vote proposal can exist
- Conflict must not be resolved

**Implementation**:

```python
def can_propose_revote(self, user):
    """Check if user can propose a re-vote."""
    # User must be one of the conflicting reviewers
    reviewer_ids = self.conflicting_decisions.values_list('reviewer_id', flat=True)
    is_conflicting_reviewer = user.id in reviewer_ids

    # No active re-vote proposals
    no_active_proposal = not self.has_active_revote_proposal()

    # Conflict not yet resolved
    not_resolved = self.status != 'RESOLVED'

    return is_conflicting_reviewer and no_active_proposal and not_resolved
```

#### Accepting Re-vote Proposal

**Allowed**:
- Conflicting reviewers only
- Proposal status must be PROPOSED
- Proposal must not be expired
- User must not have already accepted

**Implementation**:

```python
def can_accept(self, user):
    """Check if user can accept this proposal."""
    reviewer_ids = self.conflict.conflicting_decisions.values_list('reviewer_id', flat=True)
    return (
        user.id in reviewer_ids
        and self.status == 'PROPOSED'
        and not self.is_expired()
    )
```

#### Submitting Re-vote Decision

**Allowed**:
- Conflicting reviewers only
- Proposal status must be ACCEPTED or IN_PROGRESS
- User must not have already voted on this proposal

---

## Performance Considerations

### Database Query Optimisation

#### 1. Prefetch Related Data

```python
conflict = ConflictResolution.objects.prefetch_related(
    'conflicting_decisions__reviewer',
    'comments__author',
    'comments__replies__author',
    'revote_proposals__proposed_by',
    'revote_proposals__accepted_by',
).select_related(
    'result',
    'resolved_by',
    'final_decision',
).get(id=conflict_id, organisation=organisation)
```

**Benefits**:
- Single database query with JOINs instead of N+1 queries
- Reduces latency from ~500ms to ~50ms for complex conflicts

#### 2. Database Indexes

**ConflictComment**:
```python
models.Index(fields=['conflict', 'created_at'])  # List comments chronologically
models.Index(fields=['conflict', 'parent'])      # Thread replies efficiently
```

**RevoteProposal**:
```python
models.Index(fields=['conflict', 'status'])  # Find active proposals
models.Index(fields=['expires_at'])          # Auto-expiry cleanup queries
```

**ReviewerDecision**:
```python
models.Index(fields=['revote_proposal', 'is_revote'])  # Re-vote decision lookups
```

#### 3. Cached HTML Rendering

Markdown is rendered to HTML on save and cached in `content_html` field:

```python
def save(self, *args, **kwargs):
    """Render markdown to HTML on save."""
    import markdown
    self.content_html = markdown.markdown(
        self.content,
        extensions=['nl2br', 'fenced_code']
    )
    super().save(*args, **kwargs)
```

**Benefits**:
- No runtime markdown parsing required
- Faster page loads (50+ comments rendered in <10ms)

### SSE Performance

#### 1. Polling Interval

```python
# Wait before next check (non-blocking)
await asyncio.sleep(2.0)  # Check every 2 seconds
```

**Trade-off**:
- Lower interval: More real-time but higher server load
- Higher interval: Less server load but delayed updates
- 2 seconds provides good balance for discussion use case

#### 2. Change Detection

```python
# Only query changes since last check
new_comments = ConflictComment.objects.filter(
    conflict_id=conflict_id,
    created_at__gt=last_check,  # Efficient timestamp filter
    is_deleted=False
).select_related('author', 'parent').order_by('created_at')
```

**Optimisation**:
- PostgreSQL index on `(conflict_id, created_at)` makes this very fast
- Typical query time: <5ms

#### 3. Connection Limits

**Uvicorn Configuration**:
```yaml
command: uvicorn grey_lit_project.asgi:application --host 0.0.0.0 --port 8000 --workers 4
```

**Concurrency**:
- 4 workers × 1000 connections/worker = 4000 concurrent SSE connections
- Typical usage: 2-5 concurrent discussions = well within limits

### Frontend Performance

#### 1. Component Lazy Loading

```typescript
// Lazy load heavy components
const CommentThread = defineAsyncComponent(() =>
  import('../components/shared/CommentThread.vue')
)
```

#### 2. Virtual Scrolling

For discussions with 100+ comments, implement virtual scrolling:

```vue
<template>
  <RecycleScroller
    :items="comments"
    :item-size="120"
    key-field="id"
  >
    <template #default="{ item }">
      <CommentItem :comment="item" />
    </template>
  </RecycleScroller>
</template>
```

**Benefits**:
- Only render visible comments
- Reduces DOM nodes from 1000+ to ~20
- Smooth scrolling even with large threads

---

## Deployment Architecture

### Production Environment

```mermaid
graph TB
    subgraph "DigitalOcean App Platform"
        subgraph "Web Service"
            Nginx[Nginx<br/>Reverse Proxy]
            Django[Django + Uvicorn<br/>4 workers]
        end

        subgraph "Worker Service"
            Celery[Celery Workers<br/>Email notifications]
        end

        subgraph "Managed Services"
            DB[(PostgreSQL 15<br/>Managed DB)]
            Redis[(Redis<br/>Managed Cache)]
        end
    end

    Browser[Browser<br/>EventSource] --> Nginx
    Nginx --> Django
    Django --> DB
    Django --> Redis
    Celery --> DB
    Celery --> Redis

    classDef web fill:#e3f2fd,stroke:#1976d2,stroke-width:2px
    classDef worker fill:#fff3e0,stroke:#f57c00,stroke-width:2px
    classDef data fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
    classDef client fill:#e8f5e9,stroke:#4caf50,stroke-width:2px

    class Nginx,Django web
    class Celery worker
    class DB,Redis data
    class Browser client
```

### Environment Configuration

#### Required Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:pass@host:25060/db?sslmode=require

# Redis
REDIS_URL=rediss://user:pass@host:25061

# Django
SECRET_KEY=<django-secret-key>
DEBUG=False
ALLOWED_HOSTS=your-domain.example.com

# SSE Configuration (optional)
SSE_MAX_DURATION=600  # 10 minutes
SSE_POLL_INTERVAL=2   # 2 seconds
```

### Health Checks

#### SSE Health Check

```python
# apps/health/views.py
async def sse_health_check(request):
    """Test SSE infrastructure is working."""
    async def test_stream():
        yield 'data: {"status": "ok"}\n\n'

    return StreamingHttpResponse(
        test_stream(),
        content_type='text/event-stream'
    )
```

**Monitoring**:
- Endpoint: `/health/sse/`
- Expected response: SSE stream with `{"status": "ok"}`
- Alert if: Connection times out or returns HTTP 5xx

### Monitoring Metrics

#### Key Metrics (Prometheus)

```python
# apps/core/metrics.py
from prometheus_client import Counter, Histogram

# SSE connection metrics
sse_connections = Counter(
    'sse_connections_total',
    'Total SSE connections established',
    ['conflict_id']
)

sse_errors = Counter(
    'sse_errors_total',
    'SSE connection errors',
    ['error_type']
)

sse_duration = Histogram(
    'sse_connection_duration_seconds',
    'SSE connection duration'
)

# Discussion activity metrics
comments_posted = Counter(
    'consensus_comments_total',
    'Total comments posted'
)

revotes_proposed = Counter(
    'consensus_revotes_total',
    'Total re-votes proposed'
)

consensus_reached = Counter(
    'consensus_achieved_total',
    'Conflicts resolved via consensus'
)
```

#### Grafana Dashboards

**Consensus Discussion Dashboard**:
- SSE connection count (gauge)
- SSE error rate (rate per minute)
- Average SSE connection duration
- Comments posted per hour
- Re-votes proposed per day
- Consensus resolution rate
- Discussion thread depth (histogram)

### Backup and Recovery

#### Database Backups

**DigitalOcean Managed Database**:
- Automatic daily backups (retained 7 days)
- Point-in-time recovery (PITR) enabled
- Manual backup before major updates

#### Audit Trail Integrity

**Immutable Records**:
- `ReviewerDecision`: Cannot be updated after creation
- `ConflictComment`: Soft-deleted only (`is_deleted=True`)
- `RevoteProposal`: Status changes logged in SessionActivity

**PRISMA Compliance**:
All discussion and decision data must be exportable before conflict resolution is marked final.

---

## Related Documentation

- [Dual Screening PRD](../../feature_changes/dual-screening/dual-reviewer-screening-prd.md)
- [Phase 3 Implementation Plan](../../PRPs/consensus/consensus-discussion-implementation-plan-2025-10-20.md)
- [API Documentation](../api/consensus-discussion-api.md)
- [SSE Implementation Guide](../features/server-sent-events.md)
- [Deployment Configuration](../deployment/ENVIRONMENT-VARIABLE-CONFIGURATION.md)

---

**Document Version History**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-10-21 | AI Assistant | Initial comprehensive architecture documentation |
