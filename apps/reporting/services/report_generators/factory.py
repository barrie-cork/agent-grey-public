"""
Factory for creating report generators based on format type.
"""

from . import ReportGenerator
from .csv_generator import CSVReportGenerator
from .excel_generator import ExcelReportGenerator
from .html_generator import HTMLReportGenerator
from .pdf_generator import PDFReportGenerator


class ReportGeneratorFactory:
    """Factory for creating report generators."""

    _generators: dict = {
        "pdf": PDFReportGenerator,
        "csv": CSVReportGenerator,
        "html": HTMLReportGenerator,
        "xlsx": ExcelReportGenerator,
    }

    @classmethod
    def create(cls, format_type: str) -> ReportGenerator:
        """
        Create a report generator for the specified format.

        Args:
            format_type: The format type (pdf, csv, html)

        Returns:
            ReportGenerator instance

        Raises:
            ValueError: If format type is not supported
        """
        generator_class = cls._generators.get(format_type.lower())
        if not generator_class:
            raise ValueError(
                f"Unknown format type: {format_type}. "
                f"Supported formats: {', '.join(cls._generators.keys())}"
            )
        return generator_class()

    @classmethod
    def get_supported_formats(cls):
        """Get list of supported format types."""
        return list(cls._generators.keys())

    @classmethod
    def register_generator(cls, format_type: str, generator_class) -> None:
        """
        Register a new generator class for a format type.

        This allows extending the factory with custom generators.

        Args:
            format_type: The format type to register
            generator_class: The generator class to use for this format
        """
        cls._generators[format_type.lower()] = generator_class
