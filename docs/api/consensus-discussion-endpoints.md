# Consensus Discussion API Documentation

**Version:** 1.0
**Last Updated:** 21 October 2025
**Base URL:** `/api/conflicts/`

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [Common Response Patterns](#common-response-patterns)
4. [Endpoints](#endpoints)
   - [GET /api/conflicts/{conflict_id}/details/](#get-conflict-details)
   - [POST /api/conflicts/{conflict_id}/comments/](#post-comment)
   - [POST /api/conflicts/{conflict_id}/propose-revote/](#propose-revote)
   - [POST /api/conflicts/{conflict_id}/proposals/{proposal_id}/accept/](#accept-revote-proposal)
   - [POST /api/conflicts/{conflict_id}/proposals/{proposal_id}/submit-decision/](#submit-revote-decision)
   - [GET /api/conflicts/{conflict_id}/stream/](#sse-stream)
5. [Data Models](#data-models)
6. [Error Handling](#error-handling)
7. [Rate Limiting](#rate-limiting)
8. [Examples](#examples)

---

## Overview

The Consensus Discussion API enables reviewers to resolve conflicts that arise during dual screening of systematic review results. The API supports:

- Viewing conflict details and discussion history
- Posting comments and threaded replies
- Proposing and accepting re-votes
- Submitting re-vote decisions
- Real-time updates via Server-Sent Events (SSE)

All endpoints follow RESTful conventions and return JSON responses (except SSE which returns `text/event-stream`).

---

## Authentication

### Required Authentication

All endpoints require authentication via:
- **Session Authentication**: Django session cookie (for browser requests)
- **Token Authentication**: Bearer token (for API clients) - if configured

Include the CSRF token in POST requests:
- **Header**: `X-CSRFToken: <token>`
- **Cookie**: `csrftoken`

### Permission Requirements

Most endpoints require the user to be:
1. **Conflicting Reviewer**: One of the reviewers whose decisions created the conflict
2. **Administrator**: Session manager or organisation administrator

Specific permissions are documented for each endpoint.

---

## Common Response Patterns

### Success Response

```json
{
  "data": { /* response data */ },
  "status": "success"
}
```

### Error Response

```json
{
  "error": "error_code",
  "message": "Human-readable error message",
  "errors": { /* validation errors if applicable */ }
}
```

### HTTP Status Codes

- **200 OK**: Request successful
- **201 Created**: Resource created successfully
- **400 Bad Request**: Validation error or invalid request
- **403 Forbidden**: Permission denied
- **404 Not Found**: Resource not found
- **500 Internal Server Error**: Server error

---

## Endpoints

### GET Conflict Details

Retrieve full conflict data including result details, conflicting decisions, comments, and active re-vote proposal.

#### Endpoint

```
GET /api/conflicts/{conflict_id}/details/
```

#### URL Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conflict_id` | UUID | Yes | The unique identifier of the conflict |

#### Permissions

- User must be a conflicting reviewer OR administrator

#### Response (200 OK)

```json
{
  "conflict": {
    "id": "uuid",
    "result": {
      "id": "uuid",
      "title": "Search result title",
      "snippet": "Brief excerpt from the result...",
      "url": "https://example.com/document.pdf",
      "organisation": "Organisation name",
      "result_type": "POLICY_DOCUMENT",
      "identified_date": "2025-10-15T10:30:00Z"
    },
    "conflict_type": "INCLUDE_EXCLUDE",
    "status": "PENDING",
    "detected_at": "2025-10-15T14:20:00Z",
    "resolved_at": null,
    "resolution_method": null,
    "final_decision": null
  },
  "conflicting_decisions": [
    {
      "id": "uuid",
      "reviewer": {
        "id": "uuid",
        "username": "reviewer1",
        "email": "reviewer1@example.com"
      },
      "decision": "INCLUDE",
      "confidence_level": 3,
      "notes": "This document meets criteria A and B...",
      "exclusion_reason": "",
      "created_at": "2025-10-15T12:00:00Z",
      "is_revote": false
    },
    {
      "id": "uuid",
      "reviewer": {
        "id": "uuid",
        "username": "reviewer2",
        "email": "reviewer2@example.com"
      },
      "decision": "EXCLUDE",
      "confidence_level": 2,
      "notes": "Does not meet criterion C...",
      "exclusion_reason": "OUT_OF_SCOPE",
      "created_at": "2025-10-15T12:15:00Z",
      "is_revote": false
    }
  ],
  "comments": [
    {
      "id": "uuid",
      "author": {
        "id": "uuid",
        "username": "reviewer1",
        "email": "reviewer1@example.com"
      },
      "content": "I believe this document is highly relevant because...",
      "parent": null,
      "created_at": "2025-10-15T14:30:00Z",
      "is_system_message": false,
      "replies": [
        {
          "id": "uuid",
          "author": {
            "id": "uuid",
            "username": "reviewer2",
            "email": "reviewer2@example.com"
          },
          "content": "I understand your point, but...",
          "parent": "parent_comment_uuid",
          "created_at": "2025-10-15T15:00:00Z",
          "is_system_message": false,
          "replies": []
        }
      ]
    }
  ],
  "active_revote_proposal": {
    "id": "uuid",
    "proposed_by": {
      "id": "uuid",
      "username": "reviewer1",
      "email": "reviewer1@example.com"
    },
    "rationale": "After discussion, I think we should re-evaluate...",
    "status": "PROPOSED",
    "proposed_at": "2025-10-16T10:00:00Z",
    "accepted_at": null,
    "completed_at": null,
    "expires_at": "2025-10-18T10:00:00Z",
    "accepted_by_ids": ["reviewer1_uuid"],
    "all_reviewers_accepted": false,
    "resulted_in_consensus": null
  },
  "permissions": {
    "can_comment": true,
    "can_propose_revote": true,
    "can_accept_revote": false,
    "can_resolve": false
  }
}
```

#### Error Responses

**403 Forbidden**
```json
{
  "error": "permission_denied",
  "message": "Only conflicting reviewers or administrators can view conflict discussions"
}
```

**404 Not Found**
```json
{
  "error": "not_found",
  "message": "Conflict not found"
}
```

#### Example (cURL)

```bash
curl -X GET \
  -H "Cookie: sessionid=<session_id>" \
  https://api.example.com/api/conflicts/550e8400-e29b-41d4-a716-446655440000/details/
```

#### Example (JavaScript)

```javascript
const response = await fetch('/api/conflicts/550e8400-e29b-41d4-a716-446655440000/details/', {
  method: 'GET',
  headers: {
    'Accept': 'application/json',
  },
  credentials: 'include', // Include cookies
});

const data = await response.json();
console.log('Conflict details:', data);
```

---

### POST Comment

Post a new comment or reply to the conflict discussion.

#### Endpoint

```
POST /api/conflicts/{conflict_id}/comments/
```

#### URL Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conflict_id` | UUID | Yes | The unique identifier of the conflict |

#### Request Body

```json
{
  "content": "Your comment text here. Markdown is supported.",
  "parent_id": "parent_comment_uuid or null"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `content` | string | Yes | Comment content (max 5000 characters, markdown supported) |
| `parent_id` | UUID or null | No | Parent comment ID for threaded replies (null for top-level comment) |

#### Permissions

- User must be a conflicting reviewer OR administrator

#### Response (201 Created)

```json
{
  "id": "comment_uuid",
  "author": {
    "id": "user_uuid",
    "username": "reviewer1",
    "email": "reviewer1@example.com"
  },
  "content": "Your comment text here. Markdown is supported.",
  "parent": null,
  "created_at": "2025-10-15T14:30:00Z",
  "is_system_message": false,
  "replies": []
}
```

#### Side Effects

1. Conflict status changes from `PENDING` to `IN_DISCUSSION` (if currently PENDING)
2. Email notification sent to other reviewers
3. SessionActivity record created for audit trail
4. SSE event broadcast to connected clients

#### Error Responses

**400 Bad Request**
```json
{
  "error": "validation_error",
  "errors": {
    "content": ["This field is required."]
  }
}
```

**403 Forbidden**
```json
{
  "error": "permission_denied",
  "message": "Only conflicting reviewers or administrators can add discussion comments"
}
```

**404 Not Found**
```json
{
  "error": "not_found",
  "message": "Conflict not found"
}
```

#### Example (cURL)

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: <csrf_token>" \
  -H "Cookie: sessionid=<session_id>" \
  -d '{"content":"I think we should reconsider because...","parent_id":null}' \
  https://api.example.com/api/conflicts/550e8400-e29b-41d4-a716-446655440000/comments/
```

#### Example (JavaScript)

```javascript
const response = await fetch('/api/conflicts/550e8400-e29b-41d4-a716-446655440000/comments/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRFToken': getCsrfToken(),
  },
  credentials: 'include',
  body: JSON.stringify({
    content: 'I think we should reconsider because...',
    parent_id: null
  })
});

const comment = await response.json();
console.log('Posted comment:', comment);
```

---

### Propose Re-Vote

Create a re-vote proposal to allow reviewers to reconsider their decisions.

#### Endpoint

```
POST /api/conflicts/{conflict_id}/propose-revote/
```

#### URL Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conflict_id` | UUID | Yes | The unique identifier of the conflict |

#### Request Body

```json
{
  "rationale": "After our discussion, I believe we should re-evaluate this result because..."
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `rationale` | string | Yes | Explanation for why a re-vote is needed (max 2000 characters) |

#### Permissions

- User must be a conflicting reviewer
- Conflict must not already be resolved
- No active re-vote proposal can exist

#### Response (201 Created)

```json
{
  "id": "proposal_uuid",
  "proposed_by": {
    "id": "user_uuid",
    "username": "reviewer1",
    "email": "reviewer1@example.com"
  },
  "rationale": "After our discussion, I believe we should re-evaluate this result because...",
  "status": "PROPOSED",
  "proposed_at": "2025-10-16T10:00:00Z",
  "accepted_at": null,
  "completed_at": null,
  "expires_at": "2025-10-18T10:00:00Z",
  "accepted_by_ids": ["reviewer1_uuid"],
  "all_reviewers_accepted": false,
  "resulted_in_consensus": null
}
```

#### Side Effects

1. RevoteProposal record created
2. Proposer automatically added to `accepted_by` list
3. Conflict status changes to `ESCALATED`
4. System message posted to discussion
5. Email notifications sent to other reviewers
6. SessionActivity record created
7. SSE event broadcast

#### Proposal Expiry

- Proposals expire 48 hours after creation if not accepted by all reviewers
- Expired proposals cannot be accepted

#### Error Responses

**400 Bad Request**
```json
{
  "error": "proposal_not_allowed",
  "message": "Cannot propose re-vote: either not a conflicting reviewer, active proposal exists, or conflict already resolved"
}
```

**400 Bad Request** (Missing rationale)
```json
{
  "error": "validation_error",
  "message": "Rationale is required"
}
```

#### Example (cURL)

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: <csrf_token>" \
  -H "Cookie: sessionid=<session_id>" \
  -d '{"rationale":"After discussion I have reconsidered my position..."}' \
  https://api.example.com/api/conflicts/550e8400-e29b-41d4-a716-446655440000/propose-revote/
```

#### Example (JavaScript)

```javascript
const response = await fetch('/api/conflicts/550e8400-e29b-41d4-a716-446655440000/propose-revote/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRFToken': getCsrfToken(),
  },
  credentials: 'include',
  body: JSON.stringify({
    rationale: 'After discussion I have reconsidered my position...'
  })
});

const proposal = await response.json();
console.log('Proposal created:', proposal);
```

---

### Accept Re-Vote Proposal

Accept a re-vote proposal, signalling willingness to reconsider your decision.

#### Endpoint

```
POST /api/conflicts/{conflict_id}/proposals/{proposal_id}/accept/
```

#### URL Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conflict_id` | UUID | Yes | The unique identifier of the conflict |
| `proposal_id` | UUID | Yes | The unique identifier of the re-vote proposal |

#### Request Body

No request body required (empty POST).

#### Permissions

- User must be a conflicting reviewer
- Proposal must be in `PROPOSED` status
- Proposal must not be expired
- User must not have already accepted

#### Response (200 OK)

```json
{
  "id": "proposal_uuid",
  "proposed_by": {
    "id": "user_uuid",
    "username": "reviewer1",
    "email": "reviewer1@example.com"
  },
  "rationale": "After our discussion, I believe we should re-evaluate this result because...",
  "status": "ACCEPTED",
  "proposed_at": "2025-10-16T10:00:00Z",
  "accepted_at": "2025-10-16T12:00:00Z",
  "completed_at": null,
  "expires_at": "2025-10-18T10:00:00Z",
  "accepted_by_ids": ["reviewer1_uuid", "reviewer2_uuid"],
  "all_reviewers_accepted": true,
  "resulted_in_consensus": null
}
```

#### Side Effects

1. User added to `accepted_by` list
2. If all reviewers accept:
   - Proposal status changes to `ACCEPTED`
   - `accepted_at` timestamp set
   - System message posted to discussion
   - Email notification sent to all reviewers
3. SessionActivity record created
4. SSE event broadcast

#### Error Responses

**400 Bad Request**
```json
{
  "error": "cannot_accept",
  "message": "Cannot accept: either not a conflicting reviewer, proposal not in PROPOSED status, or proposal expired"
}
```

**404 Not Found**
```json
{
  "error": "not_found",
  "message": "Conflict or proposal not found"
}
```

#### Example (cURL)

```bash
curl -X POST \
  -H "X-CSRFToken: <csrf_token>" \
  -H "Cookie: sessionid=<session_id>" \
  https://api.example.com/api/conflicts/550e8400-e29b-41d4-a716-446655440000/proposals/proposal-uuid/accept/
```

#### Example (JavaScript)

```javascript
const response = await fetch('/api/conflicts/550e8400-e29b-41d4-a716-446655440000/proposals/proposal-uuid/accept/', {
  method: 'POST',
  headers: {
    'X-CSRFToken': getCsrfToken(),
  },
  credentials: 'include',
});

const proposal = await response.json();
console.log('Proposal status:', proposal.status);
```

---

### Submit Re-Vote Decision

Submit a new decision as part of a re-vote.

#### Endpoint

```
POST /api/conflicts/{conflict_id}/proposals/{proposal_id}/submit-decision/
```

#### URL Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conflict_id` | UUID | Yes | The unique identifier of the conflict |
| `proposal_id` | UUID | Yes | The unique identifier of the re-vote proposal |

#### Request Body

```json
{
  "decision": "INCLUDE",
  "notes": "After reconsidering, I now believe this should be included because...",
  "exclusion_reason": "",
  "confidence_level": 3
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `decision` | string | Yes | Decision value: `INCLUDE`, `EXCLUDE`, or `MAYBE` |
| `notes` | string | No | Explanation for decision (max 2000 characters) |
| `exclusion_reason` | string | No | Reason code if decision is `EXCLUDE` |
| `confidence_level` | integer | No | Confidence level 0-3 (default: 2) |

#### Permissions

- User must be a conflicting reviewer
- Proposal must be in `ACCEPTED` or `IN_PROGRESS` status
- User must not have already submitted a re-vote decision for this proposal

#### Response (201 Created)

```json
{
  "message": "Re-vote decision submitted successfully",
  "consensus_reached": false
}
```

#### Side Effects

1. New ReviewerDecision record created with `is_revote=True`
2. Proposal status changes to `IN_PROGRESS` (if first vote)
3. SessionActivity record created
4. If all reviewers have voted:
   - Consensus check performed
   - If consensus: Conflict resolved, email sent, SSE event
   - If no consensus: Proposal marked complete, arbitration may be needed
5. SSE event broadcast

#### Consensus Detection

When all reviewers submit re-vote decisions:
- If all decisions are identical: **Consensus reached**
  - Conflict status → `RESOLVED`
  - Resolution method → `CONSENSUS`
  - System message posted
  - Email notification sent
- If decisions differ: **Arbitration needed**
  - Proposal marked complete but no consensus
  - Conflict remains PENDING or ESCALATED

#### Error Responses

**400 Bad Request** (Already voted)
```json
{
  "error": "already_voted",
  "message": "You have already submitted a re-vote decision for this proposal"
}
```

**400 Bad Request** (Proposal not accepted)
```json
{
  "error": "proposal_not_accepted",
  "message": "Cannot submit re-vote decision: proposal not yet accepted by all reviewers"
}
```

**403 Forbidden**
```json
{
  "error": "permission_denied",
  "message": "Only conflicting reviewers can submit re-vote decisions"
}
```

#### Example (cURL)

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: <csrf_token>" \
  -H "Cookie: sessionid=<session_id>" \
  -d '{"decision":"INCLUDE","notes":"After discussion I now believe this should be included","confidence_level":3}' \
  https://api.example.com/api/conflicts/550e8400-e29b-41d4-a716-446655440000/proposals/proposal-uuid/submit-decision/
```

#### Example (JavaScript)

```javascript
const response = await fetch('/api/conflicts/550e8400-e29b-41d4-a716-446655440000/proposals/proposal-uuid/submit-decision/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRFToken': getCsrfToken(),
  },
  credentials: 'include',
  body: JSON.stringify({
    decision: 'INCLUDE',
    notes: 'After discussion I now believe this should be included',
    confidence_level: 3
  })
});

const result = await response.json();
console.log('Consensus reached:', result.consensus_reached);
```

---

### SSE Stream

Server-Sent Events stream for real-time conflict discussion updates.

#### Endpoint

```
GET /api/conflicts/{conflict_id}/stream/
```

#### URL Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conflict_id` | UUID | Yes | The unique identifier of the conflict |

#### Authentication

- Login required (session cookie)
- CSRF exempt (EventSource API does not support CSRF tokens)

#### Permissions

- User must be a conflicting reviewer OR administrator

#### Response

**Content-Type:** `text/event-stream`

**Connection:** Keep-alive

#### Event Types

##### 1. Connected Event

Sent immediately upon connection.

```
data: {"type": "connected", "conflict_id": "550e8400-e29b-41d4-a716-446655440000"}

```

##### 2. New Comment Event

```
event: new_comment
data: {"comment": {"id": "comment_uuid", "author": {...}, "content": "...", "created_at": "..."}}

```

##### 3. Re-Vote Proposed Event

```
event: revote_proposed
data: {"proposal": {"id": "proposal_uuid", "proposed_by": {...}, "rationale": "...", "status": "PROPOSED"}}

```

##### 4. Re-Vote Accepted Event

```
event: revote_accepted
data: {"proposal": {"id": "proposal_uuid", "status": "ACCEPTED", "all_reviewers_accepted": true}}

```

##### 5. Re-Vote Decision Submitted Event

```
event: revote_decision_submitted
data: {"reviewer_id": "user_uuid", "decision": "INCLUDE"}

```

##### 6. Consensus Reached Event

```
event: consensus_reached
data: {"conflict_id": "conflict_uuid", "consensus_decision": "INCLUDE", "resolution_method": "CONSENSUS"}

```

#### Connection Management

- **Timeout**: 10 minutes (600 seconds)
- **Reconnection**: Client should reconnect automatically on disconnect
- **Error Handling**: Connection errors trigger client-side retry with exponential backoff

#### Nginx Configuration

SSE requires special Nginx configuration to disable buffering:

```nginx
location ~ ^/api/conflicts/.+/stream/$ {
    proxy_pass http://web:8000;
    proxy_set_header X-Accel-Buffering no;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 600s;
    chunked_transfer_encoding off;
}
```

#### Error Events

```
data: {"type": "error", "message": "Only conflicting reviewers or administrators can view conflict discussions"}

```

```
data: {"type": "timeout", "message": "Connection timeout - please refresh"}

```

#### Example (JavaScript EventSource)

```javascript
const eventSource = new EventSource('/api/conflicts/550e8400-e29b-41d4-a716-446655440000/stream/');

// Listen for new comments
eventSource.addEventListener('new_comment', (event) => {
  const data = JSON.parse(event.data);
  console.log('New comment:', data.comment);
  // Update UI with new comment
});

// Listen for re-vote proposals
eventSource.addEventListener('revote_proposed', (event) => {
  const data = JSON.parse(event.data);
  console.log('Re-vote proposed:', data.proposal);
  // Update UI with proposal
});

// Listen for consensus
eventSource.addEventListener('consensus_reached', (event) => {
  const data = JSON.parse(event.data);
  console.log('Consensus reached!', data.consensus_decision);
  // Show success message
});

// Handle connection errors
eventSource.onerror = (error) => {
  console.error('SSE connection error:', error);
  eventSource.close();
  // Implement reconnection logic
};

// Clean up on page unload
window.addEventListener('beforeunload', () => {
  eventSource.close();
});
```

---

## Data Models

### ConflictResolution

```typescript
interface ConflictResolution {
  id: string;  // UUID
  result: SearchResult;
  conflict_type: 'INCLUDE_EXCLUDE' | 'CONFIDENCE_LEVEL';
  status: 'PENDING' | 'IN_DISCUSSION' | 'ESCALATED' | 'RESOLVED';
  detected_at: string;  // ISO 8601 timestamp
  resolved_at: string | null;
  resolution_method: 'CONSENSUS' | 'ARBITRATION' | 'ADMINISTRATIVE' | null;
  final_decision: ReviewerDecision | null;
}
```

### SearchResult

```typescript
interface SearchResult {
  id: string;
  title: string;
  snippet: string;
  url: string;
  organisation: string;
  result_type: string;
  identified_date: string;
}
```

### ReviewerDecision

```typescript
interface ReviewerDecision {
  id: string;
  reviewer: User;
  decision: 'INCLUDE' | 'EXCLUDE' | 'MAYBE';
  confidence_level: 0 | 1 | 2 | 3;
  notes: string;
  exclusion_reason: string;
  created_at: string;
  is_revote: boolean;
  revote_proposal: string | null;  // UUID
}
```

### ConflictComment

```typescript
interface ConflictComment {
  id: string;
  author: User | null;  // null for system messages
  content: string;  // Markdown supported
  parent: string | null;  // UUID of parent comment
  created_at: string;
  is_system_message: boolean;
  replies: ConflictComment[];  // Nested replies
}
```

### RevoteProposal

```typescript
interface RevoteProposal {
  id: string;
  proposed_by: User;
  rationale: string;
  status: 'PROPOSED' | 'ACCEPTED' | 'IN_PROGRESS' | 'COMPLETED' | 'EXPIRED';
  proposed_at: string;
  accepted_at: string | null;
  completed_at: string | null;
  expires_at: string;
  accepted_by_ids: string[];  // Array of user UUIDs
  all_reviewers_accepted: boolean;
  resulted_in_consensus: boolean | null;
}
```

### User

```typescript
interface User {
  id: string;
  username: string;
  email: string;
}
```

---

## Error Handling

### Standard Error Response

```json
{
  "error": "error_code",
  "message": "Human-readable error message",
  "errors": {
    "field_name": ["Validation error message"]
  }
}
```

### Common Error Codes

| Error Code | HTTP Status | Description |
|------------|-------------|-------------|
| `no_organisation` | 400 | Organisation context missing |
| `validation_error` | 400 | Request validation failed |
| `proposal_not_allowed` | 400 | Re-vote proposal not allowed |
| `cannot_accept` | 400 | Cannot accept proposal |
| `already_voted` | 400 | User already submitted vote |
| `permission_denied` | 403 | User lacks required permissions |
| `not_found` | 404 | Resource not found |

### Error Handling Best Practices

1. **Always Check Status Code**: Check `response.status` before parsing JSON
2. **Handle Network Errors**: Implement retry logic for network failures
3. **Show User-Friendly Messages**: Display `message` field to users
4. **Log Detailed Errors**: Log full error response for debugging
5. **Implement Fallbacks**: Gracefully degrade when API is unavailable

---

## Rate Limiting

Currently, rate limiting is **not enforced** at the API level. However, consider implementing client-side rate limiting to prevent excessive requests:

- **Comments**: Limit to 1 per 30 seconds
- **Re-Vote Proposals**: Limit to 1 per 5 minutes
- **API Calls**: General limit of 100 requests per minute

Future versions may implement server-side rate limiting using Django Ratelimit.

---

## Examples

### Complete Workflow Example (JavaScript)

```javascript
/**
 * Complete consensus discussion workflow
 */
class ConflictDiscussionClient {
  constructor(conflictId) {
    this.conflictId = conflictId;
    this.baseUrl = '/api/conflicts';
    this.eventSource = null;
  }

  /**
   * Load conflict details
   */
  async loadConflict() {
    const response = await fetch(`${this.baseUrl}/${this.conflictId}/details/`, {
      credentials: 'include'
    });

    if (!response.ok) {
      throw new Error(`Failed to load conflict: ${response.statusText}`);
    }

    return await response.json();
  }

  /**
   * Post a comment
   */
  async postComment(content, parentId = null) {
    const response = await fetch(`${this.baseUrl}/${this.conflictId}/comments/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': this.getCsrfToken()
      },
      credentials: 'include',
      body: JSON.stringify({ content, parent_id: parentId })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.message);
    }

    return await response.json();
  }

  /**
   * Propose re-vote
   */
  async proposeRevote(rationale) {
    const response = await fetch(`${this.baseUrl}/${this.conflictId}/propose-revote/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': this.getCsrfToken()
      },
      credentials: 'include',
      body: JSON.stringify({ rationale })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.message);
    }

    return await response.json();
  }

  /**
   * Accept re-vote proposal
   */
  async acceptProposal(proposalId) {
    const response = await fetch(`${this.baseUrl}/${this.conflictId}/proposals/${proposalId}/accept/`, {
      method: 'POST',
      headers: {
        'X-CSRFToken': this.getCsrfToken()
      },
      credentials: 'include'
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.message);
    }

    return await response.json();
  }

  /**
   * Submit re-vote decision
   */
  async submitRevoteDecision(proposalId, decision, notes, confidenceLevel = 2) {
    const response = await fetch(`${this.baseUrl}/${this.conflictId}/proposals/${proposalId}/submit-decision/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': this.getCsrfToken()
      },
      credentials: 'include',
      body: JSON.stringify({
        decision,
        notes,
        confidence_level: confidenceLevel
      })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.message);
    }

    return await response.json();
  }

  /**
   * Connect to SSE stream
   */
  connectSSE(handlers) {
    this.eventSource = new EventSource(`${this.baseUrl}/${this.conflictId}/stream/`);

    // Set up event listeners
    this.eventSource.addEventListener('new_comment', (event) => {
      const data = JSON.parse(event.data);
      handlers.onNewComment?.(data.comment);
    });

    this.eventSource.addEventListener('revote_proposed', (event) => {
      const data = JSON.parse(event.data);
      handlers.onRevoteProposed?.(data.proposal);
    });

    this.eventSource.addEventListener('revote_accepted', (event) => {
      const data = JSON.parse(event.data);
      handlers.onRevoteAccepted?.(data.proposal);
    });

    this.eventSource.addEventListener('consensus_reached', (event) => {
      const data = JSON.parse(event.data);
      handlers.onConsensusReached?.(data);
    });

    this.eventSource.onerror = (error) => {
      handlers.onError?.(error);
    };
  }

  /**
   * Disconnect SSE
   */
  disconnectSSE() {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }

  /**
   * Get CSRF token from cookie
   */
  getCsrfToken() {
    const name = 'csrftoken';
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
      const [key, value] = cookie.trim().split('=');
      if (key === name) return value;
    }
    return '';
  }
}

// Usage example
async function resolveConflict() {
  const client = new ConflictDiscussionClient('550e8400-e29b-41d4-a716-446655440000');

  // Load conflict
  const conflict = await client.loadConflict();
  console.log('Conflict loaded:', conflict);

  // Connect to SSE
  client.connectSSE({
    onNewComment: (comment) => {
      console.log('New comment:', comment);
      // Update UI
    },
    onConsensusReached: (data) => {
      console.log('Consensus reached!', data);
      // Show success message
    },
    onError: (error) => {
      console.error('SSE error:', error);
      // Reconnect logic
    }
  });

  // Post a comment
  await client.postComment('I think we should reconsider because...');

  // Propose re-vote
  const proposal = await client.proposeRevote('After discussion, I believe...');

  // Accept proposal (other reviewer)
  await client.acceptProposal(proposal.id);

  // Submit re-vote decision
  await client.submitRevoteDecision(proposal.id, 'INCLUDE', 'Changed my mind after discussion', 3);

  // Clean up
  window.addEventListener('beforeunload', () => {
    client.disconnectSSE();
  });
}
```

---

## Support

For additional API documentation or support:

- **Technical Issues**: Contact system administrator
- **API Changes**: Check changelog for version updates
- **Feature Requests**: Submit via GitHub issues or internal ticketing system

---

**Document Version:** 1.0
**Last Updated:** 21 October 2025
**API Version:** v1
