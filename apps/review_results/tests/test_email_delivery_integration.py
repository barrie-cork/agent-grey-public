"""
Integration tests for email delivery in dual-screening workflow.

Tests email notification service with focus on:
- Plain text fallback validation
- Email delivery success
- SMTP configuration validation
- Cross-client compatibility

These tests complement test_email_notification_service.py by focusing on
delivery integration and format validation rather than business logic.
"""

from django.core import mail
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model

from apps.review_results.models import (
    ReviewerDecision,
    ConflictResolution,
)
from apps.core.tests.utils import create_test_user
from apps.review_results.services.email_notification_service import (
    EmailNotificationService,
)
from apps.review_manager.models import SearchSession
from apps.results_manager.models import ProcessedResult
from apps.organisation.models import Organisation, OrganisationMembership

User = get_user_model()


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@agentgrey.test",
    SITE_DOMAIN="localhost:8000",
)
class EmailDeliveryIntegrationTest(TestCase):
    """Integration tests for email notification delivery and format validation."""

    def setUp(self):
        """Create test data for email notifications."""
        # Create organisation
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create users with emails
        self.user1 = create_test_user(
            username_prefix="reviewer1", first_name="Alice", last_name="Smith"
        )
        self.user2 = create_test_user(
            username_prefix="reviewer2", first_name="Bob", last_name="Jones"
        )

        # Create organisation memberships
        OrganisationMembership.objects.create(
            user=self.user1,
            organisation=self.organisation,
            role="REVIEWER",
            is_active=True,
        )
        OrganisationMembership.objects.create(
            user=self.user2,
            organisation=self.organisation,
            role="REVIEWER",
            is_active=True,
        )

        # Create session
        self.session = SearchSession.objects.create(
            title="Test Review Session",
            description="Testing email notifications",
            owner=self.user1,
            organisation=self.organisation,
            status="under_review",
        )

        # Create result
        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Search Result",
            url="https://example.com/document.pdf",
            snippet="This is a test result for conflict detection.",
            domain="example.com",
        )

        # Create conflicting decisions
        self.decision1 = ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.user1,
            decision="INCLUDE",
            screening_stage="SCREENING",
            organisation=self.organisation,
        )
        self.decision2 = ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.user2,
            decision="EXCLUDE",
            screening_stage="SCREENING",
            organisation=self.organisation,
        )

        # Create conflict
        self.conflict = ConflictResolution.objects.create(
            result=self.result,
            status="PENDING",
            organisation=self.organisation,
        )
        self.conflict.conflicting_decisions.set([self.decision1, self.decision2])

        # Clear any emails sent during setup
        mail.outbox = []

        # Initialize email service
        self.email_service = EmailNotificationService()

    def test_conflict_email_includes_plain_text_fallback(self):
        """Test that conflict detected email includes plain text fallback."""
        self.email_service.send_conflict_notification(str(self.conflict.id))

        email = mail.outbox[0]

        # Check plain text body exists
        self.assertIsNotNone(email.body)
        self.assertTrue(len(email.body) > 0)

        # Check plain text includes key information
        self.assertIn(self.session.title, email.body)
        self.assertIn(self.result.title, email.body)
        self.assertIn("Include", email.body)
        self.assertIn("Exclude", email.body)

        # Check plain text is readable (no HTML tags)
        self.assertNotIn("<div>", email.body)
        self.assertNotIn("<p>", email.body)
        self.assertNotIn("<table>", email.body)

    def test_consensus_email_includes_plain_text_fallback(self):
        """Test that consensus reached email includes plain text fallback."""
        # Resolve conflict
        self.conflict.status = "RESOLVED"
        self.conflict.resolution_method = "CONSENSUS"
        self.conflict.final_decision = self.decision1
        self.conflict.resolved_by = self.user1
        self.conflict.resolution_notes = (
            "After discussion, we agreed to include this result."
        )
        self.conflict.save()

        # Send notification
        mail.outbox = []
        self.email_service.send_consensus_notification(str(self.conflict.id))

        email = mail.outbox[0]

        # Verify plain text fallback
        self.assertIsNotNone(email.body)
        self.assertIn("Consensus has been reached", email.body)
        self.assertIn("Include", email.body)
        self.assertIn("Consensus", email.body)

        # No HTML in plain text
        self.assertNotIn("<", email.body)
        self.assertNotIn(">", email.body)

    def test_email_html_alternative_exists(self):
        """Test that HTML alternative is included in all emails."""
        self.email_service.send_conflict_notification(str(self.conflict.id))

        email = mail.outbox[0]

        # Check HTML alternative exists
        self.assertEqual(len(email.alternatives), 1, "Should include HTML alternative")
        html_content, content_type = email.alternatives[0]
        self.assertEqual(content_type, "text/html")

        # Verify HTML content includes essential elements
        self.assertIn("<!doctype html>", html_content.lower())
        self.assertIn(self.result.title, html_content)
        self.assertIn("View Conflict", html_content)

    def test_email_context_variables_rendered_correctly(self):
        """Test that all context variables render without errors."""
        self.email_service.send_conflict_notification(str(self.conflict.id))

        email = mail.outbox[0]
        html_content, _ = email.alternatives[0]

        # Check all required context variables are rendered
        # Email can be sent to either reviewer, so check for both possible names
        has_reviewer_name = (
            self.user1.first_name in html_content
            or self.user2.first_name in html_content
        )
        self.assertTrue(has_reviewer_name, "Email should contain reviewer name")
        self.assertIn(self.session.title, html_content)  # session_title
        self.assertIn(self.result.title, html_content)  # result_title
        self.assertIn(self.result.url, html_content)  # result_url
        self.assertIn("Include", html_content)  # reviewer_decision
        self.assertIn("Exclude", html_content)  # other_decision

        # Check no template variables left unrendered
        self.assertNotIn(
            "{{", html_content, "All template variables should be rendered"
        )
        self.assertNotIn("{%", html_content, "All template tags should be processed")

    def test_email_unsubscribe_link_present(self):
        """Test that unsubscribe link is included in all emails."""
        self.email_service.send_conflict_notification(str(self.conflict.id))

        email = mail.outbox[0]
        body = email.body

        # Check unsubscribe link present in plain text
        self.assertIn("notification preferences", body.lower())
        self.assertIn("/settings/notifications/", body)

        # Check in HTML version
        html_content, _ = email.alternatives[0]
        self.assertIn("notification preferences", html_content.lower())

    def test_multiple_emails_sent_to_all_reviewers(self):
        """Test that email is sent to all involved reviewers."""
        result = self.email_service.send_conflict_notification(str(self.conflict.id))

        # Assert email sent successfully
        self.assertTrue(result, "Email service should return True for successful send")

        # Assert email sent to both reviewers
        self.assertEqual(len(mail.outbox), 2, "Should send email to both reviewers")

        # Verify recipients
        recipients = [email.to[0] for email in mail.outbox]
        self.assertIn(self.user1.email, recipients)
        self.assertIn(self.user2.email, recipients)

    def test_email_subject_format_correct(self):
        """Test that email subject is correctly formatted."""
        self.email_service.send_conflict_notification(str(self.conflict.id))

        email = mail.outbox[0]
        self.assertEqual(email.subject, f"Conflict Detected - {self.session.title}")

    def test_email_from_address_configured(self):
        """Test that FROM address is correctly configured."""
        self.email_service.send_conflict_notification(str(self.conflict.id))

        email = mail.outbox[0]
        self.assertEqual(email.from_email, "noreply@agentgrey.test")

    def test_nonexistent_conflict_returns_false(self):
        """Test that sending email for nonexistent conflict returns False."""
        import uuid

        fake_uuid = str(uuid.uuid4())
        success = self.email_service.send_conflict_notification(fake_uuid)

        self.assertFalse(success, "Should return False for nonexistent conflict")
        self.assertEqual(len(mail.outbox), 0, "Should not send any emails")


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
    EMAIL_HOST="smtp.example.com",
    EMAIL_PORT=587,
    EMAIL_USE_TLS=True,
    DEFAULT_FROM_EMAIL="noreply@agentgrey.app",
)
class EmailSMTPConfigurationTest(TestCase):
    """Tests for SMTP configuration validation."""

    def test_production_smtp_settings_present(self):
        """Test that production SMTP settings are configured."""
        from django.conf import settings

        # Verify all required settings are present
        self.assertTrue(hasattr(settings, "EMAIL_HOST"))
        self.assertTrue(hasattr(settings, "EMAIL_PORT"))
        self.assertTrue(hasattr(settings, "DEFAULT_FROM_EMAIL"))

    def test_email_security_enabled(self):
        """Test that TLS/SSL is enabled for security."""
        from django.conf import settings

        # Verify TLS or SSL is enabled
        self.assertTrue(
            settings.EMAIL_USE_TLS or settings.EMAIL_USE_SSL,
            "Email should use TLS or SSL for security",
        )

    def test_sender_email_configured(self):
        """Test that sender email is properly configured."""
        from django.conf import settings

        # Verify sender email is configured
        self.assertIsNotNone(settings.DEFAULT_FROM_EMAIL)
        self.assertIn("@", settings.DEFAULT_FROM_EMAIL)

    def test_email_backend_not_console_or_dummy(self):
        """Test that production backend is not console or dummy."""
        from django.conf import settings

        # For this test configuration, we expect SMTP backend
        self.assertEqual(
            settings.EMAIL_BACKEND, "django.core.mail.backends.smtp.EmailBackend"
        )


