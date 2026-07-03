"""
GitHub Models API rate limit tracker for free tier compliance.
Prevents exceeding 150 req/day (low tier) and 50 req/day (high tier).

Extended to support GitHub Copilot quota tracking.
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None


class RateLimitTracker:
    """Track GitHub Models API usage to stay within free tier limits"""

    LIMITS = {
        "low": {"per_minute": 15, "per_day": 150},
        "high": {"per_minute": 10, "per_day": 50},
    }

    def __init__(self, cache_file=".github/cache/api_usage.json"):
        self.cache_file = Path(cache_file)
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.usage = self._load_usage()

    def _load_usage(self):
        """Load usage data from cache file"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file) as f:
                    data = json.load(f)
                    # Reset if new day
                    if data.get("date") != str(datetime.now().date()):
                        return self._new_usage_record()
                    return data
            except (json.JSONDecodeError, KeyError):
                pass
        return self._new_usage_record()

    def _new_usage_record(self):
        """Create new usage record for current day"""
        return {
            "date": str(datetime.now().date()),
            "low": 0,
            "high": 0,
            "copilot_reviews": 0,
            "requests": [],
        }

    def can_make_request(self, tier="low", service="github_models"):
        """
        Check if request can be made within rate limits.

        Args:
            tier: "low" or "high" (GitHub Models) OR "business" or "enterprise" (Copilot)
            service: "github_models" or "copilot"

        Returns:
            True if request allowed, False otherwise
        """
        if service == "copilot":
            quota = check_copilot_quota(tier)
            # Reserve minimum 5 reviews for critical PRs
            return quota.get("available", False) and quota.get("remaining", 0) >= 5

        elif service == "github_models":
            # Existing GitHub Models logic
            if tier not in self.LIMITS:
                return False

            current = self.usage.get(tier, 0)
            limit = self.LIMITS[tier]["per_day"]
            return current < limit

        return False

    def record_request(self, tier="low", model="unknown", tokens_used=0):
        """Record API request"""
        self.usage[tier] = self.usage.get(tier, 0) + 1
        self.usage["requests"].append(
            {
                "timestamp": datetime.now().isoformat(),
                "tier": tier,
                "model": model,
                "tokens": tokens_used,
            }
        )
        self._save_usage()

    def _save_usage(self):
        """Save usage data to cache file"""
        with open(self.cache_file, "w") as f:
            json.dump(self.usage, f, indent=2)

    def get_remaining(self, tier="low"):
        """Get remaining requests for the day"""
        used = self.usage.get(tier, 0)
        limit = self.LIMITS[tier]["per_day"]
        return limit - used

    def get_stats(self):
        """Get usage statistics including Copilot quota"""
        copilot_quota = check_copilot_quota("business")

        return {
            "date": self.usage["date"],
            "low_tier": {
                "used": self.usage.get("low", 0),
                "remaining": self.get_remaining("low"),
                "limit": self.LIMITS["low"]["per_day"],
            },
            "high_tier": {
                "used": self.usage.get("high", 0),
                "remaining": self.get_remaining("high"),
                "limit": self.LIMITS["high"]["per_day"],
            },
            "copilot_tier": {
                "used": copilot_quota.get("limit", 50)
                - copilot_quota.get("remaining", 0),
                "remaining": copilot_quota.get("remaining", 0),
                "limit": copilot_quota.get("limit", 50),
            },
            "total_requests": len(self.usage.get("requests", [])),
        }


