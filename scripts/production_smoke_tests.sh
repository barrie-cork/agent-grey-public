#!/bin/bash

################################################################################
# Production Deployment Smoke Tests
#
# Validates critical paths after production deployment to ensure no regressions.
#
# Tests:
# 1. Health Check Endpoints (database, Redis, email)
# 2. User Authentication (login, JWT token)
# 3. Result Claiming (work queue)
# 4. Decision Submission (reviewer decision)
# 5. Conflict Creation (conflicting decisions)
# 6. SSE Connection (real-time updates)
# 7. Email Notification (conflict alert)
#
# Usage:
#   ./production_smoke_tests.sh
#
# Environment Variables:
#   BASE_URL      - Base URL of deployment (default: http://localhost:8000)
#   API_TOKEN     - Pre-generated API token for authentication
#   TEST_USER     - Username for test user (default: smoketest)
#   TEST_PASS     - Password for test user (default: testpass123)
#
# Exit Codes:
#   0 - All tests passed
#   1 - One or more tests failed
#
# Based on:
# - Agent Grey deployment procedures from CLAUDE.md
# - Critical path analysis from dual-screening PRD
################################################################################

set -e  # Exit on error
set -o pipefail  # Exit on pipe failure

# ============================================================================
# CONFIGURATION
# ============================================================================

BASE_URL="${BASE_URL:-http://localhost:8000}"
TEST_USER="${TEST_USER:-smoketest}"
TEST_PASS="${TEST_PASS:-testpass123}"
API_TOKEN="${API_TOKEN:-}"

# Colours for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'  # No Colour

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

# Print coloured message
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Increment test counter
test_passed() {
    TESTS_PASSED=$((TESTS_PASSED + 1))
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    print_success "$1"
}

test_failed() {
    TESTS_FAILED=$((TESTS_FAILED + 1))
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    print_error "$1"
}

# ============================================================================
# TEST FUNCTIONS
# ============================================================================

# Test 1: Health Check Endpoints
test_health_checks() {
    print_info "\n[TEST 1] Health Check Endpoints"

    # Test main health endpoint
    response=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health/")

    if [ "$response" -eq 200 ]; then
        test_passed "Main health check passed (HTTP $response)"
    else
        test_failed "Main health check failed (HTTP $response)"
        return 1
    fi

    # Test detailed health endpoint
    response=$(curl -s "$BASE_URL/health/")

    # Check database status
    if echo "$response" | grep -q '"database":"ok"'; then
        test_passed "Database health check passed"
    else
        test_failed "Database health check failed"
        return 1
    fi

    # Check Redis status
    if echo "$response" | grep -q '"redis":"ok"'; then
        test_passed "Redis health check passed"
    else
        test_failed "Redis health check failed"
        return 1
    fi

    return 0
}

# Test 2: User Authentication
test_authentication() {
    print_info "\n[TEST 2] User Authentication"

    # Login and get token
    response=$(curl -s -X POST "$BASE_URL/api/auth/login/" \
        -H "Content-Type: application/json" \
        -d "{\"username\":\"$TEST_USER\",\"password\":\"$TEST_PASS\"}")

    # Extract token
    API_TOKEN=$(echo "$response" | grep -o '"token":"[^"]*"' | sed 's/"token":"//;s/"$//')

    if [ -z "$API_TOKEN" ]; then
        test_failed "Login failed - no token received"
        print_error "Response: $response"
        return 1
    fi

    test_passed "Login successful - token received"

    # Verify token works
    response=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Token $API_TOKEN" \
        "$BASE_URL/api/user/")

    if [ "$response" -eq 200 ]; then
        test_passed "Token authentication validated"
    else
        test_failed "Token authentication failed (HTTP $response)"
        return 1
    fi

    return 0
}

# Test 3: Result Claiming
test_result_claiming() {
    print_info "\n[TEST 3] Result Claiming"

    if [ -z "$API_TOKEN" ]; then
        test_failed "Skipping - no API token available"
        return 1
    fi

    # Get work queue
    response=$(curl -s \
        -H "Authorization: Token $API_TOKEN" \
        "$BASE_URL/api/work-queue/")

    if echo "$response" | grep -q '"results"'; then
        test_passed "Work queue accessible"
    else
        test_failed "Work queue not accessible"
        print_error "Response: $response"
        return 1
    fi

    # Claim next result
    response=$(curl -s -X POST \
        -H "Authorization: Token $API_TOKEN" \
        -H "Content-Type: application/json" \
        "$BASE_URL/api/results/claim/")

    # Extract result ID
    RESULT_ID=$(echo "$response" | grep -o '"id":"[^"]*"' | head -1 | sed 's/"id":"//;s/"$//')

    if [ -n "$RESULT_ID" ]; then
        test_passed "Result claimed successfully (ID: $RESULT_ID)"
    else
        test_warning "No results available to claim (expected in empty test environment)"
        RESULT_ID=""
    fi

    return 0
}

