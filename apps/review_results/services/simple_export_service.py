"""
Basic export functionality for review results.
"""


class SimpleExportService:
    """Basic export functionality for review results."""

    def export_review_decisions(self, session_id: str, format_type: str = "csv"):
        """Export review decisions in specified format."""
        from ..models import SimpleReviewDecision

        decisions = SimpleReviewDecision.objects.filter(
            session_id=session_id
        ).select_related("result", "reviewer")

        export_data = []
        for decision in decisions:
            export_data.append(
                {
                    "title": decision.result.title,
                    "url": decision.result.url,
                    "publication_year": decision.result.publication_year,
                    "document_type": decision.result.document_type,
                    "decision": decision.get_decision_display(),
                    "exclusion_reason": (
                        decision.get_exclusion_reason_display()
                        if decision.exclusion_reason
                        else ""
                    ),
                    "notes": decision.notes,
                    "reviewer": decision.reviewer.username if decision.reviewer else "",
                    "reviewed_at": decision.reviewed_at.isoformat(),
                }
            )

        return {
            "session_id": session_id,
            "export_data": export_data,
            "total_records": len(export_data),
        }
