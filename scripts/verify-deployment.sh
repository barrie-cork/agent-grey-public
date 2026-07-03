#!/bin/bash
# Verify DigitalOcean Deployment
# Checks app status, health endpoints, and logs for errors
#
# Usage:
#   ./scripts/verify-deployment.sh [APP_ID]

set -e

# Colour codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Agent Grey - Deployment Verification                         ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if doctl is installed
if ! command -v doctl &> /dev/null; then
    echo -e "${RED}✗ ERROR: doctl CLI not found${NC}"
    exit 1
fi

# Get APP_ID
if [ -z "$1" ]; then
    echo -e "${YELLOW}Available apps:${NC}"
    doctl apps list
    echo ""
    echo -e "${YELLOW}Usage: $0 <APP_ID>${NC}"
    exit 0
fi

APP_ID="$1"

# Verify app exists
if ! doctl apps get "$APP_ID" &> /dev/null; then
    echo -e "${RED}✗ ERROR: App not found: $APP_ID${NC}"
    exit 1
fi

echo -e "${GREEN}✓ App found${NC}"
echo ""

# Get app details
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}App Status${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

APP_NAME=$(doctl apps get "$APP_ID" --format Name --no-header)
APP_URL=$(doctl apps get "$APP_ID" --format DefaultIngress --no-header)
TIER=$(doctl apps get "$APP_ID" --format Tier --no-header)

echo -e "  Name: ${GREEN}$APP_NAME${NC}"
echo -e "  URL: ${GREEN}https://$APP_URL${NC}"
echo -e "  Tier: ${GREEN}$TIER${NC}"
echo ""

# Check active deployment
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Active Deployment${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

DEPLOYMENT_ID=$(doctl apps list-deployments "$APP_ID" --format ID --no-header | head -n1)

if [ -n "$DEPLOYMENT_ID" ]; then
    DEPLOYMENT_PHASE=$(doctl apps get-deployment "$APP_ID" "$DEPLOYMENT_ID" --format Phase --no-header)
    DEPLOYMENT_PROGRESS=$(doctl apps get-deployment "$APP_ID" "$DEPLOYMENT_ID" --format Progress --no-header)

    case "$DEPLOYMENT_PHASE" in
        "ACTIVE")
            echo -e "  Status: ${GREEN}$DEPLOYMENT_PHASE${NC}"
            ;;
        "ERROR"|"CANCELED")
            echo -e "  Status: ${RED}$DEPLOYMENT_PHASE${NC}"
            ;;
        *)
            echo -e "  Status: ${YELLOW}$DEPLOYMENT_PHASE${NC}"
            ;;
    esac

    echo -e "  Progress: $DEPLOYMENT_PROGRESS"
    echo -e "  Deployment ID: $DEPLOYMENT_ID"
else
    echo -e "${YELLOW}⚠️  No deployments found${NC}"
fi
echo ""

# Check component status
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Component Status${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

doctl apps list-components "$APP_ID" --format Name,Type 2>/dev/null || echo "No components found"
echo ""

# Test health endpoint
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Health Check${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

HEALTH_URL="https://$APP_URL/health/"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL" 2>/dev/null || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
    echo -e "  ${GREEN}✓ Health check passed${NC} (HTTP $HTTP_CODE)"

    # Get health check response
    HEALTH_RESPONSE=$(curl -s "$HEALTH_URL" 2>/dev/null)
    if [ -n "$HEALTH_RESPONSE" ]; then
        echo ""
        echo -e "  Response:"
        echo "$HEALTH_RESPONSE" | jq '.' 2>/dev/null || echo "$HEALTH_RESPONSE"
    fi
else
    echo -e "  ${RED}✗ Health check failed${NC} (HTTP $HTTP_CODE)"
    echo -e "  ${YELLOW}URL: $HEALTH_URL${NC}"
fi
echo ""

# Check recent logs for errors
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Recent Errors (Last 20 lines)${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

ERROR_LOGS=$(doctl apps logs "$APP_ID" --type RUN 2>/dev/null | grep -i "error\|exception\|failed" | tail -20 || echo "")

if [ -n "$ERROR_LOGS" ]; then
    echo -e "${YELLOW}Found errors in logs:${NC}"
    echo "$ERROR_LOGS"
else
    echo -e "${GREEN}✓ No recent errors found${NC}"
fi
echo ""

# Summary
echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Verification Summary                                          ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

if [ "$DEPLOYMENT_PHASE" = "ACTIVE" ] && [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✓ Deployment is healthy and operational${NC}"
    echo ""
    echo -e "${BLUE}Access your application:${NC}"
    echo -e "  https://$APP_URL"
    echo ""
    exit 0
elif [ "$DEPLOYMENT_PHASE" != "ACTIVE" ]; then
    echo -e "${YELLOW}⚠️  Deployment is not yet active (Status: $DEPLOYMENT_PHASE)${NC}"
    echo ""
    echo -e "${BLUE}Monitor progress:${NC}"
    echo -e "  doctl apps logs $APP_ID --type BUILD --follow"
    echo -e "  doctl apps logs $APP_ID --type DEPLOY --follow"
    echo ""
    exit 1
else
    echo -e "${RED}✗ Deployment has issues${NC}"
    echo ""
    echo -e "${BLUE}Troubleshooting:${NC}"
    echo -e "  1. Check logs: doctl apps logs $APP_ID --follow"
    echo -e "  2. Verify environment variables in console"
    echo -e "  3. Check Sentry for errors"
    echo -e "  4. Review recent commits for issues"
    echo ""
    exit 1
fi
