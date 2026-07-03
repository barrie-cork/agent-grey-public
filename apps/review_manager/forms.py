import json

from django import forms
from django.core.validators import validate_email

from apps.organisation.models import Organisation, OrganisationMembership

from .models import ReviewConfiguration, SearchSession

# Constants for review configuration
MAX_REVIEWERS = 4  # Maximum additional reviewers allowed


class SessionForm(forms.ModelForm):
    """Base form for session creation and editing -- title and description only."""

    class Meta:
        model = SearchSession
        fields = ["title", "description"]

    def __init__(self, *args, mode: str = "edit", **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["title"].widget.attrs["class"] = "form-control"
        self.fields["description"].widget.attrs["class"] = "form-control"

        if mode == "create":
            self.fields["title"].widget.attrs.update(
                {
                    "placeholder": "e.g., Diabetes Management Guidelines Review",
                    "autofocus": True,
                    "required": True,
                }
            )
            self.fields["description"].widget = forms.Textarea(
                attrs={
                    "class": "form-control",
                    "placeholder": "Brief description of your systematic review objectives (optional)",
                    "rows": 3,
                }
            )
            self.fields["title"].label = "Review Title"
            self.fields["description"].label = "Description ()"
            self.fields[
                "title"
            ].help_text = "Give your review a clear, descriptive title"
            self.fields[
                "description"
            ].help_text = "Add any additional context or objectives"
        else:
            self.fields["description"].widget = forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                }
            )


class SessionCreateForm(SessionForm):
    """Session creation form with placeholders and help text."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, mode="create", **kwargs)


class SessionEditForm(SessionForm):
    """Session editing form with minimal styling."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, mode="edit", **kwargs)


