"""
UUID configuration tests for core models.

Tests verify that Configuration model uses UUID primary key correctly.
"""

import uuid

from django.test import TestCase

from apps.core.models import Configuration


class ConfigurationUUIDTests(TestCase):
    """Test Configuration model UUID field behavior."""

    def test_configuration_uses_uuid_primary_key(self):
        """Test Configuration model uses UUID primary key."""
        config = Configuration.objects.create(key="test_uuid", value={"test": "data"})

        # Verify UUID format
        self.assertIsInstance(
            config.id, uuid.UUID, "Configuration id should be UUID instance"
        )

        # Verify field properties
        id_field = Configuration._meta.get_field("id")
        self.assertTrue(
            id_field.primary_key, "Configuration UUID field should be primary key"
        )
        self.assertFalse(
            id_field.editable, "Configuration UUID field should have editable=False"
        )
        self.assertEqual(
            id_field.default,
            uuid.uuid4,
            "Configuration UUID field should use uuid.uuid4 default",
        )

    def test_configuration_uuid_field_type(self):
        """Test Configuration UUID field uses correct Django field type."""
        from django.db import models

        id_field = Configuration._meta.get_field("id")
        self.assertIsInstance(
            id_field, models.UUIDField, "Configuration id should be UUIDField"
        )

    def test_configuration_uuid_uniqueness(self):
        """Test that Configuration UUIDs are unique."""
        config1 = Configuration.objects.create(
            key="test_unique_1", value={"test": "data1"}
        )
        config2 = Configuration.objects.create(
            key="test_unique_2", value={"test": "data2"}
        )

        # UUIDs should be different
        self.assertNotEqual(
            config1.id, config2.id, "Configuration UUIDs should be unique"
        )

    def test_configuration_uuid_not_editable_in_admin(self):
        """Test that Configuration UUID field is not editable in Django admin."""
        from django.contrib.admin.sites import site

        admin_class = site._registry.get(Configuration)
        if admin_class:
            form = admin_class.form
            self.assertNotIn(
                "id",
                form.base_fields,
                "Configuration UUID field should not be editable in admin",
            )

    def test_configuration_model_consistency(self):
        """Test Configuration model follows UUID consistency patterns."""
        # Check that the model follows the established UUID pattern
        id_field = Configuration._meta.get_field("id")

        # Should be UUID field
        self.assertEqual(id_field.__class__.__name__, "UUIDField")
        # Should be primary key
        self.assertTrue(id_field.primary_key)
        # Should not be editable
        self.assertFalse(id_field.editable)
        # Should have uuid4 default
        self.assertEqual(id_field.default, uuid.uuid4)
