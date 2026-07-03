"""
Management command to create a SearchSession at any workflow state for E2E testing.

Creates all prerequisite objects for the target state, bypassing signals
and Celery tasks to avoid triggering auto-transitions.

Usage:
    # Draft session (minimal)
    docker-compose exec -T web python manage.py setup_e2e_session --state draft

    # Ready for review with WF2 (dual screening)
    docker-compose exec -T web python manage.py setup_e2e_session \
        --state ready_for_review --workflow 2 --num-results 10

    # Completed session with conflicts resolved
    docker-compose exec -T web python manage.py setup_e2e_session \
        --state completed --workflow 2 --num-results 10

    # Custom session ID for test fixtures
    docker-compose exec -T web python manage.py setup_e2e_session \
        --state under_review --session-id my-test-session

Verified dual-screening lifecycle sequence:
    1. Create session (draft)
    2. Configure review (ReviewConfiguration with invited_reviewers)
    3. Define search strategy (SearchStrategy + SearchQuery)
    4. Auto-transition: defining_search -> ready_to_execute (signal)
    5. Execute search (SearchExecution + RawSearchResult)
    6. Process results (ProcessedResult)
    7. Auto-transition: -> ready_for_review (invitations sent, owner completion created)
    8. Reviewer accepts invitation (ReviewerCompletion created)
    9. Both reviewers screen all results (ReviewerDecision records)
    10. Mark reviewers complete (ReviewerCompletion.completed_at)
    11. Detect conflicts (ConflictResolution for disagreements)
    12. Resolve conflicts (all PENDING -> RESOLVED)
    13. Complete review (under_review -> completed)

IMPORTANT: Uses QuerySet.update() to set session status, bypassing save()
signals that would trigger auto-transitions and Celery tasks.
"""

import secrets
import uuid
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.management.commands.create_e2e_users import (
    E2E_ORG_SLUG,
)

# States in lifecycle order
ALL_STATES = [
    "draft",
    "defining_search",
    "ready_to_execute",
    "executing",
    "processing_results",
    "ready_for_review",
    "under_review",
    "completed",
    "archived",
]

# States that require each prerequisite layer
NEEDS_STRATEGY = ALL_STATES[ALL_STATES.index("defining_search") :]
NEEDS_EXECUTION = ALL_STATES[ALL_STATES.index("executing") :]
NEEDS_RESULTS = ALL_STATES[ALL_STATES.index("processing_results") :]
NEEDS_REVIEW_INFRA = ALL_STATES[ALL_STATES.index("ready_for_review") :]
NEEDS_DECISIONS = ALL_STATES[ALL_STATES.index("under_review") :]
NEEDS_COMPLETION = ALL_STATES[ALL_STATES.index("completed") :]


