"""Utility functions for the search_strategy app."""

import re


def optimize_query_string(query_string: str):
    """Analyze and optimize a search query string.

    Args:
        query_string: The search query string to optimize

    Returns:
        Dictionary containing optimization suggestions
    """
    analysis = {
        "original_query": query_string,
        "word_count": len(query_string.split()),
        "character_count": len(query_string),
        "has_quotes": '"' in query_string,
        "has_boolean_operators": any(
            op in query_string.upper() for op in ["AND", "OR", "NOT"]
        ),
        "has_wildcards": "*" in query_string or "?" in query_string,
        "suggestions": [],
    }

    # Generate optimization suggestions
    if analysis["word_count"] > 15:
        analysis["suggestions"].append(
            "Consider shortening the query - very long queries may be too specific"
        )

    if analysis["word_count"] < 3:
        analysis["suggestions"].append(
            "Consider adding more descriptive terms to improve precision"
        )

    if not analysis["has_quotes"] and analysis["word_count"] > 5:
        analysis["suggestions"].append(
            "Consider using quotes around key phrases for exact matches"
        )

    if not analysis["has_boolean_operators"] and analysis["word_count"] > 8:
        analysis["suggestions"].append(
            "Consider using AND/OR operators to structure complex queries"
        )

    # Check for common issues
    if re.search(r"\b(a|an|the|is|are)\b", query_string, re.IGNORECASE):
        analysis["suggestions"].append(
            "Consider removing common stop words (a, an, the, is, are, etc.)"
        )

    return analysis
