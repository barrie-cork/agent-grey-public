"""
Setup test data for E2E testing of dual-screening feature.

Creates:
- 2 test reviewer users
- 1 test organisation
- 1 search session with results
- Sample results for testing claim/decision workflow
"""

import os
import django
import sys
import uuid

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'grey_lit_project.settings.local')
django.setup()

from django.contrib.auth import get_user_model
from apps.organisation.models import Organisation, OrganisationMembership
from apps.review_manager.models import SearchSession
from apps.results_manager.models import ProcessedResult
from apps.search_strategy.models import SearchStrategy
from apps.review_results.models import ReviewerAssignment, ReviewerDecision, ConflictResolution

User = get_user_model()

def create_test_data():
    """Create test data for E2E testing."""

    print("=" * 60)
    print("CREATING E2E TEST DATA")
    print("=" * 60)

    # Create or get organisation
    org, created = Organisation.objects.get_or_create(
        slug='e2e-test-org',
        defaults={
            'name': 'E2E Test Organisation',
            'default_min_reviewers': 2,
            'require_dual_review': True
        }
    )
    print(f"✓ Organisation: {org.name} ({'created' if created else 'exists'})")

    # Create test reviewers
    reviewer1, created = User.objects.get_or_create(
        username='reviewer1',
        defaults={
            'email': 'reviewer1@test.com',
            'first_name': 'Reviewer',
            'last_name': 'One'
        }
    )
    if created:
        reviewer1.set_password('testpass123')
        reviewer1.save()

    # Create organisation membership for reviewer1
    OrganisationMembership.objects.get_or_create(
        organisation=org,
        user=reviewer1,
        defaults={
            'role': OrganisationMembership.ROLE_REVIEWER,
            'is_active': True
        }
    )
    print(f"✓ Reviewer 1: {reviewer1.username} (password: testpass123)")

    reviewer2, created = User.objects.get_or_create(
        username='reviewer2',
        defaults={
            'email': 'reviewer2@test.com',
            'first_name': 'Reviewer',
            'last_name': 'Two'
        }
    )
    if created:
        reviewer2.set_password('testpass123')
        reviewer2.save()

    # Create organisation membership for reviewer2
    OrganisationMembership.objects.get_or_create(
        organisation=org,
        user=reviewer2,
        defaults={
            'role': OrganisationMembership.ROLE_REVIEWER,
            'is_active': True
        }
    )
    print(f"✓ Reviewer 2: {reviewer2.username} (password: testpass123)")

    # Create admin user
    admin, created = User.objects.get_or_create(
        username='admin',
        defaults={
            'email': 'admin@test.com',
            'first_name': 'Admin',
            'last_name': 'User',
            'is_staff': True,
            'is_superuser': True
        }
    )
    if created:
        admin.set_password('adminpass123')
        admin.save()

    # Create organisation membership for admin
    OrganisationMembership.objects.get_or_create(
        organisation=org,
        user=admin,
        defaults={
            'role': OrganisationMembership.ROLE_LEAD_REVIEWER,
            'is_active': True,
            'can_create_reviews': True,
            'can_manage_users': True,
            'can_view_all_reviews': True,
            'can_edit_configurations': True,
            'can_export_data': True
        }
    )
    print(f"✓ Admin: {admin.username} (password: adminpass123)")

    # Create search session
    session, created = SearchSession.objects.get_or_create(
        title='E2E Test Session - Dual Screening',
        owner=reviewer1,
        organisation=org,
        defaults={
            'status': 'under_review',
            'description': 'Test session for E2E dual-screening tests'
        }
    )
    print(f"✓ Session: {session.title} (ID: {session.id})")

    # Create search strategy
    strategy, created = SearchStrategy.objects.get_or_create(
        session=session,
        defaults={
            'user': reviewer1,
            'population_terms': ['diabetes', 'type 2 diabetes'],
            'interest_terms': ['treatment', 'therapy'],
            'context_terms': ['clinical guidelines', 'policy'],
            'search_config': {
                'domains': ['who.int', 'nice.org.uk', 'cdc.gov'],
                'include_general_search': True,
                'file_types': ['pdf', 'doc'],
                'search_type': 'google'
            }
        }
    )
    print(f"✓ Search Strategy: {'created' if created else 'exists'}")

    # Create test results
    test_results = [
        {
            'title': 'WHO Guidelines for Diabetes Management 2024',
            'url': 'https://www.who.int/publications/guidelines/diabetes-2024.pdf',
            'snippet': 'Comprehensive guidelines for the management of type 2 diabetes in adults...',
            'snippet_html': '<b>Comprehensive guidelines</b> for the management of type 2 diabetes in adults...'
        },
        {
            'title': 'NICE Clinical Guideline: Type 2 Diabetes in Adults',
            'url': 'https://www.nice.org.uk/guidance/ng28',
            'snippet': 'Evidence-based recommendations for the treatment and management of type 2 diabetes...',
            'snippet_html': 'Evidence-based <b>recommendations</b> for the treatment and management of type 2 diabetes...'
        },
        {
            'title': 'ADA Standards of Medical Care in Diabetes - 2024',
            'url': 'https://diabetesjournals.org/care/article/47/Supplement_1/S1/153886',
            'snippet': 'The American Diabetes Association Standards of Medical Care in Diabetes...',
            'snippet_html': 'The American Diabetes Association <b>Standards of Medical Care</b> in Diabetes...'
        },
        {
            'title': 'IDF Clinical Practice Recommendations for Diabetes',
            'url': 'https://idf.org/our-activities/care-prevention/recommendations.html',
            'snippet': 'International Diabetes Federation recommendations for diabetes care...',
            'snippet_html': 'International Diabetes Federation <b>recommendations</b> for diabetes care...'
        },
        {
            'title': 'CDC Guidelines for Diabetes Prevention Program',
            'url': 'https://www.cdc.gov/diabetes/prevention/index.html',
            'snippet': 'Evidence-based program to prevent type 2 diabetes in high-risk populations...',
            'snippet_html': 'Evidence-based program to <b>prevent type 2 diabetes</b> in high-risk populations...'
        },
    ]

    results_created = 0
    for i, result_data in enumerate(test_results, 1):
        result, created = ProcessedResult.objects.get_or_create(
            session=session,
            url=result_data['url'],
            defaults={
                'title': result_data['title'],
                'snippet': result_data['snippet'],
                'domain': result_data['url'].split('/')[2],  # Extract domain from URL
                'is_pdf': result_data['url'].endswith('.pdf'),
                'processing_status': 'success',
                'is_reviewed': False,
                'review_mode': 'DUAL',  # Dual-screening mode for E2E tests
                'min_reviewers_required': 2  # Require 2 reviewers for consensus
            }
        )
        if created:
            results_created += 1

    print(f"✓ Results: {results_created} created (Total: {ProcessedResult.objects.filter(session=session).count()})")

    # Create conflicts for E2E testing
    # Use specific UUIDs that E2E tests expect
    e2e_conflict_uuids = [
        uuid.UUID('550e8400-e29b-41d4-a716-446655440000'),  # Primary test conflict
        uuid.UUID('550e8400-e29b-41d4-a716-446655440999'),  # Secondary test conflict (empty state)
    ]

    # Use first two results to create conflicts
    all_results = list(ProcessedResult.objects.filter(session=session).order_by('created_at')[:2])
    conflicts_created = 0

    if len(all_results) >= 2:
        for i, result in enumerate(all_results):
            # Create reviewer assignments
            assignment1, _ = ReviewerAssignment.objects.get_or_create(
                organisation=org,
                result=result,
                reviewer=reviewer1,
                defaults={
                    'role': 'PRIMARY',
                    'is_active': True
                }
            )

            assignment2, _ = ReviewerAssignment.objects.get_or_create(
                organisation=org,
                result=result,
                reviewer=reviewer2,
                defaults={
                    'role': 'SECONDARY',
                    'is_active': True
                }
            )

            # Create conflicting decisions
            # Reviewer 1 votes INCLUDE
            decision1, _ = ReviewerDecision.objects.get_or_create(
                organisation=org,
                result=result,
                reviewer=reviewer1,
                assignment=assignment1,
                defaults={
                    'decision': 'INCLUDE',
                    'confidence_level': 3,  # High confidence
                    'notes': 'Relevant guidelines document for diabetes management.',
                    'time_spent_seconds': 120
                }
            )

            # Reviewer 2 votes EXCLUDE
            decision2, _ = ReviewerDecision.objects.get_or_create(
                organisation=org,
                result=result,
                reviewer=reviewer2,
                assignment=assignment2,
                defaults={
                    'decision': 'EXCLUDE',
                    'confidence_level': 3,  # High confidence
                    'notes': 'Does not meet inclusion criteria - focuses on treatment not guidelines.',
                    'exclusion_reason': 'OUT_OF_SCOPE',
                    'time_spent_seconds': 150
                }
            )

            # Create conflict resolution record with specific UUID for E2E tests
            conflict_uuid = e2e_conflict_uuids[i] if i < len(e2e_conflict_uuids) else None
            conflict, created = ConflictResolution.objects.get_or_create(
                id=conflict_uuid,  # Use specific UUID
                organisation=org,
                result=result,
                defaults={
                    'conflict_type': 'INCLUDE_EXCLUDE',
                    'status': 'PENDING'
                }
            )

            if created:
                # Add the conflicting decisions to the ManyToMany field
                conflict.conflicting_decisions.add(decision1, decision2)
                conflicts_created += 1

    print(f"✓ Conflicts: {conflicts_created} created (Total: {ConflictResolution.objects.filter(organisation=org).count()})")

    print("\n" + "=" * 60)
    print("TEST DATA SUMMARY")
    print("=" * 60)
    print(f"Organisation: {org.name}")
    print(f"Session ID: {session.id}")
    print(f"Session Title: {session.title}")
    print("\nTest Users:")
    print(f"  Reviewer 1: {reviewer1.username} / testpass123")
    print(f"  Reviewer 2: {reviewer2.username} / testpass123")
    print(f"  Admin:      {admin.username} / adminpass123")
    print(f"\nResults Count: {ProcessedResult.objects.filter(session=session).count()}")
    print(f"Conflicts Count: {ConflictResolution.objects.filter(organisation=org).count()}")

    # Print conflict IDs for E2E tests
    conflicts = ConflictResolution.objects.filter(organisation=org).values_list('id', flat=True)
    if conflicts:
        print("\nConflict IDs for E2E Tests:")
        for conflict_id in conflicts:
            print(f"  - {conflict_id}")

    print("\nE2E Test URLs:")
    print("  - Work Queue: http://localhost:8000/screening/work-queue")
    print("  - Conflicts List: http://localhost:8000/screening/conflicts")
    print("  - Team Dashboard: http://localhost:8000/screening/dashboard/team")
    if conflicts:
        first_conflict = list(conflicts)[0]
        print(f"  - Conflict Discussion: http://localhost:8000/screening/conflicts/{first_conflict}/discuss")
    print("=" * 60)

    return {
        'org': org,
        'session': session,
        'reviewer1': reviewer1,
        'reviewer2': reviewer2,
        'admin': admin,
        'results_count': ProcessedResult.objects.filter(session=session).count()
    }

if __name__ == '__main__':
    data = create_test_data()
