"""
API Response Time Benchmarking

Measures response times for all critical API endpoints and validates
against performance targets (p50 <200ms, p95 <500ms, p99 <1000ms).

Usage:
    python scripts/benchmark_api.py

Requirements:
    pip install requests

Environment Variables:
    BASE_URL - Base URL (default: http://localhost:8000)
    API_TOKEN - Authentication token
    TEST_USER - Test username (default: reviewer1)
    TEST_PASS - Test password (default: testpass123)
"""

import time
import statistics
import requests
import os
import sys
from typing import List, Dict

# Configuration
BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000')
API_TOKEN = os.getenv('API_TOKEN', '')
TEST_USER = os.getenv('TEST_USER', 'reviewer1')
TEST_PASS = os.getenv('TEST_PASS', 'testpass123')

# API endpoints to benchmark
ENDPOINTS = [
    {'method': 'GET', 'url': '/api/work-queue/', 'name': 'Work Queue List', 'auth': True},
    {'method': 'GET', 'url': '/api/conflicts/', 'name': 'Conflicts List', 'auth': True},
    {'method': 'GET', 'url': '/api/dashboard/stats/', 'name': 'Dashboard Stats', 'auth': True},
    {'method': 'GET', 'url': '/api/dashboard/irr/', 'name': 'IRR Metrics', 'auth': True},
    {'method': 'GET', 'url': '/health/', 'name': 'Health Check', 'auth': False},
]

def get_auth_token() -> str:
    """Get authentication token by logging in."""
    global API_TOKEN

    if API_TOKEN:
        return API_TOKEN

    print(f"Logging in as {TEST_USER}...")

    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/login/",
            json={'username': TEST_USER, 'password': TEST_PASS},
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            API_TOKEN = data.get('token', '')
            print("✅ Login successful")
            return API_TOKEN
        else:
            print(f"❌ Login failed: {response.status_code}")
            return ''
    except Exception as e:
        print(f"❌ Login error: {str(e)}")
        return ''

def benchmark_endpoint(endpoint: Dict, iterations: int = 100) -> Dict:
    """Benchmark single endpoint."""
    response_times = []

    print(f"\nBenchmarking: {endpoint['name']}")
    print(f"Iterations: {iterations}")

    # Prepare headers
    headers = {}
    if endpoint.get('auth', False):
        token = get_auth_token()
        if not token:
            return {
                'name': endpoint['name'],
                'error': 'Authentication failed',
                'iterations': 0
            }
        headers['Authorization'] = f'Token {token}'

    successful_requests = 0
    failed_requests = 0

    for i in range(iterations):
        try:
            start = time.perf_counter()

            # Make request
            if endpoint['method'] == 'GET':
                response = requests.get(
                    f"{BASE_URL}{endpoint['url']}",
                    headers=headers,
                    timeout=10
                )
            elif endpoint['method'] == 'POST':
                response = requests.post(
                    f"{BASE_URL}{endpoint['url']}",
                    json={},
                    headers=headers,
                    timeout=10
                )

            end = time.perf_counter()
            elapsed_ms = (end - start) * 1000

            if response.status_code < 500:  # Count 4xx as successful (expected errors)
                response_times.append(elapsed_ms)
                successful_requests += 1
            else:
                failed_requests += 1

            # Progress indicator
            if (i + 1) % 10 == 0:
                print(f"  Progress: {i + 1}/{iterations} (Success: {successful_requests}, Failed: {failed_requests})")

        except Exception as e:
            failed_requests += 1
            if (i + 1) % 10 == 0:
                print(f"  Progress: {i + 1}/{iterations} (Success: {successful_requests}, Failed: {failed_requests}) - Last error: {str(e)[:50]}")

    if not response_times:
        return {
            'name': endpoint['name'],
            'error': f'All {iterations} requests failed',
            'iterations': iterations,
            'failed': failed_requests
        }

    # Calculate percentiles
    response_times.sort()
    p50 = statistics.median(response_times)
    p95 = response_times[int(len(response_times) * 0.95)] if len(response_times) > 0 else 0
    p99 = response_times[int(len(response_times) * 0.99)] if len(response_times) > 0 else 0

    return {
        'name': endpoint['name'],
        'p50': round(p50, 2),
        'p95': round(p95, 2),
        'p99': round(p99, 2),
        'min': round(min(response_times), 2),
        'max': round(max(response_times), 2),
        'mean': round(statistics.mean(response_times), 2),
        'iterations': len(response_times),
        'failed': failed_requests
    }

def validate_thresholds(results: List[Dict]) -> bool:
    """Validate results against performance thresholds."""
    print("\n" + "="*80)
    print("PERFORMANCE VALIDATION RESULTS")
    print("="*80)

    all_pass = True

    print(f"\n{'Endpoint':<30} {'p50':<10} {'p95':<10} {'p99':<10} {'Status':<10}")
    print("-"*80)

    for result in results:
        if 'error' in result:
            print(f"{result['name']:<30} {'ERROR':<10} {'ERROR':<10} {'ERROR':<10} {'❌ FAIL':<10}")
            print(f"  Error: {result['error']}")
            all_pass = False
            continue

        # Check thresholds
        p50_pass = result['p50'] < 200
        p95_pass = result['p95'] < 500
        p99_pass = result['p99'] < 1000

        status = "✅ PASS" if (p50_pass and p95_pass) else "❌ FAIL"

        if not (p50_pass and p95_pass):
            all_pass = False

        print(f"{result['name']:<30} "
              f"{result['p50']:<10.2f} "
              f"{result['p95']:<10.2f} "
              f"{result['p99']:<10.2f} "
              f"{status:<10}")

        # Show failures
        if not p50_pass:
            print(f"  ⚠️  p50 {result['p50']:.2f}ms exceeds 200ms threshold")
        if not p95_pass:
            print(f"  ⚠️  p95 {result['p95']:.2f}ms exceeds 500ms threshold")
        if not p99_pass and p99_pass is not None:
            print(f"  ⚠️  p99 {result['p99']:.2f}ms exceeds 1000ms threshold (warning)")

        # Show additional metrics
        if result.get('failed', 0) > 0:
            print(f"  ⚠️  {result['failed']} requests failed out of {result['iterations'] + result['failed']}")

    print("\n" + "="*80)
    print(f"OVERALL: {'✅ ALL PASS' if all_pass else '❌ SOME FAILURES'}")
    print("="*80 + "\n")

    return all_pass

def main():
    """Main execution function."""
    print("\n" + "="*80)
    print("API PERFORMANCE BENCHMARKING")
    print("="*80)
    print(f"\nBase URL: {BASE_URL}")
    print(f"Test User: {TEST_USER}")
    print(f"Endpoints: {len(ENDPOINTS)}")
    print("Iterations per endpoint: 100")
    print("\nThresholds:")
    print("  p50: <200ms")
    print("  p95: <500ms")
    print("  p99: <1000ms (warning)")
    print("="*80)

    results = []

    for endpoint in ENDPOINTS:
        result = benchmark_endpoint(endpoint, iterations=100)
        results.append(result)

    # Validate and exit with appropriate code
    all_pass = validate_thresholds(results)

    return 0 if all_pass else 1

if __name__ == '__main__':
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n❌ Benchmarking interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
