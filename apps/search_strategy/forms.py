from django import forms
from django.core.exceptions import ValidationError

from apps.serp_execution.providers import (
    get_default_provider_key,
    get_enabled_provider_choices,
)

from .models import SearchStrategy


class SearchStrategyForm(forms.ModelForm):
    """
    Form for creating and editing search strategies using the PIC framework.
    Provides dynamic fields for population, interest, and context terms.
    """

    # PIC Framework fields as text areas for dynamic input
    population_terms_text = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": (
                    "Enter population terms one at a time. These describe who "
                    "the research focuses on (e.g., elderly, diabetic patients)"
                ),
                "data-field": "population",
            }
        ),
        required=False,
        help_text="Enter terms describing the target population (one per line)",
    )

    interest_terms_text = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": (
                    "Enter intervention/interest terms. These describe what "
                    "you're studying (e.g., insulin therapy, diet management)"
                ),
                "data-field": "interest",
            }
        ),
        required=False,
        help_text="Enter terms describing the intervention or interest (one per line)",
    )

    context_terms_text = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": (
                    "Enter context terms. These describe where or under what "
                    "conditions (e.g., primary care, UK)"
                ),
                "data-field": "context",
            }
        ),
        required=False,
        help_text="Enter terms describing the context or setting (one per line)",
    )

    # Organization domains
    organization_domains = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Enter organization domains (e.g., nice.org.uk, who.int)",
                "data-field": "domains",
            }
        ),
        required=False,
        help_text="Enter organization domains to search (one per line)",
    )

    # Search configuration checkboxes
    include_general_search = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text="Include general web search without domain restrictions",
    )

    include_guidelines_filter = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        label="Guidelines filter",
        help_text=(
            "Add guideline-specific terms to all search queries "
            "(guideline*, guidance, statement*, recommendation*, CPG)"
        ),
    )

    # File types
    search_pdf = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        label="PDF documents",
    )

    search_doc = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        label="Word documents (.doc and .docx)",
    )

    # Search engines
    use_google_search = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        label="Google Web Search",
    )

    use_google_scholar = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        label="Google Scholar",
    )

    # Maximum results per query (pagination automatically calculated)
    max_results_per_query = forms.IntegerField(
        initial=100,  # Maximise coverage for systematic reviews
        min_value=10,
        max_value=100,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "style": "width: 100px;"}
        ),
        help_text="Total results per query - system automatically paginates (10-100)",
    )

    # Query splitting fields
    enable_query_splitting = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": "form-check-input",
                "data-bs-toggle": "collapse",
                "data-bs-target": "#splittingOptions",
            }
        ),
        label="Enable automatic query splitting",
        help_text="Automatically split long queries to avoid search engine limits",
    )

    splitting_strategy = forms.ChoiceField(
        required=False,
        initial="by_pic_terms",
        choices=[
            ("by_pic_terms", "Split by PIC term combinations"),
            ("by_domains", "Split by domains (keep existing)"),
            ("by_interest", "Split by individual interest terms"),
        ],
        widget=forms.Select(attrs={"class": "form-control"}),
        help_text="Strategy for splitting long queries",
    )

    max_query_length = forms.IntegerField(
        required=False,
        initial=2000,
        min_value=500,
        max_value=4000,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "style": "width: 150px;"}
        ),
        help_text="Maximum characters per query (recommended: 2000)",
    )

    serp_providers = forms.TypedMultipleChoiceField(
        required=True,
        coerce=str,
        widget=forms.CheckboxSelectMultiple(),
        label="Search Providers",
    )

    class Meta:
        model = SearchStrategy
        fields = [
            "population_terms",
            "interest_terms",
            "context_terms",
            "search_config",
        ]
        widgets = {
            "population_terms": forms.HiddenInput(),
            "interest_terms": forms.HiddenInput(),
            "context_terms": forms.HiddenInput(),
            "search_config": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.warnings = []  # Store non-blocking warnings

        # Populate SERP provider choices from enabled configs
        choices = get_enabled_provider_choices()
        self.fields["serp_providers"].choices = choices
        default_key = get_default_provider_key()
        self.fields["serp_providers"].initial = [default_key]

        # If we have an instance, populate the text fields from the model
        if self.instance and self.instance.pk:
            self.fields["population_terms_text"].initial = "\n".join(
                self.instance.population_terms
            )
            self.fields["interest_terms_text"].initial = "\n".join(
                self.instance.interest_terms
            )
            self.fields["context_terms_text"].initial = "\n".join(
                self.instance.context_terms
            )

            # Populate search configuration fields
            config = self.instance.search_config or {}
            self.fields["organization_domains"].initial = "\n".join(
                config.get("domains", [])
            )
            self.fields["include_general_search"].initial = config.get(
                "include_general_search", True
            )
            self.fields["include_guidelines_filter"].initial = config.get(
                "include_guidelines_filter", False
            )

            # File types
            file_types = config.get("file_types", [])
            self.fields["search_pdf"].initial = "pdf" in file_types
            self.fields["search_doc"].initial = "doc" in file_types

            # Search engines - support both list (search_types) and legacy string (search_type)
            search_types = config.get("search_types", [])
            if not search_types:
                # Backward compat: read legacy single search_type
                legacy = config.get("search_type", "google")
                search_types = [legacy] if legacy else ["google"]
            self.fields["use_google_search"].initial = "google" in search_types
            self.fields["use_google_scholar"].initial = "scholar" in search_types

            # Max results (pagination auto-calculated from this)
            self.fields["max_results_per_query"].initial = config.get(
                "max_results", 100
            )

            # Query splitting configuration
            splitting_config = config.get("query_splitting", {})
            self.fields["enable_query_splitting"].initial = splitting_config.get(
                "enabled", False
            )
            self.fields["splitting_strategy"].initial = splitting_config.get(
                "strategy", "by_pic_terms"
            )
            self.fields["max_query_length"].initial = splitting_config.get(
                "max_query_length", 2000
            )

            # SERP providers (restore saved selection)
            saved_providers = config.get("serp_providers", [])
            if saved_providers:
                self.fields["serp_providers"].initial = saved_providers

    def clean(self):
        """Custom validation for the search strategy form."""
        cleaned_data = super().clean()

        # Convert text fields to lists
        population_text = cleaned_data.get("population_terms_text", "")
        interest_text = cleaned_data.get("interest_terms_text", "")
        context_text = cleaned_data.get("context_terms_text", "")
        domains_text = cleaned_data.get("organization_domains", "")

        # Parse terms from text areas
        population_terms = self._parse_terms(population_text)
        interest_terms = self._parse_terms(interest_text)
        context_terms = self._parse_terms(context_text)
        domains = self._parse_terms(domains_text, allow_whitespace_split=True)

        # Set the model fields
        cleaned_data["population_terms"] = population_terms
        cleaned_data["interest_terms"] = interest_terms
        cleaned_data["context_terms"] = context_terms

        # Build search configuration
        file_types = []
        if cleaned_data.get("search_pdf"):
            file_types.append("pdf")
        if cleaned_data.get("search_doc"):
            file_types.append("doc")

        # Determine search types (both can be selected simultaneously)
        search_types = []
        if cleaned_data.get("use_google_search"):
            search_types.append("google")
        if cleaned_data.get("use_google_scholar"):
            search_types.append("scholar")
        if not search_types:
            search_types = ["google"]  # Default fallback

        # Build query splitting configuration
        query_splitting_config = {
            "enabled": cleaned_data.get("enable_query_splitting", False),
            "strategy": cleaned_data.get("splitting_strategy", "by_pic_terms"),
            "max_query_length": cleaned_data.get("max_query_length", 2000),
        }

        # Auto-calculate pagination from max_results (no user input needed)
        max_results = cleaned_data.get("max_results_per_query", 100)
        results_per_page = 10  # Serper API standard
        max_pages = (
            max_results + results_per_page - 1
        ) // results_per_page  # Ceiling division

        pagination_config = {
            "enabled": True,
            "results_per_page": results_per_page,
            "max_pages": max_pages,  # Auto-calculated from max_results
            "delay_between_pages": 1.0,  # Adaptive rate limiting
        }

        search_config = {
            "domains": domains,
            "include_general_search": cleaned_data.get("include_general_search", False),
            "include_guidelines_filter": cleaned_data.get(
                "include_guidelines_filter", False
            ),
            "file_types": file_types,
            "search_types": search_types,
            "max_results": max_results,
            "pagination": pagination_config,
            "query_splitting": query_splitting_config,
            "serp_providers": cleaned_data.get("serp_providers", []),
        }

        cleaned_data["search_config"] = search_config

        # Check query lengths if splitting is not enabled
        if not cleaned_data.get("enable_query_splitting", False):
            # Create temporary strategy to check query lengths
            from .models import SearchStrategy

            temp_strategy = SearchStrategy(
                population_terms=cleaned_data["population_terms"],
                interest_terms=cleaned_data["interest_terms"],
                context_terms=cleaned_data["context_terms"],
                search_config=search_config,
            )

            # Check for length issues
            length_issues = temp_strategy.check_query_lengths()
            if length_issues:
                warning_msg = (
                    f"{len(length_issues)} queries exceed the recommended {query_splitting_config['max_query_length']} "
                    f"character limit. Consider enabling query splitting to avoid search failures."
                )
                self.warnings.append(
                    {
                        "field": "general",
                        "message": warning_msg,
                        "details": length_issues,
                    }
                )

        # Validation: At least one PIC category must have terms
        if not any([population_terms, interest_terms, context_terms]):
            raise ValidationError(
                "At least one PIC category (Population, Interest, or Context) must have terms."
            )

        # Validation: Must have at least one domain or general search
        if not domains and not cleaned_data.get("include_general_search"):
            raise ValidationError(
                "You must specify at least one organization domain or enable general search."
            )

        # File types are optional - users can search for just webpages without document filters

        # Validation: At least one SERP provider must be selected
        if not cleaned_data.get("serp_providers"):
            raise ValidationError("At least one search provider must be selected.")

        return cleaned_data

    def _parse_terms(  # noqa: C901 - Term parsing logic
        self, text: str, allow_whitespace_split: bool = False
    ):
        """
        Parse terms from textarea input, intelligently handling various formats.

        Handles:
        - Each line as a separate term
        - Multiple terms on one line separated by commas
        - Quoted phrases (preserves the phrase as one term)
        - Mixed formats

        Examples:
        - "healthcare workers" -> ["healthcare workers"]
        - "nurses, doctors" -> ["nurses", "doctors"]
        - '"healthcare workers", nurses' -> ["healthcare workers", "nurses"]
        """
        if not text:
            return []

        import re

        terms = []

        # Process each line
        lines = text.strip().split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check if line contains commas (likely multiple terms)
            if "," in line:
                # Handle comma-separated terms, preserving quoted phrases
                # This regex finds either quoted strings or non-comma sequences
                pattern = r'"[^"]+"|\'[^\']+\'|[^,]+'
                matches = re.findall(pattern, line)

                for match in matches:
                    term = match.strip().strip('"').strip("'")
                    if term and term not in terms:
                        terms.append(term)
            else:
                # Allow splitting on whitespace when requested (domains field)
                if allow_whitespace_split and " " in line:
                    for term in line.split():
                        cleaned = term.strip()
                        if cleaned and cleaned not in terms:
                            terms.append(cleaned)
                else:
                    # Single term on the line (preserve multi-word terms)
                    if line and line not in terms:
                        terms.append(line)

        return terms

    def save(self, commit=True):
        """Save the strategy with the processed data."""
        strategy = super().save(commit=False)

        # The cleaned data has already been processed in clean()
        # Just ensure the fields are set
        if hasattr(self, "cleaned_data"):
            strategy.population_terms = self.cleaned_data.get("population_terms", [])
            strategy.interest_terms = self.cleaned_data.get("interest_terms", [])
            strategy.context_terms = self.cleaned_data.get("context_terms", [])
            strategy.search_config = self.cleaned_data.get("search_config", {})

        if commit:
            strategy.save()

        return strategy
