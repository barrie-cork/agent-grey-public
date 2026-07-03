#!/bin/bash
# Sentry Release Creation Script
# Creates release tag for Django 5.2.7 deployment
# Usage: ./scripts/create-sentry-release.sh <org-name> <project-name>

set -e

# Colours
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

RELEASE_TAG="django-5.2.7-6f03d44"
GIT_COMMIT="6f03d44"

# Check arguments
if [ $# -lt 2 ]; then
    echo -e "${RED}ERROR: Missing arguments${NC}"
    echo ""
    echo "Usage: $0 <org-name> <project-name>"
    echo ""
    echo "Example: $0 my-org agent-grey"
    echo ""
    echo "To find your organisation and project names:"
    echo "  1. Log in to https://sentry.io"
    echo "  2. Your URL will be: https://sentry.io/organizations/<org-name>/"
    echo "  3. Navigate to your project"
    echo "  4. Project name is shown in the sidebar"
    echo ""
    exit 1
fi

ORG_NAME="$1"
PROJECT_NAME="$2"

echo "=================================================="
echo "Sentry Release Creation"
echo "=================================================="
echo "Organisation: $ORG_NAME"
echo "Project: $PROJECT_NAME"
echo "Release Tag: $RELEASE_TAG"
echo "Git Commit: $GIT_COMMIT"
echo "=================================================="
echo ""

# Check Sentry CLI is authenticated
echo "Checking Sentry CLI authentication..."
if ! sentry-cli info >/dev/null 2>&1; then
    echo -e "${RED}✗ Sentry CLI not authenticated${NC}"
    echo ""
    echo "Run: sentry-cli login"
    echo ""
    exit 1
fi
echo -e "${GREEN}✓${NC} Sentry CLI authenticated"
echo ""

# Create release
echo "Creating Sentry release: $RELEASE_TAG..."
if sentry-cli releases new "$RELEASE_TAG" \
    --org "$ORG_NAME" \
    --project "$PROJECT_NAME" 2>&1; then
    echo -e "${GREEN}✓${NC} Release created successfully"
else
    echo -e "${YELLOW}⚠${NC} Release may already exist (continuing...)"
fi
echo ""

# Associate git commits
echo "Associating git commits with release..."
if sentry-cli releases set-commits "$RELEASE_TAG" \
    --org "$ORG_NAME" \
    --auto 2>&1; then
    echo -e "${GREEN}✓${NC} Git commits associated"
else
    echo -e "${YELLOW}⚠${NC} Could not associate commits (optional)"
fi
echo ""

# Set release properties
echo "Setting release properties..."
if sentry-cli releases set-meta "$RELEASE_TAG" \
    --org "$ORG_NAME" \
    --commit "$GIT_COMMIT" 2>&1; then
    echo -e "${GREEN}✓${NC} Release metadata set"
else
    echo -e "${YELLOW}⚠${NC} Could not set metadata (optional)"
fi
echo ""

echo "=================================================="
echo -e "${GREEN}✅ SENTRY RELEASE CREATED${NC}"
echo "=================================================="
echo ""
echo "Release Tag: $RELEASE_TAG"
echo "View in Sentry: https://sentry.io/organizations/$ORG_NAME/releases/$RELEASE_TAG/"
echo ""
echo "IMPORTANT NEXT STEPS:"
echo "1. Verify release visible in Sentry dashboard"
echo "2. Add to .env.production.local (if not already done):"
echo "   SENTRY_RELEASE=$RELEASE_TAG"
echo "3. After deployment completes, finalise release:"
echo "   sentry-cli releases finalize $RELEASE_TAG --org $ORG_NAME"
echo "4. Configure Sentry alert rules (see SENTRY-SETUP-GUIDE.md)"
echo ""
echo "For alert rules setup, run:"
echo "  Open: https://sentry.io/organizations/$ORG_NAME/alerts/rules/"
echo "  Follow: feature_changes/django5/SENTRY-SETUP-GUIDE.md (lines 88-269)"
echo ""

exit 0
