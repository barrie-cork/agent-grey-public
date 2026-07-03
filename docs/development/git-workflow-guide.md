# Git Workflow Guide for Agent Grey

## Overview

Agent Grey follows a **Git Flow** branching strategy with automated CI/CD pipelines. This guide explains the workflow for developers, the purpose of each branch, and how the CI/CD system validates changes.

---

## Branch Structure

### Main Branches

| Branch | Purpose | Protection | CI Behaviour | Deployment |
|--------|---------|-----------|--------------|------------|
| `main` | Production-ready code | Protected, requires PR + reviews | Full tests, no staging validation | Triggers production deployment |
| `develop` | Integration branch for features | Protected, requires PR | Full tests + staging validation | Triggers staging deployment |

### Supporting Branches

| Branch Type | Naming | Created From | Merged Into | Lifespan |
|-------------|--------|--------------|-------------|----------|
| Feature | `feature/<description>` | `develop` | `develop` | Temporary |
| Bugfix | `bugfix/<description>` | `develop` | `develop` | Temporary |
| Hotfix | `hotfix/<description>` | `main` | `main` AND `develop` | Temporary |
| Release | `release/<version>` | `develop` | `main` AND `develop` | Temporary |

---

## Developer Workflow

### 1. Starting New Work

#### For New Features or Non-Critical Bugs

```bash
# Ensure develop is up to date
git checkout develop
git pull origin develop

# Create feature branch
git checkout -b feature/add-export-functionality
```

#### For Production Hotfixes

```bash
# Branch from main for critical production issues
git checkout main
git pull origin main

# Create hotfix branch
git checkout -b hotfix/fix-serper-api-timeout
```

---

### 2. Development Cycle

```bash
# Make your changes
git add .
git commit -m "feat: add PDF export functionality"

# Push to remote (creates remote branch on first push)
git push -u origin feature/add-export-functionality

# Subsequent pushes
git push
```

#### Commit Message Conventions

Follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `style:` - Code style changes (formatting, no logic change)
- `refactor:` - Code refactoring
- `test:` - Adding or updating tests
- `chore:` - Maintenance tasks, dependency updates
- `perf:` - Performance improvements
- `ci:` - CI/CD pipeline changes

**Examples**:
```bash
git commit -m "feat(search): add Boolean query validation"
git commit -m "fix(results): resolve duplicate detection edge case"
git commit -m "docs: update API documentation for search endpoints"
git commit -m "test(review): add tests for manual review workflow"
```

---

### 3. Keeping Your Branch Updated

```bash
# Regularly sync with develop to avoid conflicts
git checkout develop
git pull origin develop

git checkout feature/your-feature
git rebase develop  # OR: git merge develop

# If conflicts occur, resolve them, then:
git add .
git rebase --continue  # OR: git commit (if merged)

# Force push if you rebased (rewrites history)
git push --force-with-lease
```

**Best Practice**: Sync with `develop` at least once per day for long-running features.

---

### 4. Creating a Pull Request

#### Step 1: Push Your Branch
```bash
git push origin feature/your-feature
```

