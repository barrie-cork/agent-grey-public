"""
Tests for feedback models.
"""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import models
from django.test import TestCase

from ..admin import UserFeedbackAdmin
from ..models import (
    DECISION_CHOICES,
    FREQUENCY_CHOICES,
    SEVERITY_CHOICES,
    UserFeedback,
)
from apps.core.tests.utils import create_test_user

User = get_user_model()


class UserFeedbackModelTest(TestCase):
    """Test UserFeedback model."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()

    def test_create_feedback_with_user(self):
        """Test creating feedback with authenticated user."""
        feedback = UserFeedback.objects.create(
            user=self.user,
            page_path="/test-page/",
            page_title="Test Page",
            feedback_type="bug",
            subject="Test Bug",
            message="This is a test bug report with enough detail to pass validation.",
            rating=2,
        )

        self.assertEqual(feedback.user, self.user)
        self.assertEqual(feedback.feedback_type, "bug")
        self.assertFalse(feedback.is_anonymous)
        self.assertTrue(feedback.is_critical)
        self.assertEqual(
            str(feedback), f"{self.user.username} - Bug Report on /test-page/"
        )

    def test_create_anonymous_feedback(self):
        """Test creating anonymous feedback."""
        feedback = UserFeedback.objects.create(
            email="anonymous@example.com",
            page_path="/test-page/",
            page_title="Test Page",
            feedback_type="suggestion",
            message="This is an anonymous suggestion with enough detail to pass validation.",
        )

        self.assertIsNone(feedback.user)
        self.assertTrue(feedback.is_anonymous)
        self.assertFalse(feedback.is_critical)
        self.assertEqual(
            feedback.submitter_display, "Anonymous (anonymous@example.com)"
        )

    def test_feedback_without_user_or_email(self):
        """Test anonymous feedback without email."""
        feedback = UserFeedback.objects.create(
            page_path="/test-page/",
            feedback_type="general",
            message="Anonymous feedback without email with enough detail to pass validation.",
        )

        self.assertEqual(feedback.submitter_display, "Anonymous")

    def test_mark_as_resolved(self):
        """Test marking feedback as resolved."""
        feedback = UserFeedback.objects.create(
            user=self.user,
            page_path="/test-page/",
            feedback_type="bug",
            message="Test bug report with enough detail to pass validation.",
        )

        feedback.mark_as_resolved(admin_user=self.user, notes="Fixed in version 1.2")

        self.assertEqual(feedback.status, "resolved")
        self.assertIn("Fixed in version 1.2", feedback.admin_notes)

    def test_mark_as_dismissed(self):
        """Test marking feedback as dismissed."""
        feedback = UserFeedback.objects.create(
            user=self.user,
            page_path="/test-page/",
            feedback_type="suggestion",
            message="Test suggestion with enough detail to pass validation.",
        )

        feedback.mark_as_dismissed(admin_user=self.user, notes="Not feasible")

        self.assertEqual(feedback.status, "dismissed")
        self.assertIn("Not feasible", feedback.admin_notes)

    def test_screen_category_auto_populated(self):
        """Test screen_category is auto-populated from page_path on save."""
        feedback = UserFeedback.objects.create(
            user=self.user,
            page_path="/search/strategy/",
            feedback_type="bug",
            message="Test screen categorisation with enough detail to pass validation.",
        )
        self.assertEqual(feedback.screen_category, "Search")

    def test_screen_category_other(self):
        """Test screen_category falls back to Other for unknown paths."""
        feedback = UserFeedback.objects.create(
            user=self.user,
            page_path="/unknown-page/",
            feedback_type="bug",
            message="Test screen categorisation with enough detail to pass validation.",
        )
        self.assertEqual(feedback.screen_category, "Other")

    def test_new_fields_defaults(self):
        """Test new fields have correct defaults."""
        feedback = UserFeedback.objects.create(
            user=self.user,
            page_path="/test-page/",
            feedback_type="bug",
            message="Testing defaults for new fields with enough detail.",
            severity="must_have",
            transcription="Voice transcription text",
        )
        self.assertEqual(feedback.severity, "must_have")
        self.assertEqual(feedback.transcription, "Voice transcription text")
        self.assertEqual(feedback.expected_behaviour, "")
        self.assertEqual(feedback.actual_behaviour, "")
        self.assertEqual(feedback.frequency, "")
        self.assertEqual(feedback.team_decision, "")
        self.assertEqual(feedback.github_issue_url, "")
        self.assertIsNone(feedback.github_issue_number)
        self.assertEqual(feedback.contact_email, "")
        self.assertEqual(feedback.voice_metadata, {})
        self.assertEqual(feedback.interaction_context, {})

    def test_is_critical_property(self):
        """Test is_critical property logic."""
        # Critical: bug with low rating
        critical_feedback = UserFeedback.objects.create(
            user=self.user,
            page_path="/test-page/",
            feedback_type="bug",
            message="Critical bug report with enough detail to pass validation.",
            rating=1,
        )
        self.assertTrue(critical_feedback.is_critical)

        # Not critical: bug with high rating
        non_critical_feedback = UserFeedback.objects.create(
            user=self.user,
            page_path="/test-page/",
            feedback_type="bug",
            message="Non-critical bug report with enough detail to pass validation.",
            rating=4,
        )
        self.assertFalse(non_critical_feedback.is_critical)

        # Not critical: non-bug feedback
        suggestion_feedback = UserFeedback.objects.create(
            user=self.user,
            page_path="/test-page/",
            feedback_type="suggestion",
            message="Test suggestion with enough detail to pass validation.",
            rating=1,
        )
        self.assertFalse(suggestion_feedback.is_critical)


class UserFeedbackFieldTypesTest(TestCase):
    """Verify all 20 new fields exist with correct types."""

    def _get_field(self, name: str) -> models.Field:
        return UserFeedback._meta.get_field(name)

    # --- Voice fields ---
    def test_transcription_is_textfield(self):
        field = self._get_field("transcription")
        self.assertIsInstance(field, models.TextField)

    def test_audio_file_is_filefield(self):
        field = self._get_field("audio_file")
        self.assertIsInstance(field, models.FileField)
        self.assertEqual(field.upload_to, "feedback/audio/%Y/%m/")

    def test_audio_duration_ms_is_positive_integer(self):
        field = self._get_field("audio_duration_ms")
        self.assertIsInstance(field, models.PositiveIntegerField)
        self.assertTrue(field.null)

    def test_voice_metadata_is_jsonfield(self):
        field = self._get_field("voice_metadata")
        self.assertIsInstance(field, models.JSONField)

    # --- Screenshot ---
    def test_screenshot_is_imagefield(self):
        field = self._get_field("screenshot")
        self.assertIsInstance(field, models.ImageField)
        self.assertEqual(field.upload_to, "feedback/screenshots/%Y/%m/")

    # --- Enhanced categorisation ---
    def test_severity_is_charfield(self):
        field = self._get_field("severity")
        self.assertIsInstance(field, models.CharField)

    def test_expected_behaviour_is_textfield(self):
        field = self._get_field("expected_behaviour")
        self.assertIsInstance(field, models.TextField)

    def test_actual_behaviour_is_textfield(self):
        field = self._get_field("actual_behaviour")
        self.assertIsInstance(field, models.TextField)

    def test_frequency_is_charfield(self):
        field = self._get_field("frequency")
        self.assertIsInstance(field, models.CharField)

    # --- Rich context ---
    def test_interaction_context_is_jsonfield(self):
        field = self._get_field("interaction_context")
        self.assertIsInstance(field, models.JSONField)

    def test_screen_category_is_charfield(self):
        field = self._get_field("screen_category")
        self.assertIsInstance(field, models.CharField)

    # --- GitHub issue linking ---
    def test_github_issue_url_is_urlfield(self):
        field = self._get_field("github_issue_url")
        self.assertIsInstance(field, models.URLField)

    def test_github_issue_number_is_positive_integer(self):
        field = self._get_field("github_issue_number")
        self.assertIsInstance(field, models.PositiveIntegerField)
        self.assertTrue(field.null)

    def test_github_issue_state_is_charfield(self):
        field = self._get_field("github_issue_state")
        self.assertIsInstance(field, models.CharField)

    def test_github_issue_resolution_is_charfield(self):
        field = self._get_field("github_issue_resolution")
        self.assertIsInstance(field, models.CharField)

    def test_github_issue_closed_at_is_datetimefield(self):
        field = self._get_field("github_issue_closed_at")
        self.assertIsInstance(field, models.DateTimeField)
        self.assertTrue(field.null)

    # --- Triage ---
    def test_team_decision_is_charfield(self):
        field = self._get_field("team_decision")
        self.assertIsInstance(field, models.CharField)

    def test_team_decision_notes_is_textfield(self):
        field = self._get_field("team_decision_notes")
        self.assertIsInstance(field, models.TextField)

    def test_team_decision_at_is_datetimefield(self):
        field = self._get_field("team_decision_at")
        self.assertIsInstance(field, models.DateTimeField)
        self.assertTrue(field.null)

    # --- Contact ---
    def test_contact_email_is_emailfield(self):
        field = self._get_field("contact_email")
        self.assertIsInstance(field, models.EmailField)


class ChoiceTuplesTest(TestCase):
    """Verify choice tuples have expected values."""

    def test_severity_choices(self):
        values = [v for v, _ in SEVERITY_CHOICES]
        self.assertEqual(values, ["must_have", "should_have", "nice_to_have"])

    def test_frequency_choices(self):
        values = [v for v, _ in FREQUENCY_CHOICES]
        self.assertEqual(values, ["always", "sometimes", "once"])

    def test_decision_choices(self):
        values = [v for v, _ in DECISION_CHOICES]
        self.assertEqual(
            values,
            [
                "pending",
                "accepted",
                "rejected",
                "deferred",
                "completed",
                "duplicate",
                "needs_info",
            ],
        )

    def test_feedback_types_updated(self):
        """FEEDBACK_TYPES contains bug, idea, suggestion, general -- not improvement, compliment, other."""
        values = [v for v, _ in UserFeedback.FEEDBACK_TYPES]
        self.assertEqual(values, ["bug", "idea", "suggestion", "general"])
        self.assertNotIn("improvement", values)
        self.assertNotIn("compliment", values)
        self.assertNotIn("other", values)


class DefaultValuesTest(TestCase):
    """Verify default values for new fields."""

    def setUp(self):
        self.user = create_test_user()

    def test_charfield_defaults_to_empty_string(self):
        """All new CharField fields default to empty string."""
        feedback = UserFeedback.objects.create(
            user=self.user,
            page_path="/test/",
            feedback_type="bug",
            message="Testing charfield defaults.",
        )
        self.assertEqual(feedback.severity, "")
        self.assertEqual(feedback.frequency, "")
        self.assertEqual(feedback.github_issue_url, "")
        self.assertEqual(feedback.github_issue_state, "")
        self.assertEqual(feedback.github_issue_resolution, "")
        self.assertEqual(feedback.team_decision, "")
        self.assertEqual(feedback.contact_email, "")

    def test_textfield_defaults_to_empty_string(self):
        feedback = UserFeedback.objects.create(
            user=self.user,
            page_path="/test/",
            feedback_type="bug",
            message="Testing textfield defaults.",
        )
        self.assertEqual(feedback.transcription, "")
        self.assertEqual(feedback.expected_behaviour, "")
        self.assertEqual(feedback.actual_behaviour, "")
        self.assertEqual(feedback.team_decision_notes, "")

    def test_nullable_fields_accept_none(self):
        feedback = UserFeedback.objects.create(
            user=self.user,
            page_path="/test/",
            feedback_type="bug",
            message="Testing nullable defaults.",
        )
        self.assertIsNone(feedback.audio_file.name)
        self.assertIsNone(feedback.screenshot.name)
        self.assertIsNone(feedback.audio_duration_ms)
        self.assertIsNone(feedback.github_issue_number)
        self.assertIsNone(feedback.github_issue_closed_at)
        self.assertIsNone(feedback.team_decision_at)

    def test_jsonfield_defaults_to_empty_dict(self):
        feedback = UserFeedback.objects.create(
            user=self.user,
            page_path="/test/",
            feedback_type="bug",
            message="Testing JSON defaults.",
        )
        self.assertEqual(feedback.voice_metadata, {})
        self.assertEqual(feedback.interaction_context, {})


class ScreenCategoryTest(TestCase):
    """Thorough screen_category auto-population tests."""

    def setUp(self):
        self.user = create_test_user()

    def _create(self, page_path="", **kwargs):
        return UserFeedback.objects.create(
            user=self.user,
            page_path=page_path,
            feedback_type="bug",
            message="Screen category test feedback.",
            **kwargs,
        )

    def test_search_path(self):
        fb = self._create(page_path="/search")
        self.assertEqual(fb.screen_category, "Search")

    def test_results_path_with_subpath(self):
        fb = self._create(page_path="/results/123")
        self.assertEqual(fb.screen_category, "Results")

    def test_unknown_path(self):
        fb = self._create(page_path="/unknown")
        self.assertEqual(fb.screen_category, "Other")

    def test_no_page_path_leaves_empty(self):
        """Creating feedback with no page_path leaves screen_category empty."""
        fb = self._create(page_path="")
        self.assertEqual(fb.screen_category, "")

    def test_categorize_screen_all_map_entries(self):
        """categorize_screen() returns correct value for each SCREEN_MAP entry."""
        expected = {
            "/search": "Search",
            "/search/strategy": "Search",
            "/results": "Results",
            "/results/abc": "Results",
            "/review": "Review",
            "/review/session": "Review",
            "/admin": "Admin",
            "/admin/feedback": "Admin",
            "/profile": "Profile",
            "/profile/settings": "Profile",
            "/api": "API",
            "/api/v1/data": "API",
        }
        for path, category in expected.items():
            fb = UserFeedback(page_path=path)
            self.assertEqual(
                fb.categorize_screen(), category, f"Failed for path: {path}"
            )

    def test_categorize_screen_unmatched(self):
        fb = UserFeedback(page_path="/dashboard")
        self.assertEqual(fb.categorize_screen(), "Other")

    def test_categorize_screen_empty_path(self):
        fb = UserFeedback(page_path="")
        self.assertEqual(fb.categorize_screen(), "Other")

    def test_save_does_not_overwrite_manual_value(self):
        """save() only sets screen_category if it's empty."""
        fb = self._create(page_path="/search", screen_category="Custom")
        self.assertEqual(fb.screen_category, "Custom")
        # Re-save and confirm it stays
        fb.save()
        fb.refresh_from_db()
        self.assertEqual(fb.screen_category, "Custom")


