# Agent Grey API Documentation

**Version**: 1.0.0
**Last Updated**: 2025-11-02

---

## 📚 Documentation Index

| Document | Purpose | Audience |
|----------|---------|----------|
| **[openapi.yaml](./openapi.yaml)** | Complete OpenAPI 3.0 specification | Developers, API clients, code generators |
| **[API-EXAMPLES.md](./API-EXAMPLES.md)** | Code examples in 4 languages (curl, Python, JavaScript, Django) | Developers integrating with API |
| **[E2E-APPLICATION-FLOW.md](../architecture/E2E-APPLICATION-FLOW.md)** | Complete application architecture | Developers, architects |

---

## 🚀 Quick Start

### Using Interactive Documentation

Agent Grey provides interactive API documentation via Django Spectacular:

1. **Swagger UI** (recommended for testing):
   ```
   http://localhost:8000/api/docs/
   ```

2. **ReDoc** (better for reading):
   ```
   http://localhost:8000/api/redoc/
   ```

3. **OpenAPI Schema** (JSON):
   ```
   http://localhost:8000/api/schema/
   ```

### Example: First API Call

**curl**:
```bash
# 1. Login (save cookies)
curl -X POST http://localhost:8000/accounts/login/ \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=reviewer1&password=SecurePass123!" \
  -c cookies.txt

# 2. List sessions
curl -X GET http://localhost:8000/api/review-manager/sessions/ \
  -b cookies.txt
```

**Python**:
```python
import requests

session = requests.Session()
session.post('http://localhost:8000/accounts/login/', data={
    'username': 'reviewer1',
    'password': 'SecurePass123!'
})

response = session.get('http://localhost:8000/api/review-manager/sessions/')
print(response.json())
```

**JavaScript**:
```javascript
// Login
await fetch('http://localhost:8000/accounts/login/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  body: new URLSearchParams({ username: 'reviewer1', password: 'SecurePass123!' }),
  credentials: 'include'
});

// List sessions
const response = await fetch('http://localhost:8000/api/review-manager/sessions/', {
  credentials: 'include'
});
const sessions = await response.json();
```

---

## 🔑 Authentication

All API endpoints (except `/health/` and authentication endpoints) require Django session authentication.

### Authentication Flow

```
1. POST /accounts/login/      → Receive sessionid cookie
2. Include cookie in requests  → Access protected endpoints
3. Include X-CSRFToken header  → For POST/PUT/PATCH/DELETE requests
```

### CSRF Protection

For modifying operations (POST, PUT, PATCH, DELETE), include the CSRF token:

**Extract from cookie**:
```javascript
const csrfToken = document.cookie.match(/csrftoken=([^;]+)/)?.[1];
```

**Include in request headers**:
```
X-CSRFToken: <token>
```

---

## 📊 API Overview

### Endpoint Categories

