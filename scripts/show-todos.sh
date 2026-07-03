#!/bin/bash
# Show remaining TODO items in .env.production.local
# Usage: ./scripts/show-todos.sh

ENV_FILE=".env.production.local"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}ERROR: $ENV_FILE not found${NC}"
    exit 1
fi

echo "=================================================="
echo "Remaining TODO Items in .env.production.local"
echo "=================================================="
echo ""

TODO_COUNT=$(grep -c "^[A-Z_]*=TODO" "$ENV_FILE" 2>/dev/null || echo "0")

if [ "$TODO_COUNT" -eq 0 ]; then
    echo -e "${GREEN}✅ No TODO items remaining!${NC}"
    echo ""
    echo "All values configured. Run validation:"
    echo "  ./scripts/validate-production-env.sh"
    echo ""
    exit 0
fi

echo -e "${YELLOW}Found $TODO_COUNT TODO items:${NC}"
echo ""

# Show each TODO with line number
grep -n "^[A-Z_]*=TODO" "$ENV_FILE" | while IFS=: read -r line_num content; do
    key=$(echo "$content" | cut -d'=' -f1)
    echo "  Line $line_num: $key"
done

echo ""
echo "=================================================="
echo "How to Fix"
echo "=================================================="
echo ""
echo "1. Open file for editing:"
echo "   nano .env.production.local"
echo ""
echo "2. Search for 'TODO' and replace with actual values"
echo ""
echo "3. Get credentials from:"
echo "   - DATABASE_URL: DigitalOcean → Databases → PostgreSQL"
echo "   - REDIS_URL: DigitalOcean → Databases → Redis (use rediss://)"
echo "   - SERPER_API_KEY: https://serper.dev/dashboard"
echo "   - SENTRY_DSN: Sentry.io → Project Settings → Client Keys"
echo "   - ALLOWED_HOSTS: Your production domain"
echo ""
echo "4. After filling in values, validate:"
echo "   ./scripts/validate-production-env.sh"
echo ""
echo "Full guide: PRODUCTION-SETUP-STATUS.md"
echo ""

exit 0
