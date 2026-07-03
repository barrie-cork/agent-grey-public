# Dual-Workflow API Documentation

**Version**: 2.0.0
**Date**: November 2025
**Base URL**: `https://app.agent-grey.com`

---

## Table of Contents

1. [Authentication](#authentication)
2. [Workflow #1: Work Queue APIs](#workflow-1-work-queue-apis)
3. [Workflow #2: Conflict Resolution APIs](#workflow-2-conflict-resolution-apis)
4. [IRR Metrics APIs](#irr-metrics-apis)
5. [WebSocket/SSE Endpoints](#websocketsse-endpoints)
6. [Error Responses](#error-responses)

---

## Authentication

All API endpoints require authentication via Django session or token.

**Session Authentication** (browser):
```bash
# Login first
curl -X POST https://app.agent-grey.com/accounts/login/ \
  -d "username=user@example.com" \
  -d "password=password" \
  -c cookies.txt

# Use cookies for subsequent requests
curl https://app.agent-grey.com/api/conflicts/ -b cookies.txt
```

**Token Authentication** (programmatic):
```bash
# Obtain token
curl -X POST https://app.agent-grey.com/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "user@example.com", "password": "password"}'

# Response
{"token": "<your-token>"}

# Use token in Authorization header
curl https://app.agent-grey.com/api/conflicts/ \
  -H "Authorization: Bearer <your-token>"
```

---

## Workflow #1: Work Queue APIs

### Claim Next Batch

Atomically claim next 10 unreviewed results for the current user.

**Endpoint**: `POST /api/sessions/{session_id}/claim/`

**Request**:
```bash
curl -X POST https://app.agent-grey.com/api/sessions/123e4567-e89b-12d3-a456-426614174000/claim/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "batch_size": 10
  }'
```

**Response** (200 OK):
```json
{
  "claimed_results": [
    {
      "id": "987fcdeb-51a2-43d1-9012-123456789abc",
      "title": "Mobile apps for weight loss: systematic review",
      "snippet": "Background: Mobile applications...",
      "url": "https://example.com/study.pdf",
      "claimed_at": "2025-11-01T14:30:00Z",
      "expires_at": "2025-11-01T14:40:00Z"
    }
    // ... 9 more results
  ],
  "total_claimed": 10,
  "timer_duration_seconds": 600
}
```

**Error Responses**:
- `404` - Session not found
- `403` - Not authorized for this session
- `409` - No unclaimed results available
- `400` - Invalid batch size

---

### Submit Decision

Submit review decision for a claimed result.

**Endpoint**: `POST /api/sessions/{session_id}/decide/`

**Request**:
```bash
curl -X POST https://app.agent-grey.com/api/sessions/123e4567-e89b-12d3-a456-426614174000/decide/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "result_id": "987fcdeb-51a2-43d1-9012-123456789abc",
    "decision": "include",
    "exclusion_reason": "",
    "notes": "Meets all inclusion criteria - RCT with mobile app intervention"
  }'
```

**Request Parameters**:
- `result_id` (string, required): UUID of result
- `decision` (string, required): `"include"`, `"exclude"`, or `"maybe"`
- `exclusion_reason` (string, optional): Required if `decision == "exclude"`
- `notes` (string, optional): Reviewer notes

**Response** (201 Created):
```json
{
  "id": "def12345-6789-0abc-def1-234567890abc",
  "result": "987fcdeb-51a2-43d1-9012-123456789abc",
  "decision": "include",
  "reviewer": "user@example.com",
  "created_at": "2025-11-01T14:35:00Z",
  "progress": {
    "reviewed": 45,
    "total": 200,
    "percentage": 22.5
  }
}
```

---

### Release Claimed Results

Release all claimed results for current user (e.g., if can't finish in time).

**Endpoint**: `POST /api/sessions/{session_id}/release/`

**Request**:
```bash
curl -X POST https://app.agent-grey.com/api/sessions/123e4567-e89b-12d3-a456-426614174000/release/ \
  -H "Authorization: Bearer <token>"
```

**Response** (200 OK):
```json
{
  "released_count": 7,
  "message": "7 results released for reassignment"
}
```

---

## Workflow #2: Conflict Resolution APIs

### List Conflicts

Get all conflicts for a session.

**Endpoint**: `GET /api/conflicts/?session_id={session_id}`

**Request**:
```bash
curl "https://app.agent-grey.com/api/conflicts/?session_id=123e4567-e89b-12d3-a456-426614174000" \
  -H "Authorization: Bearer <token>"
```

**Query Parameters**:
- `session_id` (string, required): Session UUID
- `status` (string, optional): Filter by status (`PENDING`, `IN_DISCUSSION`, `ESCALATED`, `RESOLVED`)
- `conflict_type` (string, optional): Filter by type (`INCLUDE_EXCLUDE`, `EXCLUSION_REASON`, `LOW_CONFIDENCE`)
- `page` (int, optional): Page number (default: 1)
- `page_size` (int, optional): Results per page (default: 20)

**Response** (200 OK):
```json
{
  "count": 15,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "abc12345-def6-7890-abcd-ef1234567890",
      "result": {
        "id": "987fcdeb-51a2-43d1-9012-123456789abc",
        "title": "Mobile apps for weight loss",
        "url": "https://example.com/study.pdf"
      },
      "decision_1": {
        "reviewer": "alice@example.com",
        "decision": "include",
        "confidence": "high",
        "notes": "Relevant RCT with clear methods"
      },
      "decision_2": {
        "reviewer": "bob@example.com",
        "decision": "exclude",
        "confidence": "medium",
        "notes": "Conference abstract, not full-text"
      },
      "conflict_type": "INCLUDE_EXCLUDE",
      "status": "PENDING",
      "resolution_method": "CONSENSUS",
      "created_at": "2025-11-01T15:00:00Z"
    }
    // ... 14 more conflicts
  ]
}
```

---

### Get Conflict Detail

Get detailed information about a specific conflict.

**Endpoint**: `GET /api/conflicts/{conflict_id}/`

**Request**:
```bash
curl https://app.agent-grey.com/api/conflicts/abc12345-def6-7890-abcd-ef1234567890/ \
  -H "Authorization: Bearer <token>"
```

**Response** (200 OK):
```json
{
  "id": "abc12345-def6-7890-abcd-ef1234567890",
  "result": {
    "id": "987fcdeb-51a2-43d1-9012-123456789abc",
    "title": "Mobile apps for weight loss: systematic review",
    "snippet": "Background: Mobile applications have become increasingly popular...",
    "url": "https://example.com/study.pdf",
    "source": "Google Scholar"
  },
  "decision_1": {
    "id": "dec11111-1111-1111-1111-111111111111",
    "reviewer": {
      "email": "alice@example.com",
      "full_name": "Alice Smith"
    },
    "decision": "include",
    "confidence": "high",
    "exclusion_reason": "",
    "notes": "Relevant RCT with clear intervention description and outcomes",
    "created_at": "2025-11-01T14:45:00Z"
  },
  "decision_2": {
    "id": "dec22222-2222-2222-2222-222222222222",
    "reviewer": {
      "email": "bob@example.com",
      "full_name": "Bob Johnson"
    },
    "decision": "exclude",
    "confidence": "medium",
    "exclusion_reason": "not_full_text",
    "notes": "Conference abstract only - insufficient detail for inclusion",
    "created_at": "2025-11-01T14:50:00Z"
  },
  "conflict_type": "INCLUDE_EXCLUDE",
  "status": "PENDING",
  "resolution_method": "CONSENSUS",
  "resolution_decision": null,
  "resolved_by": null,
  "resolved_at": null,
  "comment_count": 0,
  "created_at": "2025-11-01T15:00:00Z"
}
```

---

### Add Comment to Conflict

Post a comment in the consensus discussion thread.

**Endpoint**: `POST /api/conflicts/{conflict_id}/discuss/`

**Request**:
```bash
curl -X POST https://app.agent-grey.com/api/conflicts/abc12345-def6-7890-abcd-ef1234567890/discuss/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "I see your point about the abstract. However, I found the **full-text PDF** here: [Link](https://example.com/fulltext.pdf). The methods section is on page 3 and provides sufficient detail. Should we re-evaluate?",
    "parent_id": null
  }'
```

**Request Parameters**:
- `content` (string, required): Comment text (markdown supported)
- `parent_id` (string, optional): UUID of parent comment (for threaded replies)

**Response** (201 Created):
```json
{
  "id": "cmt12345-6789-0abc-def1-234567890abc",
  "conflict": "abc12345-def6-7890-abcd-ef1234567890",
  "author": {
    "email": "alice@example.com",
    "full_name": "Alice Smith"
  },
  "parent": null,
  "content": "I see your point about the abstract. However, I found the **full-text PDF** here: [Link](https://example.com/fulltext.pdf). The methods section is on page 3 and provides sufficient detail. Should we re-evaluate?",
  "content_html": "<p>I see your point about the abstract. However, I found the <strong>full-text PDF</strong> here: <a href=\"https://example.com/fulltext.pdf\">Link</a>. The methods section is on page 3 and provides sufficient detail. Should we re-evaluate?</p>",
  "is_edited": false,
  "created_at": "2025-11-01T15:10:00Z",
  "updated_at": "2025-11-01T15:10:00Z"
}
```

**Markdown Support**: Comments support full markdown syntax with XSS protection via DOMPurify.

---

### Mark Conflict Resolved (Consensus)

Mark a conflict as resolved after reaching consensus.

**Endpoint**: `POST /api/conflicts/{conflict_id}/resolve/`

**Request**:
```bash
curl -X POST https://app.agent-grey.com/api/conflicts/abc12345-def6-7890-abcd-ef1234567890/resolve/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "resolution_decision": "include",
    "resolution_notes": "Both reviewers agree to INCLUDE after reviewing full-text PDF. Methods section provides sufficient detail for inclusion."
  }'
```

**Request Parameters**:
- `resolution_decision` (string, required): Final decision (`"include"` or `"exclude"`)
- `resolution_notes` (string, optional): Summary of consensus reasoning

**Response** (200 OK):
```json
{
  "id": "abc12345-def6-7890-abcd-ef1234567890",
  "status": "RESOLVED",
  "resolution_decision": "include",
  "resolution_method": "CONSENSUS",
  "resolved_by": {
    "email": "alice@example.com",
    "full_name": "Alice Smith"
  },
  "resolved_at": "2025-11-01T15:20:00Z",
  "resolution_notes": "Both reviewers agree to INCLUDE after reviewing full-text PDF."
}
```

**Permissions**: Both original reviewers must agree before marking resolved (enforced by UI workflow).

---

### Arbitrate Conflict

Lead or designated arbitrator makes final decision.

**Endpoint**: `POST /api/conflicts/{conflict_id}/arbitrate/`

**Request**:
```bash
curl -X POST https://app.agent-grey.com/api/conflicts/abc12345-def6-7890-abcd-ef1234567890/arbitrate/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "resolution_decision": "exclude",
    "resolution_notes": "Lead reviewer decision: EXCLUDE. While full-text is available, study design does not meet our RCT criteria (quasi-experimental design)."
  }'
```

**Permissions**:
- `LEAD_ARBITRATION`: Session owner only
- `DESIGNATED_ARBITRATOR`: Assigned arbitrator only
- `MAJORITY`: Session owner or arbitrator (auto-resolved if votes sufficient)

**Response** (200 OK):
```json
{
  "id": "abc12345-def6-7890-abcd-ef1234567890",
  "status": "RESOLVED",
  "resolution_decision": "exclude",
  "resolution_method": "LEAD_ARBITRATION",
  "resolved_by": {
    "email": "lead@example.com",
    "full_name": "Lead Reviewer"
  },
  "resolved_at": "2025-11-01T15:30:00Z",
  "resolution_notes": "Lead reviewer decision: EXCLUDE. Study design does not meet RCT criteria."
}
```

**Error Responses**:
- `403` - Not authorized to arbitrate (not lead/arbitrator)
- `400` - Invalid resolution method for session configuration
- `409` - Conflict already resolved

---

## IRR Metrics APIs

### Get Session IRR Metrics

Get Cohen's Kappa and confusion matrix for all reviewer pairs.

**Endpoint**: `GET /api/sessions/{session_id}/irr-metrics/`

**Request**:
```bash
curl https://app.agent-grey.com/api/sessions/123e4567-e89b-12d3-a456-426614174000/irr-metrics/ \
  -H "Authorization: Bearer <token>"
```

**Response** (200 OK):
```json
{
  "session_id": "123e4567-e89b-12d3-a456-426614174000",
  "reviewer_pairs": [
    {
      "reviewer_1": {
        "email": "alice@example.com",
        "full_name": "Alice Smith"
      },
      "reviewer_2": {
        "email": "bob@example.com",
        "full_name": "Bob Johnson"
      },
      "cohens_kappa": 0.85,
      "interpretation": "Almost Perfect",
      "agreement_percentage": 92.5,
      "confusion_matrix": {
        "both_include": 150,
        "both_exclude": 35,
        "reviewer1_include_reviewer2_exclude": 10,
        "reviewer1_exclude_reviewer2_include": 5
      },
      "calculated_at": "2025-11-01T15:00:00Z"
    }
    // More pairs if 3+ reviewers
  ],
  "threshold": 0.70,
  "meets_threshold": true
}
```

**Interpretation Guide**:
- `> 0.80`: Almost Perfect
- `0.61 - 0.80`: Substantial
- `0.41 - 0.60`: Moderate
- `0.21 - 0.40`: Fair
- `0.00 - 0.20`: Slight
- `< 0.00`: Poor

---

### Get Team Dashboard IRR Data

Alternative endpoint with additional team metrics.

**Endpoint**: `GET /api/dashboard/irr/?session_id={session_id}`

**Request**:
```bash
curl "https://app.agent-grey.com/api/dashboard/irr/?session_id=123e4567-e89b-12d3-a456-426614174000" \
  -H "Authorization: Bearer <token>"
```

**Response** (200 OK):
```json
{
  "session": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "title": "Obesity Interventions Systematic Review",
    "total_results": 200
  },
  "irr_metrics": [
    {
      "pair": "Alice ↔ Bob",
      "kappa": 0.85,
      "interpretation": "Almost Perfect",
      "agreement_pct": 92.5,
      "status": "✅ Meets Threshold"
    }
  ],
  "conflicts": {
    "total": 15,
    "resolved": 12,
    "pending": 3,
    "types": {
      "INCLUDE_EXCLUDE": 8,
      "EXCLUSION_REASON": 5,
      "LOW_CONFIDENCE": 2
    }
  },
  "completion_status": {
    "all_reviewers_complete": true,
    "ready_for_reporting": false,
    "blocking_reason": "3 unresolved conflicts"
  }
}
```

---

## WebSocket/SSE Endpoints

### Conflict Discussion Stream (SSE)

Real-time updates for new comments in conflict discussion.

**Endpoint**: `GET /api/conflicts/{conflict_id}/stream/`

**Request** (JavaScript EventSource):
```javascript
const eventSource = new EventSource(
  'https://app.agent-grey.com/api/conflicts/abc12345-def6-7890-abcd-ef1234567890/stream/',
  { withCredentials: true }
);

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('New comment:', data);
  // Update UI with new comment
};

eventSource.onerror = (error) => {
  console.error('SSE error:', error);
  eventSource.close();
};
```

**SSE Event Format**:
```json
{
  "event": "new_comment",
  "data": {
    "id": "cmt67890-abcd-ef12-3456-7890abcdef12",
    "author": {
      "email": "bob@example.com",
      "full_name": "Bob Johnson"
    },
    "content_html": "<p>Good point. I'll re-review the methods section.</p>",
    "created_at": "2025-11-01T15:15:00Z"
  }
}
```

**Connection Management**:
- Auto-reconnect on disconnect
- Keep-alive: 30-second heartbeat
- Timeout: 5 minutes idle
- Browser support: All modern browsers (Chrome, Firefox, Safari, Edge)

**Nginx Configuration Required**:
```nginx
location ~ ^/api/conflicts/.+/stream/$ {
    proxy_pass http://web:8000;
    proxy_set_header X-Accel-Buffering no;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 300s;
    chunked_transfer_encoding off;
}
```

---

## Error Responses

### Standard Error Format

All error responses follow this structure:

```json
{
  "error": "Error message",
  "code": "ERROR_CODE",
  "details": {
    "field_name": ["Error detail"]
  }
}
```

### Common HTTP Status Codes

| Code | Meaning | Example |
|------|---------|---------|
| `200` | OK | Request successful |
| `201` | Created | Resource created |
| `400` | Bad Request | Invalid JSON or missing required fields |
| `401` | Unauthorized | Missing or invalid authentication |
| `403` | Forbidden | No permission for this action |
| `404` | Not Found | Resource doesn't exist |
| `409` | Conflict | Resource conflict (e.g., already resolved) |
| `429` | Too Many Requests | Rate limit exceeded |
| `500` | Server Error | Internal server error |

### Example Error Response

```json
{
  "error": "Not authorized to arbitrate this conflict",
  "code": "PERMISSION_DENIED",
  "details": {
    "required_role": "SESSION_OWNER or DESIGNATED_ARBITRATOR",
    "your_role": "REVIEWER",
    "resolution_method": "LEAD_ARBITRATION"
  }
}
```

---

## Rate Limiting

**Limits** (per user):
- `GET` requests: 1000 per hour
- `POST` requests: 100 per hour
- SSE connections: 5 concurrent per session

**Headers**:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1698854400
```

**429 Response**:
```json
{
  "error": "Rate limit exceeded",
  "code": "RATE_LIMIT_EXCEEDED",
  "details": {
    "retry_after": 3600
  }
}
```

---

## Code Examples

### Python Example: Create Session and Invite Reviewers

```python
import requests

BASE_URL = "https://app.agent-grey.com"
TOKEN = "your-auth-token"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# Create session with Workflow #2
session_data = {
    "title": "My Systematic Review",
    "min_reviewers_per_result": 2,
    "conflict_resolution_method": "CONSENSUS",
    "irr_threshold": 0.70
}
response = requests.post(f"{BASE_URL}/api/sessions/", json=session_data, headers=headers)
session_id = response.json()["id"]

# Invite reviewers
invitations = [
    {"email": "reviewer1@example.com", "role": "PRIMARY"},
    {"email": "reviewer2@example.com", "role": "SECONDARY"}
]
for inv in invitations:
    requests.post(
        f"{BASE_URL}/api/sessions/{session_id}/invite/",
        json=inv,
        headers=headers
    )

print(f"Session created: {session_id}")
```

### JavaScript Example: Real-Time Conflict Discussion

```javascript
// Connect to SSE stream
const conflictId = 'abc12345-def6-7890-abcd-ef1234567890';
const eventSource = new EventSource(
  `/api/conflicts/${conflictId}/stream/`,
  { withCredentials: true }
);

eventSource.onmessage = (event) => {
  const comment = JSON.parse(event.data);
  appendCommentToUI(comment);
};

// Post new comment
async function postComment(content) {
  const response = await fetch(`/api/conflicts/${conflictId}/discuss/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCookie('csrftoken')
    },
    body: JSON.stringify({ content })
  });

  return response.json();
}

// Mark resolved
async function resolveConflict(decision) {
  const response = await fetch(`/api/conflicts/${conflictId}/resolve/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCookie('csrftoken')
    },
    body: JSON.stringify({
      resolution_decision: decision,
      resolution_notes: 'Consensus reached via discussion'
    })
  });

  return response.json();
}
```

---

## Support and Resources

**API Issues**:
- GitHub: https://github.com/agent-grey/core/issues
- Email: api-support@agent-grey.com
- Slack: #api-support

**Documentation**:
- User Guide: `docs/guides/DUAL_WORKFLOW_USER_GUIDE.md`
- Architecture: `docs/workflows/DUAL_WORKFLOW_ARCHITECTURE.md`
- Postman Collection: https://agent-grey.com/api/postman-collection.json

---

**Document Version**: 2.0.0
**Last Updated**: November 2025
**Next Review**: March 2026
