from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView as BaseLoginView
from django.contrib.messages.views import SuccessMessageMixin
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import CreateView, TemplateView, UpdateView

from .forms import ProfileForm, SignUpForm
from .models import User


class SignUpView(CreateView):
    """User registration view with automatic login.

    Handles new user account creation using the custom User model
    with UUID primary keys. Automatically logs in the user after
    successful registration and redirects to create a new search session.
    """

    form_class = SignUpForm
    template_name = "accounts/signup.html"

    def get_success_url(self):
        """Redirect new users to create their first search session."""
        return reverse_lazy("review_manager:create_session")

    def form_valid(self, form):
        """Process valid form submission.

        Creates the user account and automatically logs them in
        to improve user experience.

        Args:
            form: Validated SignUpForm instance.

        Returns:
            HttpResponse: HTTP response redirecting to success URL.
        """
        response = super().form_valid(form)
        # Auto-login after successful signup
        # Set backend attribute on user (required when multiple backends are configured)
        # This is the same pattern Django uses after successful authenticate()
        self.object.backend = "django.contrib.auth.backends.ModelBackend"
        login(self.request, self.object)
        return response


class LoginView(BaseLoginView):
    """Custom login view with redirect to review manager dashboard.

    Extends Django's built-in LoginView to redirect users to the
    review manager dashboard after successful authentication, while
    preserving the 'next' parameter functionality for protected pages.

    Note: @ensure_csrf_cookie decorator ensures session cookie is created
    on GET request, which is required for CSRF validation on POST (Issue #33).
    """

    template_name = "accounts/login.html"

    @method_decorator(ensure_csrf_cookie)
    def dispatch(self, request, *args, **kwargs):
        """Ensure session cookie is created before rendering login form.

        Forces Django to create a session cookie on GET /accounts/login/,
        preventing CSRF validation failures on POST due to missing session.

        See: GitHub Issue #33 - E2E authentication failures
        """
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        """Determine redirect URL after successful login.

        Checks for 'next' parameter first to handle redirects from
        protected pages, otherwise redirects to review manager dashboard.
        Validates the 'next' URL to prevent open redirect attacks.

        Returns:
            str: URL to redirect to after login.
        """
        next_url = self.request.GET.get("next")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={self.request.get_host()},
            require_https=self.request.is_secure(),
        ):
            return next_url
        # Default to review manager dashboard
        return reverse_lazy("review_manager:dashboard")


class ProfileView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    """User profile management view.

    Allows authenticated users to view and update their profile
    information. Requires login and automatically restricts access
    to the current user's profile only.
    """

    model = User
    form_class = ProfileForm
    template_name = "accounts/profile.html"
    success_url = reverse_lazy("accounts:profile")
    success_message = "Profile updated successfully!"

    def get_object(self, queryset=None):
        """Return the current authenticated user."""
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["memberships"] = (
            self.request.user.organisation_memberships.select_related("organisation")
            .filter(is_active=True)
            .order_by("organisation__name")
        )
        return context


class ExtensionTokenView(LoginRequiredMixin, TemplateView):
    """
    Manage per-device Knox tokens for the browser extension.

    GET  – list existing tokens and display the issue form.
    POST – issue a new token (name in body) or revoke one (token_key in body + _method=DELETE).
    """

    template_name = "accounts/extension_tokens.html"

    def get_context_data(self, **kwargs: object) -> dict:
        from knox.models import AuthToken

        context = super().get_context_data(**kwargs)
        context["tokens"] = AuthToken.objects.filter(user=self.request.user).order_by(
            "-created"
        )
        return context

    def post(self, request, *args: object, **kwargs: object) -> JsonResponse:
        from knox.models import AuthToken

        action = request.POST.get("action", "issue")

        if action == "revoke":
            token_pk = request.POST.get("token_pk", "").strip()
            deleted, _ = AuthToken.objects.filter(
                user=request.user, pk=token_pk
            ).delete()
            return JsonResponse({"revoked": bool(deleted)})

        # Issue a new token
        name = (
            request.POST.get("name", "Extension device").strip()[:64]
            or "Extension device"
        )
        # knox's manager returns (instance, token); django-types stubs say AuthToken
        instance, token = AuthToken.objects.create(user=request.user)  # type: ignore[misc]
        return JsonResponse({"token": token, "name": name, "pk": instance.pk})
