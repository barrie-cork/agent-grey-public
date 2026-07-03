# Testing Troubleshooting Guide

> **Purpose:** Document testing issues, solutions, and lessons learned for future debugging.

Last Updated: 2026-01-01

## Test Environments Overview

| Test Type | Framework | Location | Run Command |
|-----------|-----------|----------|-------------|
| Backend Unit | Django TestCase | `apps/*/tests/` | `docker compose exec web python manage.py test --keepdb` |
| Frontend Unit | Vitest + Vue Test Utils | `frontend/src/**/__tests__/` | `npm run --prefix frontend test:unit` |
| E2E | Playwright | `tests/e2e/` | `npx playwright test` |

---

## Issue #1: Vitest Fork Pool Timeout

**Date:** 2026-01-01
**Severity:** High - blocks all frontend tests
**Status:** Partially resolved

### Symptoms
```
Error: [vitest-pool]: Timeout starting forks runner.
```
- Tests hang at `RUN v4.0.6` without executing
- Multiple `forks.js` worker processes accumulate
- Tests may run once but fail on subsequent runs

### Root Cause
Vitest v4 changed default pool to `forks` which uses `child_process.fork()`. This has known issues in:
- WSL2 environments
- Docker containers
- Dev containers
- CI environments with resource constraints

**GitHub Issues:** #8861, #8968

### Solutions Attempted

| Solution | Result | Recommended |
|----------|--------|-------------|
| Change `pool: 'forks'` to `pool: 'threads'` | Partial - still hung after process accumulation | ✅ Yes |
| Add `singleThread: true` to poolOptions | No improvement when processes accumulated | Maybe |
| Kill stale processes with `pkill -f vitest` | Temporary fix | ✅ Essential first step |
| Add explicit `root` and `include` paths | No improvement | No |
| Increase `testTimeout` and `hookTimeout` | No effect on startup hang | No |

### Recommended Configuration

```typescript
// frontend/vitest.config.ts
export default defineConfig({
  test: {
    environment: 'happy-dom',
    globals: true,
    // Use threads pool - forks has timeout issues in containers (vitest#8861)
    pool: 'threads',
    poolOptions: {
      threads: {
        singleThread: true  // Avoid worker pool issues
      }
    }
  }
})
```

### Recovery Procedure

When tests hang or fail to start:

```bash
# 1. Kill ALL vitest-related processes
pkill -9 -f vitest
pkill -9 -f "forks.js"
pkill -9 -f esbuild

# 2. Wait for cleanup
sleep 3

# 3. Verify clean state
ps aux | grep -E "vitest|forks|esbuild" | grep -v grep
# Should show no processes

# 4. Try running tests again
npm run --prefix frontend test:unit
```

### Prevention

1. Always run tests with timeout: `timeout 120 npm run --prefix frontend test:unit`
2. Don't interrupt test runs with Ctrl+C if possible - let them complete or timeout
3. If tests hang, clean up processes before retrying

---

## Issue #2: Hook Interference When Running from frontend/

**Date:** 2026-01-01
**Severity:** Low - cosmetic error
**Status:** Known limitation

### Symptoms
```
PostToolUse:Bash hook blocking error from command: "python3 .claude/hooks/context_monitor.py"
python3: can't open file '/workspaces/agent-grey-core-requirements/frontend/.claude/hooks/context_monitor.py'
```

### Root Cause
Claude Code hooks expect to run from project root. When `cd frontend` is used, hooks look for config in wrong directory.

### Solution
Always run npm commands from project root using `--prefix`:
```bash
# GOOD - runs from project root
npm run --prefix frontend test:unit

# AVOID - changes directory, breaks hooks
cd frontend && npm run test:unit
```

---

## Issue #3: WorkQueue.test.ts Regex False Positive

**Date:** 2026-01-01
**Severity:** Medium - causes test failures
**Status:** FIXED

### Symptoms
Test "should NOT have Bootstrap utility classes" fails even though only Tailwind classes are present.

### Root Cause
Regex `/class="[^"]*\btext-muted\b[^"]*"/` incorrectly matches `text-muted-foreground` (Tailwind) when it should only match `text-muted` (Bootstrap).

Word boundary `\b` matches between 'd' and '-' because '-' is a non-word character.

### Solution
Use negative lookahead to exclude Tailwind variant:
```typescript
// BEFORE (buggy)
expect(html).not.toMatch(/class="[^"]*\btext-muted\b[^"]*"/)

// AFTER (fixed)
expect(html).not.toMatch(/class="[^"]*\btext-muted(?!-foreground)[^"]*"/)
```

### Verification
```javascript
// Test the regex fix
const regex = /class="[^"]*\btext-muted(?!-foreground)[^"]*"/;
regex.test('class="text-muted"')           // true - Bootstrap detected
regex.test('class="text-muted-foreground"') // false - Tailwind ignored ✓
```

---

## Issue #4: E2E Firefox/WebKit Failures

**Date:** 2026-01-01
**Severity:** Low - chromium tests pass
**Status:** Known limitation

### Symptoms
- Chromium: 11/11 pass ✅
- Firefox: Task 1 fails
- WebKit: Task 1 fails

### Root Cause
Browser-specific configuration or compatibility issues in the dev container environment.

### Recommendation
Focus on Chromium for development. Run cross-browser tests in CI only:
```bash
# Development - chromium only (faster)
npx playwright test --project=chromium

# CI - all browsers
npx playwright test
```

---

## Quick Reference: Test Commands

```bash
# Backend tests (always use Docker)
docker compose -f docker compose.development.yml exec -T web python manage.py test --keepdb

# Frontend tests (use --prefix to avoid hook issues)
npm run --prefix frontend test:unit

# E2E tests (chromium only for speed)
npx playwright test --project=chromium

# E2E specific file
npx playwright test tests/e2e/dual_screening_automation.spec.ts --project=chromium

# Clean up stuck test processes
pkill -9 -f vitest; pkill -9 -f "forks.js"; pkill -9 -f esbuild
```

---

## Lessons Learned

1. **Vitest v4 pool issues are environment-specific** - What works locally may hang in containers
2. **Process cleanup is essential** - Failed/interrupted test runs leave zombie processes
3. **Run from project root** - Avoids hook and path resolution issues
4. **Chromium is most reliable** - Cross-browser testing best done in CI
5. **Regex word boundaries are tricky** - `\b` matches at hyphen boundaries unexpectedly

---

## Version Information

| Component | Version |
|-----------|---------|
| Node.js | v22.21.1 |
| Vitest | 4.0.6 |
| Playwright | 1.56.1 |
| Vue | 3.5.22 |
| happy-dom | 20.0.10 |
| Django | 5.1.13 |

---

## Contributing

When you encounter a new testing issue:
1. Document symptoms and error messages
2. Record what you tried and results
3. Note the root cause if found
4. Add solution or workaround
5. Update this file with date
