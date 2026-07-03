#!/usr/bin/env python3
"""
GitHub Copilot Integration Helper Script

Provides functions for triggering Copilot code reviews, checking review status,
and monitoring API quota. Supports GitHub Pro tier with graceful degradation.

Usage:
    python copilot_integration.py --test         # Run self-tests
    python copilot_integration.py --quota        # Check current quota
    python copilot_integration.py --trigger-pr <number>  # Trigger review

Environment Variables:
    GITHUB_TOKEN: GitHub token with repo and pull_requests:write permissions
    GITHUB_REPOSITORY: Format "owner/repo" (auto-set in GitHub Actions)
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict


# Configuration
QUOTA_CACHE_FILE = "/tmp/copilot_quota_cache.json"
QUOTA_CACHE_TTL_MINUTES = 5
MANUAL_QUOTA_FILE = ".github/cache/manual_quota_tracker.json"


def get_copilot_quota(repository: str, github_token: str) -> Dict:
    """
    Get Copilot quota status from manual tracking.

    GitHub does not provide a repo-level Copilot usage API.
    Quota is tracked locally via manual usage recording.

    Args:
        repository: Format "owner/repo"
        github_token: GitHub token (unused, kept for API compatibility)

    Returns:
        {
            "used": int,
            "remaining": int,
            "limit": int,
            "resets_at": str,  # ISO datetime
            "tier": str,  # "pro"
            "api_available": bool  # Always False
        }

    Raises:
        RuntimeError: If manual tracking fails
    """
    # Check cache first
    if os.path.exists(QUOTA_CACHE_FILE):
        try:
            with open(QUOTA_CACHE_FILE, "r") as f:
                cache = json.load(f)
                cache_time = datetime.fromisoformat(
                    cache.get("cached_at", "1970-01-01")
                )
                if datetime.now() - cache_time < timedelta(
                    minutes=QUOTA_CACHE_TTL_MINUTES
                ):
                    return cache["data"]
        except (json.JSONDecodeError, KeyError, ValueError):
            pass  # Cache invalid, continue to manual tracking

    return _get_manual_quota_tracking()


def _get_manual_quota_tracking() -> Dict:
    """
    Get quota from manual tracking file (Pro tier fallback).

    Manual tracking file stores estimated daily usage.
    Conservative default: 100 reviews/day limit (not official, estimated).

    Returns:
        Dictionary with quota information and tier set to "pro"
    """
    manual_file = Path(MANUAL_QUOTA_FILE)

    # Initialize if doesn't exist
    if not manual_file.exists():
        manual_file.parent.mkdir(parents=True, exist_ok=True)
        default_data = {
            "date": str(datetime.now().date()),
            "used": 0,
            "limit": 100,  # Conservative estimate for Pro tier
            "requests": [],
        }
        manual_file.write_text(json.dumps(default_data, indent=2))

    # Load tracking data
    try:
        data = json.loads(manual_file.read_text())

        # Reset if new day
        if data.get("date") != str(datetime.now().date()):
            data = {
                "date": str(datetime.now().date()),
                "used": 0,
                "limit": 100,
                "requests": [],
            }
            manual_file.write_text(json.dumps(data, indent=2))

        # Format as quota response
        quota_data = {
            "used": data.get("used", 0),
            "remaining": data.get("limit", 100) - data.get("used", 0),
            "limit": data.get("limit", 100),
            "resets_at": f"{data.get('date')}T23:59:59Z",
            "tier": "pro",
            "api_available": False,
        }

        # Cache the result
        cache = {"data": quota_data, "cached_at": datetime.now().isoformat()}
        with open(QUOTA_CACHE_FILE, "w") as f:
            json.dump(cache, f)

        return quota_data

    except (json.JSONDecodeError, KeyError) as e:
        raise RuntimeError(f"Manual quota tracking failed: {e}")


def _record_manual_quota_usage(repository: str, pr_number: int) -> None:
    """
    Record quota usage in manual tracking file.

    Args:
        repository: Repository name
        pr_number: PR number that triggered the review
    """
    manual_file = Path(MANUAL_QUOTA_FILE)
    if not manual_file.exists():
        return

    try:
        data = json.loads(manual_file.read_text())
        data["used"] = data.get("used", 0) + 1
        data["requests"].append(
            {
                "timestamp": datetime.now().isoformat(),
                "pr_number": pr_number,
                "repository": repository,
            }
        )
        manual_file.write_text(json.dumps(data, indent=2))
    except (json.JSONDecodeError, KeyError):
        pass  # Fail silently - manual tracking is best-effort


def trigger_copilot_review(pr_number: int, repository: str, github_token: str) -> Dict:
    """
    Trigger GitHub Copilot code review for a pull request.

    Works for all GitHub tiers (Pro, Business, Enterprise) via PR comment.

    Args:
        pr_number: Pull request number
        repository: Format "owner/repo"
        github_token: GitHub token with pull_requests:write permission

    Returns:
        {
            "status": "SUCCESS" | "QUOTA_WARNING" | "API_ERROR" | "TIMEOUT",
            "review_id": str (optional, if SUCCESS),
            "error_message": str (optional, if not SUCCESS),
            "quota_info": dict (quota information)
        }
    """
    # Check quota first (non-blocking warning for Pro tier)
    quota_info = None
    try:
        quota = get_copilot_quota(repository, github_token)
        quota_info = quota

        # Warning (not blocking) if quota low
        if quota["remaining"] < 5:
            return {
                "status": "QUOTA_WARNING",
                "error_message": (
                    f"Low quota: {quota['remaining']}/{quota['limit']} remaining. "
                    f"Proceeding anyway (tier: {quota['tier']})"
                ),
                "quota_info": quota,
            }
    except RuntimeError:
        # Quota check failed - proceed anyway with warning
        pass

    # Trigger Copilot review via PR comment
    cmd = [
        "gh",
        "pr",
        "comment",
        str(pr_number),
        "--repo",
        repository,
        "--body",
        "@copilot review",
    ]

    try:
        subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
            env={**os.environ, "GH_TOKEN": github_token},
        )

        # Record usage in manual tracking (if applicable)
        _record_manual_quota_usage(repository, pr_number)

        # Extract review ID (use PR number for simplicity)
        review_id = f"pr-{pr_number}-copilot"

        return {
            "status": "SUCCESS",
            "review_id": review_id,
            "quota_info": quota_info,
        }

    except subprocess.CalledProcessError as e:
        return {"status": "API_ERROR", "error_message": e.stderr}
    except subprocess.TimeoutExpired:
        return {
            "status": "TIMEOUT",
            "error_message": "Review trigger timeout (>30s)",
        }


def check_copilot_status(review_id: str, github_token: str) -> Dict:
    """
    Check status of Copilot review (simplified for Pro tier).

    Note: GitHub Pro doesn't provide detailed review status API.
    This is a simplified implementation that assumes completion.

    Args:
        review_id: Review identifier (format: "pr-{number}-copilot")
        github_token: GitHub token

    Returns:
        {
            "status": "pending" | "completed" | "failed",
            "review_url": str (optional),
            "note": str (explanation for Pro tier)
        }
    """
    # Validate review_id format
    if not review_id.startswith("pr-"):
        return {
            "status": "failed",
            "error": "Invalid review_id format (expected: pr-<number>-copilot)",
        }

    try:
        # Extract PR number from review_id
        parts = review_id.split("-")
        if len(parts) < 3:  # Should be pr-NUMBER-copilot
            raise ValueError("Cannot extract PR number")

        pr_number = parts[1]

        # Validate PR number is numeric
        if not pr_number.isdigit():
            raise ValueError("PR number must be numeric")

        # For Pro tier, assume completed (Copilot reviews are typically instant)
        # In Enterprise/Business, you would query PR reviews API for actual status
        return {
            "status": "completed",
            "review_url": f"https://github.com/{os.environ.get('GITHUB_REPOSITORY', 'owner/repo')}/pull/{pr_number}",
            "note": "Pro tier: Status assumed completed. Check PR manually for actual review.",
        }

    except (ValueError, IndexError) as e:
        return {"status": "failed", "error": f"Failed to parse review_id: {e}"}


def should_use_copilot(risk_score: int, quota_remaining: int) -> bool:
    """
    Decide whether to use Copilot based on risk score and quota.

    Decision Logic:
    - risk_score < 5: False (skip review, too low risk)
    - risk_score >= 10: True if quota_remaining > 10 (high risk, use if available)
    - 5 <= risk_score < 10: True if quota_remaining > 50 (medium risk, only if quota plentiful)

    Args:
        risk_score: PR risk score (0-100+)
        quota_remaining: Remaining Copilot quota for the day

    Returns:
        bool: True if Copilot should be used
    """
    if risk_score < 5:
        return False  # Skip low-risk PRs

    if risk_score >= 10:
        return quota_remaining > 10  # Use Copilot for high-risk if quota available

    # Medium risk (5 <= risk < 10)
    return quota_remaining > 50  # Only use if quota is plentiful


def main():
    """CLI interface for testing helper functions."""
    parser = argparse.ArgumentParser(
        description="GitHub Copilot Integration Helper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python copilot_integration.py --test
  python copilot_integration.py --quota
  python copilot_integration.py --trigger-pr 123
        """,
    )
    parser.add_argument("--test", action="store_true", help="Run self-tests")
    parser.add_argument("--quota", action="store_true", help="Check current quota")
    parser.add_argument(
        "--trigger-pr", type=int, metavar="PR_NUMBER", help="Trigger review for PR"
    )
    args = parser.parse_args()

    github_token = os.environ.get("GITHUB_TOKEN")
    repository = os.environ.get("GITHUB_REPOSITORY", "owner/repo")

    if not github_token:
        print("Error: GITHUB_TOKEN environment variable not set", file=sys.stderr)
        sys.exit(1)

    if args.quota:
        try:
            quota = get_copilot_quota(repository, github_token)
            print(json.dumps(quota, indent=2))
            print(
                f"\nTier: {quota['tier']} | API Available: {quota['api_available']}",
                file=sys.stderr,
            )
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.trigger_pr:
        try:
            result = trigger_copilot_review(args.trigger_pr, repository, github_token)
            print(json.dumps(result, indent=2))
            if result["status"] != "SUCCESS":
                sys.exit(1)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.test:
        print("Running self-tests...")

        # Test 1: Quota check
        try:
            quota = get_copilot_quota(repository, github_token)
            tier = quota.get("tier", "unknown")
            api_available = quota.get("api_available", False)
            print(
                f"✅ Quota check: {quota['remaining']}/{quota['limit']} remaining "
                f"(tier: {tier}, API: {api_available})"
            )
        except RuntimeError as e:
            print(f"❌ Quota check failed: {e}")
            sys.exit(1)

        # Test 2: Decision logic
        test_cases = [
            (3, 100, False, "Low-risk should skip"),
            (15, 20, True, "High-risk should use if quota available"),
            (15, 5, False, "High-risk should skip if quota low"),
            (7, 60, True, "Medium-risk should use if quota plentiful"),
            (7, 30, False, "Medium-risk should skip if quota low"),
        ]

        for risk, quota_rem, expected, description in test_cases:
            result = should_use_copilot(risk, quota_rem)
            if result == expected:
                print(f"✅ {description}")
            else:
                print(
                    f"❌ {description} (expected {expected}, got {result})",
                    file=sys.stderr,
                )
                sys.exit(1)

        print("\n✅ All self-tests passed")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