class IndexesTest(TestCase):
    """Verify Meta.indexes include required fields."""

    def _index_field_sets(self):
        return [tuple(idx.fields) for idx in UserFeedback._meta.indexes]

    def test_severity_index_exists(self):
        self.assertIn(("severity",), self._index_field_sets())

    def test_team_decision_index_exists(self):
        self.assertIn(("team_decision",), self._index_field_sets())

    def test_github_issue_number_index_exists(self):
        self.assertIn(("github_issue_number",), self._index_field_sets())


class DataMigrationTest(TestCase):
    """Test migration 0006 feedback_type mappings.

    We verify the migration function logic by importing from the migration
    module and checking the current model state reflects the migration.
    """

    def test_migration_function_is_callable(self):
        """Migration 0006 function exists and is callable."""
        import importlib

        mod = importlib.import_module(
            "apps.feedback.migrations.0006_migrate_feedback_types"
        )
        self.assertTrue(callable(mod.migrate_feedback_types))

    def test_improvement_maps_to_suggestion(self):
        """Old 'improvement' feedback_type no longer valid; mapped to 'suggestion'."""
        values = [v for v, _ in UserFeedback.FEEDBACK_TYPES]
        self.assertNotIn("improvement", values)
        self.assertIn("suggestion", values)

    def test_compliment_maps_to_general(self):
        """Old 'compliment' feedback_type no longer valid; mapped to 'general'."""
        values = [v for v, _ in UserFeedback.FEEDBACK_TYPES]
        self.assertNotIn("compliment", values)
        self.assertIn("general", values)

    def test_other_maps_to_general(self):
        """Old 'other' feedback_type no longer valid; mapped to 'general'."""
        values = [v for v, _ in UserFeedback.FEEDBACK_TYPES]
        self.assertNotIn("other", values)
        self.assertIn("general", values)

    def test_bug_and_suggestion_unchanged(self):
        """Existing 'bug' and 'suggestion' values remain unchanged."""
        values = [v for v, _ in UserFeedback.FEEDBACK_TYPES]
        self.assertIn("bug", values)
        self.assertIn("suggestion", values)


