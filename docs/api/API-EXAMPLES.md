# Agent Grey API Examples

**Version**: 1.0.0
**Last Updated**: 2025-11-02
**Purpose**: Code examples for Agent Grey API in multiple languages

---

## Table of Contents

1. [Authentication](#authentication)
2. [Sessions](#sessions)
3. [Review - Core (Workflow #1 & #2)](#review---core)
4. [Conflict Resolution (Workflow #2)](#conflict-resolution)
5. [Dashboard & IRR Metrics](#dashboard--irr-metrics)
6. [Organisation Management](#organisation-management)
7. [Error Handling](#error-handling)

---

## Authentication

### User Registration

**curl**:
```bash
curl -X POST http://localhost:8000/accounts/signup/ \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=reviewer1&email=reviewer1@example.com&password1=SecurePass123!&password2=SecurePass123!"
```

**Python (requests)**:
```python
import requests

response = requests.post(
    'http://localhost:8000/accounts/signup/',
    data={
        'username': 'reviewer1',
        'email': 'reviewer1@example.com',
        'password1': 'SecurePass123!',
        'password2': 'SecurePass123!'
    }
)

# Captures session cookie automatically
session = requests.Session()
session.cookies = response.cookies
```

**JavaScript (fetch)**:
```javascript
const response = await fetch('http://localhost:8000/accounts/signup/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/x-www-form-urlencoded',
  },
  body: new URLSearchParams({
    username: 'reviewer1',
    email: 'reviewer1@example.com',
    password1: 'SecurePass123!',
    password2: 'SecurePass123!'
  }),
  credentials: 'include'  // Important: Include cookies
});
```

**Django Test (APIClient)**:
```python
from django.test import TestCase
from django.contrib.auth import get_user_model

User = get_user_model()

class AuthenticationTestCase(TestCase):
    def test_user_registration(self):
        response = self.client.post('/accounts/signup/', {
            'username': 'reviewer1',
            'email': 'reviewer1@example.com',
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!'
        })

        self.assertEqual(response.status_code, 302)  # Redirect on success
        self.assertTrue(User.objects.filter(username='reviewer1').exists())
```

---

### User Login

**curl**:
```bash
# Login and save cookies
curl -X POST http://localhost:8000/accounts/login/ \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=reviewer1&password=SecurePass123!" \
  -c cookies.txt  # Save cookies to file

# Use saved cookies in subsequent requests
curl -X GET http://localhost:8000/api/results/queue/ \
  -b cookies.txt  # Load cookies from file
```

**Python (requests)**:
```python
import requests

# Create session to persist cookies
session = requests.Session()

# Login
response = session.post(
    'http://localhost:8000/accounts/login/',
    data={
        'username': 'reviewer1',
        'password': 'SecurePass123!'
    }
)

# Extract CSRF token for subsequent requests
csrf_token = session.cookies.get('csrftoken')

# Use session for authenticated requests
response = session.get('http://localhost:8000/api/results/queue/')
```

**JavaScript (fetch)**:
```javascript
// Login
const loginResponse = await fetch('http://localhost:8000/accounts/login/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/x-www-form-urlencoded',
  },
  body: new URLSearchParams({
    username: 'reviewer1',
    password: 'SecurePass123!'
  }),
  credentials: 'include'  // Important: Include cookies
});

// Extract CSRF token from cookie
function getCsrfToken() {
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  return match ? match[1] : '';
}

// Use in subsequent requests
const response = await fetch('http://localhost:8000/api/results/queue/', {
  method: 'GET',
  headers: {
    'X-CSRFToken': getCsrfToken()
  },
  credentials: 'include'
});
```

**Django Test (APIClient)**:
```python
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

User = get_user_model()

class AuthenticatedAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='reviewer1',
            email='reviewer1@example.com',
            password='SecurePass123!'
        )
        self.client.force_authenticate(user=self.user)

    def test_authenticated_request(self):
        response = self.client.get('/api/results/queue/')
        self.assertEqual(response.status_code, 200)
```

---

## Sessions

### Create Search Session

**curl**:
```bash
# First, get CSRF token
CSRF_TOKEN=$(curl -s -c cookies.txt http://localhost:8000/accounts/login/ | grep -oP 'csrfmiddlewaretoken" value="\K[^"]+')

# Create session
curl -X POST http://localhost:8000/api/review-manager/sessions/ \
  -b cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: ${CSRF_TOKEN}" \
  -d '{
    "title": "Grey Literature Review: Telehealth Interventions",
    "description": "Systematic review of telehealth interventions for elderly populations"
  }'
```

**Python (requests)**:
```python
import requests

session = requests.Session()
# Assume already logged in
session.post('http://localhost:8000/accounts/login/', data={'username': 'reviewer1', 'password': 'SecurePass123!'})

csrf_token = session.cookies.get('csrftoken')

response = session.post(
    'http://localhost:8000/api/review-manager/sessions/',
    headers={'X-CSRFToken': csrf_token},
    json={
        'title': 'Grey Literature Review: Telehealth Interventions',
        'description': 'Systematic review of telehealth interventions for elderly populations'
    }
)

session_data = response.json()
session_id = session_data['id']
print(f"Created session: {session_id}")
```

**JavaScript (fetch)**:
```javascript
const createSession = async () => {
  const csrfToken = getCsrfToken();

  const response = await fetch('http://localhost:8000/api/review-manager/sessions/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken
    },
    credentials: 'include',
    body: JSON.stringify({
      title: 'Grey Literature Review: Telehealth Interventions',
      description: 'Systematic review of telehealth interventions for elderly populations'
    })
  });

  const sessionData = await response.json();
  console.log('Created session:', sessionData.id);
  return sessionData;
};
```

**Django Test (APIClient)**:
```python
from rest_framework.test import APIClient
from apps.review_manager.models import SearchSession

class SessionAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='reviewer1', password='pass')
        self.client.force_authenticate(user=self.user)

    def test_create_session(self):
        response = self.client.post('/api/review-manager/sessions/', {
            'title': 'Grey Literature Review: Telehealth Interventions',
            'description': 'Systematic review of telehealth interventions'
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['title'], 'Grey Literature Review: Telehealth Interventions')
        self.assertTrue(SearchSession.objects.filter(title__icontains='Telehealth').exists())
```

---

### Get Session Status

**curl**:
```bash
curl -X GET http://localhost:8000/api/session/550e8400-e29b-41d4-a716-446655440000/status/ \
  -b cookies.txt \
  -H "X-CSRFToken: ${CSRF_TOKEN}"
```

**Python (requests)**:
```python
session_id = '550e8400-e29b-41d4-a716-446655440000'
response = session.get(f'http://localhost:8000/api/session/{session_id}/status/')

status_data = response.json()
print(f"Session status: {status_data['status']}")
print(f"Progress: {status_data['reviewed_count']}/{status_data['results_count']}")
```

**JavaScript (fetch)**:
```javascript
const getSessionStatus = async (sessionId) => {
  const response = await fetch(`http://localhost:8000/api/session/${sessionId}/status/`, {
    method: 'GET',
    credentials: 'include'
  });

  const status = await response.json();
  console.log(`Status: ${status.status}`);
  console.log(`Progress: ${status.reviewed_count}/${status.results_count}`);
  return status;
};
```

**Django Test (APIClient)**:
```python
def test_get_session_status(self):
    session = SearchSession.objects.create(
        owner=self.user,
        title='Test Session',
        status='under_review'
    )

    response = self.client.get(f'/api/session/{session.id}/status/')

    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.data['status'], 'under_review')
```

---

### SSE: Real-Time Session Updates

**curl (blocking)**:
```bash
# This will stream events in real-time
curl -N http://localhost:8000/sessions/550e8400-e29b-41d4-a716-446655440000/stream/ \
  -b cookies.txt
```

**Python (requests with streaming)**:
```python
import requests

session_id = '550e8400-e29b-41d4-a716-446655440000'

with requests.get(
    f'http://localhost:8000/sessions/{session_id}/stream/',
    cookies=session.cookies,
    stream=True
) as response:
    for line in response.iter_lines():
        if line:
            line_str = line.decode('utf-8')
            if line_str.startswith('data:'):
                data = line_str[6:]  # Remove 'data: ' prefix
                print(f"Update: {data}")
```

**JavaScript (EventSource)**:
```javascript
const sessionId = '550e8400-e29b-41d4-a716-446655440000';
const eventSource = new EventSource(`http://localhost:8000/sessions/${sessionId}/stream/`);

eventSource.addEventListener('status_update', (event) => {
  const data = JSON.parse(event.data);
  console.log(`Status: ${data.status}, Progress: ${data.progress}%`);
});

eventSource.addEventListener('complete', (event) => {
  const data = JSON.parse(event.data);
  console.log(`Session complete: ${data.total_results} results found`);
  eventSource.close();
});

eventSource.addEventListener('error', (error) => {
  console.error('SSE error:', error);
  eventSource.close();
});

// Close connection when done
// eventSource.close();
```

**Django Test (SSE testing)**:
```python
# Note: Testing SSE requires special handling
from django.test import TestCase
from apps.review_manager.views.sse import session_status_stream

class SSETestCase(TestCase):
    def test_sse_stream_format(self):
        # SSE streams are hard to test directly
        # Usually test the underlying data generation logic instead
        session = SearchSession.objects.create(
            owner=self.user,
            title='Test Session',
            status='executing'
        )

        # Test that SSE view is accessible
        response = self.client.get(f'/sessions/{session.id}/stream/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/event-stream')
```

---

## Review - Core

### Claim Next Result (Workflow #1)

**curl**:
```bash
curl -X POST http://localhost:8000/api/results/claim/ \
  -b cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: ${CSRF_TOKEN}" \
  -d '{
    "session_id": "550e8400-e29b-41d4-a716-446655440000"
  }'
```

**Python (requests)**:
```python
response = session.post(
    'http://localhost:8000/api/results/claim/',
    headers={'X-CSRFToken': csrf_token},
    json={
        'session_id': '550e8400-e29b-41d4-a716-446655440000'
    }
)

if response.status_code == 200:
    result = response.json()
    print(f"Claimed result: {result['title']}")
    print(f"URL: {result['url']}")
elif response.status_code == 404:
    print("No results available")
```

**JavaScript (fetch)**:
```javascript
const claimNextResult = async (sessionId) => {
  const csrfToken = getCsrfToken();

  const response = await fetch('http://localhost:8000/api/results/claim/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken
    },
    credentials: 'include',
    body: JSON.stringify({
      session_id: sessionId
    })
  });

  if (response.ok) {
    const result = await response.json();
    console.log(`Claimed: ${result.title}`);
    return result;
  } else if (response.status === 404) {
    console.log('No results available');
    return null;
  } else {
    throw new Error(`Claim failed: ${response.statusText}`);
  }
};
```

**Django Test (APIClient)**:
```python
def test_claim_next_result(self):
    session = SearchSession.objects.create(
        owner=self.user,
        title='Test Session',
        status='ready_for_review'
    )
    result = ProcessedResult.objects.create(
        session=session,
        title='Test Result',
        url='https://example.com/doc.pdf',
        snippet='Test snippet'
    )

    response = self.client.post('/api/results/claim/', {
        'session_id': str(session.id)
    }, format='json')

    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.data['title'], 'Test Result')
```

---

### Submit Review Decision

**curl**:
```bash
curl -X POST http://localhost:8000/api/results/550e8400-e29b-41d4-a716-446655440000/decide/ \
  -b cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: ${CSRF_TOKEN}" \
  -d '{
    "decision": "INCLUDE",
    "confidence_level": 3,
    "notes": "Meets all inclusion criteria",
    "screening_stage": "SCREENING"
  }'