class ReviewConfigurationForm(forms.ModelForm):
    """
    Form for configuring review methodology settings with dynamic reviewer invitations.

    Features:
    - Dynamic reviewer invitation (up to 4 additional reviewers)
    - Conditional section visibility based on reviewer count
    - Reordered conflict resolution methods (Lead Arbitration first)
    - Dynamic consensus criteria labels based on reviewer count

    The form processes invited reviewers as JSON data submitted from JavaScript,
    validates the configuration, and stores it in the ReviewConfiguration model.
    """

    # Hidden field to receive JSON data from JavaScript
    invited_reviewers_data = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
        help_text="JSON string of invited reviewers (populated by JavaScript)",
    )

    class Meta:
        model = ReviewConfiguration
        fields = [
            "min_reviewers_per_result",
            "conflict_resolution_method",
            "consensus_criteria",
            "designated_arbitrator_email",
            "designated_arbitrator_name",
        ]

        widgets = {
            "min_reviewers_per_result": forms.Select(
                attrs={
                    "class": "form-select",
                    "id": "id_min_reviewers_per_result",
                }
            ),
            "conflict_resolution_method": forms.RadioSelect(
                attrs={
                    "class": "form-check-input",
                    "data-toggle": "arbitrator-fields",
                }
            ),
            "consensus_criteria": forms.RadioSelect(
                attrs={
                    "class": "form-check-input",
                }
            ),
            "designated_arbitrator_email": forms.EmailInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g., james.wilson@uni.ac.uk",
                    "data-arbitrator-field": "true",
                }
            ),
            "designated_arbitrator_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g., Dr. James Wilson",
                    "data-arbitrator-field": "true",
                }
            ),
        }

        labels = {
            "min_reviewers_per_result": "Number of Reviewers Per Result",
            "conflict_resolution_method": "Conflict Resolution Method",
            "consensus_criteria": "Consensus Criteria",
            "designated_arbitrator_email": "Arbitrator Email",
            "designated_arbitrator_name": "Arbitrator Name",
        }

        help_texts = {
            "min_reviewers_per_result": "How many reviewers should independently screen each result?",
            "conflict_resolution_method": "How should conflicts between reviewers be resolved?",
            "consensus_criteria": "What defines agreement when reviewers vote?",
            "designated_arbitrator_email": "Email address of the designated arbitrator",
            "designated_arbitrator_name": "Full name of the designated arbitrator",
        }

    def __init__(self, *args, **kwargs) -> None:
        """Initialise form with organisation defaults if available."""
        self.session: SearchSession | None = kwargs.pop("session", None)
        super().__init__(*args, **kwargs)

        # Pre-populate with organisation defaults if creating new config
        # Note: UUID pk fields always have a value (default=uuid.uuid4), so
        # check _state.adding to detect truly unsaved instances
        if self.instance._state.adding and self.session and self.session.organisation:
            org_defaults = self.session.organisation.get_review_defaults()
            self.fields["min_reviewers_per_result"].initial = org_defaults.get(
                "min_reviewers_per_result", 2
            )
            self.fields["conflict_resolution_method"].initial = org_defaults.get(
                "conflict_resolution_method", "LEAD_ARBITRATION"
            )
            self.fields["consensus_criteria"].initial = org_defaults.get(
                "consensus_criteria", "MAJORITY"
            )

    def clean_invited_reviewers_data(self) -> list:
        """
        Parse and validate invited reviewers JSON data.

        Returns:
            list: Validated list of reviewer dicts with email, first_name, last_name

        Raises:
            ValidationError: If JSON invalid, max reviewers exceeded, or duplicate emails
        """
        data = self.cleaned_data.get("invited_reviewers_data", "")
        if not data or data.strip() == "":
            return []

        try:
            reviewers = json.loads(data)
        except json.JSONDecodeError:
            raise forms.ValidationError("Invalid reviewer data format")

        if not isinstance(reviewers, list):
            raise forms.ValidationError("Reviewer data must be a list")

        if len(reviewers) > MAX_REVIEWERS:
            raise forms.ValidationError(
                f"Maximum {MAX_REVIEWERS} additional reviewers allowed"
            )

        # Validate each reviewer has required fields
        emails_seen: set[str] = set()
        for idx, reviewer in enumerate(reviewers):
            if not isinstance(reviewer, dict):
                raise forms.ValidationError(f"Reviewer {idx + 1} must be an object")

            if "email" not in reviewer or not reviewer["email"]:
                raise forms.ValidationError(f"Reviewer {idx + 1} missing email address")
            if "first_name" not in reviewer or not reviewer["first_name"]:
                raise forms.ValidationError(f"Reviewer {idx + 1} missing first name")

            email_lower = reviewer["email"].lower()
            if email_lower in emails_seen:
                raise forms.ValidationError(
                    f"Duplicate email address: {reviewer['email']}"
                )
            emails_seen.add(email_lower)

            try:
                validate_email(reviewer["email"])
            except forms.ValidationError:
                raise forms.ValidationError(
                    f"Invalid email address: {reviewer['email']}"
                )

        return reviewers

    def clean(self) -> dict[str, object]:
        """
        Cross-field validation for form-specific concerns.

        Model-level validations (arbitrator requirements, unanimous/majority constraints)
        are handled by ReviewConfiguration.clean() which Django calls automatically.
        This method handles form-only concerns: reviewer count vs invited reviewers,
        and clearing arbitrator fields when not needed.
        """
        cleaned_data = super().clean()
        conflict_method = cleaned_data.get("conflict_resolution_method")
        min_reviewers = cleaned_data.get("min_reviewers_per_result")
        invited_reviewers = cleaned_data.get("invited_reviewers_data", [])

        # Validate min_reviewers doesn't exceed total available reviewers
        total_reviewers = 1 + len(invited_reviewers)
        if min_reviewers and min_reviewers > total_reviewers:
            self.add_error(
                "min_reviewers_per_result",
                f"Cannot require {min_reviewers} reviewers per result when only {total_reviewers} total reviewer(s) available",
            )

        # Reset conflict resolution to default when solo (no reviewers invited)
        # This prevents stale radio values from hidden sections causing validation errors
        if total_reviewers == 1:
            cleaned_data["conflict_resolution_method"] = "CONSENSUS"
            conflict_method = "CONSENSUS"

        # Clear arbitrator fields if not using designated arbitrator
        if conflict_method != "DESIGNATED_ARBITRATOR":
            cleaned_data["designated_arbitrator_email"] = ""
            cleaned_data["designated_arbitrator_name"] = ""

        return cleaned_data


