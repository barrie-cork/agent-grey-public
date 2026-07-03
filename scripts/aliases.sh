#!/bin/bash
# scripts/aliases.sh
# Common aliases for Edit tool verification

# Quick git status check
alias check-edits='git status --short'

# Detailed diff of recent changes
alias show-edits='git diff --stat && echo "" && git diff'

# Verify specific files
verify-files() {
    ./scripts/verify-edit-success.sh "$@"
}

# Quick check after Edit tool use
alias verify-last='git diff --name-only HEAD | xargs ./scripts/verify-edit-success.sh'

echo "✅ Edit verification aliases loaded"
echo "Available commands:"
echo "  - check-edits     : Quick git status"
echo "  - show-edits      : Show detailed diff"
echo "  - verify-files    : Verify specific files"
echo "  - verify-last     : Verify all changed files"
