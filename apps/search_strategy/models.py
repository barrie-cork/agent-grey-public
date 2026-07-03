import uuid

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.core.models import TimeStampedModel
from apps.review_manager.models import SearchSession


def format_term(term: str) -> str:
    """Add quotes only to multi-word terms."""
    if " " in term:
        return f'"{term}"'
    return term


def default_search_config():
    """Default configuration for search strategy."""
    return {
        "domains": [],
        "file_types": [],
        "include_general_search": True,
        "include_guidelines_filter": False,
        "search_types": ["google"],
        "max_results": 100,  # Maximise coverage for systematic reviews
        "pagination": {
            "enabled": True,
            "results_per_page": 10,  # Serper API standard
            "max_pages": 10,  # Automatically calculated from max_results
            "delay_between_pages": 2.0,  # Increased to reduce rate limiting (was 1.0s)
        },
    }


class SearchStrategy(TimeStampedModel):
    """
    Represents a search strategy using the PIC framework.
    Generates Boolean queries for multiple domains and file types.
    """

    # Relationships
    session = models.OneToOneField(
        SearchSession, on_delete=models.CASCADE, related_name="search_strategy"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="search_strategies",
    )

    # PIC Framework fields using PostgreSQL ArrayField
    population_terms = ArrayField(
        models.CharField(max_length=200),
        default=list,
        blank=True,
        help_text="Terms describing the population (e.g., 'elderly', 'children with autism')",
    )
    interest_terms = ArrayField(
        models.CharField(max_length=200),
        default=list,
        blank=True,
        help_text="Terms describing the intervention/interest (e.g., 'telehealth', 'cognitive therapy')",
    )
    context_terms = ArrayField(
        models.CharField(max_length=200),
        default=list,
        blank=True,
        help_text="Terms describing the context/setting (e.g., 'rural', 'low-income countries')",
    )

    # Search configuration
    search_config = models.JSONField(
        default=default_search_config,
        blank=True,
        help_text=(
            "Configuration for domains, file types, and search parameters. "
            "See SearchConfigType in model_types.py"
        ),
    )
    # Structure: {
    #     "domains": ["nice.org.uk", "who.int", "custom-domain.com"],
    #     "include_general_search": true,
    #     "file_types": ["pdf", "doc"],
    #     "search_types": ["google", "scholar"]  # one or both
    # }

    # Metadata
    is_complete = models.BooleanField(default=False)
    validation_errors = models.JSONField(
        default=dict,
        blank=True,
        help_text="Validation error messages. See ValidationErrorsType in model_types.py",
    )

    # Cache for query generation (not persisted to DB)
    _cached_queries = None

    class Meta:
        db_table = "search_strategies"
        verbose_name = "Search Strategy"
        verbose_name_plural = "Search Strategies"
        indexes = [
            models.Index(fields=["session"]),
            models.Index(fields=["user"]),
            models.Index(fields=["is_complete"]),
        ]

    def __str__(self) -> str:
        return f"Strategy for {self.session.title}"

    def validate_completeness(self) -> bool:
        """Validate that the strategy has all required components."""
        errors = {}

        # At least one PIC category must have terms
        if not any([self.population_terms, self.interest_terms, self.context_terms]):
            errors["pic_terms"] = "At least one PIC category must have terms"

        # Must have at least one domain or general search enabled
        domains = self.search_config.get("domains", [])
        include_general = self.search_config.get("include_general_search", False)
        if not domains and not include_general:
            errors["domains"] = "At least one domain or general search must be selected"

        # File types are optional - can search for just webpages

        self.validation_errors = errors
        self.is_complete = len(errors) == 0
        return self.is_complete

    def generate_base_query(self) -> str:
        """Generate the base Boolean query from PIC terms.

        CORE_REQUIREMENTS: Must preserve full query structure
        for display during execution (line 189).
        """
        import logging

        logger = logging.getLogger(__name__)

        query_parts = []

        # Build query parts for each PIC category
        if self.population_terms:
            pop_query = " OR ".join(format_term(term) for term in self.population_terms)
            query_parts.append(f"({pop_query})")

        if self.interest_terms:
            int_query = " OR ".join(format_term(term) for term in self.interest_terms)
            query_parts.append(f"({int_query})")

        if self.context_terms:
            ctx_query = " OR ".join(format_term(term) for term in self.context_terms)
            query_parts.append(f"({ctx_query})")

        # Add guidelines filter if enabled
        if self.search_config.get("include_guidelines_filter", False):
            guidelines_terms = (
                "(guideline* OR guidance OR statement* OR recommendation* OR CPG)"
            )
            query_parts.append(guidelines_terms)

        # Combine with AND operators
        final_query = " AND ".join(query_parts) if query_parts else ""
        logger.debug(
            f"Generated base query: {final_query}"
        )  # Changed from info to debug
        return final_query

    def _generate_domain_queries(self, base_query: str, file_type_filter: str) -> list:
        """Generate domain-specific search queries.

        Args:
            base_query: The base Boolean query from PIC terms.
            file_type_filter: Pre-built file type filter string.

        Returns:
            List of query dictionaries for each domain.
        """
        queries = []
        domains = self.search_config.get("domains", [])

        for domain in domains:
            domain_query = f"site:{domain} {base_query}"
            if file_type_filter:
                # Google treats spaces as implicit AND; explicit AND is interpreted
                # as a literal word. filetype: is a search operator, not a Boolean
                # term. Parentheses kept for multi-type OR grouping.
                domain_query += f" ({file_type_filter})"
            queries.append(
                {"query": domain_query, "domain": domain, "type": "domain-specific"}
            )

        return queries

    def _generate_general_query(self, base_query: str, file_type_filter: str) -> list:
        """Generate the general (non-domain-specific) search query.

        Args:
            base_query: The base Boolean query from PIC terms.
            file_type_filter: Pre-built file type filter string.

        Returns:
            List containing the general query dict, or empty list if disabled.
        """
        if not self.search_config.get("include_general_search", False):
            return []

        general_query = base_query
        if file_type_filter:
            general_query += f" ({file_type_filter})"
        return [{"query": general_query, "domain": None, "type": "general"}]

    def generate_queries(self):
        """Generate all search queries based on domains and file types.

        CORE_REQUIREMENTS Alignment:
        - Preserves full query text (line 189)
        - Includes domain, search terms, file type
        - Cached for performance during request lifecycle
        """
        # Return cached if available and not invalidated
        if hasattr(self, "_cached_queries") and self._cached_queries is not None:
            return self._cached_queries

        base_query = self.generate_base_query()
        if not base_query:
            self._cached_queries = []
            return []

        file_types = self.search_config.get("file_types", [])
        file_type_filter = self._build_file_type_filter(file_types)

        queries = []
        queries.extend(self._generate_domain_queries(base_query, file_type_filter))
        queries.extend(self._generate_general_query(base_query, file_type_filter))

        # Cache before returning
        self._cached_queries = queries
        return queries

    def count_queries(self):
        """Count queries without generating full text.

        Aligned with CORE_REQUIREMENTS: Enables faster status updates.
        """
        if not self.validate_completeness():
            return 0

        count = 0
        domains = self.search_config.get("domains", [])
        include_general = self.search_config.get("include_general_search", False)

        # Count domain-specific queries
        count += len(domains)

        # Count general search query
        if include_general:
            count += 1

        return count

    def invalidate_cache(self):
        """Clear cached queries when strategy changes."""
        self._cached_queries = None

    def save(self, *args, **kwargs):
        """Override save to invalidate cache on changes."""
        self.invalidate_cache()
        super().save(*args, **kwargs)

    def check_query_lengths(self, max_length=None):
        """Check if any generated queries exceed the maximum length.

        Args:
            max_length: Maximum allowed query length (defaults to config or 2000)

        Returns:
            List of dictionaries with query info for queries exceeding max_length
        """
        if max_length is None:
            max_length = self.search_config.get("query_splitting", {}).get(
                "max_query_length", 2000
            )

        queries = self.generate_queries()
        length_issues = []

        for idx, query_data in enumerate(queries):
            query_text = query_data["query"]
            query_length = len(query_text)

            if query_length > max_length:
                length_issues.append(
                    {
                        "index": idx,
                        "query": (
                            query_text[:100] + "..."
                            if len(query_text) > 100
                            else query_text
                        ),
                        "length": query_length,
                        "excess": query_length - max_length,
                        "type": query_data["type"],
                        "domain": query_data.get("domain"),
                    }
                )

        return length_issues

    def _build_file_type_filter(self, file_types):
        """Build file type filter with proper AND grouping.

        Args:
            file_types: List of file types (e.g., ["pdf", "doc"])

        Returns:
            String filter with proper grouping (e.g., "(filetype:pdf OR filetype:doc OR filetype:docx)")
        """
        if not file_types:
            return ""

        file_type_parts = []
        for ft in file_types:
            if ft == "pdf":
                file_type_parts.append("filetype:pdf")
            elif ft == "doc":
                file_type_parts.append("filetype:doc")
                file_type_parts.append("filetype:docx")

        return " OR ".join(file_type_parts) if file_type_parts else ""

    def _split_by_pic_terms(self, base_query, original_index):
        """Split a query by PIC terms to reduce length.

        Args:
            base_query: Query data dictionary with query text and metadata
            original_index: Index of the original query

        Returns:
            List of split query dictionaries
        """
        split_queries = []

        # Extract components from the original query
        domain = base_query.get("domain")
        query_type = base_query["type"]

        # Build individual queries for each PIC combination
        # This creates queries with reduced term combinations while maintaining search intent
        file_types = self.search_config.get("file_types", [])
        file_type_filter = self._build_file_type_filter(file_types)

        # Strategy: Create queries with Population + Interest, Population + Context, Interest + Context
        # This reduces query length while maintaining comprehensive coverage
        combinations = []

        if self.population_terms and self.interest_terms:
            pop_query = " OR ".join(format_term(term) for term in self.population_terms)
            int_query = " OR ".join(format_term(term) for term in self.interest_terms)
            combinations.append(
                {
                    "query_parts": [f"({pop_query})", f"({int_query})"],
                    "split_info": {
                        "population": self.population_terms,
                        "interest": self.interest_terms,
                        "context": [],
                        "original_index": original_index,
                        "split_strategy": "population_interest",
                    },
                }
            )

        if self.population_terms and self.context_terms:
            pop_query = " OR ".join(format_term(term) for term in self.population_terms)
            ctx_query = " OR ".join(format_term(term) for term in self.context_terms)
            combinations.append(
                {
                    "query_parts": [f"({pop_query})", f"({ctx_query})"],
                    "split_info": {
                        "population": self.population_terms,
                        "interest": [],
                        "context": self.context_terms,
                        "original_index": original_index,
                        "split_strategy": "population_context",
                    },
                }
            )

        if self.interest_terms and self.context_terms:
            int_query = " OR ".join(format_term(term) for term in self.interest_terms)
            ctx_query = " OR ".join(format_term(term) for term in self.context_terms)
            combinations.append(
                {
                    "query_parts": [f"({int_query})", f"({ctx_query})"],
                    "split_info": {
                        "population": [],
                        "interest": self.interest_terms,
                        "context": self.context_terms,
                        "original_index": original_index,
                        "split_strategy": "interest_context",
                    },
                }
            )

        # Build final queries with domain and file type filters
        for idx, combo in enumerate(combinations):
            base_split_query = " AND ".join(combo["query_parts"])

            # Add domain if domain-specific
            if domain:
                final_query = f"site:{domain} {base_split_query}"
            else:
                final_query = base_split_query

            # Add file type filter with proper AND grouping
            if file_type_filter:
                final_query += f" AND ({file_type_filter})"

            split_queries.append(
                {
                    "query": final_query,
                    "type": query_type,
                    "domain": domain,
                    "split_info": {**combo["split_info"], "split_index": idx},
                }
            )

        return split_queries if split_queries else [base_query]

    def generate_split_queries(self):
        """Generate queries with splitting based on configuration.

        Returns:
            List of query dictionaries, potentially split to reduce length
        """
        base_queries = self.generate_queries()

        # Return original if splitting disabled
        splitting_config = self.search_config.get("query_splitting", {})
        if not splitting_config.get("enabled", False):
            return base_queries

        splitting_strategy = splitting_config.get("strategy", "by_pic_terms")
        max_length = splitting_config.get("max_query_length", 2000)

        split_queries = []
        for idx, base_query in enumerate(base_queries):
            if len(base_query["query"]) > max_length:
                if splitting_strategy == "by_pic_terms":
                    splits = self._split_by_pic_terms(base_query, idx)
                    split_queries.extend(splits)
                elif splitting_strategy == "by_domains":
                    # For domain splitting, we'd create separate queries per domain
                    # This is simpler as domains are already separate in base queries
                    split_queries.append(base_query)
                elif splitting_strategy == "by_interest":
                    # Split by individual interest terms
                    splits = self._split_by_interest_terms(base_query, idx)
                    split_queries.extend(splits)
                else:
                    # Unknown strategy, keep original
                    split_queries.append(base_query)
            else:
                # Query is within length limit, keep as-is
                split_queries.append(base_query)

        return split_queries

    def _split_by_interest_terms(self, base_query, original_index):
        """Split a query by individual interest terms.

        Args:
            base_query: Query data dictionary
            original_index: Index of the original query

        Returns:
            List of split query dictionaries with one interest term each
        """
        if not self.interest_terms:
            return [base_query]

        split_queries = []
        domain = base_query.get("domain")
        query_type = base_query["type"]

        file_types = self.search_config.get("file_types", [])
        file_type_filter = self._build_file_type_filter(file_types)

        # Create one query per interest term
        for idx, interest_term in enumerate(self.interest_terms):
            query_parts = []

            if self.population_terms:
                pop_query = " OR ".join(
                    format_term(term) for term in self.population_terms
                )
                query_parts.append(f"({pop_query})")

            # Single interest term
            query_parts.append(format_term(interest_term))

            if self.context_terms:
                ctx_query = " OR ".join(
                    format_term(term) for term in self.context_terms
                )
                query_parts.append(f"({ctx_query})")

            base_split_query = " AND ".join(query_parts)

            # Add domain if domain-specific
            if domain:
                final_query = f"site:{domain} {base_split_query}"
            else:
                final_query = base_split_query

            # Add file type filter
            if file_type_filter:
                final_query += f" AND ({file_type_filter})"

            split_queries.append(
                {
                    "query": final_query,
                    "type": query_type,
                    "domain": domain,
                    "split_info": {
                        "population": self.population_terms,
                        "interest": [interest_term],
                        "context": self.context_terms,
                        "original_index": original_index,
                        "split_index": idx,
                        "split_strategy": "by_interest",
                    },
                }
            )

        return split_queries

    def get_stats(self):
        """Get statistics about the search strategy.

        Optimized to avoid redundant query generation per CORE_REQUIREMENTS
        performance guidelines (max 2-second update delay).
        """
        return {
            "population_count": len(self.population_terms),
            "interest_count": len(self.interest_terms),
            "context_count": len(self.context_terms),
            "total_terms": sum(
                [
                    len(self.population_terms),
                    len(self.interest_terms),
                    len(self.context_terms),
                ]
            ),
            "domain_count": len(self.search_config.get("domains", [])),
            "query_count": self.count_queries(),  # Changed from len(self.generate_queries())
            "is_complete": self.is_complete,
        }


