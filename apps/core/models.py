"""
Core models for configuration and shared functionality.
"""

import json
import logging
import secrets
import uuid
from datetime import timedelta
from typing import Any

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)

User = get_user_model()


class TimeStampedModel(models.Model):
    """Abstract base model with UUID primary key and timestamp fields."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AbstractInvitation(models.Model):
    """
    Abstract base for invitation models with magic link tokens.

    Provides shared token generation, expiry, status tracking, and
    magic link URL generation. Subclasses must implement
    `get_magic_link_url_name()` to specify the URL pattern name.

    Does not inherit from TimeStampedModel to avoid adding columns
    to existing tables that manage their own timestamps differently.
    """

    STATUS_PENDING = "PENDING"
    STATUS_ACCEPTED = "ACCEPTED"
    STATUS_EXPIRED = "EXPIRED"
    STATUS_REVOKED = "REVOKED"

    BASE_STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_REVOKED, "Revoked"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token = models.CharField(max_length=64, unique=True, editable=False)
    status = models.CharField(
        max_length=20, choices=BASE_STATUS_CHOICES, default=STATUS_PENDING
    )
    expires_at = models.DateTimeField()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """Generate token and set expiry on creation."""
        if self._state.adding:
            self.token = secrets.token_urlsafe(48)
            if self.expires_at is None:
                self.expires_at = timezone.now() + timedelta(days=7)
        super().save(*args, **kwargs)

    def is_valid(self) -> bool:
        """Check if invitation is still valid (pending and not expired)."""
        if self.status != self.STATUS_PENDING:
            return False
        if timezone.now() > self.expires_at:
            self.status = self.STATUS_EXPIRED
            self.save(update_fields=["status"])
            return False
        return True

    def get_magic_link_url_name(self) -> str:
        """Return the URL pattern name for this invitation type."""
        raise NotImplementedError("Subclasses must implement get_magic_link_url_name()")

    def get_magic_link(self, request=None) -> str:
        """Generate magic link URL for this invitation."""
        from django.urls import reverse

        path = reverse(self.get_magic_link_url_name(), kwargs={"token": self.token})
        if request:
            return request.build_absolute_uri(path)
        return path


class Configuration(TimeStampedModel):
    """
    Runtime editable configuration stored in database.
    Allows for dynamic configuration changes without code deployment.
    """

    key = models.CharField(
        max_length=100, unique=True, db_index=True, help_text="Unique configuration key"
    )
    value = models.JSONField(
        default=dict,
        blank=True,
        encoder=DjangoJSONEncoder,
        help_text="Configuration value (JSON format). See ConfigValueType in model_types.py",
    )
    description = models.TextField(
        blank=True, help_text="Description of what this configuration controls"
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="configuration_changes",
        help_text="User who last updated this configuration",
    )

    class Meta:
        db_table = "core_configuration"
        ordering = ["key"]
        verbose_name = "Configuration"
        verbose_name_plural = "Configurations"

    def __str__(self):
        return f"{self.key}: {self.get_value_preview()}"

    def get_value_preview(self, max_length=50):
        """Get a preview of the value for display purposes."""
        value_str = json.dumps(self.value)
        if len(value_str) > max_length:
            return f"{value_str[:max_length]}..."
        return value_str

    def clean(self):
        """Validate the configuration value."""
        if not isinstance(self.value, (dict, list, str, int, float, bool, type(None))):
            raise ValidationError(
                {"value": "Configuration value must be JSON-serializable"}
            )

    @classmethod
    def get_config(cls, key: str, default=None) -> Any:
        """
        Get configuration value by key.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Any: Configuration value or default
        """
        try:
            config = cls.objects.get(key=key)
            return config.value
        except cls.DoesNotExist:
            logger.debug(f"Configuration key '{key}' not found, using default")
            return default

    @classmethod
    def set_config(
        cls, key: str, value, description: str = "", user=None
    ) -> "Configuration":
        """
        Set configuration value by key.

        Args:
            key: Configuration key
            value: Configuration value (must be JSON-serializable)
            description: Configuration description
            user: User making the change

        Returns:
            Configuration: The created/updated configuration
        """
        config, created = cls.objects.update_or_create(
            key=key,
            defaults={"value": value, "description": description, "updated_by": user},
        )

        action = "created" if created else "updated"
        logger.info(f"Configuration '{key}' {action}")

        return config

    @classmethod
    def delete_config(cls, key: str) -> bool:
        """
        Delete configuration by key.

        Args:
            key: Configuration key to delete

        Returns:
            bool: True if deleted, False if not found
        """
        try:
            config = cls.objects.get(key=key)
            config.delete()
            logger.info(f"Configuration '{key}' deleted")
            return True
        except cls.DoesNotExist:
            logger.warning(f"Configuration '{key}' not found for deletion")
            return False

    @classmethod
    def list_configs(cls) -> Any:
        """
        List all configurations.

        Returns:
            QuerySet: All configuration objects
        """
        return cls.objects.all()

    @classmethod
    def bulk_update(cls, configs: dict, user=None) -> tuple:
        """
        Bulk update multiple configurations.

        Args:
            configs: Dict of {key: value} pairs
            user: User making the changes

        Returns:
            tuple: (created_count, updated_count)
        """
        created_count = 0
        updated_count = 0

        for key, value in configs.items():
            config, created = cls.objects.update_or_create(
                key=key, defaults={"value": value, "updated_by": user}
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

        logger.info(
            f"Bulk config update: {created_count} created, {updated_count} updated"
        )
        return created_count, updated_count