```

**Python (requests)**:
```python
result_id = '550e8400-e29b-41d4-a716-446655440000'

response = session.post(
    f'http://localhost:8000/api/results/{result_id}/decide/',
    headers={'X-CSRFToken': csrf_token},
    json={
        'decision': 'INCLUDE',
        'confidence_level': 3,
        'notes': 'Meets all inclusion criteria',
        'screening_stage': 'SCREENING'
    }
)

decision_response = response.json()
print(f"Decision: {decision_response['decision']}")
print(f"Status: {decision_response['status']}")

# Handle different statuses
if decision_response['status'] == 'awaiting_second_reviewer':
    print("Waiting for second reviewer")
elif decision_response['status'] == 'consensus_reached':
    print("Both reviewers agree!")
elif decision_response['status'] == 'conflict_detected':
    print("Conflict detected - requires resolution")
```

**JavaScript (fetch)**:
```javascript
const submitDecision = async (resultId, decision, notes) => {
  const csrfToken = getCsrfToken();

  const response = await fetch(`http://localhost:8000/api/results/${resultId}/decide/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken
    },
    credentials: 'include',
    body: JSON.stringify({
      decision: decision,        // 'INCLUDE' | 'EXCLUDE' | 'MAYBE' | 'ABSTAIN'
      confidence_level: 3,       // 1=Low, 2=Medium, 3=High
      notes: notes,
      screening_stage: 'SCREENING'
    })
  });

  const result = await response.json();
  console.log(`Decision submitted: ${result.status}`);
  return result;
};

// Example usage
await submitDecision(
  '550e8400-e29b-41d4-a716-446655440000',
  'INCLUDE',
  'Meets all inclusion criteria'
);
```

**Django Test (APIClient)**:
```python
def test_submit_decision(self):
    result = ProcessedResult.objects.create(
        session=self.session,
        title='Test Result',
        url='https://example.com/doc.pdf'
    )

    response = self.client.post(f'/api/results/{result.id}/decide/', {
        'decision': 'INCLUDE',
        'confidence_level': 3,
        'notes': 'Meets inclusion criteria',
        'screening_stage': 'SCREENING'
    }, format='json')

    self.assertEqual(response.status_code, 201)
    self.assertEqual(response.data['decision'], 'INCLUDE')

    # Verify decision was created
    self.assertTrue(
        ReviewerDecision.objects.filter(
            result=result,
            reviewer=self.user,
            decision='INCLUDE'
        ).exists()
    )
```

---

### Release Claimed Result

**curl**:
```bash
curl -X POST http://localhost:8000/api/results/550e8400-e29b-41d4-a716-446655440000/release/ \
  -b cookies.txt \
  -H "X-CSRFToken: ${CSRF_TOKEN}"
```

**Python (requests)**:
```python
result_id = '550e8400-e29b-41d4-a716-446655440000'

response = session.post(
    f'http://localhost:8000/api/results/{result_id}/release/',
    headers={'X-CSRFToken': csrf_token}
)

if response.status_code == 200:
    print("Result released successfully")
else:
    print("Error releasing result")
```

**JavaScript (fetch)**:
```javascript
const releaseResult = async (resultId) => {
  const csrfToken = getCsrfToken();

  const response = await fetch(`http://localhost:8000/api/results/${resultId}/release/`, {
    method: 'POST',
    headers: {
      'X-CSRFToken': csrfToken
    },
    credentials: 'include'
  });

  if (response.ok) {
    console.log('Result released');
    return true;
  } else {
    console.error('Failed to release result');
    return false;
  }
};
```

**Django Test (APIClient)**:
```python
def test_release_result(self):
    result = ProcessedResult.objects.create(
        session=self.session,
        title='Test Result',
        url='https://example.com/doc.pdf'
    )

    # Create assignment
    assignment = ReviewerAssignment.objects.create(
        result=result,
        reviewer=self.user,
        role='PRIMARY',
        is_active=True
    )

    response = self.client.post(f'/api/results/{result.id}/release/')

    self.assertEqual(response.status_code, 200)
    assignment.refresh_from_db()
    self.assertFalse(assignment.is_active)