class SessionCreateAndConfigForm(SessionForm):
    """
    Combined form for session creation with inline review configuration.

    Merges SessionCreateForm (title, description) with ReviewConfigurationForm
    fields so users complete both in a single step instead of being redirected
    to a separate setup page.

    Organisation assignment is deterministic: the ``organisation`` selector is
    only added (and rendered) when the user has more than one active
    membership. Single-org users are auto-assigned silently via
    ``single_organisation``; the view reads that attribute when the field is
    absent.
    """

    # Hidden field to receive JSON data from JavaScript (from ReviewConfigurationForm)
    invited_reviewers_data = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
        help_text="JSON string of invited reviewers (populated by JavaScript)",
    )

    # Review configuration fields (mirrored from ReviewConfigurationForm)
    min_reviewers_per_result = forms.IntegerField(
        required=False,
        widget=forms.Select(
            attrs={"class": "form-select", "id": "id_min_reviewers_per_result"},
            choices=[
                (1, "1 Reviewer (Single Screening)"),
                (2, "2 Reviewers (Dual Screening)"),
                (3, "3 Reviewers (Triple Screening)"),
                (4, "4 Reviewers (Multiple Screening)"),
            ],
        ),
        label="Number of Reviewers Per Result",
        help_text="How many reviewers should independently screen each result?",
    )

    conflict_resolution_method = forms.ChoiceField(
        required=False,
        widget=forms.RadioSelect(
            attrs={"class": "form-check-input", "data-toggle": "arbitrator-fields"}
        ),
        choices=ReviewConfiguration.RESOLUTION_METHOD_CHOICES,
        label="Conflict Resolution Method",
        help_text="How should conflicts between reviewers be resolved?",
    )

    consensus_criteria = forms.ChoiceField(
        required=False,
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
        choices=[
            ("MAJORITY", "Simple Majority (>50%)"),
            ("UNANIMOUS", "Unanimous Agreement (100%)"),
        ],
        label="Consensus Criteria",
        help_text="What defines agreement when reviewers vote?",
    )

    designated_arbitrator_email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "e.g., james.wilson@uni.ac.uk",
                "data-arbitrator-field": "true",
            }
        ),
        label="Arbitrator Email",
        help_text="Email address of the designated arbitrator",
    )

    designated_arbitrator_name = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "e.g., Dr. James Wilson",
                "data-arbitrator-field": "true",
            }
        ),
        label="Arbitrator Name",
        help_text="Full name of the designated arbitrator",
    )

    def __init__(self, *args, **kwargs) -> None:
        self.user = kwargs.pop("user", None)
        super().__init__(*args, mode="create", **kwargs)
        # Pre-populate with org defaults - will be set in view if session.org exists

        # Build the user's active-organisation choices. The selector is only
        # added when the user belongs to more than one active organisation;
        # single-org users are auto-assigned silently (see single_organisation).
        self.active_organisations = self._get_active_organisations()
        self.single_organisation = None

        org_count = len(self.active_organisations)
        if org_count > 1:
            self.fields["organisation"] = forms.ModelChoiceField(
                queryset=self.active_organisations,
                required=True,
                widget=forms.Select(
                    attrs={
                        "class": "form-select",
                        "id": "id_organisation",
                    }
                ),
                label="Organisation",
                help_text=(
                    "Choose which organisation this review belongs to. "
                    "You are an active member of more than one."
                ),
                empty_label="Select an organisation",
            )
        elif org_count == 1:
            self.single_organisation = self.active_organisations[0]

    def _get_active_organisations(self):
        """Return the organisations the user is an active member of."""
        if self.user is None:
            return Organisation.objects.none()

        return (
            Organisation.objects.filter(
                memberships__user=self.user,
                memberships__is_active=True,
            )
            .distinct()
            .order_by("name")
        )

    def clean_organisation(self):
        """Reject any organisation the user is not an active member of.

        The ModelChoiceField queryset already constrains valid choices, but
        this guard is explicit so a tampered POST can never assign a session to
        an organisation the user does not actively belong to.
        """
        organisation = self.cleaned_data.get("organisation")
        if organisation is None:
            return organisation

        if not OrganisationMembership.objects.filter(
            user=self.user,
            organisation=organisation,
            is_active=True,
        ).exists():
            raise forms.ValidationError(
                "You are not an active member of the selected organisation."
            )

        return organisation

    def clean_invited_reviewers_data(self) -> list:
        """Parse and validate invited reviewers JSON data."""
        data = self.cleaned_data.get("invited_reviewers_data", "")
        if not data or data.strip() == "":
            return []

        try:
            reviewers = json.loads(data)
        except json.JSONDecodeError:
            raise forms.ValidationError("Invalid reviewer data format")

        if not isinstance(reviewers, list):
            raise forms.ValidationError("Reviewer data must be a list")

        if len(reviewers) > MAX_REVIEWERS:
            raise forms.ValidationError(
                f"Maximum {MAX_REVIEWERS} additional reviewers allowed"
            )

        emails_seen: set[str] = set()
        for idx, reviewer in enumerate(reviewers):
            if not isinstance(reviewer, dict):
                raise forms.ValidationError(f"Reviewer {idx + 1} must be an object")
            if "email" not in reviewer or not reviewer["email"]:
                raise forms.ValidationError(f"Reviewer {idx + 1} missing email address")
            if "first_name" not in reviewer or not reviewer["first_name"]:
                raise forms.ValidationError(f"Reviewer {idx + 1} missing first name")

            email_lower = reviewer["email"].lower()
            if email_lower in emails_seen:
                raise forms.ValidationError(
                    f"Duplicate email address: {reviewer['email']}"
                )
            emails_seen.add(email_lower)

            try:
                validate_email(reviewer["email"])
            except forms.ValidationError:
                raise forms.ValidationError(
                    f"Invalid email address: {reviewer['email']}"
                )

        return reviewers

    def clean(self) -> dict[str, object]:
        """Cross-field validation for combined form."""
        cleaned_data = super().clean()
        conflict_method = cleaned_data.get("conflict_resolution_method")
        min_reviewers = cleaned_data.get("min_reviewers_per_result")
        invited_reviewers = cleaned_data.get("invited_reviewers_data", [])

        # Handle solo reviewer case (no invited reviewers)
        if not isinstance(invited_reviewers, list):
            invited_reviewers = []

        total_reviewers = 1 + len(invited_reviewers)

        # Validate min_reviewers doesn't exceed total available reviewers
        if min_reviewers and min_reviewers > total_reviewers:
            self.add_error(
                "min_reviewers_per_result",
                f"Cannot require {min_reviewers} reviewers per result when only {total_reviewers} total reviewer(s) available",
            )

        # Reset conflict resolution to default when solo (no reviewers invited)
        if total_reviewers == 1:
            cleaned_data["conflict_resolution_method"] = "CONSENSUS"
            conflict_method = "CONSENSUS"

        # Clear arbitrator fields if not using designated arbitrator
        if conflict_method != "DESIGNATED_ARBITRATOR":
            cleaned_data["designated_arbitrator_email"] = ""
            cleaned_data["designated_arbitrator_name"] = ""

        return cleaned_data