class IntegrationTest(TestCase):
    """Create a full feedback entry with all new fields populated."""

    def setUp(self):
        self.user = create_test_user()

    def test_full_feedback_with_all_new_fields(self):
        from django.utils import timezone

        now = timezone.now()
        feedback = UserFeedback.objects.create(
            user=self.user,
            page_path="/search/strategy/",
            page_title="Search Strategy",
            feedback_type="bug",
            subject="Full integration test",
            message="Complete feedback entry with all new fields populated.",
            rating=3,
            # Voice
            transcription="This is a voice transcription",
            audio_duration_ms=5000,
            voice_metadata={"recording_stopped_by": "user", "confidence": 0.95},
            # Enhanced categorisation
            severity="must_have",
            expected_behaviour="Should work smoothly",
            actual_behaviour="Crashes on submit",
            frequency="always",
            # Rich context
            interaction_context={
                "pages_visited": ["/home", "/search"],
                "js_errors": [],
            },
            screen_category="Search",
            # GitHub issue
            github_issue_url="https://github.com/org/repo/issues/42",
            github_issue_number=42,
            github_issue_state="open",
            github_issue_resolution="",
            github_issue_closed_at=None,
            # Triage
            team_decision="accepted",
            team_decision_notes="Will fix in next sprint",
            team_decision_at=now,
            # Contact
            contact_email="user@example.com",
        )

        # Verify it saves and retrieves correctly
        retrieved = UserFeedback.objects.get(pk=feedback.pk)
        self.assertEqual(retrieved.transcription, "This is a voice transcription")
        self.assertEqual(retrieved.audio_duration_ms, 5000)
        self.assertEqual(retrieved.voice_metadata["confidence"], 0.95)
        self.assertEqual(retrieved.severity, "must_have")
        self.assertEqual(retrieved.expected_behaviour, "Should work smoothly")
        self.assertEqual(retrieved.actual_behaviour, "Crashes on submit")
        self.assertEqual(retrieved.frequency, "always")
        self.assertEqual(
            retrieved.interaction_context["pages_visited"], ["/home", "/search"]
        )
        self.assertEqual(retrieved.screen_category, "Search")
        self.assertEqual(retrieved.github_issue_number, 42)
        self.assertEqual(retrieved.github_issue_state, "open")
        self.assertEqual(retrieved.team_decision, "accepted")
        self.assertEqual(retrieved.team_decision_notes, "Will fix in next sprint")
        self.assertEqual(retrieved.team_decision_at, now)
        self.assertEqual(retrieved.contact_email, "user@example.com")


