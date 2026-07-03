# Consensus Discussion API Schemas

**Phase**: Phase 2 - Serializers
**Date**: 2025-10-20
**Version**: 1.0

This document provides JSON schema specifications for the Consensus Discussion feature API endpoints. All endpoints return JSON responses and accept JSON request bodies where applicable.

---

## Table of Contents

1. [ConflictCommentSerializer (Read)](#conflictcommentserializer-read)
2. [ConflictCommentCreateSerializer (Write)](#conflictcommentcreateserializer-write)
3. [RevoteProposalSerializer (Read)](#revoteproposalserializer-read)
4. [ReviewerDecisionCreateSerializer (Write)](#reviewerdecisioncreateserializer-write)
5. [ConflictResolutionDetailSerializer (Read)](#conflictresolutiondetailserializer-read)
6. [Error Response Format](#error-response-format)

---

## ConflictCommentSerializer (Read)

**Purpose**: Displays conflict comments with threaded replies.

**Use Cases**:
- Fetching comment threads for a conflict
- Displaying nested comment discussions
- Showing comment metadata (edited, system messages)

### Response Schema

```json
{
  "id": "uuid",
  "conflict": "uuid",
  "author": {
    "id": "uuid",
    "username": "string",
    "email": "string",
    "first_name": "string",
    "last_name": "string"
  },
  "parent": "uuid | null",
  "content": "string",
  "content_html": "string",
  "created_at": "ISO 8601 timestamp",
  "updated_at": "ISO 8601 timestamp",
  "is_edited": "boolean",
  "edited_at": "ISO 8601 timestamp | null",
  "is_deleted": "boolean",
  "is_system_message": "boolean",
  "replies": [
    {
      // Recursive ConflictComment objects
    }
  ]
}
```

### Example Response

```json
{
  "id": "a1b2c3d4-e5f6-4789-a1b2-c3d4e5f67890",
  "conflict": "f1e2d3c4-b5a6-4987-f1e2-d3c4b5a69876",
  "author": {
    "id": "12345678-1234-1234-1234-123456789012",
    "username": "reviewer1",
    "email": "reviewer1@example.com",
    "first_name": "John",
    "last_name": "Doe"
  },
  "parent": null,
  "content": "**I think** we should include this result based on the research focus.",
  "content_html": "<p><strong>I think</strong> we should include this result based on the research focus.</p>",
  "created_at": "2025-10-20T14:30:00Z",
  "updated_at": "2025-10-20T14:30:00Z",
  "is_edited": false,
  "edited_at": null,
  "is_deleted": false,
  "is_system_message": false,
  "replies": [
    {
      "id": "b2c3d4e5-f6a7-4890-b2c3-d4e5f6a78901",
      "conflict": "f1e2d3c4-b5a6-4987-f1e2-d3c4b5a69876",
      "author": {
        "id": "87654321-4321-4321-4321-876543210987",
        "username": "reviewer2",
        "email": "reviewer2@example.com",
        "first_name": "Jane",
        "last_name": "Smith"
      },
      "parent": "a1b2c3d4-e5f6-4789-a1b2-c3d4e5f67890",
      "content": "I disagree - the methodology is flawed.",
      "content_html": "<p>I disagree - the methodology is flawed.</p>",
      "created_at": "2025-10-20T14:35:00Z",
      "updated_at": "2025-10-20T14:35:00Z",
      "is_edited": false,
      "edited_at": null,
      "is_deleted": false,
      "is_system_message": false,
      "replies": []
    }
  ]
}
```

### Field Descriptions

| Field | Type | Description | Notes |
|-------|------|-------------|-------|
| `id` | UUID | Unique comment identifier | Read-only |
| `conflict` | UUID | Associated conflict ID | Read-only |
| `author` | Object | Nested user object | `null` for system messages |
| `parent` | UUID | Parent comment ID for threading | `null` for top-level comments |
| `content` | String | Original markdown content | Read-only |
| `content_html` | String | Rendered HTML from markdown | Auto-generated |
| `created_at` | DateTime | Comment creation timestamp | ISO 8601 format |
| `updated_at` | DateTime | Last update timestamp | ISO 8601 format |
| `is_edited` | Boolean | Whether comment was edited | Read-only |
| `edited_at` | DateTime | Edit timestamp | `null` if not edited |
| `is_deleted` | Boolean | Soft delete flag | Hidden from UI when `true` |
| `is_system_message` | Boolean | System-generated message flag | No author when `true` |
| `replies` | Array | Nested child comments | Recursive structure, excludes deleted |

---

## ConflictCommentCreateSerializer (Write)

**Purpose**: Creates new conflict comments.

**Use Cases**:
- Posting new comments
- Replying to existing comments
- Threaded discussions

### Request Schema

```json
{
  "content": "string (required, 1-5000 chars)",
  "parent_id": "uuid (optional)"
}
```

### Request Example

**Top-level comment:**
```json
{
  "content": "I believe this result should be **included** based on our criteria."
}
```

**Reply to existing comment:**
```json
{
  "content": "Could you clarify which specific criterion supports inclusion?",
  "parent_id": "a1b2c3d4-e5f6-4789-a1b2-c3d4e5f67890"
}
```

### Response

Returns the created `ConflictComment` object (see [ConflictCommentSerializer](#conflictcommentserializer-read)).

### Validation Rules

| Field | Rule | Error Message |
|-------|------|---------------|
| `content` | Required, min 1 char, max 5000 chars | "Comment content cannot be empty." |
| `content` | No whitespace-only content | "Comment content cannot be empty." |
| `parent_id` | Must exist in database | "Parent comment does not exist." |
| `parent_id` | Must belong to same conflict | "Parent comment must belong to the same conflict." |

### Error Response Examples

**Empty content:**
```json
{
  "content": ["Comment content cannot be empty."]
}
```

**Invalid parent:**
```json
{
  "parent_id": ["Parent comment does not exist."]
}
```

---

## RevoteProposalSerializer (Read)

**Purpose**: Displays re-vote proposals with acceptance tracking.

**Use Cases**:
- Showing active re-vote proposals
- Tracking proposal acceptance status
- Displaying proposal history

### Response Schema

```json
{
  "id": "uuid",
  "conflict": "uuid",
  "proposed_by": {
    "id": "uuid",
    "username": "string",
    "email": "string",
    "first_name": "string",
    "last_name": "string"
  },
  "proposed_at": "ISO 8601 timestamp",
  "rationale": "string",
  "status": "string",
  "status_display": "string",
  "accepted_by": [
    {
      "id": "uuid",
      "username": "string",
      "email": "string",
      "first_name": "string",
      "last_name": "string"
    }
  ],
  "accepted_at": "ISO 8601 timestamp | null",
  "completed_at": "ISO 8601 timestamp | null",
  "resulted_in_consensus": "boolean",
  "expires_at": "ISO 8601 timestamp",
  "is_expired": "boolean"
}
```

### Example Response

**Proposed (pending acceptance):**
```json
{
  "id": "c1d2e3f4-a5b6-4789-c1d2-e3f4a5b67890",
  "conflict": "f1e2d3c4-b5a6-4987-f1e2-d3c4b5a69876",
  "proposed_by": {
    "id": "12345678-1234-1234-1234-123456789012",
    "username": "reviewer1",
    "email": "reviewer1@example.com",
    "first_name": "John",
    "last_name": "Doe"
  },
  "proposed_at": "2025-10-20T15:00:00Z",
  "rationale": "After further discussion, I think we should re-vote with clearer criteria.",
  "status": "PROPOSED",
  "status_display": "Proposed",
  "accepted_by": [
    {
      "id": "12345678-1234-1234-1234-123456789012",
      "username": "reviewer1",
      "email": "reviewer1@example.com",
      "first_name": "John",
      "last_name": "Doe"
    }
  ],
  "accepted_at": null,
  "completed_at": null,
  "resulted_in_consensus": false,
  "expires_at": "2025-10-22T15:00:00Z",
  "is_expired": false
}
```

**Completed (consensus reached):**
```json
{
  "id": "d2e3f4a5-b6c7-4890-d2e3-f4a5b6c78901",
  "conflict": "f1e2d3c4-b5a6-4987-f1e2-d3c4b5a69876",
  "proposed_by": {
    "id": "12345678-1234-1234-1234-123456789012",
    "username": "reviewer1",
    "email": "reviewer1@example.com",
    "first_name": "John",
    "last_name": "Doe"
  },
  "proposed_at": "2025-10-19T10:00:00Z",
  "rationale": "Let's re-evaluate based on the full document.",
  "status": "COMPLETED",
  "status_display": "Completed",
  "accepted_by": [
    {
      "id": "12345678-1234-1234-1234-123456789012",
      "username": "reviewer1",
      "email": "reviewer1@example.com",
      "first_name": "John",
      "last_name": "Doe"
    },
    {
      "id": "87654321-4321-4321-4321-876543210987",
      "username": "reviewer2",
      "email": "reviewer2@example.com",
      "first_name": "Jane",
      "last_name": "Smith"
    }
  ],
  "accepted_at": "2025-10-19T11:00:00Z",
  "completed_at": "2025-10-19T14:30:00Z",
  "resulted_in_consensus": true,
  "expires_at": "2025-10-21T10:00:00Z",
  "is_expired": false
}
```

### Field Descriptions

| Field | Type | Description | Notes |
|-------|------|-------------|-------|
| `id` | UUID | Unique proposal identifier | Read-only |
| `conflict` | UUID | Associated conflict ID | Read-only |
| `proposed_by` | Object | User who proposed re-vote | Nested user object |
| `proposed_at` | DateTime | Proposal creation timestamp | ISO 8601 format |
| `rationale` | String | Reason for proposing re-vote | Required |
| `status` | String | Current status | `PROPOSED`, `ACCEPTED`, `IN_PROGRESS`, `COMPLETED`, `EXPIRED` |
| `status_display` | String | Human-readable status | "Proposed", "Accepted", etc. |
| `accepted_by` | Array | Users who accepted | Empty array if none accepted |
| `accepted_at` | DateTime | When all reviewers accepted | `null` if not yet accepted |
| `completed_at` | DateTime | When re-vote completed | `null` if not completed |
| `resulted_in_consensus` | Boolean | Whether re-vote achieved consensus | `false` until completed |
| `expires_at` | DateTime | Expiry timestamp | Proposals expire after 48 hours |
| `is_expired` | Boolean | Computed expiry status | `true` if past expiry and still PROPOSED |

---

## ReviewerDecisionCreateSerializer (Write)

**Purpose**: Submits re-vote decisions.

**Use Cases**:
- Submitting new decision during re-vote
- Recording decision rationale

### Request Schema

```json
{
  "decision": "string (required: INCLUDE | EXCLUDE | MAYBE)",
  "exclusion_reason": "string (required if decision=EXCLUDE, max 100 chars)",
  "notes": "string (optional, max 1000 chars)"
}
```

### Request Examples

**Include decision:**
```json
{
  "decision": "INCLUDE",
  "notes": "After reviewing the full document, I now believe this meets our inclusion criteria."
}
```

**Exclude decision:**
```json
{
  "decision": "EXCLUDE",
  "exclusion_reason": "Methodology flawed",
  "notes": "The study does not use a validated assessment tool as required by our protocol."
}
```

**Maybe decision:**
```json
{
  "decision": "MAYBE",
  "notes": "Need to consult with senior reviewer before making final decision."
}
```

### Response

Returns HTTP 201 with created decision details.

### Validation Rules

| Field | Rule | Error Message |
|-------|------|---------------|
| `decision` | Required, must be INCLUDE/EXCLUDE/MAYBE | "This field is required." |
| `exclusion_reason` | Required if `decision=EXCLUDE` | "This field is required when decision is EXCLUDE." |
| `exclusion_reason` | Must NOT be set for INCLUDE/MAYBE | "This field should only be set when decision is EXCLUDE." |
| `exclusion_reason` | Max 100 characters | "Ensure this field has no more than 100 characters." |
| `notes` | Max 1000 characters | "Ensure this field has no more than 1000 characters." |

### Error Response Examples

**EXCLUDE without reason:**
```json
{
  "exclusion_reason": ["This field is required when decision is EXCLUDE."]
}
```

**INCLUDE with reason:**
```json
{
  "exclusion_reason": ["This field should only be set when decision is EXCLUDE."]
}
```

---

## ConflictResolutionDetailSerializer (Read)

**Purpose**: Provides complete conflict resolution data including discussion summary.

**Use Cases**:
- Conflict detail page data
- Displaying full conflict context
- Tracking discussion activity

### Response Schema

```json
{
  "id": "uuid",
  "result": {
    // ProcessedResult object (nested)
  },
  "conflicting_decisions": [
    {
      // ReviewerDecision objects (minimal)
    }
  ],
  "conflict_type": "string",
  "conflict_type_display": "string",
  "status": "string",
  "status_display": "string",
  "detected_at": "ISO 8601 timestamp",
  "resolution_method": "string | null",
  "resolution_method_display": "string | null",
  "final_decision": {
    // ReviewerDecision object (full) | null
  },
  "resolved_at": "ISO 8601 timestamp | null",
  "resolved_by": {
    // User object | null
  },
  "resolution_notes": "string | null",
  "discussion_summary": {
    "comment_count": "integer",
    "participant_count": "integer",
    "revote_count": "integer",
    "last_activity": "ISO 8601 timestamp | null"
  },
  "active_revote_proposal": {
    // RevoteProposal object | null
  }
}
```

### Example Response

```json
{
  "id": "f1e2d3c4-b5a6-4987-f1e2-d3c4b5a69876",
  "result": {
    "id": "e1f2a3b4-c5d6-4789-e1f2-a3b4c5d67890",
    "title": "Clinical Practice Guidelines for Diabetes Management",
    "snippet": "This guideline provides evidence-based recommendations...",
    "url": "https://example.org/guidelines/diabetes-2024.pdf"
  },
  "conflicting_decisions": [
    {
      "id": "d1e2f3a4-b5c6-4789-d1e2-f3a4b5c67890",
      "reviewer": {
        "id": "12345678-1234-1234-1234-123456789012",
        "username": "reviewer1",
        "email": "reviewer1@example.com",
        "first_name": "John",
        "last_name": "Doe"
      },
      "decision": "INCLUDE",
      "exclusion_reason": "",
      "confidence_level": 3,
      "decided_at": "2025-10-20T10:00:00Z"
    },
    {
      "id": "e2f3a4b5-c6d7-4890-e2f3-a4b5c6d78901",
      "reviewer": {
        "id": "87654321-4321-4321-4321-876543210987",
        "username": "reviewer2",
        "email": "reviewer2@example.com",
        "first_name": "Jane",
        "last_name": "Smith"
      },
      "decision": "EXCLUDE",
      "exclusion_reason": "Not a guideline",
      "confidence_level": 2,
      "decided_at": "2025-10-20T10:15:00Z"
    }
  ],
  "conflict_type": "INCLUDE_EXCLUDE",
  "conflict_type_display": "Include vs Exclude",
  "status": "PENDING",
  "status_display": "Pending",
  "detected_at": "2025-10-20T10:15:00Z",
  "resolution_method": null,
  "resolution_method_display": null,
  "final_decision": null,
  "resolved_at": null,
  "resolved_by": null,
  "resolution_notes": null,
  "discussion_summary": {
    "comment_count": 5,
    "participant_count": 2,
    "revote_count": 1,
    "last_activity": "2025-10-20T15:45:00Z"
  },
  "active_revote_proposal": {
    "id": "c1d2e3f4-a5b6-4789-c1d2-e3f4a5b67890",
    "conflict": "f1e2d3c4-b5a6-4987-f1e2-d3c4b5a69876",
    "proposed_by": {
      "id": "12345678-1234-1234-1234-123456789012",
      "username": "reviewer1",
      "email": "reviewer1@example.com",
      "first_name": "John",
      "last_name": "Doe"
    },
    "proposed_at": "2025-10-20T15:00:00Z",
    "rationale": "After discussion, let's re-evaluate with clearer criteria.",
    "status": "PROPOSED",
    "status_display": "Proposed",
    "accepted_by": [
      {
        "id": "12345678-1234-1234-1234-123456789012",
        "username": "reviewer1",
        "email": "reviewer1@example.com",
        "first_name": "John",
        "last_name": "Doe"
      }
    ],
    "accepted_at": null,
    "completed_at": null,
    "resulted_in_consensus": false,
    "expires_at": "2025-10-22T15:00:00Z",
    "is_expired": false
  }
}
```

### Field Descriptions (New in Phase 2)

| Field | Type | Description | Notes |
|-------|------|-------------|-------|
| `discussion_summary` | Object | Discussion activity summary | Computed field |
| `discussion_summary.comment_count` | Integer | Number of active comments | Excludes deleted |
| `discussion_summary.participant_count` | Integer | Unique comment authors | Distinct count |
| `discussion_summary.revote_count` | Integer | Number of re-vote proposals | All statuses |
| `discussion_summary.last_activity` | DateTime | Most recent comment timestamp | `null` if no comments |
| `active_revote_proposal` | Object | Currently active re-vote proposal | `null` if none active |

---

## Error Response Format

All API endpoints return errors in a consistent format:

### Validation Error (HTTP 400)

```json
{
  "field_name": ["Error message 1", "Error message 2"]
}
```

Example:
```json
{
  "content": ["Comment content cannot be empty."],
  "parent_id": ["Parent comment does not exist."]
}
```

### Not Found (HTTP 404)

```json
{
  "detail": "Not found."
}
```

### Unauthorized (HTTP 401)

```json
{
  "detail": "Authentication credentials were not provided."
}
```

### Forbidden (HTTP 403)

```json
{
  "detail": "You do not have permission to perform this action."
}
```

### Server Error (HTTP 500)

```json
{
  "detail": "A server error occurred."
}
```

---

## Common Patterns

### Nested User Object

All user references use the `SimpleUserSerializer`:

```typescript
interface User {
  id: string;           // UUID
  username: string;
  email: string;
  first_name: string;
  last_name: string;
}
```

### Timestamp Format

All timestamps use ISO 8601 format with UTC timezone:

```
2025-10-20T14:30:00Z
```

### UUID Format

All IDs are UUIDs in string format:

```
"a1b2c3d4-e5f6-4789-a1b2-c3d4e5f67890"
```

---

## TypeScript Type Definitions (Optional)

```typescript
// ConflictComment (read)
interface ConflictComment {
  id: string;
  conflict: string;
  author: User | null;
  parent: string | null;
  content: string;
  content_html: string;
  created_at: string;
  updated_at: string;
  is_edited: boolean;
  edited_at: string | null;
  is_deleted: boolean;
  is_system_message: boolean;
  replies: ConflictComment[];
}

// ConflictCommentCreate (write)
interface ConflictCommentCreate {
  content: string;
  parent_id?: string;
}

// RevoteProposal (read)
interface RevoteProposal {
  id: string;
  conflict: string;
  proposed_by: User;
  proposed_at: string;
  rationale: string;
  status: 'PROPOSED' | 'ACCEPTED' | 'IN_PROGRESS' | 'COMPLETED' | 'EXPIRED';
  status_display: string;
  accepted_by: User[];
  accepted_at: string | null;
  completed_at: string | null;
  resulted_in_consensus: boolean;
  expires_at: string;
  is_expired: boolean;
}

// ReviewerDecisionCreate (write)
interface ReviewerDecisionCreate {
  decision: 'INCLUDE' | 'EXCLUDE' | 'MAYBE';
  exclusion_reason?: string;
  notes?: string;
}

// DiscussionSummary (computed)
interface DiscussionSummary {
  comment_count: number;
  participant_count: number;
  revote_count: number;
  last_activity: string | null;
}

// ConflictResolutionDetail (read)
interface ConflictResolutionDetail {
  id: string;
  result: ProcessedResult;
  conflicting_decisions: ReviewerDecision[];
  conflict_type: string;
  conflict_type_display: string;
  status: string;
  status_display: string;
  detected_at: string;
  resolution_method: string | null;
  resolution_method_display: string | null;
  final_decision: ReviewerDecision | null;
  resolved_at: string | null;
  resolved_by: User | null;
  resolution_notes: string | null;
  discussion_summary: DiscussionSummary;
  active_revote_proposal: RevoteProposal | null;
}
```

---

## Notes for Frontend Developers

1. **Recursive Comments**: The `ConflictCommentSerializer` supports infinite nesting. Ensure your UI component can handle recursive rendering of `replies`.

2. **Markdown Rendering**: The backend provides both `content` (original markdown) and `content_html` (rendered HTML). Use `content_html` for display and `content` for editing.

3. **Soft Deletes**: Deleted comments have `is_deleted=true` but are still returned in the API. Filter them out in the UI or use the `replies` field which already excludes deleted comments.

4. **Expiry Checking**: Use the `is_expired` computed field instead of comparing `expires_at` client-side to avoid timezone issues.

5. **Validation**: Always handle validation errors from write endpoints. The error format is consistent across all endpoints.

6. **Optimistic Updates**: When posting comments or proposals, update the UI optimistically and rollback on error for better UX.

7. **Real-time Updates**: Integrate with SSE (Server-Sent Events) to receive real-time notifications when:
   - New comments are posted
   - Re-vote proposals are created/accepted
   - Conflicts are resolved

---

**End of Documentation**

For questions or issues, contact the backend development team or refer to the source code in `apps/review_results/serializers.py`.