class SearchQuery(models.Model):
    """
    Represents an individual search query generated from the strategy.
    Tracks execution and results for each query.

    Denormalized Fields:
        session: Direct reference to SearchSession for performance.
                Use this instead of strategy__session in queries.
                Must be kept in sync with strategy.session.

    Usage:
        # Preferred - uses denormalized field
        SearchQuery.objects.filter(session=my_session)

        # Also works but slower - uses JOIN
        SearchQuery.objects.filter(strategy__session=my_session)
    """

    # Primary key and relationships
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    strategy = models.ForeignKey(
        SearchStrategy, on_delete=models.CASCADE, related_name="search_queries"
    )
    # Denormalized for performance - direct reference to session
    session = models.ForeignKey(
        SearchSession, on_delete=models.CASCADE, related_name="search_queries_denorm"
    )

    # Query details
    query_text = models.TextField(help_text="The complete search query string")
    query_type = models.CharField(
        max_length=50,
        choices=[("domain-specific", "Domain Specific"), ("general", "General Search")],
    )
    target_domain = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Domain for site-specific searches",
    )

    # Formatted query for user-friendly display
    formatted_query = models.CharField(
        max_length=500,
        blank=True,
        help_text="User-friendly formatted query for display",
    )

    # Execution tracking
    execution_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    estimated_results = models.IntegerField(default=0)

    class Meta:
        db_table = "search_queries"
        verbose_name = "Search Query"
        verbose_name_plural = "Search Queries"
        ordering = ["execution_order", "created_at"]
        indexes = [
            models.Index(fields=["strategy"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.query_type}: {self.query_text[:50]}..."

    def extract_domain(self) -> str:
        """
        Extract domain from site-specific query.

        Returns:
            str: Domain name (e.g., 'www.cnn.com') or empty string
        """
        if self.query_type == "domain-specific" and self.target_domain:
            return self.target_domain

        # Try to extract from query_text if site: operator is present
        if "site:" in self.query_text:
            import re

            match = re.search(r"site:([^\s]+)", self.query_text)
            if match:
                return match.group(1)

        return ""

    def get_search_terms(self) -> str:
        """
        Extract search terms from query, removing site: and filetype: operators.

        Returns:
            str: Clean search terms
        """
        import re

        query = self.query_text

        # Remove site: operator
        query = re.sub(r"site:[^\s]+\s*", "", query)

        # Remove filetype: operator
        query = re.sub(r"filetype:[^\s]+\s*", "", query)

        # Clean up extra spaces and parentheses
        query = re.sub(r"\s+", " ", query).strip()
        query = re.sub(r"^\(|\)$", "", query).strip()

        return query

    def get_file_types(self) -> list:
        """
        Extract file types from query.

        Returns:
            list: List of file types (e.g., ['pdf', 'doc'])
        """
        import re

        file_types = []

        # Find all filetype: operators
        matches = re.findall(r"filetype:([^\s]+)", self.query_text)
        for match in matches:
            if match not in file_types:
                file_types.append(match)

        return file_types

    def save(self, *args, **kwargs) -> None:
        """Override save to auto-generate formatted query."""
        if not self.formatted_query and self.query_text:
            # Import here to avoid circular imports
            from apps.serp_execution.utils import parse_query_details

            # Parse query details
            query_details = parse_query_details(self.query_text)

            # Build formatted text
            if query_details.get("full_text"):
                self.formatted_query = query_details["full_text"]
            else:
                # Fallback to raw query if parsing fails
                self.formatted_query = self.query_text

        super().save(*args, **kwargs)

    def get_display_query(self, action: str = "") -> str:
        """
        Get formatted query for display.

        Args:
            action: Optional action prefix (e.g., "Executing", "Completed")

        Returns:
            User-friendly formatted query string
        """
        # Generate formatted query if not cached
        if not self.formatted_query:
            from apps.serp_execution.utils import parse_query_details

            query_details = parse_query_details(self.query_text)
            if query_details.get("full_text"):
                self.formatted_query = query_details["full_text"]
            else:
                self.formatted_query = self.query_text

            # Save the formatted query for future use
            self.save(update_fields=["formatted_query"])

        # Add action prefix if provided
        if action:
            return f"{action} {self.formatted_query}"
        return self.formatted_query
