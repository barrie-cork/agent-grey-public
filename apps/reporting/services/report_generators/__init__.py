"""
Report generator classes for different export formats.

This module provides a strategy pattern implementation for generating
reports in various formats (PDF, CSV, JSON).
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.reporting.models import ExportReport


class ReportGenerator(ABC):
    """Base class for report generators."""

    @abstractmethod
    def generate(self, report: "ExportReport", data: dict) -> bytes:
        """
        Generate report content.

        Args:
            report: ExportReport instance containing report metadata
            data: Dictionary containing report data

        Returns:
            bytes: Generated report content
        """
        pass

    @abstractmethod
    def get_content_type(self) -> str:
        """
        Get MIME content type for the generated report.

        Returns:
            str: MIME content type
        """
        pass

    @abstractmethod
    def get_file_extension(self) -> str:
        """
        Get file extension for the generated report.

        Returns:
            str: File extension (without dot)
        """
        pass
