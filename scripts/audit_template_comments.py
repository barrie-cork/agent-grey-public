#!/usr/bin/env python3
"""Audit Django templates for dangerous multi-line comment patterns.

Django's {# ... #} comment syntax only works for single-line comments.
When spread across multiple lines, any {% %} template tags inside are
executed as real code, which can cause RecursionError or other issues.

This script detects:
- Multi-line {# ... #} comments (where {# and #} are on different lines)
- Comments containing template tags ({% ... %})

Safe patterns (not flagged):
- Single-line {# ... #} comments
- {% comment %} ... {% endcomment %} blocks

Usage:
    python scripts/audit_template_comments.py [--verbose]

Exit codes:
    0 - All templates pass
    1 - Issues found
"""

import argparse
import re
import sys
from pathlib import Path

# Template directories to audit
TEMPLATE_DIRS = [
    "templates",
    "apps/accounts/templates",
    "apps/feedback/templates",
    "apps/reporting/templates",
    "apps/results_manager/templates",
    "apps/review_manager/templates",
    "apps/review_results/templates",
    "apps/search_strategy/templates",
    "apps/serp_execution/templates",
]

# Patterns
COMMENT_START = re.compile(r"\{#")
COMMENT_END = re.compile(r"#\}")
TEMPLATE_TAG = re.compile(r"\{%.*?%\}")
SAFE_COMMENT_BLOCK = re.compile(r"\{%\s*comment\s*%\}")


def find_multiline_comments(content: str, filepath: str) -> list[dict]:
    """Find multi-line {# ... #} comments in template content.

    Returns list of issues found, each with:
    - start_line: Line number where {# appears
    - end_line: Line number where #} appears
    - template_tags: List of template tags found in the comment
    - snippet: The problematic code snippet
    """
    issues = []
    lines = content.split("\n")

    i = 0
    while i < len(lines):
        line = lines[i]

        # Skip lines inside {% comment %} blocks
        if SAFE_COMMENT_BLOCK.search(line):
            # Find matching {% endcomment %}
            j = i + 1
            while j < len(lines) and not re.search(r"\{%\s*endcomment\s*%\}", lines[j]):
                j += 1
            i = j + 1
            continue

        # Look for {# that isn't closed on the same line
        start_match = COMMENT_START.search(line)
        if start_match:
            # Check if #} is on the same line AFTER the {#
            rest_of_line = line[start_match.end() :]
            if COMMENT_END.search(rest_of_line):
                # Single-line comment, safe
                i += 1
                continue

            # Multi-line comment detected - find the closing #}
            start_line = i + 1  # 1-indexed
            comment_lines = [line[start_match.start() :]]

            j = i + 1
            found_end = False
            while j < len(lines):
                comment_lines.append(lines[j])
                if COMMENT_END.search(lines[j]):
                    found_end = True
                    break
                j += 1

            if found_end:
                end_line = j + 1  # 1-indexed
                comment_content = "\n".join(comment_lines)

                # Check for template tags in the comment
                template_tags = TEMPLATE_TAG.findall(comment_content)
                # Filter out {% comment %} and {% endcomment %} tags
                dangerous_tags = [
                    tag
                    for tag in template_tags
                    if not re.search(r"\{%\s*(end)?comment\s*%\}", tag)
                ]

                if dangerous_tags:
                    issues.append(
                        {
                            "start_line": start_line,
                            "end_line": end_line,
                            "template_tags": dangerous_tags,
                            "snippet": comment_content[:200]
                            + ("..." if len(comment_content) > 200 else ""),
                        }
                    )

                i = j + 1
                continue

        i += 1

    return issues


def audit_file(filepath: Path, verbose: bool = False) -> list[dict]:
    """Audit a single template file for comment issues."""
    # Skip broken symlinks
    if filepath.is_symlink() and not filepath.exists():
        if verbose:
            print(f"    SKIP: {filepath.name} (broken symlink)")
        return []

    try:
        content = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError, OSError) as e:
        if verbose:
            print(f"    SKIP: {filepath.name} ({type(e).__name__})")
        return []

    issues = find_multiline_comments(content, str(filepath))

    for issue in issues:
        issue["filepath"] = str(filepath)

    return issues


def audit_directory(
    base_path: Path, template_dir: str, verbose: bool = False
) -> list[dict]:
    """Audit all HTML templates in a directory."""
    dir_path = base_path / template_dir
    if not dir_path.exists():
        if verbose:
            print(f"  SKIP: {dir_path} (does not exist)")
        return []

    all_issues = []
    html_files = list(dir_path.rglob("*.html"))

    if verbose:
        print(f"  Scanning {len(html_files)} files in {template_dir}/")

    for filepath in html_files:
        issues = audit_file(filepath, verbose)
        all_issues.extend(issues)

    return all_issues


def format_issue(issue: dict) -> str:
    """Format an issue for display."""
    lines = [
        f"ERROR: {issue['filepath']}:{issue['start_line']}-{issue['end_line']}",
        "  Multi-line {# #} comment contains template tags:",
    ]

    for tag in issue["template_tags"]:
        lines.append(f"    - {tag}")

    lines.extend(
        [
            "",
            "  Fix: Use single-line comments or {% comment %}...{% endcomment %}",
            "",
        ]
    )

    return "\n".join(lines)


def main():
    """Run the template comment audit."""
    parser = argparse.ArgumentParser(
        description="Audit Django templates for dangerous multi-line comment patterns"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed progress"
    )
    parser.add_argument(
        "--path",
        type=str,
        default=None,
        help="Base path to project (default: auto-detect)",
    )
    args = parser.parse_args()

    # Find project root
    if args.path:
        base_path = Path(args.path)
    else:
        # Try to find project root by looking for manage.py
        base_path = Path(__file__).parent.parent
        if not (base_path / "manage.py").exists():
            base_path = Path.cwd()

    if not (base_path / "manage.py").exists():
        print(f"ERROR: Could not find Django project root (no manage.py in {base_path})")
        sys.exit(1)

    print("Django Template Comment Audit")
    print(f"{'=' * 40}")
    print(f"Project root: {base_path}")
    print()

    all_issues = []
    total_files = 0

    for template_dir in TEMPLATE_DIRS:
        dir_path = base_path / template_dir
        if dir_path.exists():
            html_files = list(dir_path.rglob("*.html"))
            total_files += len(html_files)

    print(f"Scanning {total_files} HTML templates across {len(TEMPLATE_DIRS)} directories...")
    print()

    for template_dir in TEMPLATE_DIRS:
        issues = audit_directory(base_path, template_dir, args.verbose)
        all_issues.extend(issues)

    if all_issues:
        print(f"FAILED: Found {len(all_issues)} issue(s)")
        print()
        for issue in all_issues:
            print(format_issue(issue))
        sys.exit(1)
    else:
        print(f"PASSED: All {total_files} templates are clean")
        print()
        print("No multi-line {# #} comments with template tags found.")
        sys.exit(0)


if __name__ == "__main__":
    main()