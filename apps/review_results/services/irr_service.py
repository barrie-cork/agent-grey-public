"""
Inter-Rater Reliability Service for Cohen's Kappa calculation.

Provides reliability metrics for reviewer pairs in dual screening workflows,
supporting PRISMA 2020 reporting requirements.
"""

from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

from django.utils import timezone

from apps.core.services.base import BaseService
from apps.organisation.models import Organisation
from apps.review_manager.models import SearchSession
from apps.review_results.models import InterRaterReliability, ReviewerDecision
from apps.accounts.models import User


def _cohens_kappa(y1: list[str], y2: list[str]) -> float:
    """Cohen's Kappa for two equal-length label sequences (stdlib only).

    Algebraically identical to sklearn.metrics.cohen_kappa_score with default
    (unweighted) settings: kappa = (po - pe) / (1 - pe). The pe >= 1 guard
    covers the single-shared-label case where both raters used one identical
    label (sklearn returns NaN there; we treat it as perfect agreement, matching
    the existing y1 == y2 short-circuit).
    """
    n = len(y1)
    if n == 0:
        return 0.0
    po = sum(a == b for a, b in zip(y1, y2)) / n
    c1, c2 = Counter(y1), Counter(y2)
    labels = set(c1) | set(c2)
    pe = sum((c1[label] / n) * (c2[label] / n) for label in labels)
    if pe >= 1.0:  # both raters used a single identical label
        return 1.0
    return (po - pe) / (1.0 - pe)