```

---

## Conflict Resolution

### List Conflicts

**curl**:
```bash
curl -X GET "http://localhost:8000/api/conflicts/?session_id=550e8400-e29b-41d4-a716-446655440000&status=PENDING" \
  -b cookies.txt
```

**Python (requests)**:
```python
session_id = '550e8400-e29b-41d4-a716-446655440000'

response = session.get(
    'http://localhost:8000/api/conflicts/',
    params={
        'session_id': session_id,
        'status': 'PENDING',
        'page': 1,
        'per_page': 20
    }
)

conflicts_data = response.json()
print(f"Total conflicts: {conflicts_data['count']}")

for conflict in conflicts_data['results']:
    print(f"Conflict #{conflict['id']}: {conflict['conflict_type']} - {conflict['status']}")
```

**JavaScript (fetch)**:
```javascript
const listConflicts = async (sessionId, status = 'PENDING') => {
  const url = new URL('http://localhost:8000/api/conflicts/');
  url.searchParams.append('session_id', sessionId);
  url.searchParams.append('status', status);

  const response = await fetch(url, {
    method: 'GET',
    credentials: 'include'
  });

  const data = await response.json();
  console.log(`Total conflicts: ${data.count}`);

  data.results.forEach((conflict, index) => {
    console.log(`${index + 1}. ${conflict.conflict_type} - ${conflict.status}`);
  });

  return data.results;
};
```

**Django Test (APIClient)**:
```python
def test_list_conflicts(self):
    conflict = ConflictResolution.objects.create(
        session=self.session,
        result=self.result,
        conflict_type='INCLUDE_EXCLUDE',
        status='PENDING'
    )

    response = self.client.get('/api/conflicts/', {
        'session_id': str(self.session.id)
    })

    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.data['count'], 1)
    self.assertEqual(response.data['results'][0]['conflict_type'], 'INCLUDE_EXCLUDE')
