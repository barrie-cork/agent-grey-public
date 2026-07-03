#!/bin/bash
# E2E Test Database Setup Script
# Sets up test users with organisation memberships for E2E testing
# This script is idempotent and safe to run multiple times

set -e  # Exit on error

echo "======================================"
echo "E2E Test Database Setup"
echo "======================================"
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker is not running. Please start Docker and try again."
    exit 1
fi

# Check if web container is running
if ! docker compose ps web | grep -q "Up"; then
    echo "❌ Error: web container is not running. Please start the application:"
    echo "   docker compose up -d"
    exit 1
fi

echo "✅ Docker is running"
echo ""

# Run migrations first
echo "📦 Running database migrations..."
docker compose exec -T web python manage.py migrate --noinput
echo "✅ Migrations complete"
echo ""

# Create test data using Django shell
echo "👥 Creating test users and organisation..."
docker compose exec -T web python manage.py shell << 'EOF'
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

if created:
    print(f"✅ Created organisation: {org.name}")
else:
    print(f"ℹ️  Organisation already exists: {org.name}")

# Create test users with organisation memberships
test_users = [
    {
        'username': 'reviewer1',
        'email': 'reviewer1@test.com',
        'password': 'testpass123',
        'role': 'REVIEWER'
    },
    {
        'username': 'reviewer2',
        'email': 'reviewer2@test.com',
        'password': 'testpass123',
        'role': 'REVIEWER'
    },
    {
        'username': 'admin',
        'email': 'admin@test.com',
        'password': 'adminpass123',
        'role': 'ADMIN'
    },
    {
        'username': 'session_owner',
        'email': 'owner@test.com',
        'password': 'testpass123',
        'role': 'ADMIN'
    },
]

users_created = 0
memberships_created = 0

for user_data in test_users:
    # Create or get user
    user, user_created = User.objects.get_or_create(
        username=user_data['username'],
        defaults={'email': user_data['email']}
    )

    if user_created:
        user.set_password(user_data['password'])
        user.save()
        users_created += 1
        print(f"✅ Created user: {user.username}")
    else:
        print(f"ℹ️  User already exists: {user.username}")

    # Create or get organisation membership
    membership, m_created = OrganisationMembership.objects.get_or_create(
        user=user,
        organisation=org,
        defaults={
            'role': user_data['role'],
            'is_active': True
        }
    )

    if m_created:
        memberships_created += 1
        print(f"✅ Created membership: {user.username} -> {org.name} ({membership.role})")
    else:
        print(f"ℹ️  Membership already exists: {user.username} -> {org.name} ({membership.role})")

print("")
print("=" * 50)
print(f"Summary:")
print(f"  New users created: {users_created}")
print(f"  New memberships created: {memberships_created}")
print(f"  Total test users: {len(test_users)}")
print("=" * 50)
EOF

echo ""
echo "======================================"
echo "✅ E2E Test Database Setup Complete!"
echo "======================================"
echo ""
echo "Test users ready:"
echo "  • reviewer1 / testpass123 (REVIEWER)"
echo "  • reviewer2 / testpass123 (REVIEWER)"
echo "  • admin / adminpass123 (ADMIN)"
echo "  • session_owner / testpass123 (ADMIN)"
echo ""
echo "Organisation: E2E Test Organisation (e2e-test-org)"
echo ""
