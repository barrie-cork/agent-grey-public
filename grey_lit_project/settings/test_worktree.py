"""
Worktree test settings -- used by Junior tasks running in isolated worktrees.

Imports everything from .test (eager Celery, LocMemCache, MD5 hasher, etc)
then overrides the database to use a job-specific test database so multiple
worktrees can run tests in parallel without colliding.

Required environment variables:
    DATABASE_URL       -- PostgreSQL connection string
    WORKTREE_JOB_ID   -- numeric job ID extracted from the worktree path
"""

import os

import dj_database_url

from .test import *  # noqa: F401, F403

# --- Required env vars (fail hard if missing) ---

if "DATABASE_URL" not in os.environ:
    raise RuntimeError(
        "DATABASE_URL is required for worktree tests. "
        "Use scripts/run-worktree-tests.sh to set it automatically."
    )

WORKTREE_JOB_ID = os.environ.get("WORKTREE_JOB_ID")
if not WORKTREE_JOB_ID:
    raise RuntimeError(
        "WORKTREE_JOB_ID is required for worktree tests. "
        "Use scripts/run-worktree-tests.sh to set it automatically."
    )

# --- Database (job-isolated) ---

DATABASES = {
    "default": dj_database_url.parse(
        os.environ["DATABASE_URL"],
        conn_max_age=0,
        conn_health_checks=False,
    )
}

# Each worktree gets its own test database to avoid collisions
DATABASES["default"]["TEST"] = {
    "NAME": f"test_agent_grey_job_{WORKTREE_JOB_ID}",
}

CONN_MAX_AGE = 0