def check_copilot_quota(tier="business"):
    """
    Get Copilot quota status from GitHub API.

    Uses the correct endpoint: GET /orgs/{org}/copilot/billing

    Quota limits by tier:
    - Business: 50 reviews/hour
    - Enterprise: 100 reviews/hour

    Args:
        tier: Copilot subscription tier ("business" or "enterprise")

    Returns:
        Dict with available, limit, remaining, reset_at, error
    """
    quota_limits = {"business": 50, "enterprise": 100}
    limit = quota_limits.get(tier, 50)

    # Check cache first (1 hour TTL)
    cache_file = Path(".github/.copilot_quota_cache")
    if cache_file.exists():
        try:
            cache_data = json.loads(cache_file.read_text())
            cache_time = datetime.fromisoformat(cache_data["timestamp"])
            if datetime.now() - cache_time < timedelta(hours=1):
                return cache_data["quota"]
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

    # If requests not available, fall back to local tracking
    if requests is None:
        return _get_local_copilot_quota(limit)

    # Query GitHub API using correct endpoint
    github_token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY", "")

    if not github_token or not repo:
        return _get_local_copilot_quota(
            limit, error="GITHUB_TOKEN or GITHUB_REPOSITORY not set"
        )

    # Extract org from repo (format: "owner/repo")
    org = repo.split("/")[0] if "/" in repo else None
    if not org:
        return _get_local_copilot_quota(limit, error="Invalid GITHUB_REPOSITORY format")

    try:
        response = requests.get(
            f"https://api.github.com/orgs/{org}/copilot/billing",
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=10,
        )

        if response.status_code == 200:
            data = response.json()
            seat_breakdown = data.get("seat_breakdown", {})
            total_seats = seat_breakdown.get("total", 0)
            active_seats = seat_breakdown.get("active_this_cycle", 0)
            remaining = max(0, total_seats - active_seats)
            quota = {
                "available": remaining > 0,
                "limit": total_seats,
                "remaining": remaining,
                "reset_at": f"{datetime.now().date()}T23:59:59Z",
                "tier": data.get("plan_type", tier),
            }
        elif response.status_code == 404:
            quota = _get_local_copilot_quota(
                limit, error="Copilot billing endpoint not found (404)"
            )
        elif response.status_code == 403:
            quota = _get_local_copilot_quota(
                limit, error="Forbidden - insufficient permissions for Copilot billing"
            )
        else:
            quota = _get_local_copilot_quota(
                limit, error=f"API error: {response.status_code}"
            )
    except requests.RequestException as e:
        quota = _get_local_copilot_quota(limit, error=f"Request failed: {e}")

    # Cache result
    try:
        cache_file.parent.mkdir(exist_ok=True)
        cache_file.write_text(
            json.dumps({"timestamp": datetime.now().isoformat(), "quota": quota})
        )
    except OSError:
        pass  # Cache write failure is non-critical

    return quota


def _get_local_copilot_quota(limit: int, error: str = None):
    """
    Fallback to local usage tracking when API is unavailable.

    Args:
        limit: Copilot seat limit
        error: Optional error message to include

    Returns:
        Dict with available, limit, remaining, reset_at, error
    """
    usage_file = Path(".github/cache/api_usage.json")
    used = 0
    if usage_file.exists():
        try:
            data = json.loads(usage_file.read_text())
            if data.get("date") == str(datetime.now().date()):
                used = data.get("copilot_reviews", 0)
        except (json.JSONDecodeError, KeyError):
            pass

    remaining = max(0, limit - used)
    quota = {
        "available": remaining > 0,
        "limit": limit,
        "remaining": remaining,
        "reset_at": f"{datetime.now().date()}T23:59:59Z",
    }
    if error:
        quota["error"] = error
    return quota


def main():
    """CLI interface for rate limit tracker"""
    tracker = RateLimitTracker()

    if len(sys.argv) < 2:
        print(
            "Usage: python rate_limit_tracker.py [check|record|stats] [tier] [model] [tokens]"
        )
        sys.exit(1)

    command = sys.argv[1]

    if command == "check":
        tier = sys.argv[2] if len(sys.argv) > 2 else "low"
        can_request = tracker.can_make_request(tier)
        remaining = tracker.get_remaining(tier)
        print(f"can_request={can_request}")
        print(f"remaining={remaining}")
        sys.exit(0 if can_request else 1)

    elif command == "record":
        tier = sys.argv[2] if len(sys.argv) > 2 else "low"
        model = sys.argv[3] if len(sys.argv) > 3 else "unknown"
        tokens = int(sys.argv[4]) if len(sys.argv) > 4 else 0
        tracker.record_request(tier, model, tokens)
        print(f"Recorded {tier} tier request for model {model}")
        sys.exit(0)

    elif command == "stats":
        try:
            stats = tracker.get_stats()
        except Exception as e:
            # Return valid JSON even on error so the workflow can parse it
            stats = {
                "date": str(datetime.now().date()),
                "low_tier": {"used": 0, "remaining": 150, "limit": 150},
                "high_tier": {"used": 0, "remaining": 50, "limit": 50},
                "copilot_tier": {"used": 0, "remaining": 0, "limit": 50},
                "total_requests": 0,
                "error": str(e),
            }
        print(json.dumps(stats, indent=2))
        sys.exit(0)

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