```

---

### Get Conflict Details

**curl**:
```bash
curl -X GET http://localhost:8000/api/conflicts/550e8400-e29b-41d4-a716-446655440000/details/ \
  -b cookies.txt
```

**Python (requests)**:
```python
conflict_id = '550e8400-e29b-41d4-a716-446655440000'

response = session.get(f'http://localhost:8000/api/conflicts/{conflict_id}/details/')

data = response.json()

# Access conflict details
conflict = data['conflict']
print(f"Conflict type: {conflict['conflict_type']}")
print(f"Result: {conflict['result']['title']}")

# Access conflicting decisions
for decision in conflict['conflicting_decisions']:
    print(f"{decision['reviewer']['username']}: {decision['decision']}")

# Access comments
for comment in data['comments']:
    print(f"{comment['author']['username']}: {comment['content']}")

# Check permissions
permissions = data['permissions']
if permissions['can_resolve']:
    print("You can resolve this conflict")
```

**JavaScript (fetch)**:
```javascript
const getConflictDetails = async (conflictId) => {
  const response = await fetch(
    `http://localhost:8000/api/conflicts/${conflictId}/details/`,
    {
      method: 'GET',
      credentials: 'include'
    }
  );

  const data = await response.json();

  console.log('Conflict:', data.conflict.conflict_type);
  console.log('Result:', data.conflict.result.title);

  console.log('\nDecisions:');
  data.conflict.conflicting_decisions.forEach((decision) => {
    console.log(`- ${decision.reviewer.username}: ${decision.decision}`);
  });

  console.log('\nComments:');
  data.comments.forEach((comment) => {
    console.log(`- ${comment.author.username}: ${comment.content}`);
  });

  return data;
};
```

**Django Test (APIClient)**:
```python
def test_get_conflict_details(self):
    conflict = ConflictResolution.objects.create(
        session=self.session,
        result=self.result,
        conflict_type='INCLUDE_EXCLUDE',
        status='PENDING'
    )

    decision1 = ReviewerDecision.objects.create(
        result=self.result,
        reviewer=self.user,
        decision='INCLUDE'
    )
    decision2 = ReviewerDecision.objects.create(
        result=self.result,
        reviewer=self.reviewer2,
        decision='EXCLUDE'
    )

    conflict.conflicting_decisions.add(decision1, decision2)

    response = self.client.get(f'/api/conflicts/{conflict.id}/details/')

    self.assertEqual(response.status_code, 200)
    self.assertEqual(len(response.data['conflict']['conflicting_decisions']), 2)
