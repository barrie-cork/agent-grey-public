"""
Forms for the reporting app.

This module implements forms for report generation and configuration,
including validation for format compatibility and PRISMA compliance.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator


class ReportGenerationForm(forms.Form):
    """
    Form for generating various types of reports with format selection.

    Handles:
    - Report type selection (PRISMA flow, full report, etc.)
    - Export format selection with compatibility validation
    -  parameters for detailed exports
    """

    REPORT_CHOICES = [
        ("prisma_flow", "PRISMA Flow Diagram"),
        ("full_report", "Complete PRISMA Report"),
        ("search_strategy", "Search Strategy Documentation"),
        ("results_summary", "Results Summary Table"),
        ("bibliography", "Bibliography Export"),
        ("irr_metrics", "Inter-Rater Reliability Metrics"),
        ("audit_trail", "Decision Audit Trail"),
    ]

    FORMAT_CHOICES = [
        ("pdf", "PDF Document"),
        ("csv", "CSV File"),
        ("json", "JSON Data"),
    ]

    # Format compatibility mapping
    FORMAT_COMPATIBILITY = {
        "prisma_flow": ["pdf", "json"],
        "full_report": ["pdf"],
        "search_strategy": ["pdf", "json"],
        "results_summary": ["csv", "json"],
        "bibliography": ["json", "csv"],
        "irr_metrics": ["csv", "pdf", "json"],
        "audit_trail": ["csv", "json"],
    }

    report_type = forms.ChoiceField(
        choices=REPORT_CHOICES,
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
        label="Report Type",
        help_text="Select the type of report to generate",
    )

    export_format = forms.ChoiceField(
        choices=FORMAT_CHOICES,
        widget=forms.Select(attrs={"class": "form-control"}),
        label="Export Format",
        help_text="Select the file format for the report",
    )

    title = forms.CharField(
        max_length=200,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Enter report title"}
        ),
        label="Report Title",
        help_text="A descriptive title for your report",
    )

    include_appendices = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        label="Include detailed appendices",
        help_text="Add supplementary data and detailed breakdowns",
    )

    include_raw_data = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        label="Include raw search data",
        help_text="Export complete search results and metadata",
    )

    def __init__(self, *args, **kwargs):
        """Initialize form with session context."""
        self.session = kwargs.pop("session", None)
        super().__init__(*args, **kwargs)

        if self.session:
            self.fields["title"].initial = f"{self.session.title} - Report"

    def clean(self):
        """Validate form data including format compatibility."""
        cleaned_data = super().clean()
        report_type = cleaned_data.get("report_type")
        export_format = cleaned_data.get("export_format")

        if report_type and export_format:
            # Check format compatibility
            valid_formats = self.FORMAT_COMPATIBILITY.get(report_type, [])
            if export_format not in valid_formats:
                raise ValidationError(
                    f"{export_format.upper()} format not supported for {dict(self.REPORT_CHOICES)[report_type]}. "
                    f"Supported formats: {', '.join(f.upper() for f in valid_formats)}"
                )

        # Validate raw data inclusion
        if cleaned_data.get("include_raw_data") and report_type == "prisma_flow":
            raise ValidationError(
                "Raw data export is not available for PRISMA Flow Diagram reports."
            )

        return cleaned_data


class BulkExportForm(forms.Form):
    """
    Form for bulk export of multiple report types at once.

    Supports generating multiple reports in a single operation
    for comprehensive documentation packages.
    """

    BULK_REPORT_CHOICES = [
        ("complete_package", "Complete Documentation Package"),
        ("prisma_bundle", "PRISMA Compliance Bundle"),
        ("data_export", "Data Export Package"),
        ("custom", "Custom Selection"),
    ]

    export_package = forms.ChoiceField(
        choices=BULK_REPORT_CHOICES,
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
        label="Export Package",
        initial="complete_package",
    )

    selected_reports = forms.MultipleChoiceField(
        choices=ReportGenerationForm.REPORT_CHOICES,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        required=False,
        label="Select Reports",
        help_text="Choose specific reports to include (for custom packages)",
    )

    unified_format = forms.ChoiceField(
        choices=[("pdf", "PDF"), ("json", "JSON")],
        widget=forms.Select(attrs={"class": "form-control"}),
        label="Package Format",
        initial="pdf",
    )

    def clean(self):
        """Validate bulk export selections."""
        cleaned_data = super().clean()
        package = cleaned_data.get("export_package")
        selected = cleaned_data.get("selected_reports", [])

        if package == "custom" and not selected:
            raise ValidationError(
                "Please select at least one report for custom export package."
            )

        return cleaned_data


class ReportSchedulingForm(forms.Form):
    """
    Form for scheduling periodic report generation.

    Allows users to set up recurring report generation
    for ongoing systematic reviews.
    """

    FREQUENCY_CHOICES = [
        ("once", "One-time Report"),
        ("weekly", "Weekly"),
        ("monthly", "Monthly"),
        ("quarterly", "Quarterly"),
    ]

    frequency = forms.ChoiceField(
        choices=FREQUENCY_CHOICES,
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
        label="Report Frequency",
        initial="once",
    )

    start_date = forms.DateField(
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        label="Start Date",
        help_text="When to generate the first report",
    )

    email_notification = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        label="Email notifications",
        help_text="Receive email when reports are ready",
    )

    auto_download = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        label="Auto-download reports",
        help_text="Automatically download reports when generated",
    )


class ExcelImportForm(forms.Form):
    """
    Form for uploading Excel offline backup files for import.

    Handles:
    - File upload with .xlsx validation
    - File size limit (10MB)
    - Session association for import targeting
    """

    excel_file = forms.FileField(
        label="Excel Backup File",
        help_text="Upload the offline backup Excel file (.xlsx) with your review changes",
        validators=[
            FileExtensionValidator(allowed_extensions=["xlsx"]),
        ],
        widget=forms.FileInput(attrs={"accept": ".xlsx", "class": "form-control"}),
    )

    session = forms.UUIDField(widget=forms.HiddenInput())

    def clean_excel_file(self):
        """Validate file size."""
        file = self.cleaned_data.get("excel_file")
        if file.size > 10 * 1024 * 1024:  # 10MB limit
            raise ValidationError("File size must be under 10MB")
        return file


class PrismaOtherMethodsForm(forms.Form):
    """Form for editing PRISMA 2020 'other methods' identification data."""

    websites = forms.IntegerField(
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        label="Websites",
        help_text="Records identified from websites",
    )
    organisations = forms.IntegerField(
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        label="Organisations",
        help_text="Records identified from organisations",
    )
    other_sources = forms.IntegerField(
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        label="Other sources",
        help_text="Records from citation searching or other sources",
    )
    citation_searching = forms.IntegerField(
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        label="Citation searching",
        help_text="Records identified via citation searching",
    )
    reports_sought = forms.IntegerField(
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        label="Reports sought for retrieval",
    )
    reports_not_retrieved = forms.IntegerField(
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        label="Reports not retrieved",
    )
    reports_assessed = forms.IntegerField(
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        label="Reports assessed for eligibility",
    )
    reports_excluded = forms.IntegerField(
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        label="Reports excluded",
    )

    def clean(self) -> dict:
        """Validate arithmetic consistency (warnings, not blocking errors)."""
        cleaned_data = super().clean()
        self.warnings: list[str] = []

        reports_sought = cleaned_data.get("reports_sought")
        reports_not_retrieved = cleaned_data.get("reports_not_retrieved")
        reports_assessed = cleaned_data.get("reports_assessed")
        reports_excluded = cleaned_data.get("reports_excluded")

        if (
            reports_sought is not None
            and reports_not_retrieved is not None
            and reports_assessed is not None
        ):
            expected = reports_sought - reports_not_retrieved
            if reports_assessed != expected:
                self.warnings.append(
                    f"Reports assessed ({reports_assessed}) does not equal "
                    f"reports sought ({reports_sought}) minus not retrieved "
                    f"({reports_not_retrieved}) = {expected}."
                )

        if reports_excluded is not None and reports_assessed is not None:
            if reports_excluded > reports_assessed:
                self.warnings.append(
                    f"Reports excluded ({reports_excluded}) exceeds "
                    f"reports assessed ({reports_assessed})."
                )

        return cleaned_data
