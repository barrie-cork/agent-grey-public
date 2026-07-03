#!/usr/bin/env python
"""Create E2E test users"""
from django.contrib.auth import get_user_model
from apps.organisation.models import Organisation, OrganisationMembership

User = get_user_model()

# Create test organisation
org, created = Organisation.objects.get_or_create(
    slug='e2e-test-org',
    defaults={
        'name': 'E2E Test Organisation',
        'default_review_mode': 'DUAL_BLIND',
        'default_min_reviewers': 2,
        'require_dual_review': True
    }
)

print(f"Organisation: {org.name} ({'created' if created else 'exists'})")

# Create test users
test_users = [
    {'username': 'reviewer1', 'email': 'reviewer1@test.com', 'password': 'testpass123', 'role': 'REVIEWER'},
    {'username': 'reviewer2', 'email': 'reviewer2@test.com', 'password': 'testpass123', 'role': 'REVIEWER'},
    {'username': 'admin', 'email': 'admin@test.com', 'password': 'adminpass123', 'role': 'ADMIN'},
    {'username': 'session_owner', 'email': 'owner@test.com', 'password': 'testpass123', 'role': 'ADMIN'},
]

for user_data in test_users:
    user, user_created = User.objects.get_or_create(
        username=user_data['username'],
        defaults={'email': user_data['email']}
    )

    if user_created:
        user.set_password(user_data['password'])
        user.save()
        print(f"Created user: {user.username}")
    else:
        # Update password in case it changed
        user.set_password(user_data['password'])
        user.save()
        print(f"Updated user: {user.username}")

    # Create membership
    membership, m_created = OrganisationMembership.objects.get_or_create(
        user=user,
        organisation=org,
        defaults={'role': user_data['role'], 'is_active': True}
    )

    if m_created:
        print(f"  -> Added to {org.name} as {membership.role}")
    else:
        print(f"  -> Already in {org.name} as {membership.role}")

print("\n✅ Test users ready for E2E tests")
