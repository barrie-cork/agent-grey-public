"""
Formatting utilities for the reporting app.

This module provides centralized formatting functions for consistent
display of data across the reporting app.
"""


class FileFormatters:
    """Centralized formatting utilities for file-related operations."""

    @staticmethod
    def format_file_size(size_bytes) -> str:
        """
        Format file size with proper handling of edge cases.

        Args:
            size_bytes: File size in bytes (can be None)

        Returns:
            Human-readable file size string

        Examples:
            >>> FileFormatters.format_file_size(1024)
            '1.0 KB'
            >>> FileFormatters.format_file_size(0)
            '0 bytes'
            >>> FileFormatters.format_file_size(None)
            'Not available'
        """
        if size_bytes is None:
            return "Not available"

        if size_bytes == 0:
            return "0 bytes"

        # Handle negative sizes (shouldn't happen but be defensive)
        if size_bytes < 0:
            return "Invalid size"

        for unit in ["bytes", "KB", "MB", "GB"]:
            if size_bytes < 1024.0:
                if unit == "bytes":
                    return f"{size_bytes} {unit}"
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0

        return f"{size_bytes:.1f} TB"

    @staticmethod
    def format_percentage(value: float, decimal_places: int = 0) -> str:
        """
        Format a percentage value with specified decimal places.

        Args:
            value: The percentage value (0-100)
            decimal_places: Number of decimal places to show

        Returns:
            Formatted percentage string
        """
        if value is None:
            return "N/A"

        # For whole numbers, avoid showing decimals even if decimal_places > 0
        if decimal_places == 0 or value == int(value):
            return f"{int(value)}%"

        return f"{value:.{decimal_places}f}%"

    @staticmethod
    def format_count(count: int, singular: str, plural: str | None = None) -> str:
        """
        Format a count with proper singular/plural forms.

        Args:
            count: The number to format
            singular: Singular form of the noun
            plural: Plural form (if None, adds 's' to singular)

        Returns:
            Formatted string with count and proper noun form

        Examples:
            >>> FileFormatters.format_count(1, "result")
            '1 result'
            >>> FileFormatters.format_count(5, "result")
            '5 results'
            >>> FileFormatters.format_count(2, "study", "studies")
            '2 studies'
        """
        if plural is None:
            plural = f"{singular}s"

        noun = singular if count == 1 else plural
        return f"{count} {noun}"


class DateFormatters:
    """Formatting utilities for dates and times."""

    @staticmethod
    def format_duration(days: int) -> str:
        """
        Format duration in days to human-readable string.

        Args:
            days: Number of days

        Returns:
            Human-readable duration string

        Examples:
            >>> DateFormatters.format_duration(1)
            '1 day'
            >>> DateFormatters.format_duration(7)
            '1 week'
            >>> DateFormatters.format_duration(31)
            '1 month, 3 days'
        """
        if days == 0:
            return "Less than 1 day"

        if days == 1:
            return "1 day"

        # Calculate larger units
        years = days // 365
        remaining_days = days % 365
        months = remaining_days // 30
        remaining_days = remaining_days % 30
        weeks = remaining_days // 7
        remaining_days = remaining_days % 7

        parts = []

        if years > 0:
            parts.append(FileFormatters.format_count(years, "year"))
        if months > 0:
            parts.append(FileFormatters.format_count(months, "month"))
        if weeks > 0:
            parts.append(FileFormatters.format_count(weeks, "week"))
        if remaining_days > 0:
            parts.append(FileFormatters.format_count(remaining_days, "day"))

        if len(parts) == 1:
            return parts[0]
        elif len(parts) == 2:
            return f"{parts[0]}, {parts[1]}"
        else:
            # Join all but last with commas, then add "and" before last
            return ", ".join(parts[:-1]) + f" and {parts[-1]}"


class StatusFormatters:
    """Formatting utilities for status displays."""

    # Status to Tailwind badge classes mapping
    STATUS_CLASSES = {
        "pending": "bg-warning text-white",
        "generating": "bg-primary text-primary-foreground",
        "completed": "bg-success text-white",
        "failed": "bg-destructive text-destructive-foreground",
        "expired": "bg-secondary text-secondary-foreground",
        "draft": "bg-secondary text-secondary-foreground",
        "defining_search": "bg-primary text-primary-foreground",
        "ready_to_execute": "bg-primary text-primary-foreground",
        "executing": "bg-primary text-primary-foreground",
        "processing_results": "bg-primary text-primary-foreground",
        "ready_for_review": "bg-primary text-primary-foreground",
        "under_review": "bg-warning text-white",
        "archived": "bg-secondary text-secondary-foreground",
    }

    # Status to inline SVG icon mapping
    STATUS_ICONS = {
        "pending": '<svg class="w-3 h-3 mr-1 inline-block" fill="none" stroke="currentColor" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke-width="2"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6l4 2"/></svg>',
        "generating": '<svg class="w-3 h-3 mr-1 inline-block" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>',
        "completed": '<svg class="w-3 h-3 mr-1 inline-block" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>',
        "failed": '<svg class="w-3 h-3 mr-1 inline-block" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>',
        "expired": '<svg class="w-3 h-3 mr-1 inline-block" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4"/></svg>',
    }

    # Default icon for unknown statuses
    DEFAULT_ICON = '<svg class="w-3 h-3 mr-1 inline-block" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>'

    @classmethod
    def get_status_class(cls, status: str) -> str:
        """Get Tailwind classes for a status badge."""
        return cls.STATUS_CLASSES.get(status, "bg-secondary text-secondary-foreground")

    @classmethod
    def get_status_icon(cls, status: str) -> str:
        """Get inline SVG icon for a status."""
        return cls.STATUS_ICONS.get(status, cls.DEFAULT_ICON)

    @classmethod
    def format_status_badge(cls, status: str, display_text: str | None = None) -> str:
        """
        Format a status as an HTML badge with Tailwind styling.

        Args:
            status: The status string
            display_text: Text to display (defaults to status)

        Returns:
            HTML string for Tailwind badge with inline SVG icon
        """
        if display_text is None:
            display_text = status.replace("_", " ").title()

        css_class = cls.get_status_class(status)
        icon = cls.get_status_icon(status)

        return (
            f'<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium {css_class}">'
            f"{icon}{display_text}"
            f"</span>"
        )