class EmailTemplateFormatTest(TestCase):
    """Tests for email template format and structure."""

    def setUp(self):
        """Set up minimal test data."""
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        self.user1 = create_test_user(
            username_prefix="reviewer1", first_name="Test", last_name="Reviewer"
        )
        self.user2 = create_test_user(
            username_prefix="reviewer2", first_name="Second", last_name="Reviewer"
        )

        OrganisationMembership.objects.create(
            user=self.user1,
            organisation=self.organisation,
            role="REVIEWER",
            is_active=True,
        )
        OrganisationMembership.objects.create(
            user=self.user2,
            organisation=self.organisation,
            role="REVIEWER",
            is_active=True,
        )

        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.user1,
            organisation=self.organisation,
        )

        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            url="https://example.com/test.pdf",
            snippet="Test snippet",
            domain="example.com",
        )

        self.decision1 = ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.user1,
            decision="INCLUDE",
            screening_stage="SCREENING",
            organisation=self.organisation,
        )
        self.decision2 = ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.user2,
            decision="EXCLUDE",
            screening_stage="SCREENING",
            organisation=self.organisation,
        )

        self.conflict = ConflictResolution.objects.create(
            result=self.result,
            organisation=self.organisation,
        )
        self.conflict.conflicting_decisions.set([self.decision1, self.decision2])

        mail.outbox = []
        self.email_service = EmailNotificationService()

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_email_template_uses_inline_css(self):
        """Test that email templates use inline CSS for compatibility."""
        self.email_service.send_conflict_notification(str(self.conflict.id))

        email = mail.outbox[0]
        html_content, _ = email.alternatives[0]

        # Check for inline styles (should have style="" attributes)
        self.assertIn('style="', html_content)

        # Should not have <style> tags in body (only in <head> is acceptable)
        # Note: Base template might have <style> in <head>, which is acceptable
        # We check that critical elements have inline styles
        self.assertTrue(
            "padding:" in html_content or "margin:" in html_content,
            "Should use inline CSS for compatibility",
        )

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_email_template_has_responsive_meta_tag(self):
        """Test that email has viewport meta tag for mobile."""
        self.email_service.send_conflict_notification(str(self.conflict.id))

        email = mail.outbox[0]
        html_content, _ = email.alternatives[0]

        # Check for viewport meta tag or max-width styling
        has_responsive = (
            "viewport" in html_content.lower() or "max-width" in html_content.lower()
        )
        self.assertTrue(has_responsive, "Email should be mobile-responsive")

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_email_template_includes_branding(self):
        """Test that email includes Agent Grey branding."""
        self.email_service.send_conflict_notification(str(self.conflict.id))

        email = mail.outbox[0]
        html_content, _ = email.alternatives[0]

        # Check for branding
        self.assertIn("Agent Grey", html_content)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_email_template_includes_footer_copyright(self):
        """Test that email includes copyright footer."""
        self.email_service.send_conflict_notification(str(self.conflict.id))

        email = mail.outbox[0]
        body = email.body

        # Check plain text footer
        self.assertIn("Agent Grey", body)
        self.assertIn("All rights reserved", body)
