"""
Management command to backfill review_mode and min_reviewers_required for WF2
ProcessedResults created before fix #178 shipped.

Pre-#178 rows are stuck at review_mode="SINGLE" / min_reviewers_required=1 even
though their session requires dual (or higher) screening. This command reads the
correct values from the session config via the #178 helper and updates affected rows.

Also resets consensus_reached=False for results that were falsely marked as
consensus-reached by a single reviewer (one reviewer cannot produce real consensus).

Idempotent: once fixed, the filter (review_mode="SINGLE") no longer matches the
rows, so re-running is a safe no-op.

Reversal: manual .update(review_mode="SINGLE", min_reviewers_required=1) if needed.
WF1 sessions are never touched.
"""

import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.results_manager.models import ProcessedResult
from apps.results_manager.services.processors.batch_processor import BatchProcessor
from apps.review_results.models import ReviewerDecision
from apps.review_results.services.review_coordination_service import decide_consensus

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Backfill review_mode/min_reviewers_required for pre-#178 WF2 results.

    Pre-#178 rows are stuck at review_mode="SINGLE" / min_reviewers_required=1
    even though their session requires dual (or higher) screening. Reads the
    correct values from the session config via the #178 helper and updates
    affected rows, and resets consensus_reached=False on results that were
    falsely marked resolved by a single reviewer. WF1 sessions are untouched.
    """

    help = "Backfill WF2 ProcessedResults stuck at review_mode=SINGLE (pre-#178 rows)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be changed without writing anything",
        )
        parser.add_argument(
            "--session-id",
            type=str,
            default=None,
            help="Scope backfill to a single session UUID (optional)",
        )

    def handle(self, *args, **options):
        """Run the backfill.

        Args:
            *args: Unused positional arguments.
            **options: Parsed options; ``dry_run`` (bool) previews without
                writing, ``session_id`` (str|None) scopes to one session.
        """
        dry_run = options["dry_run"]
        session_id_filter = options.get("session_id")

        if dry_run:
            self.stdout.write(
                self.style.WARNING("[DRY RUN] No changes will be written.")
            )

        qs = ProcessedResult.objects.filter(
            session__current_configuration__min_reviewers_per_result__gte=2,
            review_mode="SINGLE",
        ).select_related("session__current_configuration")

        if session_id_filter:
            qs = qs.filter(session_id=session_id_filter)
            self.stdout.write(f"Scoped to session: {session_id_filter}")

        total_affected = qs.count()
        if total_affected == 0:
            self.stdout.write(
                self.style.SUCCESS("No affected results found. Nothing to do.")
            )
            return

        self.stdout.write(
            f"Found {total_affected} affected result(s) across WF2 session(s)."
        )

        session_ids = list(qs.values_list("session_id", flat=True).distinct())
        processor = BatchProcessor()

        total_updated = 0
        total_consensus_reset = 0
        total_skipped = 0

        for sid in session_ids:
            session_results = list(qs.filter(session_id=sid))
            review_mode, min_reviewers = processor._get_review_mode_defaults(str(sid))

            if review_mode == "SINGLE" and min_reviewers == 1:
                self.stdout.write(
                    self.style.WARNING(
                        f"  Session {sid}: helper returned SINGLE/1 "
                        f"(WF1 or no config) — skipping {len(session_results)} result(s)"
                    )
                )
                total_skipped += len(session_results)
                continue

            # Pre-compute which results need a consensus reset.
            # A pre-#178 result was falsely marked consensus_reached=True when
            # the evaluator ran at 1 reviewer. Reset it unless it has REAL
            # consensus under the session's configured criteria.
            # Phase 1 of #203 fixed the evaluator to honour consensus_criteria;
            # this backfill now uses the same shared helper in lockstep.
            # Bulk-fetch decision values per result to avoid an N+1 query.
            _cfg = (
                session_results[0].session.current_configuration
                if session_results
                else None
            )
            session_criteria = (
                _cfg.consensus_criteria
                if _cfg and _cfg.consensus_criteria
                else "MAJORITY"
            )
            result_pks = [r.pk for r in session_results]
            decisions_by_result: dict = {}
            for result_pk, decision in (
                ReviewerDecision.objects.filter(result__pk__in=result_pks)
                .exclude(decision="ABSTAIN")
                .values_list("result__pk", "decision")
            ):
                decisions_by_result.setdefault(result_pk, []).append(decision)

            to_reset_consensus = set()
            for result in session_results:
                if not result.consensus_reached:
                    continue
                values = decisions_by_result.get(result.pk, [])
                # Use shared helper — matches the live evaluator exactly.
                has_real_consensus = (
                    decide_consensus(
                        values,
                        session_criteria,
                        min_reviewers,
                        len(values),
                    )
                    == "consensus"
                )
                if not has_real_consensus:
                    to_reset_consensus.add(result.pk)

            self.stdout.write(
                f"  Session {sid}: {len(session_results)} result(s) → "
                f"mode={review_mode}, min_reviewers={min_reviewers}, "
                f"consensus_reset={len(to_reset_consensus)}"
            )

            if dry_run:
                total_updated += len(session_results)
                total_consensus_reset += len(to_reset_consensus)
                continue

            with transaction.atomic():
                for result in session_results:
                    update_fields = ["review_mode", "min_reviewers_required"]
                    result.review_mode = review_mode
                    result.min_reviewers_required = min_reviewers

                    if result.pk in to_reset_consensus:
                        result.consensus_reached = False
                        update_fields.append("consensus_reached")

                    result.save(update_fields=update_fields)

            total_updated += len(session_results)
            total_consensus_reset += len(to_reset_consensus)

        self.stdout.write("\n" + "=" * 50)
        if dry_run:
            self.stdout.write(f"Results that would be updated: {total_updated}")
            self.stdout.write(
                f"Results that would have consensus_reached reset: {total_consensus_reset}"
            )
            if total_skipped:
                self.stdout.write(
                    f"Results skipped (WF1/no-config sessions): {total_skipped}"
                )
        else:
            self.stdout.write(self.style.SUCCESS(f"Results updated: {total_updated}"))
            self.stdout.write(
                self.style.SUCCESS(
                    f"Results with consensus_reached reset: {total_consensus_reset}"
                )
            )
            if total_skipped:
                self.stdout.write(
                    f"Results skipped (WF1/no-config sessions): {total_skipped}"
                )
