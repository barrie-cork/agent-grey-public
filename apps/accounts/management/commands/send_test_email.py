"""
Django management command to send test emails.
"""

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string


class Command(BaseCommand):
    help = "Send a test email to verify email configuration"

    def add_arguments(self, parser):
        parser.add_argument(
            "email", type=str, help="Email address to send test email to"
        )
        parser.add_argument(
            "--type",
            choices=["welcome", "simple"],
            default="simple",
            help="Type of test email to send (default: simple)",
        )

    def handle(self, *args, **options):
        email = options["email"]
        email_type = options["type"]

        self.stdout.write(f"Sending {email_type} test email to {email}...")

        try:
            if email_type == "welcome":
                self.send_welcome_test(email)
            else:
                self.send_simple_test(email)

            self.stdout.write(
                self.style.SUCCESS(f"Test email sent successfully to {email}")
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to send email: {str(e)}"))

    def send_simple_test(self, email):
        """Send a simple test email."""
        subject = "Agent Grey - Email Test"
        message = f"""
Hello!

This is a test email from Agent Grey to verify that the email system is working correctly.

Email configuration:
- Backend: {settings.EMAIL_BACKEND}
- From: {settings.DEFAULT_FROM_EMAIL}
- Time: {self.get_current_time()}

If you received this email, the email system is functioning properly.

Best regards,
The Agent Grey Team
"""

        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )

    def send_welcome_test(self, email):
        """Send a welcome email test using the template."""
        # Create a mock user for template rendering
        mock_user = type(
            "MockUser",
            (),
            {
                "username": "testuser",
                "email": email,
                "first_name": "Test",
                "last_name": "User",
                "get_full_name": lambda: "Test User",
            },
        )()

        subject = "Agent Grey - Welcome Email Test"
        html_message = render_to_string(
            "accounts/welcome_email.html",
            {
                "user": mock_user,
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
            message="Welcome to Agent Grey! (This is a test email)",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            html_message=html_message,
            fail_silently=False,
        )

    def get_current_time(self):
        """Get current time as string."""
        from datetime import datetime

        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