class Command(BaseCommand):
    help = "Create a SearchSession at any workflow state for E2E testing"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--state",
            type=str,
            required=True,
            choices=ALL_STATES,
            help="Target workflow state",
        )
        parser.add_argument(
            "--owner",
            type=str,
            default="e2e-owner@test.local",
            help="Email of session owner (must exist)",
        )
        parser.add_argument(
            "--workflow",
            type=int,
            default=1,
            choices=[1, 2],
            help="Workflow type: 1=Work Distribution, 2=Independent Screening",
        )
        parser.add_argument(
            "--num-results",
            type=int,
            default=10,
            help="Number of ProcessedResult records to create",
        )
        parser.add_argument(
            "--session-id",
            type=str,
            default=None,
            help="Custom identifier suffix for the session title",
        )
        parser.add_argument(
            "--agreement-rate",
            type=float,
            default=0.7,
            help="Fraction of results where reviewers agree (0.0-1.0), rest become conflicts",
        )
        parser.add_argument(
            "--pending-invitations",
            action="store_true",
            default=False,
            help="Create invitations with PENDING status (not ACCEPTED) and output tokens",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        from django.contrib.auth import get_user_model

        from apps.organisation.models import Organisation

        User = get_user_model()

        state = options["state"]
        workflow = options["workflow"]
        num_results = options["num_results"]
        session_suffix = options["session_id"] or f"{state}-{secrets.token_hex(4)}"
        agreement_rate = options["agreement_rate"]
        pending_invitations = options["pending_invitations"]

        # Resolve owner
        try:
            owner = User.objects.get(email=options["owner"])
        except User.DoesNotExist:
            raise CommandError(
                f"Owner {options['owner']} not found. Run create_e2e_users first."
            )

        # Resolve organisation
        try:
            org = Organisation.objects.get(slug=E2E_ORG_SLUG)
        except Organisation.DoesNotExist:
            raise CommandError(
                f"Organisation {E2E_ORG_SLUG} not found. Run create_e2e_users first."
            )

        self.stdout.write(
            self.style.WARNING(f"\n=== Setup E2E Session: {state} (WF{workflow}) ===\n")
        )

        # Step 1: Create session in draft state
        session = self._create_session(owner, org, session_suffix, workflow)

        # Step 2: Create ReviewConfiguration
        config = self._create_config(session, owner, org, workflow)

        # Step 3+: Build prerequisite layers based on target state
        strategy = None
        if state in NEEDS_STRATEGY:
            strategy = self._create_strategy(session, owner)
            self._create_queries(strategy, session)

        if state in NEEDS_EXECUTION:
            self._create_execution_data(session, strategy)

        if state in NEEDS_RESULTS:
            self._create_processed_results(session, num_results)

        if state in NEEDS_REVIEW_INFRA:
            self._create_review_infrastructure(
                session,
                config,
                owner,
                org,
                workflow,
                pending_invitations=pending_invitations,
            )

        if state in NEEDS_DECISIONS:
            self._create_review_decisions(session, owner, org, workflow, agreement_rate)

        if state in NEEDS_COMPLETION:
            self._complete_session(session, org, workflow)

        # Final step: Force session to target state (bypass signals)
        self._force_state(session, state)

        self.stdout.write(self.style.SUCCESS(f"\nSession ready: {session.id}"))
        self.stdout.write(f"  Title: {session.title}")
        self.stdout.write(f"  State: {state}")
        self.stdout.write(f"  Workflow: {workflow}")
        self.stdout.write(f"  Owner: {owner.email}")

        # Output session ID for test fixtures
        self.stdout.write(f"\nSESSION_ID={session.id}")

    def _create_session(self, owner, org, suffix, workflow):
        """Create session in draft state."""
        from apps.review_manager.models import SearchSession

        title = f"E2E Test Session ({suffix})"
        session = SearchSession(
            title=title,
            description=f"E2E test session for workflow {workflow} testing",
            status="draft",
            owner=owner,
            organisation=org,
        )
        # Use save() here -- draft state won't trigger auto-transitions
        session.save()
        self.stdout.write(f"  Created session: {title}")
        return session

    def _create_config(self, session, owner, org, workflow):
        """Create ReviewConfiguration for the session."""
        from apps.review_manager.models import ReviewConfiguration

        min_reviewers = 2 if workflow == 2 else 1
        resolution_method = "CONSENSUS" if workflow == 2 else "LEAD_ARBITRATION"

        # Build invited reviewers list for WF2
        invited_reviewers = []
        if workflow == 2:
            invited_reviewers = [
                {
                    "email": "e2e-reviewer1@test.local",
                    "first_name": "E2E",
                    "last_name": "Reviewer1",
                },
                {
                    "email": "e2e-reviewer2@test.local",
                    "first_name": "E2E",
                    "last_name": "Reviewer2",
                },
            ]

        config = ReviewConfiguration.objects.create(
            session=session,
            version=1,
            min_reviewers_per_result=min_reviewers,
            conflict_resolution_method=resolution_method,
            consensus_criteria="MAJORITY",
            blind_screening_enforced=True,
            irr_threshold=0.70,
            invited_reviewers=invited_reviewers,
            created_by=owner,
            organisation=org,
        )

        # Link config to session (bypass save to avoid signals)
        from apps.review_manager.models import SearchSession

        SearchSession.objects.filter(id=session.id).update(current_configuration=config)
        session.refresh_from_db()

        self.stdout.write(
            f"  Created config: WF{workflow}, {min_reviewers} reviewer(s)"
        )
        return config

    def _create_strategy(self, session, owner):
        """Create SearchStrategy with PIC terms."""
        from apps.search_strategy.models import SearchStrategy

        strategy = SearchStrategy.objects.create(
            session=session,
            user=owner,
            population_terms=["elderly", "older adults"],
            interest_terms=["telehealth", "remote monitoring"],
            context_terms=["primary care", "community"],
            search_config={
                "domains": ["nice.org.uk"],
                "include_general_search": True,
                "file_types": ["pdf"],
                "search_type": "google",
            },
            is_complete=True,
            validation_errors={},
        )
        self.stdout.write("  Created search strategy (PIC terms)")
        return strategy

    def _create_queries(self, strategy, session):
        """Create SearchQuery records for the strategy."""
        from apps.search_strategy.models import SearchQuery

        queries_data = [
            {
                "query_text": 'site:nice.org.uk (elderly OR "older adults") AND (telehealth OR "remote monitoring") AND ("primary care" OR community) AND (filetype:pdf)',
                "query_type": "domain-specific",
                "target_domain": "nice.org.uk",
                "execution_order": 1,
            },
            {
                "query_text": '(elderly OR "older adults") AND (telehealth OR "remote monitoring") AND ("primary care" OR community) AND (filetype:pdf)',
                "query_type": "general",
                "target_domain": "",
                "execution_order": 2,
            },
        ]

        for qd in queries_data:
            # Use bulk_create or direct SQL to avoid check_strategy_completion signal
            SearchQuery.objects.bulk_create(
                [
                    SearchQuery(
                        id=uuid.uuid4(),
                        strategy=strategy,
                        session=session,
                        query_text=qd["query_text"],
                        query_type=qd["query_type"],
                        target_domain=qd["target_domain"],
                        execution_order=qd["execution_order"],
                        is_active=True,
                    )
                ]
            )

        self.stdout.write(f"  Created {len(queries_data)} search queries")

    def _create_execution_data(self, session, strategy):
        """Create SearchExecution and RawSearchResult records."""
        from apps.serp_execution.models import RawSearchResult, SearchExecution

        queries = session.search_queries_denorm.all()
        for query in queries:
            execution = SearchExecution.objects.create(
                query=query,
                search_engine="google",
                status="completed",
                results_count=5,
                started_at=timezone.now(),
                completed_at=timezone.now(),
            )

            # Create a few raw results per execution
            for i in range(5):
                RawSearchResult.objects.create(
                    execution=execution,
                    title=f"E2E Raw Result {i + 1} - {query.target_domain or 'general'}",
                    link=f"https://example.com/e2e-result-{uuid.uuid4().hex[:8]}",
                    snippet=f"E2E test snippet for result {i + 1}",
                    position=i + 1,
                    raw_data={"source": "e2e_seed"},
                )

        self.stdout.write(f"  Created execution data ({queries.count()} executions)")

    def _create_processed_results(self, session, num_results):
        """Create ProcessedResult records for the session."""
        from apps.results_manager.models import ProcessedResult

        config = session.current_configuration
        review_mode, min_reviewers_required = (
            config.review_mode_defaults if config else ("SINGLE", 1)
        )

        results = []
        for i in range(num_results):
            results.append(
                ProcessedResult(
                    session=session,
                    title=f"E2E Grey Literature Result {i + 1}: Policy Document on Healthcare",
                    url=f"https://example.com/e2e-processed-{uuid.uuid4().hex[:8]}",
                    snippet=f"This is a test grey literature document about healthcare policy. Result {i + 1} of {num_results}.",
                    document_type="report",
                    language="en",
                    source_organization="E2E Test Org",
                    domain="example.com",
                    execution_round=1,
                    review_mode=review_mode,
                    min_reviewers_required=min_reviewers_required,
                )
            )

        ProcessedResult.objects.bulk_create(results)

        # Update session total_results count
        from apps.review_manager.models import SearchSession

        SearchSession.objects.filter(id=session.id).update(total_results=num_results)
        session.refresh_from_db()

        self.stdout.write(f"  Created {num_results} processed results")

    def _create_review_infrastructure(
        self, session, config, owner, org, workflow, pending_invitations=False
    ):
        """Create ReviewInvitation + ReviewerCompletion records.

        For WF2: Creates accepted invitations and completion records for
        both invited reviewers AND the owner (who doesn't have an invitation).
        For WF1: Creates completion record for owner only.

        When pending_invitations=True, invitations are created with PENDING status
        (not ACCEPTED), invitee is not linked, and ReviewerCompletion is not created
        for invited reviewers. Outputs INVITATION_TOKEN for each pending invitation.
        """
        from django.contrib.auth import get_user_model

        from apps.review_manager.models import ReviewInvitation
        from apps.review_results.models import ReviewerCompletion

        User = get_user_model()
        total_results = session.total_results

        # Create owner's ReviewerCompletion (no invitation -- matches signal behaviour)
        ReviewerCompletion.objects.get_or_create(
            session=session,
            reviewer=owner,
            defaults={
                "invitation": None,
                "total_results": total_results,
                "reviewed_results": 0,
            },
        )

        if workflow == 2:
            # Create accepted invitations for each invited reviewer
            for reviewer_data in config.invited_reviewers:
                email = reviewer_data["email"]
                try:
                    reviewer_user = User.objects.get(email=email)
                except User.DoesNotExist:
                    self.stdout.write(
                        self.style.WARNING(f"  Reviewer {email} not found, skipping")
                    )
                    continue

                inv_status = (
                    ReviewInvitation.STATUS_PENDING
                    if pending_invitations
                    else ReviewInvitation.STATUS_ACCEPTED
                )
                inv_defaults = {
                    "inviter": owner,
                    "invitee": None if pending_invitations else reviewer_user,
                    "invitee_name": f"{reviewer_data.get('first_name', '')} {reviewer_data.get('last_name', '')}".strip(),
                    "status": inv_status,
                    "token": secrets.token_urlsafe(48),
                }
                if not pending_invitations:
                    inv_defaults["responded_at"] = timezone.now()

                invitation, inv_created = ReviewInvitation.objects.get_or_create(
                    session=session,
                    invitee_email=email,
                    defaults=inv_defaults,
                )

                if pending_invitations:
                    # Output token for E2E test consumption
                    self.stdout.write(f"INVITATION_TOKEN={invitation.token}")
                else:
                    # Create ReviewerCompletion for accepted invitations
                    ReviewerCompletion.objects.get_or_create(
                        session=session,
                        reviewer=reviewer_user,
                        defaults={
                            "invitation": invitation,
                            "total_results": total_results,
                            "reviewed_results": 0,
                        },
                    )

        self.stdout.write("  Created review infrastructure (invitations + completions)")

    def _create_review_decisions(self, session, owner, org, workflow, agreement_rate):
        """Create review decisions for all results.

        For WF1: SimpleReviewDecision (OneToOne) by owner.
        For WF2: ReviewerDecision by owner + each invited reviewer.
                 agreement_rate controls fraction with consensus.
        """
        from django.contrib.auth import get_user_model

        from apps.results_manager.models import ProcessedResult
        from apps.review_results.models import (
            ReviewerCompletion,
            ReviewerDecision,
            SimpleReviewDecision,
        )

        User = get_user_model()
        results = list(ProcessedResult.objects.filter(session=session))

        if workflow == 1:
            # WF1: owner makes all decisions
            decisions = []
            for i, result in enumerate(results):
                decision = "include" if i % 3 != 0 else "exclude"
                decisions.append(
                    SimpleReviewDecision(
                        result=result,
                        session=session,
                        reviewer=owner,
                        decision=decision,
                        exclusion_reason="not_relevant"
                        if decision == "exclude"
                        else "",
                    )
                )
            SimpleReviewDecision.objects.bulk_create(decisions)

            # Update ProcessedResult.is_reviewed
            ProcessedResult.objects.filter(session=session).update(is_reviewed=True)

        elif workflow == 2:
            # WF2: owner + invited reviewers all review all results
            reviewers = [owner]
            config = session.current_configuration
            for rd in config.invited_reviewers:
                try:
                    reviewers.append(User.objects.get(email=rd["email"]))
                except User.DoesNotExist:
                    pass

            agree_count = int(len(results) * agreement_rate)

            for reviewer in reviewers:
                decisions = []
                for i, result in enumerate(results):
                    if i < agree_count:
                        # Agreed results: all reviewers say INCLUDE
                        decision = "INCLUDE"
                    else:
                        # Disagreed results: owner says INCLUDE, others say EXCLUDE
                        if reviewer == owner:
                            decision = "INCLUDE"
                        else:
                            decision = "EXCLUDE"

                    decisions.append(
                        ReviewerDecision(
                            organisation=org,
                            result=result,
                            reviewer=reviewer,
                            decision=decision,
                            confidence_level=3,
                            exclusion_reason="Wrong population"
                            if decision == "EXCLUDE"
                            else "",
                            notes=f"E2E test decision by {reviewer.username}",
                            is_blinded=True,
                            screening_stage="SCREENING",
                        )
                    )
                ReviewerDecision.objects.bulk_create(decisions)

            # Mark all reviewers complete
            ReviewerCompletion.objects.filter(session=session).update(
                reviewed_results=len(results),
                completed_at=timezone.now(),
            )

            # Update ProcessedResult review tracking
            ProcessedResult.objects.filter(session=session).update(
                is_reviewed=True,
                reviewers_completed=len(reviewers),
            )

            # Mark agreed results as consensus
            agreed_result_ids = [r.id for r in results[:agree_count]]
            ProcessedResult.objects.filter(id__in=agreed_result_ids).update(
                consensus_reached=True
            )

        # Update session reviewed_results count
        from apps.review_manager.models import SearchSession

        SearchSession.objects.filter(id=session.id).update(
            reviewed_results=len(results),
            included_results=len([r for i, r in enumerate(results) if i % 3 != 0]),
        )
        session.refresh_from_db()

        self.stdout.write(
            f"  Created review decisions ({len(results)} results, WF{workflow})"
        )

    def _complete_session(self, session, org, workflow):
        """Create conflict detection + resolution records for completed state.

        For WF2: Detect conflicts from disagreements and mark them all RESOLVED.
        """
        if workflow == 2:
            from apps.results_manager.models import ProcessedResult
            from apps.review_results.models import (
                ConflictResolution,
                ReviewerDecision,
            )

            # Find results without consensus (disagreements)
            disagreed_results = ProcessedResult.objects.filter(
                session=session, consensus_reached=False
            )

            for result in disagreed_results:
                decisions = list(
                    ReviewerDecision.objects.filter(
                        result=result, screening_stage="SCREENING", is_revote=False
                    )
                )

                if len(decisions) < 2:
                    continue

                # Determine conflict type
                decision_values = [d.decision for d in decisions]
                if "INCLUDE" in decision_values and "EXCLUDE" in decision_values:
                    conflict_type = "INCLUDE_EXCLUDE"
                else:
                    conflict_type = "LOW_CONFIDENCE"

                conflict = ConflictResolution.objects.create(
                    organisation=org,
                    result=result,
                    conflict_type=conflict_type,
                    status="RESOLVED",
                    resolution_method="CONSENSUS",
                    final_decision=decisions[0],  # Owner's decision wins
                    resolved_at=timezone.now(),
                    resolved_by=session.owner,
                    resolution_notes="E2E test: auto-resolved for seeding",
                )
                conflict.conflicting_decisions.set(decisions)

            conflict_count = ConflictResolution.objects.filter(
                result__session=session
            ).count()
            self.stdout.write(f"  Created {conflict_count} resolved conflicts")

    def _force_state(self, session, target_state):
        """Force session to target state, bypassing signals and validation.

        Uses QuerySet.update() which does NOT trigger:
        - model save() override
        - post_save signals
        - full_clean() validation
        """
        from apps.review_manager.models import SearchSession

        update_fields = {"status": target_state}

        if target_state == "executing":
            update_fields["started_at"] = timezone.now()
        elif target_state in ("completed", "archived"):
            update_fields["completed_at"] = timezone.now()

        # Bypass save() and signals
        SearchSession.objects.filter(id=session.id).update(**update_fields)
        session.refresh_from_db()

        self.stdout.write(f"  Forced state: {target_state}")
