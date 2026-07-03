import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user model with UUID primary key.

    Extends Django's AbstractUser to use UUID primary keys instead of
    auto-incrementing integers for better distributed system compatibility
    and security. Used throughout the grey literature search application.

    Attributes:
        id: UUID primary key field.
        email: User's email address (unique).
        created_at: Timestamp when user account was created.
        updated_at: Timestamp when user account was last modified.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, blank=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        """Return string representation of the user.

        Returns:
            str: Username or email if username is not available.
        """
        return self.username or self.email or str(self.id)

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