```

---

### Add Comment to Conflict Discussion

**curl**:
```bash
curl -X POST http://localhost:8000/api/conflicts/550e8400-e29b-41d4-a716-446655440000/comments/ \
  -b cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: ${CSRF_TOKEN}" \
  -d '{
    "content": "I think we should include this because the methodology is sound.",
    "parent_id": null
  }'
```

**Python (requests)**:
```python
conflict_id = '550e8400-e29b-41d4-a716-446655440000'

response = session.post(
    f'http://localhost:8000/api/conflicts/{conflict_id}/comments/',
    headers={'X-CSRFToken': csrf_token},
    json={
        'content': 'I think we should include this because the methodology is sound.',
        'parent_id': None  # Set to comment ID for threaded reply
    }
)

comment = response.json()
print(f"Comment added: {comment['id']}")
```

**JavaScript (fetch)**:
```javascript
const addComment = async (conflictId, content, parentId = null) => {
  const csrfToken = getCsrfToken();

  const response = await fetch(
    `http://localhost:8000/api/conflicts/${conflictId}/comments/`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken
      },
      credentials: 'include',
      body: JSON.stringify({
        content: content,
        parent_id: parentId
      })
    }
  );

  const comment = await response.json();
  console.log('Comment added:', comment.id);
  return comment;
};

// Example: Add comment with markdown
await addComment(
  '550e8400-e29b-41d4-a716-446655440000',
  '**Rationale**: The study meets criteria 1-3:\n1. Population matches\n2. Intervention is telehealth\n3. Outcomes are relevant'
);
```

**Django Test (APIClient)**:
```python
def test_add_comment(self):
    conflict = ConflictResolution.objects.create(
        session=self.session,
        result=self.result,
        conflict_type='INCLUDE_EXCLUDE',
        status='IN_DISCUSSION'
    )

    response = self.client.post(f'/api/conflicts/{conflict.id}/comments/', {
        'content': 'I think we should include this',
        'parent_id': None
    }, format='json')

    self.assertEqual(response.status_code, 201)
    self.assertEqual(response.data['content'], 'I think we should include this')

    # Verify comment was created
    self.assertTrue(
        ConflictComment.objects.filter(
            conflict=conflict,
            author=self.user
        ).exists()
    )
```

---

### Resolve Conflict

**curl**:
```bash
curl -X POST http://localhost:8000/api/conflicts/550e8400-e29b-41d4-a716-446655440000/resolve/ \
  -b cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: ${CSRF_TOKEN}" \
  -d '{
    "resolution_method": "CONSENSUS",
    "decision": "INCLUDE",
    "notes": "After discussion, both reviewers agreed to include",
    "exclusion_reason": ""
  }'
```

**Python (requests)**:
```python
conflict_id = '550e8400-e29b-41d4-a716-446655440000'

response = session.post(
    f'http://localhost:8000/api/conflicts/{conflict_id}/resolve/',
    headers={'X-CSRFToken': csrf_token},
    json={
        'resolution_method': 'CONSENSUS',
        'decision': 'INCLUDE',
        'notes': 'After discussion, both reviewers agreed to include',
        'exclusion_reason': ''
    }
)

if response.status_code == 200:
    result = response.json()
    print(f"Conflict resolved: {result['final_decision']['decision']}")
    print(f"Method: {result['resolution_method']}")
else:
    print(f"Error: {response.json()['message']}")
```

**JavaScript (fetch)**:
```javascript
const resolveConflict = async (conflictId, method, decision, notes) => {
  const csrfToken = getCsrfToken();

  const response = await fetch(
    `http://localhost:8000/api/conflicts/${conflictId}/resolve/`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken
      },
      credentials: 'include',
      body: JSON.stringify({
        resolution_method: method,  // CONSENSUS | LEAD_ARBITRATION | DESIGNATED_ARBITRATOR | MAJORITY
        decision: decision,          // INCLUDE | EXCLUDE | MAYBE
        notes: notes,
        exclusion_reason: decision === 'EXCLUDE' ? 'Reason here' : ''
      })
    }
  );

  if (response.ok) {
    const result = await response.json();
    console.log('Conflict resolved:', result.final_decision.decision);
    return result;
  } else {
    const error = await response.json();
    throw new Error(error.message);
  }
};
```

**Django Test (APIClient)**:
```python
def test_resolve_conflict(self):
    conflict = ConflictResolution.objects.create(
        session=self.session,
        result=self.result,
        conflict_type='INCLUDE_EXCLUDE',
        status='PENDING',
        resolution_method='CONSENSUS'
    )

    response = self.client.post(f'/api/conflicts/{conflict.id}/resolve/', {
        'resolution_method': 'CONSENSUS',
        'decision': 'INCLUDE',
        'notes': 'Agreed to include after discussion',
        'exclusion_reason': ''
    }, format='json')

    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.data['status'], 'RESOLVED')

    conflict.refresh_from_db()
    self.assertEqual(conflict.status, 'RESOLVED')
