#!/bin/bash
# scripts/verify-edit-success.sh
# Verify that Edit tool changes were actually written to disk

set -euo pipefail

# Colours for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Colour

if [ $# -eq 0 ]; then
    echo -e "${RED}❌ Error: No files specified${NC}"
    echo "Usage: $0 <file1> [file2] [file3] ..."
    exit 1
fi

echo "🔍 Verifying Edit tool changes..."
echo ""

FAILED_FILES=()
SUCCESS_FILES=()

for file in "$@"; do
    # Check if file exists
    if [ ! -f "$file" ]; then
        echo -e "${RED}❌ File not found: $file${NC}"
        FAILED_FILES+=("$file")
        continue
    fi

    # Check if file is modified according to git
    if git status --porcelain "$file" | grep -q "^ M\|^M "; then
        echo -e "${GREEN}✅ VERIFIED: $file${NC}"
        SUCCESS_FILES+=("$file")
    else
        echo -e "${RED}❌ SILENT FAILURE: $file (no changes detected)${NC}"
        FAILED_FILES+=("$file")
    fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ ${#FAILED_FILES[@]} -eq 0 ]; then
    echo -e "${GREEN}✅ All files verified successfully!${NC}"
    echo ""
    echo "Changes summary:"
    git diff --stat "$@"
    exit 0
else
    echo -e "${RED}❌ EDIT TOOL SILENT FAILURE DETECTED${NC}"
    echo ""
    echo "Failed files (${#FAILED_FILES[@]}):"
    for file in "${FAILED_FILES[@]}"; do
        echo "  - $file"
    done
    echo ""
    echo -e "${YELLOW}⚠️  WARNING: Edit tool reported success but changes were not written!${NC}"
    echo ""
    echo "Recommended actions:"
    echo "1. Re-run the Edit tool on failed files"
    echo "2. Verify changes with: git diff <file>"
    echo "3. Report this incident at: https://github.com/anthropics/claude-code/issues"
    exit 1
fi