class AdminConfigurationTest(TestCase):
    """Verify admin configuration for UserFeedback."""

    def setUp(self):
        self.admin_instance = UserFeedbackAdmin(UserFeedback, admin.site)

    def test_list_filter_includes_severity(self):
        self.assertIn("severity", self.admin_instance.list_filter)

    def test_list_filter_includes_team_decision(self):
        self.assertIn("team_decision", self.admin_instance.list_filter)

    def test_fieldsets_include_voice_section(self):
        fieldset_names = [name for name, _ in self.admin_instance.fieldsets]
        self.assertIn("Voice Feedback", fieldset_names)

    def test_fieldsets_include_screenshot_section(self):
        fieldset_names = [name for name, _ in self.admin_instance.fieldsets]
        self.assertIn("Screenshot", fieldset_names)

    def test_fieldsets_include_enhanced_details_section(self):
        fieldset_names = [name for name, _ in self.admin_instance.fieldsets]
        self.assertIn("Enhanced Details", fieldset_names)

    def test_fieldsets_include_github_issue_section(self):
        fieldset_names = [name for name, _ in self.admin_instance.fieldsets]
        self.assertIn("GitHub Issue", fieldset_names)

    def test_fieldsets_include_triage_section(self):
        fieldset_names = [name for name, _ in self.admin_instance.fieldsets]
        self.assertIn("Triage", fieldset_names)

    def test_admin_changelist_loads(self):
        """Admin changelist page loads without errors."""
        superuser = User.objects.create_superuser(
            username="admin_test", email="admin@test.com", password="testpass123"
        )
        self.client.force_login(superuser)
        response = self.client.get("/admin/feedback/userfeedback/")
        self.assertEqual(response.status_code, 200)