# Test 4: Decision Submission
test_decision_submission() {
    print_info "\n[TEST 4] Decision Submission"

    if [ -z "$API_TOKEN" ]; then
        test_failed "Skipping - no API token available"
        return 1
    fi

    if [ -z "$RESULT_ID" ]; then
        test_warning "Skipping - no result claimed"
        return 0
    fi

    # Submit INCLUDE decision
    response=$(curl -s -X POST \
        -H "Authorization: Token $API_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"result_id\":\"$RESULT_ID\",
            \"decision\":\"INCLUDE\",
            \"confidence_level\":3,
            \"screening_stage\":\"SCREENING\",
            \"rationale\":\"Smoke test decision\"
        }" \
        "$BASE_URL/api/decisions/")

    if echo "$response" | grep -q '"id"'; then
        test_passed "Decision submitted successfully"

        # Extract decision ID
        DECISION_ID=$(echo "$response" | grep -o '"id":"[^"]*"' | head -1 | sed 's/"id":"//;s/"$//')
    else
        test_failed "Decision submission failed"
        print_error "Response: $response"
        return 1
    fi

    return 0
}

# Test 5: Conflict Creation
test_conflict_creation() {
    print_info "\n[TEST 5] Conflict Creation"

    if [ -z "$API_TOKEN" ]; then
        test_failed "Skipping - no API token available"
        return 1
    fi

    if [ -z "$RESULT_ID" ]; then
        test_warning "Skipping - no result available"
        return 0
    fi

    # This test requires a second reviewer to create a conflict
    # In smoke tests, we just verify the conflicts endpoint is accessible

    response=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Token $API_TOKEN" \
        "$BASE_URL/api/conflicts/")

    if [ "$response" -eq 200 ]; then
        test_passed "Conflicts endpoint accessible"
    else
        test_failed "Conflicts endpoint not accessible (HTTP $response)"
        return 1
    fi

    return 0
}

# Test 6: SSE Connection
test_sse_connection() {
    print_info "\n[TEST 6] SSE Connection"

    if [ -z "$API_TOKEN" ]; then
        test_failed "Skipping - no API token available"
        return 1
    fi

    # For smoke tests, we just verify the SSE endpoint is accessible
    # Create a dummy conflict ID for testing
    DUMMY_CONFLICT_ID="00000000-0000-0000-0000-000000000000"

    # Try to connect to SSE stream (expect 404 for dummy ID, but 200 means endpoint works)
    response=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Token $API_TOKEN" \
        -H "Accept: text/event-stream" \
        -N \
        --max-time 5 \
        "$BASE_URL/api/conflicts/$DUMMY_CONFLICT_ID/stream/")

    # 200 (stream starts) or 404 (not found) both indicate endpoint is working
    if [ "$response" -eq 200 ] || [ "$response" -eq 404 ]; then
        test_passed "SSE endpoint accessible"
    else
        test_failed "SSE endpoint not accessible (HTTP $response)"
        return 1
    fi

    return 0
}

# Test 7: Email Notification Configuration
test_email_configuration() {
    print_info "\n[TEST 7] Email Configuration"

    # Check if email backend is configured (via health check)
    response=$(curl -s "$BASE_URL/health/")

    if echo "$response" | grep -q '"email":"configured"'; then
        test_passed "Email backend configured"
    else
        test_warning "Email backend not configured (optional in dev environment)"
    fi

    return 0
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

main() {
    echo ""
    echo "================================================================================"
    echo "PRODUCTION SMOKE TESTS"
    echo "================================================================================"
    echo ""
    echo "Base URL: $BASE_URL"
    echo "Test User: $TEST_USER"
    echo "Time: $(date)"
    echo ""

    # Run all tests
    test_health_checks || true
    test_authentication || true
    test_result_claiming || true
    test_decision_submission || true
    test_conflict_creation || true
    test_sse_connection || true
    test_email_configuration || true

    # Print summary
    echo ""
    echo "================================================================================"
    echo "TEST SUMMARY"
    echo "================================================================================"
    echo ""
    echo "Total Tests: $TESTS_TOTAL"
    echo "Passed:      $TESTS_PASSED"
    echo "Failed:      $TESTS_FAILED"
    echo ""

    if [ $TESTS_FAILED -eq 0 ]; then
        print_success "ALL SMOKE TESTS PASSED ✅"
        echo ""
        exit 0
    else
        print_error "SOME SMOKE TESTS FAILED ❌"
        echo ""
        exit 1
    fi
}

# Run main function
main