| Category | Endpoints | Description |
|----------|-----------|-------------|
| **Authentication** | 4 endpoints | Login, signup, logout, profile |
| **Sessions** | 8 endpoints | Create, list, status, SSE streams |
| **Review - Core** | 6 endpoints | Claim, decide, release (Workflow #1 & #2) |
| **Review - Conflicts** | 9 endpoints | List, discuss, resolve, SSE (Workflow #2) |
| **Review - Dashboard** | 3 endpoints | Stats, IRR metrics, progress |
| **Organisation** | 4 endpoints | Dashboard, reviews, invitations, quality reports |
| **Health** | 3 endpoints | Health checks, readiness probes |

**Total**: 65+ documented endpoints

### Key Workflows

**Workflow #1: Work Distribution** (Single-reviewer per result):
```
1. POST /api/results/claim/          # Claim next result
2. POST /api/results/{id}/decide/    # Submit decision
3. Repeat until all results reviewed
```

**Workflow #2: Independent Screening** (Multi-reviewer with conflicts):
```
1. POST /api/results/{id}/decide/           # Both reviewers decide independently
2. GET /api/conflicts/?session_id={uuid}   # List conflicts (auto-detected)
3. POST /api/conflicts/{id}/discuss/        # Threaded discussion
4. POST /api/conflicts/{id}/resolve/        # Resolve via consensus/arbitration
5. GET /api/dashboard/irr/?session_id={}   # Cohen's Kappa metrics
```

---

## 📖 API Structure

### Request Format

All JSON API endpoints accept:
```json
{
  "field_name": "value",
  "nested_object": {
    "key": "value"
  }
}
```

### Response Format

**Success** (200/201/202):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "field": "value",
  ...
}
```

**Error** (400/401/403/404/409/500):
```json
{
  "error": "error_code",
  "message": "Human-readable error message",
  "errors": {
    "field_name": ["Error 1", "Error 2"]
  }
}
```

### Pagination

Paginated endpoints return:
```json
{
  "count": 100,
  "page": 1,
  "num_pages": 5,
  "next": true,
  "previous": false,
  "results": [...]
}
```

**Query Parameters**:
- `page` (integer, default: 1)
- `per_page` (integer, default: 20, max: 100)

---

## 🔍 OpenAPI Specification

### Using the OpenAPI Spec

**Generate Client Libraries**:
```bash
# Install OpenAPI Generator
npm install @openapitools/openapi-generator-cli -g

# Generate Python client
openapi-generator-cli generate \
  -i docs/api/openapi.yaml \
  -g python \
  -o clients/python

# Generate TypeScript client
openapi-generator-cli generate \
  -i docs/api/openapi.yaml \
  -g typescript-fetch \
  -o clients/typescript
```

**Validate Spec**:
```bash
# Install Swagger CLI
npm install -g @apidevtools/swagger-cli

# Validate
swagger-cli validate docs/api/openapi.yaml

# Generate JSON
swagger-cli bundle docs/api/openapi.yaml \
  --outfile docs/api/openapi.json \
  --type json
```

**Import to Postman**:
1. Open Postman
2. Click Import → File → Upload `docs/api/openapi.yaml`
3. Auto-generates collection with all endpoints

---

## 🧪 Testing

### Manual Testing (curl)

```bash
# Health check (no auth)
curl http://localhost:8000/health/

# Login and test authenticated endpoint
curl -X POST http://localhost:8000/accounts/login/ \
  -d "username=reviewer1&password=pass" \
  -c cookies.txt

curl http://localhost:8000/api/review-manager/sessions/ \
  -b cookies.txt
```

### Automated Testing (Django)

```python
from rest_framework.test import APIClient

client = APIClient()
client.force_authenticate(user=user)

response = client.get('/api/review-manager/sessions/')
assert response.status_code == 200
```

### Load Testing (Apache Bench)

```bash
# Test health endpoint
ab -n 1000 -c 10 http://localhost:8000/health/

# Test authenticated endpoint (requires session)
ab -n 100 -c 5 \
  -H "Cookie: sessionid=abc123..." \
  http://localhost:8000/api/review-manager/sessions/
```

---

## 🚨 Common Issues

### Issue: 403 Forbidden (CSRF)

**Cause**: Missing or invalid CSRF token

**Solution**:
```bash
# Include CSRF token in header
curl -X POST http://localhost:8000/api/results/claim/ \
  -b cookies.txt \
  -H "X-CSRFToken: ${CSRF_TOKEN}" \
  -d '{"session_id": "uuid"}'
```

### Issue: 401 Unauthorized

**Cause**: Not authenticated or session expired

**Solution**:
```bash
# Login again
curl -X POST http://localhost:8000/accounts/login/ \
  -d "username=user&password=pass" \
  -c cookies.txt
```

### Issue: 400 Validation Error

**Cause**: Invalid request body

**Solution**: Check error response for field-specific errors:
```json
{
  "error": "validation_error",
  "errors": {
    "decision": ["This field is required"]
  }
}
```

---

## 📦 SDKs & Libraries

### Recommended Libraries

**Python**:
- `requests` - HTTP client with session support
- `httpx` - Async HTTP client

**JavaScript**:
- `fetch` API (built-in, recommended)
- `axios` - Promise-based HTTP client

**Django Testing**:
- `APIClient` (Django REST Framework)
- `pytest-django` - Testing framework

### Example: Python SDK Wrapper

```python
import requests

class AgentGreyAPI:
    def __init__(self, base_url='http://localhost:8000'):
        self.base_url = base_url
        self.session = requests.Session()

    def login(self, username, password):
        response = self.session.post(
            f'{self.base_url}/accounts/login/',
            data={'username': username, 'password': password}
        )
        self.csrf_token = self.session.cookies.get('csrftoken')
        return response.status_code == 302

    def get_sessions(self):
        return self.session.get(f'{self.base_url}/api/review-manager/sessions/').json()

    def claim_result(self, session_id):
        return self.session.post(
            f'{self.base_url}/api/results/claim/',
            headers={'X-CSRFToken': self.csrf_token},
            json={'session_id': session_id}
        ).json()

# Usage
api = AgentGreyAPI()
api.login('reviewer1', 'pass')
sessions = api.get_sessions()
```

---

## 🔗 Related Resources

### Internal Documentation

- **Architecture**: `docs/architecture/E2E-APPLICATION-FLOW.md`
- **Workflows**: `docs/workflows/DUAL_WORKFLOW_ARCHITECTURE.md`
- **User Guide**: `docs/guides/DUAL_WORKFLOW_USER_GUIDE.md`
- **Deployment**: `docs/deployment/DIGITALOCEAN-CONFIGURATION.md`

### External Resources

- **OpenAPI Specification**: https://swagger.io/specification/
- **Django REST Framework**: https://www.django-rest-framework.org/
- **Django Spectacular**: https://drf-spectacular.readthedocs.io/
- **PRISMA 2020**: https://www.prisma-statement.org/

---

## 🤝 Support

### Questions?

- **Documentation Issues**: Create issue at GitHub repository
- **API Bugs**: Report via `/feedback/submit/` endpoint
- **Feature Requests**: Submit to product team

### Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-11-02 | Initial OpenAPI 3.0 specification |

---

**Maintained By**: Agent Grey Development Team
**License**: MIT
**Last Updated**: 2025-11-02
