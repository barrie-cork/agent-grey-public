#!/bin/bash
# Production Environment Validation Script
# Validates .env.production.local before deployment
# Usage: ./scripts/validate-production-env.sh

# Note: We don't use 'set -e' because we want to check all items even if some fail

# Colours for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Colour

ENV_FILE=".env.production.local"

echo "=================================================="
echo "Agent Grey - Production Environment Validation"
echo "Django 5.2.7 Deployment"
echo "=================================================="
echo ""

# Check if .env.production.local exists
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}✗ ERROR: $ENV_FILE not found${NC}"
    echo "  Run: cp .env.production.local.template .env.production.local"
    exit 1
fi

echo -e "${GREEN}✓${NC} $ENV_FILE exists"
echo ""

# Validation counters
ERRORS=0
WARNINGS=0
SUCCESS=0

# Function to check for TODO markers
check_todo() {
    local key=$1
    local description=$2
    if grep -q "^${key}=TODO" "$ENV_FILE" 2>/dev/null; then
        echo -e "${RED}✗ ${key}${NC} - ${description} (TODO marker found)"
        ((ERRORS++))
    elif grep -q "^${key}=REPLACE" "$ENV_FILE" 2>/dev/null; then
        echo -e "${RED}✗ ${key}${NC} - ${description} (REPLACE marker found)"
        ((ERRORS++))
    elif grep -q "^${key}=.*FILL.*IN" "$ENV_FILE" 2>/dev/null; then
        echo -e "${RED}✗ ${key}${NC} - ${description} (FILL IN marker found)"
        ((ERRORS++))
    else
        if grep -q "^${key}=.\\{1,\\}" "$ENV_FILE" 2>/dev/null; then
            echo -e "${GREEN}✓ ${key}${NC} - Configured"
            ((SUCCESS++))
        else
            echo -e "${YELLOW}⚠ ${key}${NC} - Not set (optional)"
            ((WARNINGS++))
        fi
    fi
}

# Function to check secret key length
check_secret_key_length() {
    local secret_key=$(grep "^SECRET_KEY=" "$ENV_FILE" | sed 's/^SECRET_KEY=//')
    local length=${#secret_key}

    if [ $length -lt 50 ]; then
        echo -e "${RED}✗ SECRET_KEY${NC} - Too short (${length} chars, minimum 50)"
        ((ERRORS++))
    else
        echo -e "${GREEN}✓ SECRET_KEY${NC} - Length OK (${length} chars)"
        ((SUCCESS++))
    fi
}

# Function to check DEBUG is False
check_debug_false() {
    if grep -q "^DEBUG=False" "$ENV_FILE"; then
        echo -e "${GREEN}✓ DEBUG${NC} - Set to False (correct for production)"
        ((SUCCESS++))
    else
        echo -e "${RED}✗ DEBUG${NC} - MUST be False in production"
        ((ERRORS++))
    fi
}

# Function to check Redis URL uses SSL
check_redis_ssl() {
    if grep -q "^REDIS_URL=rediss://" "$ENV_FILE"; then
        echo -e "${GREEN}✓ REDIS_URL${NC} - Using SSL (rediss://)"
        ((SUCCESS++))
    elif grep -q "^REDIS_URL=redis://" "$ENV_FILE"; then
        echo -e "${RED}✗ REDIS_URL${NC} - NOT using SSL (should be rediss:// not redis://)"
        ((ERRORS++))
    elif grep -q "^REDIS_URL=TODO" "$ENV_FILE"; then
        echo -e "${RED}✗ REDIS_URL${NC} - Not configured (TODO marker found)"
        ((ERRORS++))
    else
        echo -e "${YELLOW}⚠ REDIS_URL${NC} - Cannot verify SSL protocol"
        ((WARNINGS++))
    fi
}

# Function to check Sentry release tag
check_sentry_release() {
    if grep -q "^SENTRY_RELEASE=django-5.2.7-6f03d44" "$ENV_FILE"; then
        echo -e "${GREEN}✓ SENTRY_RELEASE${NC} - Correct tag (django-5.2.7-6f03d44)"
        ((SUCCESS++))
    else
        echo -e "${YELLOW}⚠ SENTRY_RELEASE${NC} - Does not match expected tag (django-5.2.7-6f03d44)"
        ((WARNINGS++))
    fi
}

echo "=== CRITICAL SETTINGS ==="
echo ""
check_secret_key_length
check_debug_false
echo ""

echo "=== DATABASE CONFIGURATION ==="
echo ""
check_todo "DATABASE_URL" "DigitalOcean PostgreSQL URL"
echo ""

echo "=== REDIS & CACHING ==="
echo ""
check_redis_ssl
check_todo "CELERY_BROKER_URL" "Celery broker (Redis DB 0)"
check_todo "CELERY_RESULT_BACKEND" "Celery results (Redis DB 1)"
echo ""

echo "=== EXTERNAL SERVICES ==="
echo ""
check_todo "SERPER_API_KEY" "Serper search API key"
check_todo "SENTRY_DSN" "Sentry error tracking DSN"
check_sentry_release
echo ""

echo "=== DOMAIN CONFIGURATION ==="
echo ""
check_todo "ALLOWED_HOSTS" "Allowed hostnames"
check_todo "CSRF_TRUSTED_ORIGINS" "CSRF trusted origins"
echo ""

# Check git status
echo "=== GIT TRACKING ==="
echo ""
if git ls-files --error-unmatch "$ENV_FILE" >/dev/null 2>&1; then
    echo -e "${RED}✗ $ENV_FILE is tracked by git${NC} - SECURITY RISK!"
    echo "  Run: git rm --cached $ENV_FILE"
    ((ERRORS++))
else
    echo -e "${GREEN}✓ $ENV_FILE not tracked by git${NC} - Secure"
    ((SUCCESS++))
fi
echo ""

# Summary
echo "=================================================="
echo "VALIDATION SUMMARY"
echo "=================================================="
echo -e "${GREEN}✓ Success:${NC} $SUCCESS"
echo -e "${YELLOW}⚠ Warnings:${NC} $WARNINGS"
echo -e "${RED}✗ Errors:${NC} $ERRORS"
echo ""

if [ $ERRORS -gt 0 ]; then
    echo -e "${RED}❌ VALIDATION FAILED${NC}"
    echo ""
    echo "Action required:"
    echo "  1. Fix all ERROR items above"
    echo "  2. Fill in TODO values with actual DigitalOcean credentials"
    echo "  3. Run this script again: ./scripts/validate-production-env.sh"
    echo ""
    exit 1
fi

if [ $WARNINGS -gt 0 ]; then
    echo -e "${YELLOW}⚠️  VALIDATION PASSED WITH WARNINGS${NC}"
    echo ""
    echo "Warnings detected (review recommended):"
    echo "  - Some optional settings may need configuration"
    echo "  - Proceed with caution"
    echo ""
    exit 0
fi

echo -e "${GREEN}✅ VALIDATION PASSED${NC}"
echo ""
echo "Next steps:"
echo "  1. Review configuration: nano $ENV_FILE"
echo "  2. Test Docker config: docker-compose -f docker-compose.production.yml config"
echo "  3. Run deployment checks: docker-compose -f docker-compose.production.yml run --rm web python manage.py check --deploy"
echo "  4. Continue with Sentry alert rules setup (60 minutes)"
echo ""

exit 0
