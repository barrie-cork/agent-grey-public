"""
Base email notification service providing shared email infrastructure.

Extracted from duplicated code in:
- apps/review_manager/services/notification_service.py
- apps/review_results/services/email_notification_service.py
"""

import logging
import smtplib
from typing import Dict, List

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template import TemplateDoesNotExist, TemplateSyntaxError
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from apps.core.services.base import BaseService

logger = logging.getLogger(__name__)


class BaseEmailNotificationService(BaseService):
    """
    Base class for email notification services.

    Provides shared email infrastructure: configuration, URL building,
    and HTML email sending with plain text fallback. Subclasses implement
    domain-specific notification methods.
    """

    def _initialize(self) -> None:
        """Initialise email notification service resources."""
        pass

    def health_check(self) -> bool:
        """
        Check if service is healthy.

        Subclasses may override to check domain-specific models.
        """
        return True

    def get_default_config(self) -> Dict:
        """Get default configuration for email notification service."""
        return {
            "cache_timeout": 300,
            "send_email": True,
            "from_email": getattr(
                settings, "DEFAULT_FROM_EMAIL", "noreply@agentgrey.app"
            ),
            "site_domain": getattr(settings, "SITE_DOMAIN", "localhost:8000"),
            "use_https": getattr(settings, "SECURE_SSL_REDIRECT", False),
        }

    def _get_base_url(self) -> str:
        """Get base URL for email links."""
        protocol = "https" if self.config.get("use_https", False) else "http"
        domain = self.config.get("site_domain", "localhost:8000")
        return f"{protocol}://{domain}"

    def _send_email(
        self,
        subject: str,
        html_template: str,
        context: Dict,
        recipient_list: List[str],
    ) -> bool:
        """
        Send HTML email with plain text fallback.

        Args:
            subject: Email subject line
            html_template: Path to HTML template
            context: Template context dictionary
            recipient_list: List of recipient email addresses

        Returns:
            bool: True if email sent successfully
        """
        try:
            # Merge base context without mutating the caller's dictionary
            full_context = {
                "site_name": "Agent Grey",
                "preferences_url": f"{self._get_base_url()}/settings/notifications/",
                **context,  # Caller's context takes precedence
            }

            # Render HTML email
            html_message = render_to_string(html_template, full_context)

            # Try to use dedicated plain text template, fallback to strip_tags
            text_template = html_template.replace(".html", ".txt")
            try:
                text_message = render_to_string(text_template, full_context)
            except TemplateDoesNotExist:
                # Fallback: create plain text version by stripping HTML
                text_message = strip_tags(html_message)

            # Create email message
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_message,
                from_email=self.config.get("from_email"),
                to=recipient_list,
            )
            email.attach_alternative(html_message, "text/html")

            # Send email
            email.send(fail_silently=False)

            self.logger.info(
                f"Email sent: {subject} to {len(recipient_list)} recipient(s)",
                extra={
                    "recipient_count": len(recipient_list),
                    "template": html_template,
                },
            )

            return True

        except (
            smtplib.SMTPException,
            OSError,
            ConnectionError,
            TemplateSyntaxError,
            TemplateDoesNotExist,
        ) as e:
            self._handle_error(
                e,
                operation="_send_email",
                context={"subject": subject, "recipient_count": len(recipient_list)},
            )
            # Don't raise - email failure shouldn't block the operation
            return False
