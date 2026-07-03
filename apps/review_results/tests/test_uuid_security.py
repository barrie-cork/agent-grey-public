"""
UUID security tests for review_results models.

Tests verify that UUID fields have editable=False to prevent admin editing.
"""

from django.contrib.admin.sites import site
from django.test import TestCase

from apps.review_results.models import SimpleReviewDecision, URLAccessLog


class UUIDSecurityTests(TestCase):
    """Test UUID field security for review_results models."""

    def test_uuid_fields_not_editable_in_admin(self):
        """Test that UUID fields cannot be edited in Django admin."""
        # Test SimpleReviewDecision
        admin_class = site._registry.get(SimpleReviewDecision)
        if admin_class:
            form = admin_class.form
            self.assertNotIn(
                "id",
                form.base_fields,
                "SimpleReviewDecision UUID field should not be editable in admin",
            )

        # Test URLAccessLog
        admin_class = site._registry.get(URLAccessLog)
        if admin_class:
            form = admin_class.form
            self.assertNotIn(
                "id",
                form.base_fields,
                "URLAccessLog UUID field should not be editable in admin",
            )

    def test_uuid_field_readonly_property(self):
        """Test UUID fields have editable=False."""
        # Test SimpleReviewDecision UUID field
        decision_id_field = SimpleReviewDecision._meta.get_field("id")
        self.assertFalse(
            decision_id_field.editable,
            "SimpleReviewDecision UUID field should have editable=False",
        )

        # Test URLAccessLog UUID field
        log_id_field = URLAccessLog._meta.get_field("id")
        self.assertFalse(
            log_id_field.editable, "URLAccessLog UUID field should have editable=False"
        )

    def test_uuid_field_is_primary_key(self):
        """Test that UUID fields are correctly configured as primary keys."""
        # Test SimpleReviewDecision
        decision_id_field = SimpleReviewDecision._meta.get_field("id")
        self.assertTrue(
            decision_id_field.primary_key,
            "SimpleReviewDecision UUID field should be primary key",
        )

        # Test URLAccessLog
        log_id_field = URLAccessLog._meta.get_field("id")
        self.assertTrue(
            log_id_field.primary_key, "URLAccessLog UUID field should be primary key"
        )

    def test_uuid_field_type(self):
        """Test that UUID fields use correct field type."""
        from django.db import models

        # Test SimpleReviewDecision
        decision_id_field = SimpleReviewDecision._meta.get_field("id")
        self.assertIsInstance(
            decision_id_field,
            models.UUIDField,
            "SimpleReviewDecision id should be UUIDField",
        )

        # Test URLAccessLog
        log_id_field = URLAccessLog._meta.get_field("id")
        self.assertIsInstance(
            log_id_field, models.UUIDField, "URLAccessLog id should be UUIDField"
        )
