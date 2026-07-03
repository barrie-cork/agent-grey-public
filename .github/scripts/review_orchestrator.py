#!/usr/bin/env python3
"""
Review Orchestrator - Selects review service based on quota availability.

Priority: Copilot (if quota available) → GitHub Models (fallback) → Skip
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, Literal

# Import from existing scripts
sys.path.append(str(Path(__file__).parent))
from rate_limit_tracker import RateLimitTracker, check_copilot_quota

ReviewService = Literal["copilot", "github_models", "skip"]


def select_review_service(tier: str = "business") -> Dict:
    """
    Select review service based on quota availability.

    Decision tree:
    1. Check Copilot quota → Use if available (remaining ≥ 5)
    2. Check GitHub Models quota → Use if Copilot unavailable
    3. Skip if both exhausted

    Args:
        tier: Copilot subscription tier ("business" or "enterprise")

    Returns:
        Dict with selected service, reason, and quota info
    """
    # Priority 1: Copilot (if quota available)
    copilot_quota = check_copilot_quota(tier)

    if copilot_quota.get("available", False) and copilot_quota.get("remaining", 0) >= 5:
        return {
            "service": "copilot",
            "reason": "quota_available",
            "quota_remaining": copilot_quota["remaining"],
            "quota_limit": copilot_quota["limit"],
        }

    # Priority 2: GitHub Models (fallback)
    tracker = RateLimitTracker()
    if tracker.can_make_request(tier="high", service="github_models"):
        return {
            "service": "github_models",
            "reason": (
                "copilot_quota_exhausted"
                if copilot_quota.get("remaining", 0) < 5
                else "copilot_error"
            ),
            "quota_remaining": 0,
            "quota_limit": copilot_quota.get("limit", 50),
        }

    # Priority 3: Skip (all quotas exhausted)
    return {
        "service": "skip",
        "reason": "all_quotas_exhausted",
        "quota_remaining": 0,
        "quota_limit": 0,
    }


def execute_review(
    service: ReviewService, pr_number: int, repo: str, github_token: str
) -> Dict:
    """
    Execute review with selected service.

    Args:
        service: "copilot", "github_models", or "skip"
        pr_number: PR number to review
        repo: Repository in owner/name format
        github_token: GitHub authentication token

    Returns:
        Dict with status, service_used, review_url (if applicable)
    """
    if service == "copilot":
        # Call copilot_integration.py
        result = subprocess.run(
            [
                "python",
                ".github/scripts/copilot_integration.py",
                "--trigger-pr",
                str(pr_number),
            ],
            capture_output=True,
            text=True,
            env={"GITHUB_TOKEN": github_token, "GITHUB_REPOSITORY": repo},
        )

        if result.returncode == 0:
            try:
                output = json.loads(result.stdout.strip())
                return {
                    "status": "success",
                    "service": "copilot",
                    "review_id": output.get("review_id"),
                }
            except json.JSONDecodeError:
                return {
                    "status": "success",
                    "service": "copilot",
                    "output": result.stdout.strip(),
                }
        else:
            return {
                "status": "error",
                "service": "copilot",
                "error": result.stderr.strip() or result.stdout.strip(),
            }

    elif service == "github_models":
        # Dispatch fallback workflow
        result = subprocess.run(
            [
                "gh",
                "workflow",
                "run",
                "ai-code-review-fallback.yml",
                "-f",
                f"pr_number={pr_number}",
                "-f",
                "reason=copilot_quota_exhausted",
            ],
            capture_output=True,
            text=True,
            env={"GH_TOKEN": github_token},
        )

        if result.returncode == 0:
            return {
                "status": "success",
                "service": "github_models",
                "message": "Fallback workflow dispatched",
            }
        else:
            return {
                "status": "error",
                "service": "github_models",
                "error": result.stderr.strip() or result.stdout.strip(),
            }

    else:  # skip
        return {
            "status": "skipped",
            "service": "skip",
            "reason": "All quotas exhausted",
        }


def main():
    """CLI interface for review orchestrator"""
    parser = argparse.ArgumentParser(description="Review service orchestrator")
    parser.add_argument("--pr", type=int, help="PR number (required for execution)")
    parser.add_argument("--repo", help="Repository (owner/name, required for execution)")
    parser.add_argument("--token", help="GitHub token (required for execution)")
    parser.add_argument(
        "--tier", default="business", help="Copilot tier (default: business)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Dry run (no execution)"
    )
    parser.add_argument(
        "--select-only",
        action="store_true",
        help="Only select service, don't execute",
    )

    args = parser.parse_args()

    # Select service
    selection = select_review_service(args.tier)
    print(f"Selected service: {selection['service']}")
    print(f"Reason: {selection['reason']}")
    print(
        f"Quota remaining: {selection['quota_remaining']}/{selection['quota_limit']}"
    )

    if args.dry_run or args.select_only:
        print("\n✅ Dry run complete - no execution")
        sys.exit(0)

    # Validate required parameters for execution
    if not args.pr or not args.repo or not args.token:
        print(
            "\n❌ Error: --pr, --repo, and --token are required for execution",
            file=sys.stderr,
        )
        print("Use --dry-run or --select-only to skip execution", file=sys.stderr)
        sys.exit(1)

    # Execute review
    print(f"\nExecuting review for PR #{args.pr}...")
    result = execute_review(selection["service"], args.pr, args.repo, args.token)
    print(f"Execution result: {json.dumps(result, indent=2)}")
    sys.exit(0 if result["status"] in ["success", "skipped"] else 1)


if __name__ == "__main__":
    main()
