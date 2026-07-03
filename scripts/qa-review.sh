#!/usr/bin/env bash
# QA Review Script for Agent Grey
# Used by gemini-worker (or any agent) to validate PRs before merge.
#
# Note: Ruff lint/format, Django tests, and security checks run in CI (test.yml).
# This script covers local-only checks: type checking and migration health.
#
# Usage: bash scripts/qa-review.sh [--pr NUMBER]

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0

pr_number=""
while [[ $# -gt 0 ]]; do
    case ${1:-} in
        --pr)
            if [[ ${2:-} == "" || ${2:-} == "--"* ]]; then
                echo "Error: --pr requires a PR number argument"
                echo "Usage: bash scripts/qa-review.sh [--pr NUMBER]"
                exit 1
            fi
            pr_number="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

check() {
    local name="$1"
    shift
    echo -n "  $name... "
    if "$@" > /tmp/qa-check-output.txt 2>&1; then
        echo -e "${GREEN}PASS${NC}"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}FAIL${NC}"
        tail -5 /tmp/qa-check-output.txt | sed 's/^/    /'
        FAIL=$((FAIL + 1))
    fi
}

warn_check() {
    local name="$1"
    shift
    echo -n "  $name... "
    if "$@" > /tmp/qa-check-output.txt 2>&1; then
        echo -e "${GREEN}PASS${NC}"
        PASS=$((PASS + 1))
    else
        echo -e "${YELLOW}WARN${NC}"
        tail -3 /tmp/qa-check-output.txt | sed 's/^/    /'
        WARN=$((WARN + 1))
    fi
}

echo "========================================"
echo "  Agent Grey QA Review (local checks)"
echo "  Ruff, tests, and security run in CI."
if [ -n "$pr_number" ]; then
    echo "  PR #${pr_number}"
fi
echo "  $(date '+%Y-%m-%d %H:%M')"
echo "========================================"
echo ""

# --- Type Checking ---
echo "== Type Checking =="
warn_check "basedpyright" pipx run basedpyright apps/ 2>/dev/null
echo ""

# --- Migration Health ---
echo "== Migration Health =="
check "Migration check" sg docker -c "docker compose exec -T web python scripts/check-migration-health.py"
echo ""

# --- PR-specific checks ---
if [ -n "$pr_number" ]; then
    echo "== PR #${pr_number} Checks =="

    # Get changed files
    changed_files=$(gh pr diff "$pr_number" --name-only 2>/dev/null || echo "")
    if [ -n "$changed_files" ]; then
        file_count=$(echo "$changed_files" | wc -l)
        echo "  Changed files: ${file_count}"

        # Check for migration files
        migration_files=$(echo "$changed_files" | grep -c "migrations/" || true)
        if [ "$migration_files" -gt 0 ]; then
            echo -e "  Migrations included: ${GREEN}YES${NC} (${migration_files} files)"
        fi

        # Check for test files
        test_files=$(echo "$changed_files" | grep -c "test" || true)
        if [ "$test_files" -gt 0 ]; then
            echo -e "  Test coverage: ${GREEN}YES${NC} (${test_files} test files)"
        else
            echo -e "  Test coverage: ${YELLOW}WARN${NC} -- no test files in diff"
            WARN=$((WARN + 1))
        fi

        # Check for env/secret patterns in changed files
        if gh pr diff "$pr_number" 2>/dev/null | grep -qiE '(password|secret|api_key|token)\s*=\s*["\x27][^"\x27]'; then
            echo -e "  Hardcoded secrets: ${RED}FAIL${NC} -- potential secrets in diff"
            FAIL=$((FAIL + 1))
        else
            echo -e "  Hardcoded secrets: ${GREEN}PASS${NC}"
            PASS=$((PASS + 1))
        fi
    else
        echo "  Could not fetch PR diff"
    fi
    echo ""
fi

# --- Summary ---
echo "========================================"
echo "  Results: ${GREEN}${PASS} passed${NC}, ${RED}${FAIL} failed${NC}, ${YELLOW}${WARN} warnings${NC}"
echo "========================================"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