```

---

### SSE: Real-Time Conflict Updates

**JavaScript (EventSource)**:
```javascript
const conflictId = '550e8400-e29b-41d4-a716-446655440000';
const eventSource = new EventSource(
  `http://localhost:8000/api/conflicts/${conflictId}/stream/`
);

eventSource.addEventListener('comment_added', (event) => {
  const data = JSON.parse(event.data);
  console.log(`New comment by ${data.author}: ${data.content}`);
  // Update UI with new comment
});

eventSource.addEventListener('status_change', (event) => {
  const data = JSON.parse(event.data);
  console.log(`Conflict status changed to: ${data.status}`);
  if (data.status === 'RESOLVED') {
    console.log(`Resolution: ${data.resolution_method}`);
    eventSource.close();
  }
});

eventSource.addEventListener('revote_proposed', (event) => {
  const data = JSON.parse(event.data);
  console.log(`Re-vote proposed by ${data.proposed_by}`);
  // Show revote notification
});

eventSource.onerror = (error) => {
  console.error('SSE error:', error);
  eventSource.close();
};
```

---

## Dashboard & IRR Metrics

### Get Team Statistics

**curl**:
```bash
curl -X GET "http://localhost:8000/api/dashboard/stats/?session_id=550e8400-e29b-41d4-a716-446655440000&period=week" \
  -b cookies.txt
```

**Python (requests)**:
```python
session_id = '550e8400-e29b-41d4-a716-446655440000'

response = session.get(
    'http://localhost:8000/api/dashboard/stats/',
    params={
        'session_id': session_id,
        'period': 'week'  # today | week | month | all
    }
)

stats = response.json()

print(f"Total results: {stats['overview']['total_results']}")
print(f"Reviewed: {stats['overview']['reviewed']}")
print(f"Progress: {stats['progress']['percentage_complete']}%")
print(f"Active reviewers: {stats['team_performance']['active_reviewers']}")

# IRR metrics
for pair in stats['inter_rater_reliability']['pairs']:
    print(f"Kappa ({pair['reviewer1']} vs {pair['reviewer2']}): {pair['cohens_kappa']:.2f}")
```

**JavaScript (fetch)**:
```javascript
const getTeamStats = async (sessionId, period = 'all') => {
  const url = new URL('http://localhost:8000/api/dashboard/stats/');
  url.searchParams.append('session_id', sessionId);
  url.searchParams.append('period', period);

  const response = await fetch(url, {
    method: 'GET',
    credentials: 'include'
  });

  const stats = await response.json();

  console.log(`Progress: ${stats.progress.percentage_complete}%`);
  console.log(`Pending conflicts: ${stats.overview.pending_conflicts}`);

  // Display reviewer breakdown
  stats.reviewer_breakdown.forEach((reviewer) => {
    console.log(`${reviewer.reviewer.username}: ${reviewer.total_reviews} reviews`);
  });

  return stats;
};
```

**Django Test (APIClient)**:
```python
def test_get_team_stats(self):
    response = self.client.get('/api/dashboard/stats/', {
        'session_id': str(self.session.id),
        'period': 'week'
    })

    self.assertEqual(response.status_code, 200)
    self.assertIn('overview', response.data)
    self.assertIn('team_performance', response.data)
    self.assertIn('inter_rater_reliability', response.data)
```

---

### Get Cohen's Kappa (IRR Metrics)

**curl**:
```bash
curl -X GET "http://localhost:8000/api/dashboard/irr/?session_id=550e8400-e29b-41d4-a716-446655440000" \
  -b cookies.txt
```

**Python (requests)**:
```python
session_id = '550e8400-e29b-41d4-a716-446655440000'

response = session.get(
    'http://localhost:8000/api/dashboard/irr/',
    params={'session_id': session_id}
)

irr_metrics = response.json()

for metric in irr_metrics:
    kappa = metric['cohens_kappa']
    r1 = metric['reviewer1']['username']
    r2 = metric['reviewer2']['username']

    print(f"{r1} vs {r2}:")
    print(f"  Cohen's Kappa: {kappa:.3f}")
    print(f"  Interpretation: {metric['interpretation']}")
    print(f"  % Agreement: {metric['percent_agreement']:.1f}%")
    print(f"  Samples: {metric['samples_compared']}")

    if kappa >= 0.70:
        print("  ✓ PASS (Cochrane threshold ≥0.70)")
    else:
        print("  ✗ FAIL (Below Cochrane threshold)")
