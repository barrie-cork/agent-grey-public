"""
Simple query builder service for serp_execution slice.
Business capability: Basic query construction from PIC framework.
"""

from urllib.parse import quote_plus


class QueryBuilder:
    """Simple service for building search queries from PIC framework."""

    def build_query(
        self,
        population: str,
        interest: str,
        context: str,
        file_types=None,
    ) -> str:
        """
        Build a simple search query from PIC framework components.

        Args:
            population: Target population terms
            interest: Interest/intervention terms
            context: Context/setting terms
            file_types: List of file types to filter (pdf, doc, etc.)

        Returns:
            Simple search query string
        """
        # Build basic query from PIC components
        query_parts = []

        if population:
            query_parts.append(f'"{population}"')
        if interest:
            query_parts.append(f'"{interest}"')
        if context:
            query_parts.append(f'"{context}"')

        # Join with AND
        base_query = " AND ".join(query_parts)

        # Add file type filter if specified
        if file_types:
            file_filter = self._build_file_type_filter(file_types)
            if file_filter:
                base_query = f"{base_query} {file_filter}"

        return base_query.strip()

    def _build_file_type_filter(self, file_types: list) -> str:
        """Build simple file type filter string."""
        filters = []
        for file_type in file_types:
            filters.append(f"filetype:{file_type.lower()}")

        if not filters:
            return ""

        # No parentheses around file type filters per Google best practices
        return " OR ".join(filters)

    def encode_for_url(self, query: str) -> str:
        """Encode query for use in URLs."""
        return quote_plus(query)