#### Step 2: Open PR on GitHub
1. Navigate to [repository](https://github.com/barrie-cork/agent-grey)
2. Click **"Compare & pull request"**
3. Set base branch:
   - **Features/bugfixes** → base: `develop`
   - **Hotfixes** → base: `main`

#### Step 3: Fill PR Template

```markdown
## Summary
Brief description of what this PR does (1-3 sentences)

## Changes
- Added PDF export functionality to reporting module
- Implemented WeasyPrint integration
- Added export permissions checks

## Testing
- [ ] Unit tests pass locally
- [ ] Manual testing completed
- [ ] No new security warnings
- [ ] Documentation updated

## Related Issues
Closes #123
```

#### Step 4: Wait for CI Checks

Your PR will automatically trigger:
- ✅ Code quality checks (flake8, black, isort)
- ✅ Security scans (safety, bandit with SARIF)
- ✅ Django tests (4 parallel test groups)
- ✅ Docker build validation
- ✅ Smoke tests (`manage.py check --deploy`)

**CI Duration**: ~15 minutes for PRs

---

### 5. Addressing Review Feedback

```bash
# Make requested changes
git add .
git commit -m "refactor: improve error handling per review feedback"
git push

# CI automatically re-runs on new commits
```

**Tips**:
- Respond to each review comment
- Mark conversations as resolved when addressed
- Request re-review after pushing changes

---

### 6. Merging Your PR

#### Requirements Before Merge
- ✅ All CI checks passing
- ✅ At least 1 approval from code owner
- ✅ No merge conflicts with base branch
- ✅ Security scans passing (vulnerabilities block merge)

#### Merge Methods

| Method | When to Use | Effect |
|--------|-------------|--------|
| **Squash and merge** (Recommended) | Clean up messy commit history | All commits become 1 commit on base branch |
| **Rebase and merge** | Already have clean commits | Individual commits preserved |
| **Merge commit** | Need to preserve exact history | Creates merge commit |

**Default**: Use **Squash and merge** for most PRs.

---

## Release Workflow

### Creating a Release

```bash
# Start from develop
git checkout develop
git pull origin develop

# Create release branch
git checkout -b release/1.2.0

# Update version numbers
# - Update CHANGELOG.md
# - Update version in __init__.py or version.py

git add .
git commit -m "chore: prepare release 1.2.0"
git push -u origin release/1.2.0
```

### Testing Release Candidate

```bash
# Deploy to staging (automatic on develop pushes)
# Manually test all functionality
# Fix any release-blocking bugs in the release branch
```

### Finalising Release

```bash
# Merge to main (via PR)
# 1. Create PR: release/1.2.0 → main
# 2. Get approvals
# 3. Merge (use "Create a merge commit")

# Tag the release
git checkout main
git pull origin main
git tag -a v1.2.0 -m "Release version 1.2.0"
git push origin v1.2.0

# Merge back to develop (via PR)
# 1. Create PR: release/1.2.0 → develop (or main → develop)
# 2. Merge
# 3. Delete release branch
```

---

## Hotfix Workflow

For **critical production bugs** that cannot wait for the next release:

```bash
# 1. Branch from main
git checkout main
git pull origin main
git checkout -b hotfix/critical-bug-fix

# 2. Make the fix
git add .
git commit -m "fix: resolve critical Serper API timeout"
git push -u origin hotfix/critical-bug-fix

# 3. Create PR to main
# - Base: main
# - Get expedited review
# - Merge when CI passes

# 4. Also merge to develop
git checkout develop
git pull origin develop
git merge hotfix/critical-bug-fix
git push origin develop

# 5. Tag the hotfix
git checkout main
git pull origin main
git tag -a v1.2.1 -m "Hotfix: Serper API timeout"
git push origin v1.2.1

# 6. Delete hotfix branch
git branch -d hotfix/critical-bug-fix
git push origin --delete hotfix/critical-bug-fix
```

---

## CI/CD Pipeline Behaviour

### Pull Request to `develop`
```
┌─────────────────┐
│   PR Created    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Code Quality   │ (flake8, black, isort)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Security Scan  │ (safety, bandit → BLOCKS on vulnerabilities)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Django Tests   │ (4 parallel test groups, ~10 min)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Docker Build   │ (development, staging, production)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Smoke Tests    │ (manage.py check --deploy, ~2 min)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Test Summary   │ (Pass/Fail report)
└─────────────────┘
```

**Total Duration**: ~15 minutes

### Push to `develop`
```
Same as PR + additional step:
         │
         ▼
┌─────────────────┐
│ Staging Deploy  │ (DigitalOcean App Platform)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Health Checks   │ (Verify deployment)
└─────────────────┘
```

**Total Duration**: ~20-25 minutes (includes deployment)

### Push to `main`
```
Same as PR (no staging validation) + production deployment:
         │
         ▼
┌─────────────────┐
│Production Deploy│ (Requires approval via GitHub Environments)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Health Checks   │ (Comprehensive production validation)
└─────────────────┘
```

**Total Duration**: ~20-30 minutes (includes deployment + approval wait)

### Nightly (2 AM UTC)
```
┌─────────────────┐
│  Full Staging   │ (Docker Compose integration tests)
│   Validation    │ (Performance baseline)
└─────────────────┘
```

**Total Duration**: ~30 minutes

---

## Common Scenarios

### Scenario 1: Multiple Developers on Same Feature

```bash
# Developer A creates feature branch
git checkout -b feature/new-api

# Developer B wants to contribute
git fetch origin
git checkout feature/new-api
git pull origin feature/new-api

# Make changes
git add .
git commit -m "feat: add validation logic"
git push origin feature/new-api

# Developer A syncs
git pull origin feature/new-api  # Gets Developer B's changes
```

### Scenario 2: Rebasing vs Merging

#### Use Rebase When:
- Cleaning up your feature branch before PR
- Updating from `develop` during development
- You haven't shared the branch with others

```bash
git checkout feature/your-feature
git fetch origin
git rebase origin/develop
git push --force-with-lease
```

#### Use Merge When:
- Multiple developers working on same branch
- Preserving exact history is important
- Unsure about rebase safety

```bash
git checkout feature/your-feature
git merge develop
git push
```

### Scenario 3: Merge Conflict Resolution

```bash
# During rebase or merge
git status  # See conflicted files

# Edit conflicted files, look for:
<<<<<<< HEAD
Your changes
=======
Their changes
>>>>>>> develop

# After resolving
git add .
git rebase --continue  # If rebasing
# OR
git commit  # If merging

git push --force-with-lease  # If rebased
```

### Scenario 4: Accidentally Committed to Wrong Branch

```bash
# You committed to develop instead of feature branch
git checkout develop
git log  # Note the commit hash

# Undo the commit (keep changes)
git reset --soft HEAD~1

# Create correct branch
git checkout -b feature/correct-branch
git commit -m "feat: your changes"
git push -u origin feature/correct-branch
```

---

## Best Practices

### 1. Branch Naming
✅ **Good**:
- `feature/add-pdf-export`
- `bugfix/fix-duplicate-detection`
- `hotfix/serper-timeout`

❌ **Bad**:
- `my-branch`
- `fix`
- `updates`

### 2. Commit Frequency
- Commit logical units of work
- Don't commit broken code
- Commit often (every 30-60 minutes of work)

### 3. Pull Request Size
- Aim for < 400 lines changed
- Split large features into smaller PRs
- One logical change per PR

### 4. Code Review
- Review your own PR before requesting review
- Respond to all comments
- Don't take feedback personally

### 5. Security
- Never commit secrets (`.env` files, API keys)
- Run security scans locally: `safety check`, `bandit -r apps/`
- Fix security issues before requesting review

---

## Troubleshooting

### CI Failing on Security Checks

```bash
# Run locally first
safety check --exit-code
bandit -r apps/ grey_lit_project/ -ll

# Fix vulnerabilities
pip install --upgrade <package>

# Fix bandit issues or suppress false positives
# Add comment: # nosec B123
```

### Tests Passing Locally But Failing in CI

```bash
# Use same test settings as CI
export DJANGO_SETTINGS_MODULE=grey_lit_project.settings.test
export DATABASE_URL=postgres://postgres:postgres@localhost:5432/test_db

# Run tests
python manage.py test --verbosity=2
```

### Merge Conflicts on PR

```bash
# Update your branch
git checkout feature/your-feature
git fetch origin
git rebase origin/develop

# Resolve conflicts
# ... edit files ...

git add .
git rebase --continue
git push --force-with-lease
```

### CI Taking Too Long

- **PRs**: Should complete in ~15 minutes
- **Develop pushes**: ~25 minutes (includes staging deploy)
- If longer, check [Actions tab](https://github.com/barrie-cork/agent-grey/actions) for stuck jobs

---

## Quick Reference

### Daily Workflow
```bash
# Morning: Sync with develop
git checkout develop && git pull origin develop

# Create feature branch
git checkout -b feature/your-work

# Work, commit, push
git add . && git commit -m "feat: description"
git push -u origin feature/your-work

# Create PR on GitHub
# Wait for CI + reviews
# Squash and merge when approved
```

### Branch Status Check
```bash
# See all branches
git branch -a

# See remote branches
git branch -r

# Delete merged local branches
git branch --merged | grep -v "\*\|main\|develop" | xargs -n 1 git branch -d
```

### Undoing Mistakes
```bash
# Undo last commit (keep changes)
git reset --soft HEAD~1

# Undo last commit (discard changes)
git reset --hard HEAD~1

# Revert a pushed commit (safe, creates new commit)
git revert <commit-hash>
```

---

## Getting Help

- **CI Issues**: Check [Actions tab](https://github.com/barrie-cork/agent-grey/actions)
- **Git Questions**: Ask in team chat or check [Git documentation](https://git-scm.com/doc)
- **Workflow Questions**: Review this guide or ask project maintainers

---

**Document Version**: 1.0
**Last Updated**: 2025-10-07
**Maintained By**: Agent Grey Core Team