```

**JavaScript (fetch)**:
```javascript
const getIRRMetrics = async (sessionId) => {
  const url = new URL('http://localhost:8000/api/dashboard/irr/');
  url.searchParams.append('session_id', sessionId);

  const response = await fetch(url, {
    method: 'GET',
    credentials: 'include'
  });

  const metrics = await response.json();

  metrics.forEach((metric) => {
    console.log(`${metric.reviewer1.username} vs ${metric.reviewer2.username}:`);
    console.log(`  Kappa: ${metric.cohens_kappa.toFixed(3)}`);
    console.log(`  Interpretation: ${metric.interpretation}`);
    console.log(`  Agreement: ${metric.percent_agreement.toFixed(1)}%`);

    if (metric.cohens_kappa >= 0.70) {
      console.log('  ✓ Cochrane compliant');
    } else {
      console.log('  ✗ Below threshold');
    }
  });

  return metrics;
};
```

**Django Test (APIClient)**:
```python
def test_get_irr_metrics(self):
    # Create IRR record
    irr = InterRaterReliability.objects.create(
        search_session=self.session,
        reviewer1=self.user,
        reviewer2=self.reviewer2,
        cohens_kappa=0.75,
        percent_agreement=85.0,
        samples_compared=100
    )

    response = self.client.get('/api/dashboard/irr/', {
        'session_id': str(self.session.id)
    })

    self.assertEqual(response.status_code, 200)
    self.assertEqual(len(response.data), 1)
    self.assertEqual(response.data[0]['cohens_kappa'], 0.75)
```

---

## Organisation Management

### Get Organisation Dashboard

**curl**:
```bash
curl -X GET http://localhost:8000/api/organisation/550e8400-e29b-41d4-a716-446655440000/dashboard/ \
  -b cookies.txt
```

**Python (requests)**:
```python
org_id = '550e8400-e29b-41d4-a716-446655440000'

response = session.get(f'http://localhost:8000/api/organisation/{org_id}/dashboard/')

dashboard = response.json()

print(f"Organisation: {dashboard['organisation']['name']}")
print(f"\nMetrics:")
print(f"  Total reviews: {dashboard['metrics']['total_reviews']}")
print(f"  Active reviews: {dashboard['metrics']['active_reviews']}")
print(f"  Avg Kappa: {dashboard['metrics']['avg_kappa_organisation']:.2f}")
print(f"  Reviews below threshold: {dashboard['metrics']['reviews_below_threshold']}")

print(f"\nRecent Activity:")
for activity in dashboard['recent_activity']:
    print(f"  {activity['review_title']}: {activity['status']}")
```

**JavaScript (fetch)**:
```javascript
const getOrgDashboard = async (orgId) => {
  const response = await fetch(
    `http://localhost:8000/api/organisation/${orgId}/dashboard/`,
    {
      method: 'GET',
      credentials: 'include'
    }
  );

  const dashboard = await response.json();

  console.log(`Organisation: ${dashboard.organisation.name}`);
  console.log(`Active reviews: ${dashboard.metrics.active_reviews}`);
  console.log(`Avg Kappa: ${dashboard.metrics.avg_kappa_organisation.toFixed(2)}`);

  return dashboard;
};
```

**Django Test (APIClient)**:
```python
def test_get_org_dashboard(self):
    response = self.client.get(f'/api/organisation/{self.org.id}/dashboard/')

    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.data['organisation']['id'], str(self.org.id))
    self.assertIn('metrics', response.data)
    self.assertIn('recent_activity', response.data)
```

---

## Error Handling

### Handling Common Errors

**Python (comprehensive error handling)**:
```python
import requests
from requests.exceptions import RequestException

def make_api_request(session, method, url, **kwargs):
    """Robust API request with error handling"""
    try:
        response = session.request(method, url, **kwargs)

        # Handle success
        if response.status_code in (200, 201, 202):
            return response.json()

        # Handle specific error codes
        elif response.status_code == 400:
            error_data = response.json()
            print(f"Validation error: {error_data.get('message')}")
            if 'errors' in error_data:
                for field, errors in error_data['errors'].items():
                    print(f"  {field}: {', '.join(errors)}")
            return None

        elif response.status_code == 401:
            print("Authentication required - please login")
            return None

        elif response.status_code == 403:
            print("Permission denied - insufficient privileges")
            return None

        elif response.status_code == 404:
            print("Resource not found")
            return None

        elif response.status_code == 409:
            error_data = response.json()
            print(f"Conflict: {error_data.get('message')}")
            return None

        elif response.status_code >= 500:
            print(f"Server error: {response.status_code}")
            return None

    except RequestException as e:
        print(f"Request failed: {e}")
        return None

# Usage example
result = make_api_request(
    session,
    'POST',
    'http://localhost:8000/api/results/claim/',
    json={'session_id': session_id},
    headers={'X-CSRFToken': csrf_token}
)
```

**JavaScript (async/await error handling)**:
```javascript
async function apiRequest(url, options = {}) {
  try {
    const response = await fetch(url, {
      ...options,
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken(),
        ...options.headers
      }
    });

    // Parse JSON response
    const data = await response.json();

    // Handle success
    if (response.ok) {
      return { success: true, data };
    }

    // Handle errors
    if (response.status === 400) {
      console.error('Validation error:', data.message);
      if (data.errors) {
        Object.entries(data.errors).forEach(([field, errors]) => {
          console.error(`  ${field}: ${errors.join(', ')}`);
        });
      }
    } else if (response.status === 401) {
      console.error('Authentication required');
      // Redirect to login
      window.location.href = '/accounts/login/';
    } else if (response.status === 403) {
      console.error('Permission denied');
    } else if (response.status === 404) {
      console.error('Resource not found');
    } else if (response.status === 409) {
      console.error('Conflict:', data.message);
    } else if (response.status >= 500) {
      console.error('Server error:', response.status);
    }

    return { success: false, error: data };

  } catch (error) {
    console.error('Network error:', error);
    return { success: false, error: { message: 'Network error' } };
  }
}

