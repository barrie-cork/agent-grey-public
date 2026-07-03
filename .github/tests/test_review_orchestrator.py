"""
Unit tests for review_orchestrator.py

Tests cover:
- Core logic: Service selection based on quota availability
- Contextual integration: Workflow dispatch, error handling
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


# Import orchestrator
sys.path.append(str(Path(__file__).parent.parent / ".github" / "scripts"))
from review_orchestrator import execute_review, select_review_service


# Core Logic Tests (🎯⟨coverage:core⟩)


def test_select_copilot_when_quota_available():
    """Test Copilot selected when quota available and remaining ≥ 5."""
    with patch("review_orchestrator.check_copilot_quota") as mock_quota:
        mock_quota.return_value = {
            "available": True,
            "remaining": 20,
            "limit": 50,
            "reset_at": "2025-10-24T12:00:00Z",
        }

        result = select_review_service("business")

        assert result["service"] == "copilot"
        assert result["reason"] == "quota_available"
        assert result["quota_remaining"] == 20
        assert result["quota_limit"] == 50


def test_select_fallback_when_quota_exhausted():
    """Test GitHub Models selected when Copilot quota < 5."""
    with patch("review_orchestrator.check_copilot_quota") as mock_copilot, patch(
        "review_orchestrator.RateLimitTracker"
    ) as mock_tracker:

        mock_copilot.return_value = {
            "available": True,
            "remaining": 3,  # < 5 threshold
            "limit": 50,
            "reset_at": "2025-10-24T12:00:00Z",
        }

        mock_instance = MagicMock()
        mock_instance.can_make_request.return_value = True
        mock_tracker.return_value = mock_instance

        result = select_review_service("business")

        assert result["service"] == "github_models"
        assert result["reason"] == "copilot_quota_exhausted"


def test_select_skip_when_all_quotas_exhausted():
    """Test skip when both Copilot and GitHub Models exhausted."""
    with patch("review_orchestrator.check_copilot_quota") as mock_copilot, patch(
        "review_orchestrator.RateLimitTracker"
    ) as mock_tracker:

        mock_copilot.return_value = {
            "available": False,
            "remaining": 0,
            "limit": 50,
            "reset_at": None,
        }

        mock_instance = MagicMock()
        mock_instance.can_make_request.return_value = False
        mock_tracker.return_value = mock_instance

        result = select_review_service("business")

        assert result["service"] == "skip"
        assert result["reason"] == "all_quotas_exhausted"


def test_reserve_minimum_5_reviews():
    """Test that minimum 5 reviews reserved (doesn't use Copilot if remaining = 4)."""
    with patch("review_orchestrator.check_copilot_quota") as mock_quota, patch(
        "review_orchestrator.RateLimitTracker"
    ) as mock_tracker:

        mock_quota.return_value = {
            "available": True,
            "remaining": 4,  # Below threshold
            "limit": 50,
            "reset_at": "...",
        }

        mock_instance = MagicMock()
        mock_instance.can_make_request.return_value = True
        mock_tracker.return_value = mock_instance

        result = select_review_service("business")

        # Should NOT select Copilot with only 4 remaining
        assert result["service"] != "copilot"
        assert result["service"] == "github_models"


def test_copilot_error_fallback():
    """Test fallback when Copilot available but not enough quota."""
    with patch("review_orchestrator.check_copilot_quota") as mock_copilot, patch(
        "review_orchestrator.RateLimitTracker"
    ) as mock_tracker:

        mock_copilot.return_value = {
            "available": True,
            "remaining": 2,  # Available but below threshold
            "limit": 50,
            "reset_at": "2025-10-24T12:00:00Z",
        }

        mock_instance = MagicMock()
        mock_instance.can_make_request.return_value = True
        mock_tracker.return_value = mock_instance

        result = select_review_service("business")

        assert result["service"] == "github_models"
        assert result["reason"] == "copilot_quota_exhausted"


# Contextual Integration Tests (🎯⟨coverage:context⟩)


def test_execute_review_with_copilot():
    """Test review execution with Copilot service."""
    with patch("review_orchestrator.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"review_id": "123", "status": "SUCCESS"}',
            stderr="",
        )

        result = execute_review("copilot", 123, "owner/repo", "fake_token")

        assert result["status"] == "success"
        assert result["service"] == "copilot"
        assert "review_id" in result


def test_execute_review_with_github_models():
    """Test review execution with GitHub Models fallback."""
    with patch("review_orchestrator.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="Workflow dispatched", stderr=""
        )

        result = execute_review("github_models", 123, "owner/repo", "fake_token")

        assert result["status"] == "success"
        assert result["service"] == "github_models"
        assert "message" in result


def test_execute_review_skip():
    """Test skipping review when no service available."""
    result = execute_review("skip", 123, "owner/repo", "fake_token")

    assert result["status"] == "skipped"
    assert result["service"] == "skip"
    assert result["reason"] == "All quotas exhausted"


def test_workflow_dispatch_integration():
    """Test fallback workflow dispatch mechanism."""
    with patch("review_orchestrator.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = execute_review("github_models", 456, "owner/repo", "token")

        # Verify gh workflow run called with correct inputs
        call_args = mock_run.call_args[0][0]
        assert "gh" in call_args
        assert "workflow" in call_args
        assert "run" in call_args
        assert "ai-code-review-fallback.yml" in call_args
        assert "-f" in call_args

        # Find pr_number argument
        pr_number_arg = None
        for i, arg in enumerate(call_args):
            if "pr_number=" in str(arg):
                pr_number_arg = arg
                break

        assert pr_number_arg == "pr_number=456"
        assert result["status"] == "success"


def test_error_handling_copilot_failure():
    """Test error handling when Copilot API fails."""
    with patch("review_orchestrator.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="API error"
        )

        result = execute_review("copilot", 123, "owner/repo", "token")

        assert result["status"] == "error"
        assert result["service"] == "copilot"
        assert "error" in result


def test_error_handling_github_models_failure():
    """Test error handling when GitHub Models dispatch fails."""
    with patch("review_orchestrator.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="Workflow not found"
        )

        result = execute_review("github_models", 123, "owner/repo", "token")

        assert result["status"] == "error"
        assert result["service"] == "github_models"
        assert "error" in result


def test_copilot_non_json_output():
    """Test handling of non-JSON output from Copilot integration."""
    with patch("review_orchestrator.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="Review triggered successfully", stderr=""
        )

        result = execute_review("copilot", 123, "owner/repo", "token")

        assert result["status"] == "success"
        assert result["service"] == "copilot"
        assert "output" in result


def test_enterprise_tier_quota_limit():
    """Test that enterprise tier uses correct quota limit (100)."""
    with patch("review_orchestrator.check_copilot_quota") as mock_quota:
        mock_quota.return_value = {
            "available": True,
            "remaining": 60,
            "limit": 100,  # Enterprise limit
            "reset_at": "2025-10-24T12:00:00Z",
        }

        result = select_review_service("enterprise")

        assert result["service"] == "copilot"
        assert result["quota_limit"] == 100


def test_quota_boundary_condition_exactly_5():
    """Test boundary condition when exactly 5 reviews remaining."""
    with patch("review_orchestrator.check_copilot_quota") as mock_quota:
        mock_quota.return_value = {
            "available": True,
            "remaining": 5,  # Exactly at threshold
            "limit": 50,
            "reset_at": "2025-10-24T12:00:00Z",
        }

        result = select_review_service("business")

        # Should select Copilot when remaining = 5 (threshold is ≥ 5)
        assert result["service"] == "copilot"
        assert result["reason"] == "quota_available"


# Test Configuration and Edge Cases


def test_copilot_unavailable_reason_mapping():
    """Test reason is set to copilot_error when available but error occurs."""
    with patch("review_orchestrator.check_copilot_quota") as mock_copilot, patch(
        "review_orchestrator.RateLimitTracker"
    ) as mock_tracker:

        # Copilot not available (error), but some remaining quota
        mock_copilot.return_value = {
            "available": False,
            "remaining": 10,  # > 5 but marked unavailable
            "limit": 50,
            "reset_at": None,
        }

        mock_instance = MagicMock()
        mock_instance.can_make_request.return_value = True
        mock_tracker.return_value = mock_instance

        result = select_review_service("business")

        assert result["service"] == "github_models"
        # Should be copilot_error since remaining > 5 but not available
        assert result["reason"] == "copilot_error"
