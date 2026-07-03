#!/bin/bash
# Shared deployment utilities for DigitalOcean App Platform
#
# This library consolidates common deployment functions used across
# multiple deployment scripts to eliminate code duplication.
#
# Usage:
#   source "$(dirname "$0")/lib/deployment-utils.sh"

# Colour codes (centralized)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Colour

# Environment variable extraction (unified from 3 implementations)
# Handles quoted and unquoted values, strips leading/trailing whitespace
#
# Args:
#   $1 - Variable name
#   $2 - Environment file path (default: .env.production.local)
#
# Returns:
#   Variable value (via stdout)
get_env_var() {
    local var_name="$1"
    local env_file="${2:-.env.production.local}"

    if [[ ! -f "$env_file" ]]; then
        echo ""
        return 1
    fi

    grep "^${var_name}=" "$env_file" 2>/dev/null | \
        head -1 | \
        cut -d '=' -f2- | \
        sed 's/^[[:space:]]*//;s/[[:space:]]*$//;s/^['\''"]//;s/['\''"]$//'
}

# Validate required variables exist and are non-empty
#
# Args:
#   $1 - Environment file path
#   $@ - Required variable names (remaining args)
#
# Returns:
#   0 if all variables present, 1 if any missing
validate_required_vars() {
    local env_file="$1"
    shift
    local required_vars=("$@")
    local missing=()

    if [[ ! -f "$env_file" ]]; then
        echo -e "${RED}✗ Environment file not found: $env_file${NC}"
        return 1
    fi

    for var in "${required_vars[@]}"; do
        local value
        value=$(get_env_var "$var" "$env_file")
        if [[ -z "$value" ]]; then
            missing+=("$var")
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        echo -e "${RED}✗ Missing required variables:${NC}"
        for var in "${missing[@]}"; do
            echo -e "  - $var"
        done
        return 1
    fi

    echo -e "${GREEN}✓ All required variables present${NC}"
    return 0
}

# Wait for deployment to reach ACTIVE or terminal state
# Polls deployment status every 10 seconds
#
# Args:
#   $1 - App ID
#   $2 - Deployment ID
#   $3 - Max wait time in seconds (default: 600)
#
# Returns:
#   0 if deployment successful, 1 if failed/timeout
wait_for_deployment_active() {
    local app_id="$1"
    local deployment_id="$2"
    local max_wait="${3:-600}"  # 10 minutes default
    local elapsed=0

    echo -e "${BLUE}Monitoring deployment status...${NC}"
    echo -e "${YELLOW}(Press Ctrl+C to stop monitoring - deployment will continue)${NC}"
    echo ""

    # Wait a few seconds for deployment to start
    sleep 5

    while [[ $elapsed -lt $max_wait ]]; do
        local status
        status=$(doctl apps get-deployment "$app_id" "$deployment_id" \
            --format Phase --no-header 2>/dev/null || echo "UNKNOWN")

        case "$status" in
            "ACTIVE")
                echo -e "${GREEN}✓ Deployment succeeded!${NC}"
                return 0
                ;;
            "SUPERSEDED")
                echo -e "${GREEN}✓ Deployment active (superseded by newer deployment)${NC}"
                return 0
                ;;
            "ERROR"|"CANCELED")
                echo -e "${RED}✗ Deployment failed: $status${NC}"
                echo ""
                echo "View logs:"
                echo "  doctl apps logs $app_id --type BUILD --follow"
                echo "  doctl apps logs $app_id --type DEPLOY --follow"
                return 1
                ;;
            "UNKNOWN")
                echo -e "${RED}✗ Could not retrieve deployment status${NC}"
                return 1
                ;;
            "PENDING_BUILD"|"BUILDING"|"PENDING_DEPLOY"|"DEPLOYING")
                echo -e "${YELLOW}⏳ Status: $status (${elapsed}s elapsed)${NC}"
                ;;
            *)
                echo -e "${YELLOW}⏳ Status: $status (${elapsed}s elapsed)${NC}"
                ;;
        esac

        sleep 10
        elapsed=$((elapsed + 10))
    done

    echo -e "${RED}✗ Deployment timeout after ${max_wait}s${NC}"
    return 1
}

# Verify application health endpoint
#
# Args:
#   $1 - App URL (without https://)
#   $2 - Timeout in seconds (default: 10)
#
# Returns:
#   0 if health check passed (HTTP 200), 1 otherwise
verify_health_endpoint() {
    local app_url="$1"
    local timeout="${2:-10}"

    echo -e "${BLUE}Verifying health endpoint...${NC}"

    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" \
        -m "$timeout" "https://$app_url/health/" 2>/dev/null || echo "000")

    if [[ "$http_code" = "200" ]]; then
        echo -e "${GREEN}✓ Health check passed (HTTP $http_code)${NC}"
        return 0
    else
        echo -e "${RED}✗ Health check failed (HTTP $http_code)${NC}"
        echo -e "${YELLOW}   App may still be starting. Wait a few minutes and check:${NC}"
        echo -e "${YELLOW}   https://$app_url/health/${NC}"
        return 1
    fi
}

# Display environment variables formatted for manual DigitalOcean console entry
#
# Args:
#   $1 - Environment file path
#   $@ - Required variable names (remaining args)
display_env_vars_for_console() {
    local env_file="$1"
    shift
    local required_vars=("$@")

    echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║  DigitalOcean Console Configuration Required                  ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${YELLOW}Copy these values to DigitalOcean console:${NC}"
    echo -e "${YELLOW}Settings → Environment Variables → Edit${NC}"
    echo ""
    echo -e "${YELLOW}IMPORTANT: Configure for ALL components (web, celery-worker, celery-beat)${NC}"
    echo ""

    for var in "${required_vars[@]}"; do
        local value
        value=$(get_env_var "$var" "$env_file")
        if [[ -n "$value" ]]; then
            echo -e "   ${GREEN}$var${NC} = $value"
            echo -e "   ${YELLOW}(Mark as Encrypted)${NC}"
            echo ""
        fi
    done

    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# Check if doctl CLI is installed and authenticated
#
# Returns:
#   0 if ready, 1 if not installed/authenticated
check_doctl() {
    if ! command -v doctl &> /dev/null; then
        echo -e "${RED}✗ ERROR: doctl CLI not found${NC}"
        echo "  Install: https://docs.digitalocean.com/reference/doctl/how-to/install/"
        return 1
    fi

    echo -e "${GREEN}✓ doctl CLI found${NC}"

    if ! doctl auth list &> /dev/null; then
        echo -e "${RED}✗ ERROR: doctl not authenticated${NC}"
        echo "  Run: doctl auth init"
        return 1
    fi

    echo -e "${GREEN}✓ doctl authenticated${NC}"
    return 0
}

# Validate app ID exists
#
# Args:
#   $1 - App ID
#
# Returns:
#   0 if valid, 1 if not found
validate_app_id() {
    local app_id="$1"

    if [[ -z "$app_id" ]]; then
        echo -e "${YELLOW}No APP_ID provided. Listing available apps:${NC}"
        echo ""
        doctl apps list
        echo ""
        echo -e "${YELLOW}Usage: $0 <APP_ID>${NC}"
        return 1
    fi

    if ! doctl apps get "$app_id" &> /dev/null; then
        echo -e "${RED}✗ ERROR: App ID not found: $app_id${NC}"
        echo ""
        echo "Available apps:"
        doctl apps list
        return 1
    fi

    echo -e "${GREEN}✓ Validated App ID: $app_id${NC}"
    return 0
}
