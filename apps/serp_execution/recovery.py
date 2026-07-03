"""
Simplified error recovery for SERP execution.
Basic retry logic with fixed delays for MVP.
"""

import logging

logger = logging.getLogger(__name__)


class SimpleRecoveryManager:
    """
    Simple recovery manager for MVP.
    Uses fixed delays based on error type.
    """

    # Fixed delays for different error types
    RATE_LIMIT_DELAY = 60  # 1 minute for rate limits
    NETWORK_ERROR_DELAY = 10  # 10 seconds for network errors
    DEFAULT_DELAY = 5  # 5 seconds for other errors
    MAX_RETRIES = 3  # Maximum retry attempts

    def should_retry(self, error: Exception, retry_count: int) -> bool:
        """
        Determine if retry should be attempted.

        Args:
            error: The exception that occurred
            retry_count: Number of retries already attempted

        Returns:
            True if should retry, False otherwise
        """
        # Don't retry if max attempts reached
        if retry_count >= self.MAX_RETRIES:
            return False

        # Don't retry authentication errors
        error_message = str(error).lower()
        if "auth" in error_message or "api key" in error_message:
            return False

        # Don't retry quota errors
        if "quota" in error_message:
            return False

        # Retry everything else
        return True

    def get_retry_delay(self, error) -> int:
        """
        Get delay in seconds before retry.

        Args:
            error: The exception that occurred or error message string

        Returns:
            Delay in seconds
        """
        # Handle both Exception objects and string error messages
        error_message = str(error).lower()

        # Check for rate limit errors
        if "rate limit" in error_message or "429" in error_message:
            return self.RATE_LIMIT_DELAY

        # Check for network errors
        if any(term in error_message for term in ["timeout", "connection", "network"]):
            return self.NETWORK_ERROR_DELAY

        # Default delay for other errors
        return self.DEFAULT_DELAY

    def get_error_category(self, error_message: str) -> str:
        """
        Categorize error for display purposes.

        Args:
            error_message: The error message

        Returns:
            Error category string
        """
        error_lower = error_message.lower()

        if "rate limit" in error_lower or "429" in error_lower:
            return "rate_limit"
        if any(term in error_lower for term in ["timeout", "connection", "network"]):
            return "network"
        if "auth" in error_lower or "api key" in error_lower:
            return "authentication"
        if "quota" in error_lower:
            return "quota"
        return "general"

    def analyze_error(self, execution):
        """
        Analyze an execution's error and provide recovery recommendations.

        Args:
            execution: SearchExecution object with error

        Returns:
            Dict with error analysis and recovery recommendations
        """
        error_message = execution.error_message or ""
        error_category = self.get_error_category(error_message)
        retry_count = execution.retry_count

        can_retry = self.should_retry(Exception(error_message), retry_count)
        retry_delay = self.get_retry_delay(error_message) if can_retry else 0

        return {
            "error_category": error_category,
            "error_message": error_message,
            "can_retry": can_retry,
            "retry_count": retry_count,
            "max_retries": self.MAX_RETRIES,
            "retry_delay": retry_delay,
            "recommended_action": self._get_recommended_action(
                error_category, can_retry
            ),
        }

    def _get_recommended_action(self, error_category: str, can_retry: bool) -> str:
        """Get recommended action based on error category."""
        if not can_retry:
            if error_category == "authentication":
                return "Check API key configuration"
            elif error_category == "quota":
                return "Quota exceeded, contact support or upgrade plan"
            else:
                return "Maximum retries reached, manual intervention required"

        if error_category == "rate_limit":
            return "Wait for rate limit to reset and retry"
        elif error_category == "network":
            return "Network issue, retry in a few seconds"
        else:
            return "Retry the operation"

    def get_recovery_options(self, execution):
        """
        Get recovery options for a failed execution.

        Args:
            execution: SearchExecution object with error

        Returns:
            List of recovery options with descriptions
        """
        error_message = execution.error_message or ""
        error_category = self.get_error_category(error_message)
        can_retry = self.should_retry(Exception(error_message), execution.retry_count)

        options = []

        if can_retry:
            options.append(
                {
                    "action": "retry",
                    "label": "Retry Now",
                    "description": "Retry the execution immediately",
                    "recommended": error_category in ["network", "general"],
                }
            )

            if error_category == "rate_limit":
                options.append(
                    {
                        "action": "retry_later",
                        "label": "Retry Later",
                        "description": f"Wait {self.RATE_LIMIT_DELAY} seconds before retrying",
                        "recommended": True,
                    }
                )

        options.append(
            {
                "action": "skip",
                "label": "Skip Query",
                "description": "Skip this query and continue with others",
                "recommended": not can_retry,
            }
        )

        options.append(
            {
                "action": "manual",
                "label": "Manual Review",
                "description": "Mark for manual intervention",
                "recommended": error_category == "authentication",
            }
        )

        return options


# Global instance
recovery_manager = SimpleRecoveryManager()
