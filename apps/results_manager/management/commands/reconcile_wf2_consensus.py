"""
Management command to reconcile WF2 false-conflict records created before #203 Phase 1.

Pre-#203 rows were evaluated under a hardcoded-unanimity rule, which flagged
INCLUDE/EXCLUDE splits as conflicts even when a real MAJORITY existed. This
command identifies fully-reviewed MAJORITY-config results that carry a PENDING
spurious conflict and flips them: marks consensus_reached=True and retires the
conflict as RESOLVED via MAJORITY.

This is the INVERSE of fix_wf2_review_mode (#192): that command RESET falsely-set
consensus→False; this one FLIPS false-conflict→consensus.

Status scope: PENDING only. IN_DISCUSSION and ESCALATED conflicts are left alone
because a human is actively working them. These are counted as "skipped (human-active)".

UNANIMOUS-config sessions are never touched: unanimity was the old hardcoded rule,
so pre-#203 UNANIMOUS sessions were already correct.

Idempotent: after a flip the conflict is RESOLVED (not PENDING) and
consensus_reached=True, so the PENDING-active filter no longer matches; re-run
is a safe no-op.

Reversal: manual database update is required if a flip must be undone. No
automated reversal command is provided (like #192).
"""

import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.results_manager.models import ProcessedResult
from apps.review_results.models import ConflictResolution, ReviewerDecision
from apps.review_results.services.review_coordination_service import (
    consensus_value,
    decide_consensus,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Flip pre-#203 false-conflicts → consensus for MAJORITY-config WF2 sessions."""

    help = (
        "Reconcile WF2 false-conflicts created before #203 Phase 1: flip PENDING "
        "spurious conflicts → RESOLVED where a real MAJORITY now holds."
    )

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
            help="Scope reconciliation to a single session UUID (optional)",
        )

    def handle(self, *args, **options):
        """Run the reconciliation.

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

        # Candidate results: WF2 MAJORITY-config, fully reviewed, with a PENDING conflict.
        qs = (
            ProcessedResult.objects.filter(
                session__current_configuration__min_reviewers_per_result__gte=2,
                session__current_configuration__consensus_criteria="MAJORITY",
                consensus_reached=False,
                conflicts__status=ConflictResolution.STATUS_PENDING,
            )
            .select_related("session__current_configuration")
            .distinct()
        )

        if session_id_filter:
            qs = qs.filter(session_id=session_id_filter)
            self.stdout.write(f"Scoped to session: {session_id_filter}")

        candidate_results = list(qs)
        if not candidate_results:
            self.stdout.write(
                self.style.SUCCESS(
                    "No candidate results found (no PENDING WF2 MAJORITY conflicts). Nothing to do."
                )
            )
            return

        self.stdout.write(
            f"Found {len(candidate_results)} candidate result(s) with PENDING conflicts."
        )

        # Group by session so we can bulk-fetch decisions per session (avoid N+1).
        sessions: dict = {}
        for result in candidate_results:
            sid = result.session_id
            sessions.setdefault(sid, []).append(result)

        total_inspected = 0
        total_flipped = 0
        total_left_as_conflict = 0
        total_skipped_human_active = 0

        for sid, session_results in sessions.items():
            cfg = session_results[0].session.current_configuration
            min_reviewers = cfg.min_reviewers_per_result

            # Bulk-fetch non-abstain decision values for ALL results in this session.
            result_pks = [r.pk for r in session_results]
            decisions_by_result: dict = {}
            for result_pk, decision in (
                ReviewerDecision.objects.filter(result__pk__in=result_pks)
                .exclude(decision="ABSTAIN")
                .values_list("result__pk", "decision")
            ):
                decisions_by_result.setdefault(result_pk, []).append(decision)

            # Bulk-fetch the PENDING conflicts for these results.
            pending_conflicts = {
                c.result_id: c
                for c in ConflictResolution.objects.filter(
                    result__pk__in=result_pks,
                    status=ConflictResolution.STATUS_PENDING,
                )
            }

            # Count human-active (IN_DISCUSSION / ESCALATED) conflicts on these results
            # that are NOT PENDING — so we can report them as skipped.
            human_active_result_ids = set(
                ConflictResolution.objects.filter(
                    result__pk__in=result_pks,
                    status__in=[
                        ConflictResolution.STATUS_IN_DISCUSSION,
                        ConflictResolution.STATUS_ESCALATED,
                    ],
                ).values_list("result_id", flat=True)
            )

            for result in session_results:
                total_inspected += 1

                # pending_conflicts is a separate query from the candidate qs; guard
                # the lookup before dereferencing conflict.pk in the mutation below.
                conflict = pending_conflicts.get(result.pk)
                if conflict is None:
                    continue

                # Skip human-active results (belt-and-braces: the qs filter already
                # excludes these, but a result could have both PENDING and a human-active
                # conflict in theory — leave it alone).
                if result.pk in human_active_result_ids:
                    total_skipped_human_active += 1
                    continue

                values = decisions_by_result.get(result.pk, [])

                # decide_consensus gates on completion itself — it returns "pending"
                # when reviewers_completed < min_reviewers, which the "!= consensus"
                # check below treats as left-as-conflict. (reviewers_completed is the
                # denormalised counter; tests must set it explicitly — PMD #318.)
                outcome = decide_consensus(
                    values,
                    "MAJORITY",
                    min_reviewers,
                    result.reviewers_completed,
                )
                if outcome != "consensus":
                    total_left_as_conflict += 1
                    continue

                # Real majority holds → pick a deterministic ReviewerDecision as the
                # final_decision. winning_value is non-None here (decide_consensus
                # returned "consensus"); the final_rd guard below is the single
                # belt-and-braces check on the mutation that follows.
                winning_value = consensus_value(values, "MAJORITY", min_reviewers)
                final_rd = (
                    ReviewerDecision.objects.filter(
                        result=result,
                        decision=winning_value,
                    )
                    .exclude(decision="ABSTAIN")
                    .order_by("decided_at")
                    .first()
                )
                if final_rd is None:
                    total_left_as_conflict += 1
                    continue

                self.stdout.write(
                    f"  Result {result.pk}: MAJORITY holds ({winning_value}), "
                    f"retiring conflict {conflict.pk}"
                )

                if dry_run:
                    total_flipped += 1
                    continue

                with transaction.atomic():
                    result.consensus_reached = True
                    result.save(update_fields=["consensus_reached"])

                    # Retire the conflict via QuerySet.update(), NOT instance.save():
                    # ConflictResolution post_save fires consensus_reached_handler
                    # (apps/review_results/signals.py), which emails all reviewers when
                    # status flips to RESOLVED. This is a historical backfill — emailing
                    # reviewers about ancient conflicts would be spam. .update() does a
                    # direct SQL UPDATE and never fires post_save. (CodeRabbit P1, #207)
                    ConflictResolution.objects.filter(pk=conflict.pk).update(
                        status=ConflictResolution.STATUS_RESOLVED,
                        resolution_method="MAJORITY",
                        resolved_at=timezone.now(),
                        final_decision=final_rd,
                        resolution_notes="Reconciled by #204: real MAJORITY existed under post-#203 rule.",
                    )

                total_flipped += 1

        self.stdout.write("\n" + "=" * 50)
        if dry_run:
            self.stdout.write(f"Results inspected:              {total_inspected}")
            self.stdout.write(f"Results that would be flipped:  {total_flipped}")
            self.stdout.write(
                f"Left as conflict (genuine split): {total_left_as_conflict}"
            )
            if total_skipped_human_active:
                self.stdout.write(
                    f"Skipped (human-active):         {total_skipped_human_active}"
                )
        else:
            self.stdout.write(f"Results inspected:              {total_inspected}")
            self.stdout.write(
                self.style.SUCCESS(f"Results flipped → consensus:    {total_flipped}")
            )
            self.stdout.write(
                f"Left as conflict (genuine split): {total_left_as_conflict}"
            )
            if total_skipped_human_active:
                self.stdout.write(
                    f"Skipped (human-active):         {total_skipped_human_active}"
                )
