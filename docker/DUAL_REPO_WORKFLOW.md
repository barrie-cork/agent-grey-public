# Dual Repository Workflow Guide

## Overview

This setup allows you to maintain a **single development environment** while managing two GitHub repositories:

1. **Private Repository** (`the-grey`) - Contains all files including private documentation
2. **Public Repository** (`agent-grey`) - Contains only production code, no private files

## 🚀 Quick Start

### Check Current Setup
```bash
./manage_public.sh status
```

### Sync to Public Repository
```bash
./sync_to_public.sh
```

## 📁 Repository Structure

### What Gets Synced to Public
✅ **Included:**
- All Django apps (`apps/`)
- Project settings (`grey_lit_project/`)
- Templates and static files
- Requirements files
- Docker configurations
- Public documentation (README.md)

### What Stays Private
❌ **Excluded:**
- CLAUDE.md and CLAUDE_DETAILED.md
- All files in `docs/`, `PRPs/`, `tests/`
- Environment files (`.env*` except examples)
- Deployment configurations
- Logs and monitoring data
- Sync scripts themselves

## 🔄 Daily Workflow

### 1. Regular Development
Work normally in your single folder:
```bash
cd /mnt/d/Python/Projects/django/HTA-projects/agent-grey

# Make changes
code .  # or your editor

# Commit to private repo
git add .
git commit -m "feat: Add new feature"
git push origin main  # Pushes to private the-grey
```

### 2. Sync to Public
When ready to update public repo:
```bash
# Manual sync
./sync_to_public.sh

# Or check what would be synced first
./manage_public.sh dry-run
```

### 3. Automated Sync (GitHub Actions)
The GitHub Action will automatically sync when you push to main, excluding private files.

To set this up:
```bash
./manage_public.sh setup  # Shows instructions for GitHub token
```

## 🛠️ Available Commands

### manage_public.sh Commands
| Command | Description |
|---------|-------------|
| `status` | Show repository configuration and what files would be excluded |
| `dry-run` | Simulate sync without making changes |
| `compare` | Compare commits between private and public repos |
| `init` | Initialize public repo (first sync) |
| `sync` | Run full sync to public repository |
| `setup` | Show GitHub Actions setup instructions |
| `help` | Show help message |

### sync_to_public.sh
Main sync script that:
1. Creates temporary branch
2. Removes private files per `.gitignore.public`
3. Updates README and .gitignore for public
4. Pushes to public repository
5. Cleans up and returns to original branch

## 📋 Configuration Files

### .gitignore.public
Defines what to exclude from public repo. Edit this to control what stays private.

### .github/workflows/sync-to-public.yml
GitHub Action for automated syncing. Requires `PUBLIC_REPO_TOKEN` secret.

### Remote Configuration
```bash
# Verify remotes are set up correctly
git remote -v

# Should show:
# origin  https://github.com/barrie-cork/the-grey.git (private)
# public  https://github.com/barrie-cork/agent-grey.git (public)
```

## 🔐 Security Best Practices

1. **Never commit secrets** - Use environment variables
2. **Review before syncing** - Run `dry-run` first
3. **Audit regularly** - Use `audit_agent_grey_public.py`
4. **Keep .gitignore.public updated** - Add new private files as needed

## 🚨 Troubleshooting

### Push Permission Denied
```bash
# Check GitHub authentication
git config --global user.name
git config --global user.email

# May need to re-authenticate
git push public main  # Will prompt for credentials
```

### Sync Conflicts
```bash
# If public repo has diverged
./sync_to_public.sh  # Will use --force-with-lease

# For force push (careful!)
git push public main --force
```

### Files Still Appearing in Public
1. Check `.gitignore.public` patterns
2. Files might be cached: `git rm --cached <file>`
3. Run sync again

## 📊 Workflow Diagram

```
┌─────────────────────────────────┐
│   Local Development (One Folder) │
│     agent-grey/                  │
│   ┌──────────────────────────┐   │
│   │  All files including:    │   │
│   │  - Source code           │   │
│   │  - Private docs          │   │
│   │  - Test files            │   │
│   │  - Deployment configs    │   │
│   └──────────────────────────┘   │
└─────────────┬───────────────────┘
              │
     ┌────────┴────────┐
     ▼                 ▼
┌──────────┐      ┌──────────┐
│ Private  │      │  Public  │
│  Repo    │      │   Repo   │
│(the-grey)│      │(agent-   │
│          │      │  grey)   │
│   ALL    │      │Production│
│  FILES   │      │   Only   │
└──────────┘      └──────────┘
     ▲                 ▲
     │                 │
  git push         sync_to_public.sh
   origin              (filtered)
```

## 🎯 Best Practices

1. **Commit to private first** - Always push to private before syncing public
2. **Use meaningful commits** - They'll appear in public repo history
3. **Test locally** - Ensure code works before syncing
4. **Update README** - Keep README_PUBLIC.md updated for public users
5. **Regular syncs** - Don't let repos diverge too much

## 📝 Example Session

```bash
# Morning: Start work
cd /mnt/d/Python/Projects/django/HTA-projects/agent-grey
git pull origin main  # Get latest from private

# Work on features
# ... make changes ...

# Commit to private
git add .
git commit -m "feat: Add search optimization"
git push origin main

# Ready to make public
./manage_public.sh dry-run  # Check what will sync
./sync_to_public.sh         # Sync to public

# End of day
git status  # Ensure everything committed
```

## 🆘 Help

```bash
# Get help on commands
./manage_public.sh help

# Check current configuration
./manage_public.sh status

# See what's different between repos
./manage_public.sh compare
```

---

**Remember:** You only maintain ONE folder locally. The scripts handle the complexity of managing two repos with different content!