class InterRaterReliabilityService(BaseService):
    """
    Service for calculating inter-rater reliability metrics.

    Implements a stdlib Cohen's Kappa calculation for reviewer pairs,
    meeting Cochrane minimum threshold of ≥0.70.
    """

    SERVICE_NAME = "InterRaterReliabilityService"
    SERVICE_VERSION = "1.0.0"

    def _initialize(self) -> None:
        """Initialize IRR service resources."""
        pass

    def health_check(self) -> bool:
        """
        Check if IRR service is healthy.

        Returns:
            bool: True if service is operational
        """
        try:
            # Test database connectivity
            InterRaterReliability.objects.count()
            return True
        except Exception as e:
            self._handle_error(e, operation="health_check")
            return False

    def get_default_config(self) -> dict:
        """Get default configuration for IRR service."""
        return {
            "min_common_results": 2,  # Minimum results both reviewers must assess
            "cache_timeout_seconds": 300,  # Cache IRR results for 5 minutes
            "cochrane_threshold": 0.70,  # Cochrane minimum for acceptable agreement
        }

    def calculate_cohens_kappa(
        self,
        reviewer_a: User,
        reviewer_b: User,
        organisation: Organisation,
        search_session: SearchSession,
        screening_stage: str = "SCREENING",
    ) -> Optional[InterRaterReliability]:
        """
        Calculate Cohen's Kappa for a reviewer pair.

        Args:
            reviewer_a: First reviewer
            reviewer_b: Second reviewer
            organisation: Organisation context
            search_session: SearchSession to calculate metrics for
            screening_stage: Screening stage (default: SCREENING)

        Returns:
            InterRaterReliability: Created IRR record, or None if insufficient data

        Raises:
            ValueError: If organisation or search_session is None
        """
        if not organisation:
            raise ValueError("Organisation is required for calculating IRR")
        if not search_session:
            raise ValueError("SearchSession is required for calculating IRR")

        with self._measure_performance("calculate_cohens_kappa"):
            try:
                # Get all results both reviewers assessed
                decisions_a = (
                    ReviewerDecision.objects.filter(
                        organisation=organisation,
                        result__session=search_session,
                        reviewer=reviewer_a,
                        screening_stage=screening_stage,
                    )
                    .exclude(decision="ABSTAIN")
                    .values_list("result_id", "decision")
                )

                decisions_b = (
                    ReviewerDecision.objects.filter(
                        organisation=organisation,
                        result__session=search_session,
                        reviewer=reviewer_b,
                        screening_stage=screening_stage,
                    )
                    .exclude(decision="ABSTAIN")
                    .values_list("result_id", "decision")
                )

                # Convert to dictionaries for easier comparison
                decisions_a_dict = dict(decisions_a)
                decisions_b_dict = dict(decisions_b)

                # Find common results
                common_results = set(decisions_a_dict.keys()) & set(
                    decisions_b_dict.keys()
                )

                min_common = self.config.get("min_common_results", 2)
                if len(common_results) < min_common:
                    self.logger.info(
                        f"Insufficient common results for IRR calculation: "
                        f"{len(common_results)} < {min_common} "
                        f"(reviewers: {reviewer_a.username}, {reviewer_b.username})"
                    )
                    return None

                # Build aligned label sequences
                y1 = [decisions_a_dict[r] for r in sorted(common_results)]
                y2 = [decisions_b_dict[r] for r in sorted(common_results)]

                # Calculate Cohen's Kappa (stdlib implementation).
                # Special case: if both reviewers made identical decisions for all
                # results there is no variance (kappa is undefined / NaN); we treat
                # this as perfect agreement (kappa=1.0). _cohens_kappa's pe>=1 guard
                # handles it too, but the short-circuit keeps intent explicit.
                if y1 == y2:
                    kappa = 1.0
                else:
                    kappa = _cohens_kappa(y1, y2)

                # Calculate percentage agreement
                agreements = sum(
                    1
                    for r in common_results
                    if decisions_a_dict[r] == decisions_b_dict[r]
                )
                percentage_agreement = (agreements / len(common_results)) * 100

                # Determine calculation window
                calculation_window_start = search_session.created_at
                calculation_window_end = timezone.now()

                # Store in database
                irr = InterRaterReliability.objects.create(
                    organisation=organisation,
                    search_session=search_session,
                    reviewer_a=reviewer_a,
                    reviewer_b=reviewer_b,
                    cohens_kappa=kappa,
                    percentage_agreement=percentage_agreement,
                    total_comparisons=len(common_results),
                    agreements=agreements,
                    disagreements=len(common_results) - agreements,
                    screening_stage=screening_stage,
                    calculation_window_start=calculation_window_start,
                    calculation_window_end=calculation_window_end,
                )

                cochrane_threshold = self.config.get("cochrane_threshold", 0.70)
                meets_cochrane = kappa >= cochrane_threshold

                self.logger.info(
                    f"Calculated IRR for {reviewer_a.username} & {reviewer_b.username} "
                    f"in session {search_session.id}: "
                    f"Kappa={kappa:.3f}, Agreement={percentage_agreement:.1f}% "
                    f"(Cochrane: {'✓' if meets_cochrane else '✗'})"
                )

                return irr

            except Exception as e:
                self._handle_error(
                    e,
                    operation="calculate_cohens_kappa",
                    context={
                        "reviewer_a_id": str(reviewer_a.id),
                        "reviewer_b_id": str(reviewer_b.id),
                        "organisation_id": str(organisation.id),
                        "session_id": str(search_session.id),
                    },
                )
                raise

    def calculate_percentage_agreement(
        self,
        reviewer_a: User,
        reviewer_b: User,
        organisation: Organisation,
        search_session: SearchSession,
        screening_stage: str = "SCREENING",
    ) -> Optional[float]:
        """
        Calculate simple percentage agreement (without chance correction).

        Args:
            reviewer_a: First reviewer
            reviewer_b: Second reviewer
            organisation: Organisation context
            search_session: SearchSession to calculate metrics for
            screening_stage: Screening stage (default: SCREENING)

        Returns:
            float: Percentage agreement (0-100), or None if insufficient data

        Raises:
            ValueError: If organisation or search_session is None
        """
        if not organisation:
            raise ValueError("Organisation is required for calculating agreement")
        if not search_session:
            raise ValueError("SearchSession is required for calculating agreement")

        with self._measure_performance("calculate_percentage_agreement"):
            try:
                # Get all results both reviewers assessed
                decisions_a = dict(
                    ReviewerDecision.objects.filter(
                        organisation=organisation,
                        result__session=search_session,
                        reviewer=reviewer_a,
                        screening_stage=screening_stage,
                    )
                    .exclude(decision="ABSTAIN")
                    .values_list("result_id", "decision")
                )

                decisions_b = dict(
                    ReviewerDecision.objects.filter(
                        organisation=organisation,
                        result__session=search_session,
                        reviewer=reviewer_b,
                        screening_stage=screening_stage,
                    )
                    .exclude(decision="ABSTAIN")
                    .values_list("result_id", "decision")
                )

                # Find common results
                common_results = set(decisions_a.keys()) & set(decisions_b.keys())

                if len(common_results) < self.config.get("min_common_results", 2):
                    return None

                # Calculate agreement
                agreements = sum(
                    1 for r in common_results if decisions_a[r] == decisions_b[r]
                )
                percentage = (agreements / len(common_results)) * 100

                self.logger.debug(
                    f"Percentage agreement for {reviewer_a.username} & {reviewer_b.username}: "
                    f"{percentage:.1f}% ({agreements}/{len(common_results)})"
                )

                return percentage

            except Exception as e:
                self._handle_error(
                    e,
                    operation="calculate_percentage_agreement",
                    context={
                        "reviewer_a_id": str(reviewer_a.id),
                        "reviewer_b_id": str(reviewer_b.id),
                        "organisation_id": str(organisation.id),
                        "session_id": str(search_session.id),
                    },
                )
                raise

    def get_irr_metrics(
        self, organisation: Organisation, search_session: SearchSession
    ) -> List[InterRaterReliability]:
        """
        Get all IRR metrics for a search session.

        Args:
            organisation: Organisation context
            search_session: SearchSession to get metrics for

        Returns:
            List[InterRaterReliability]: List of IRR records ordered by calculation time

        Raises:
            ValueError: If organisation or search_session is None
        """
        if not organisation:
            raise ValueError("Organisation is required for getting IRR metrics")
        if not search_session:
            raise ValueError("SearchSession is required for getting IRR metrics")

        with self._measure_performance("get_irr_metrics"):
            try:
                metrics = list(
                    InterRaterReliability.objects.filter(
                        organisation=organisation, search_session=search_session
                    )
                    .select_related("reviewer_a", "reviewer_b")
                    .order_by("-calculated_at")
                )

                self.logger.debug(
                    f"Retrieved {len(metrics)} IRR metrics for session {search_session.id}"
                )

                return metrics

            except Exception as e:
                self._handle_error(
                    e,
                    operation="get_irr_metrics",
                    context={
                        "organisation_id": str(organisation.id),
                        "session_id": str(search_session.id),
                    },
                )
                raise

    def get_irr_summary(
        self, organisation: Organisation, search_session: SearchSession
    ) -> Dict[str, Any]:
        """
        Get summary statistics for IRR metrics in a session.

        Args:
            organisation: Organisation context
            search_session: SearchSession to summarize

        Returns:
            Dict with IRR summary including:
                - average_kappa: Mean Cohen's Kappa across all pairs
                - average_agreement: Mean percentage agreement
                - pairs_below_threshold: Number of pairs below Cochrane threshold
                - total_pairs: Total number of reviewer pairs
                - meets_cochrane: Whether average kappa meets Cochrane standard

        Raises:
            ValueError: If organisation or search_session is None
        """
        if not organisation:
            raise ValueError("Organisation is required for IRR summary")
        if not search_session:
            raise ValueError("SearchSession is required for IRR summary")

        with self._measure_performance("get_irr_summary"):
            try:
                metrics = self.get_irr_metrics(organisation, search_session)

                if not metrics:
                    return {
                        "average_kappa": None,
                        "average_agreement": None,
                        "pairs_below_threshold": 0,
                        "pairs_with_valid_kappa": [],
                        "total_pairs": 0,
                        "meets_cochrane": False,
                        "note": "No IRR metrics calculated yet",
                    }

                # Calculate averages
                total_kappa = sum(
                    m.cohens_kappa for m in metrics if m.cohens_kappa is not None
                )
                total_agreement = sum(m.percentage_agreement for m in metrics)
                valid_kappa_count = sum(
                    1 for m in metrics if m.cohens_kappa is not None
                )

                avg_kappa = (
                    total_kappa / valid_kappa_count if valid_kappa_count > 0 else None
                )
                avg_agreement = total_agreement / len(metrics)

                # Check Cochrane threshold
                cochrane_threshold = self.config.get("cochrane_threshold", 0.70)
                pairs_below = sum(
                    1
                    for m in metrics
                    if m.cohens_kappa is not None
                    and m.cohens_kappa < cochrane_threshold
                )

                meets_cochrane = (
                    avg_kappa is not None and avg_kappa >= cochrane_threshold
                )

                summary = {
                    "average_kappa": round(avg_kappa, 3)
                    if avg_kappa is not None
                    else None,
                    "average_agreement": round(avg_agreement, 1),
                    "pairs_below_threshold": pairs_below,
                    "total_pairs": len(metrics),
                    "pairs_with_valid_kappa": valid_kappa_count,
                    "meets_cochrane": meets_cochrane,
                    "cochrane_threshold": cochrane_threshold,
                    "calculated_at": timezone.now().isoformat(),
                }

                self.logger.info(
                    f"IRR summary for session {search_session.id}: "
                    f"Avg Kappa={summary['average_kappa']}, "
                    f"Cochrane: {'✓' if meets_cochrane else '✗'}"
                )

                return summary

            except Exception as e:
                self._handle_error(
                    e,
                    operation="get_irr_summary",
                    context={
                        "organisation_id": str(organisation.id),
                        "session_id": str(search_session.id),
                    },
                )
                raise

    def get_per_reviewer_breakdown(
        self,
        organisation: Organisation,
        search_session: SearchSession,
    ) -> List[Dict[str, Any]]:
        """Build per-reviewer IRR breakdown with pairwise comparisons."""
        if not organisation:
            raise ValueError("Organisation is required for per-reviewer breakdown")
        if not search_session:
            raise ValueError("SearchSession is required for per-reviewer breakdown")

        with self._measure_performance("get_per_reviewer_breakdown"):
            try:
                irr_records = self.get_irr_metrics(organisation, search_session)

                if not irr_records:
                    return []

                cochrane_threshold = self.config.get("cochrane_threshold", 0.70)

                reviewer_data: Dict[str, Dict] = defaultdict(
                    lambda: {
                        "pairwise": [],
                        "kappas": [],
                        "agreements": [],
                        "total_comparisons": 0,
                    }
                )

                for record in irr_records:
                    for reviewer, partner in [
                        (record.reviewer_a, record.reviewer_b),
                        (record.reviewer_b, record.reviewer_a),
                    ]:
                        if reviewer is None:
                            continue
                        rid = str(reviewer.id)
                        reviewer_data[rid]["user"] = reviewer
                        reviewer_data[rid]["pairwise"].append(
                            {
                                "with_reviewer_id": str(partner.id)
                                if partner
                                else None,
                                "with_reviewer_name": (
                                    partner.get_full_name() or partner.username
                                    if partner
                                    else None
                                ),
                                "cohens_kappa": record.cohens_kappa,
                                "percentage_agreement": record.percentage_agreement,
                                "agreements": record.agreements,
                                "disagreements": record.disagreements,
                                "total_comparisons": record.total_comparisons,
                                "meets_threshold": (
                                    record.cohens_kappa is not None
                                    and record.cohens_kappa >= cochrane_threshold
                                ),
                            }
                        )
                        if record.cohens_kappa is not None:
                            reviewer_data[rid]["kappas"].append(record.cohens_kappa)
                        reviewer_data[rid]["agreements"].append(
                            record.percentage_agreement
                        )
                        reviewer_data[rid]["total_comparisons"] += (
                            record.total_comparisons
                        )

                breakdown = []
                for rid, data in reviewer_data.items():
                    user = data["user"]
                    avg_kappa = (
                        sum(data["kappas"]) / len(data["kappas"])
                        if data["kappas"]
                        else None
                    )
                    avg_agreement = (
                        sum(data["agreements"]) / len(data["agreements"])
                        if data["agreements"]
                        else 0.0
                    )
                    breakdown.append(
                        {
                            "reviewer_id": rid,
                            "reviewer_name": user.get_full_name() or user.username,
                            "reviewer_email": user.email,
                            "average_kappa": (
                                round(avg_kappa, 3) if avg_kappa is not None else None
                            ),
                            "average_agreement": round(avg_agreement, 1),
                            "pairwise_comparisons": data["pairwise"],
                            "total_comparisons": data["total_comparisons"],
                            "meets_cochrane_average": (
                                avg_kappa is not None
                                and avg_kappa >= cochrane_threshold
                            ),
                        }
                    )

                return breakdown

            except Exception as e:
                self._handle_error(
                    e,
                    operation="get_per_reviewer_breakdown",
                    context={
                        "organisation_id": str(organisation.id),
                        "session_id": str(search_session.id),
                    },
                )
                raise
