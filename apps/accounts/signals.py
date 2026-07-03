"""
Django signals for the accounts app.
Handles email notifications for user registration and organization setup.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.template.loader import render_to_string

from .models import User

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User, dispatch_uid="accounts.send_user_registration_emails")
def send_user_registration_emails(sender, instance, created, **kwargs):
    """
    Send welcome email to new user and notification to admins.

    Args:
        sender: The User model class
        instance: The User instance that was saved
        created: Boolean indicating if this is a new user
        **kwargs: Additional signal arguments
    """
    if not created or not instance.email:
        return

    # Send welcome email to user
    try:
        subject = "Welcome to Agent Grey!"
        html_message = render_to_string(
            "accounts/welcome_email.html",
            {
                "user": instance,
                "site_name": "Agent Grey",
                "protocol": (
                    "https"
                    if getattr(settings, "SECURE_SSL_REDIRECT", False)
                    else "http"
                ),
                "domain": getattr(settings, "SITE_DOMAIN", "localhost:8000"),
            },
        )

        send_mail(
            subject=subject,
            message=html_message,  # Template is plain text despite .html extension
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[instance.email],
            html_message=html_message,
            fail_silently=True,
        )

        logger.info(
            f"Welcome email sent to user: {instance.username} ({instance.email})"
        )

    except Exception as e:
        logger.error(f"Failed to send welcome email to {instance.email}: {str(e)}")

    # Send admin notification
    try:
        if hasattr(settings, "ADMINS") and settings.ADMINS:
            admin_subject = f"New user registered: {instance.username}"
            admin_message = f"""A new user has registered on Agent Grey:

Username: {instance.username}
Email: {instance.email}
Full Name: {instance.get_full_name() or "Not provided"}
Registration Date: {instance.date_joined.strftime("%Y-%m-%d %H:%M:%S")}

You can view their profile in the Django admin panel.
"""

            admin_emails = [email for name, email in settings.ADMINS]

            send_mail(
                subject=admin_subject,
                message=admin_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=admin_emails,
                fail_silently=True,
            )

            logger.info(f"Admin notification sent for new user: {instance.username}")

    except Exception as e:
        logger.error(
            f"Failed to send admin notification for {instance.username}: {str(e)}"
        )


@receiver(post_save, sender=User, dispatch_uid="accounts.create_personal_organisation")
def create_personal_organisation(sender, instance, created, **kwargs):
    """
    Auto-create a personal organisation for new users.

    FIX (Issue #31): New users need an organisation to access dual-screening SPA.
    This signal creates a personal organisation with the user as owner, enabling
    immediate access to all features without manual organisation setup.

    Args:
        sender: The User model class
        instance: The User instance that was saved
        created: Boolean indicating if this is a new user
        **kwargs: Additional signal arguments
    """
    if not created:
        return

    try:
        from apps.organisation.models import Organisation, OrganisationMembership
        from django.utils.text import slugify

        # Create personal organisation
        org_name = f"{instance.get_full_name() or instance.username}'s Organisation"
        base_slug = slugify(instance.username)

        # Ensure unique slug
        slug = base_slug
        counter = 1
        while Organisation.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1

        organisation = Organisation.objects.create(
            name=org_name,
            slug=slug,
            default_review_mode="DUAL",  # Default to dual-screening
            default_min_reviewers=2,
            require_dual_review=False,  # Allow user to choose
        )

        # Add user as organisation owner (using INFORMATION_SPECIALIST role)
        OrganisationMembership.objects.create(
            organisation=organisation,
            user=instance,
            role="INFORMATION_SPECIALIST",
            is_active=True,
        )

        logger.info(
            f"Created personal organisation '{org_name}' for user {instance.username}"
        )

    except Exception as e:
        logger.error(
            f"Failed to create organisation for {instance.username}: {str(e)}",
            exc_info=True,
        )
