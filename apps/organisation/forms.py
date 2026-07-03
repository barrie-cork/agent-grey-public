"""Forms for organisation management."""

from django import forms
from django.utils.text import slugify

from .models import Organisation


class CreateOrganisationForm(forms.ModelForm):
    """Form for creating a new organisation.

    Auto-generates a unique slug from the organisation name.
    """

    class Meta:
        model = Organisation
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "placeholder": "e.g. University of Edinburgh Library",
                    "data-testid": "input-org-name",
                }
            ),
        }

    def clean_name(self) -> str:
        name = self.cleaned_data["name"].strip()
        if len(name) < 2:
            raise forms.ValidationError(
                "Organisation name must be at least 2 characters."
            )
        return name

    def save(self, commit: bool = True) -> Organisation:
        """Save with auto-generated unique slug."""
        instance = super().save(commit=False)
        base_slug = slugify(instance.name)
        slug = base_slug
        counter = 1
        while Organisation.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        instance.slug = slug
        if commit:
            instance.save()
        return instance