// Usage example
const result = await apiRequest('http://localhost:8000/api/results/claim/', {
  method: 'POST',
  body: JSON.stringify({ session_id: sessionId })
});

if (result.success) {
  console.log('Result:', result.data);
} else {
  console.error('Error:', result.error);
}
```

**Django Test (error case testing)**:
```python
def test_error_handling(self):
    # Test 400 - Validation error
    response = self.client.post('/api/results/claim/', {
        # Missing required session_id
    }, format='json')
    self.assertEqual(response.status_code, 400)
    self.assertIn('error', response.data)

    # Test 404 - Not found
    response = self.client.get('/api/results/00000000-0000-0000-0000-000000000000/')
    self.assertEqual(response.status_code, 404)

    # Test 403 - Permission denied
    other_user = User.objects.create_user(username='other', password='pass')
    self.client.force_authenticate(user=other_user)

    response = self.client.post(f'/api/conflicts/{self.conflict.id}/resolve/', {
        'resolution_method': 'CONSENSUS',
        'decision': 'INCLUDE'
    }, format='json')
    self.assertEqual(response.status_code, 403)

    # Test 409 - Conflict (already decided)
    decision = ReviewerDecision.objects.create(
        result=self.result,
        reviewer=self.user,
        decision='INCLUDE'
    )

    response = self.client.post(f'/api/results/{self.result.id}/decide/', {
        'decision': 'EXCLUDE'
    }, format='json')
    self.assertEqual(response.status_code, 409)
```

---

## Complete Workflow Examples

### End-to-End: Workflow #2 (Independent Screening)

**Python (complete workflow)**:
```python
import requests

# 1. Login
session = requests.Session()
session.post('http://localhost:8000/accounts/login/', data={
    'username': 'reviewer1',
    'password': 'SecurePass123!'
})

csrf_token = session.cookies.get('csrftoken')

# 2. Create session
response = session.post(
    'http://localhost:8000/api/review-manager/sessions/',
    headers={'X-CSRFToken': csrf_token},
    json={
        'title': 'Telehealth Review',
        'description': 'Independent screening with dual reviewers'
    }
)
session_id = response.json()['id']

# 3. Claim next result
response = session.post(
    'http://localhost:8000/api/results/claim/',
    headers={'X-CSRFToken': csrf_token},
    json={'session_id': session_id}
)
result = response.json()

# 4. Submit decision
response = session.post(
    f'http://localhost:8000/api/results/{result["id"]}/decide/',
    headers={'X-CSRFToken': csrf_token},
    json={
        'decision': 'INCLUDE',
        'confidence_level': 3,
        'notes': 'Meets all criteria'
    }
)
decision_response = response.json()

# 5. Check for conflicts (after both reviewers complete)
if decision_response['status'] == 'conflict_detected':
    # Get conflicts
    response = session.get(
        'http://localhost:8000/api/conflicts/',
        params={'session_id': session_id, 'status': 'PENDING'}
    )
    conflicts = response.json()['results']

    # Discuss first conflict
    conflict_id = conflicts[0]['id']
    session.post(
        f'http://localhost:8000/api/conflicts/{conflict_id}/comments/',
        headers={'X-CSRFToken': csrf_token},
        json={'content': 'Let's discuss this result', 'parent_id': None}
    )

    # Resolve after consensus
    session.post(
        f'http://localhost:8000/api/conflicts/{conflict_id}/resolve/',
        headers={'X-CSRFToken': csrf_token},
        json={
            'resolution_method': 'CONSENSUS',
            'decision': 'INCLUDE',
            'notes': 'Agreed to include'
        }
    )

# 6. Get IRR metrics
response = session.get(
    'http://localhost:8000/api/dashboard/irr/',
    params={'session_id': session_id}
)
irr_metrics = response.json()

for metric in irr_metrics:
    print(f"Cohen's Kappa: {metric['cohens_kappa']:.2f}")
    if metric['cohens_kappa'] >= 0.70:
        print("✓ PRISMA 2020 compliant")
```

---

## Related Documentation

- **OpenAPI Specification**: `docs/api/openapi.yaml`
- **E2E Application Flow**: `docs/architecture/E2E-APPLICATION-FLOW.md`
- **Dual-Workflow Architecture**: `docs/workflows/DUAL_WORKFLOW_ARCHITECTURE.md`
- **User Guide**: `docs/guides/DUAL_WORKFLOW_USER_GUIDE.md`

---

**Document Version**: 1.0.0
**Last Updated**: 2025-11-02
**Maintained By**: Agent Grey Development Team
