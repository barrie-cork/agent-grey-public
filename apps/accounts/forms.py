import logging

from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import User

logger = logging.getLogger(__name__)


class SignUpForm(UserCreationForm):
    """Simplified signup form with email and password only. Username is auto-generated."""

    email = forms.EmailField(
        required=True,
        help_text="Required. Enter a valid email address.",
        widget=forms.EmailInput(
            attrs={"class": "form-control", "placeholder": "Email", "autofocus": True}
        ),
    )

    class Meta:
        model = User
        fields = ("email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].widget.attrs.update(
            {"class": "form-control", "placeholder": "Password"}
        )
        self.fields["password2"].widget.attrs.update(
            {"class": "form-control", "placeholder": "Confirm Password"}
        )

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if email and User.objects.filter(email=email).exists():
            raise forms.ValidationError("This email is already registered.")
        return email

    def save(self, commit=True):
        """Save user with auto-generated username from email prefix."""
        user = super().save(commit=False)
        email = self.cleaned_data["email"]

        # Auto-generate username from email prefix
        base_username = email.split("@")[0][:30]  # Max 30 chars from email prefix
        username = base_username
        counter = 1

        # Handle collisions by appending counter
        while User.objects.filter(username=username).exists():
            # Leave room for counter suffix
            username = f"{base_username[:25]}{counter}"
            counter += 1

        user.username = username
        if commit:
            user.save()
        return user


class ProfileForm(UserChangeForm):
    password = None  # Remove password field from profile form

    class Meta:
        model = User
        fields = ("email", "first_name", "last_name")
        widgets = {
            "email": forms.EmailInput(
                attrs={"class": "form-control", "placeholder": "Email"}
            ),
            "first_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "First Name"}
            ),
            "last_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Last Name"}
            ),
        }

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if (
            email
            and User.objects.exclude(pk=self.instance.pk).filter(email=email).exists()
        ):
            raise forms.ValidationError("This email is already registered.")
        return email


class CustomAuthenticationForm(forms.Form):
    """Email-only authentication form (does not inherit AuthenticationForm)."""

    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "Email",
                "autofocus": True,
            }
        ),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "Password"}
        )
    )

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def get_user(self):
        return self.user_cache

    def confirm_login_allowed(self, user):
        if not user.is_active:
            raise forms.ValidationError("This account is inactive.")

    def clean(self):
        email = self.cleaned_data.get("email")
        password = self.cleaned_data.get("password")

        if email and password:
            # Look up user by email and authenticate
            try:
                user = User.objects.get(email=email)
                self.user_cache = authenticate(
                    self.request, username=user.username, password=password
                )
            except User.DoesNotExist:
                self.user_cache = None

            if self.user_cache is None:
                raise forms.ValidationError(
                    "Invalid login credentials. Please try again.",
                    code="invalid_login",
                )

            self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data


class AdminUserCreationForm(UserCreationForm):
    """
    Custom user creation form for Django admin.
    Includes email (required) and organisation assignment.
    """

    email = forms.EmailField(
        required=True,
        help_text="Required. User's email address.",
    )

    organisation = forms.ModelChoiceField(
        queryset=None,  # Set in __init__
        required=False,
        help_text="Select existing organisation or create new below",
    )

    create_new_org = forms.BooleanField(
        required=False,
        label="Create new organisation",
        help_text="Check to create a new organisation for this user",
    )

    new_org_name = forms.CharField(
        required=False,
        max_length=100,
        help_text="Name for new organisation (required if creating new)",
    )

    default_role = forms.ChoiceField(
        required=True,
        help_text="User's role in the organisation",
    )

    class Meta:
        model = User
        fields = ("username", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Import here to avoid circular imports
        from apps.organisation.models import Organisation, OrganisationMembership

        # Set organisation queryset
        self.fields["organisation"].queryset = Organisation.objects.all()

        # Set role choices (excluding constants, just use tuples directly)
        self.fields["default_role"].choices = OrganisationMembership.ROLE_CHOICES
        self.fields["default_role"].initial = "REVIEWER"

    def clean_email(self):
        """Validate email uniqueness."""
        email = self.cleaned_data.get("email")
        if email and User.objects.filter(email=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email

    def clean(self):
        """Validate organisation selection."""
        cleaned_data = super().clean()
        create_new = cleaned_data.get("create_new_org")
        new_name = cleaned_data.get("new_org_name")
        organisation = cleaned_data.get("organisation")

        if create_new and not new_name:
            raise forms.ValidationError(
                {
                    "new_org_name": "Organisation name is required when creating new organisation"
                }
            )

        if not create_new and not organisation:
            raise forms.ValidationError(
                {"organisation": "Please select an organisation or create a new one"}
            )

        return cleaned_data
