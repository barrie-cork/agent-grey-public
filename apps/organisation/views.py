"""
Views for organisation management.

Implements:
- Organisation dashboard
- User invitation management
- Invitation acceptance
"""

import logging
from smtplib import SMTPException

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView

from .forms import CreateOrganisationForm
from .models import Organisation, OrganisationInvitation, OrganisationMembership
from .services import InvitationService, OrganisationService

logger = logging.getLogger(__name__)


class OrganisationDashboardView(LoginRequiredMixin, DetailView):
    """
    Organisation dashboard view showing org-wide metrics.

    Accessible by: active organisation members.
    Invite form shown only to members with can_manage_users permission.
    """

    model = Organisation
    template_name = "organisation/dashboard.html"
    context_object_name = "organisation"
    pk_url_kwarg = "org_id"

    def get_object(self, queryset=None):
        """Verify user is an active member of the organisation."""
        org = super().get_object(queryset)
        try:
            self.membership = OrganisationMembership.objects.get(
                user=self.request.user, organisation=org, is_active=True
            )
        except OrganisationMembership.DoesNotExist:
            raise PermissionDenied("You are not a member of this organisation")
        return org

    def get_context_data(self, **kwargs):
        """Add organisation metrics, membership, and invitations to context."""
        context = super().get_context_data(**kwargs)

        # Get organisation metrics using service
        org_service = OrganisationService()
        context["metrics"] = org_service.get_org_metrics(self.object)
        context["quality_metrics"] = org_service.get_quality_metrics(self.object)

        # Membership info for permission-gated UI
        context["membership"] = self.membership
        context["can_invite"] = self.membership.can_manage_users

        # Invite form data (only fetched if user can invite)
        if self.membership.can_manage_users:
            context["role_choices"] = OrganisationMembership.ROLE_CHOICES
            context["pending_invitations"] = (
                OrganisationInvitation.objects.filter(
                    organisation=self.object,
                    status=OrganisationInvitation.STATUS_PENDING,
                )
                .select_related("invited_by")
                .order_by("-created_at")
            )

        # Members list
        context["members"] = (
            OrganisationMembership.objects.filter(
                organisation=self.object, is_active=True
            )
            .select_related("user")
            .order_by("role", "joined_at")
        )

        return context


class InviteUserView(LoginRequiredMixin, View):
    """
    Create and send user invitation.

    Accessible by: Information Specialists only (with can_manage_users permission)
    """

    def post(self, request, org_id):
        """Handle invitation creation with security checks."""
        org = get_object_or_404(Organisation, id=org_id)

        # SECURITY FIX: Verify user is member of organisation
        try:
            membership = OrganisationMembership.objects.get(
                user=request.user, organisation=org, is_active=True
            )
        except OrganisationMembership.DoesNotExist:
            raise PermissionDenied("You are not a member of this organisation")

        # SECURITY FIX: Verify user has permission to invite (Information Specialist)
        if not membership.can_manage_users:
            raise PermissionDenied(
                "You do not have permission to invite users. "
                "Only Information Specialists can send organisation invitations."
            )

        # Get form data (rate limiting is handled by InvitationService)
        email = request.POST.get("email")
        role = request.POST.get("role")
        name = request.POST.get("name", "")

        if not email or not role:
            return JsonResponse({"error": "Email and role are required"}, status=400)

        try:
            # Create invitation using service (now secured)
            invitation_service = InvitationService()
            invitation = invitation_service.create_invitation(
                organisation=org,
                email=email,
                role=role,
                invited_by=request.user,
                name=name,
                request=request,
            )

            # If coming from a form submission (not AJAX), redirect with success message
            if request.headers.get("X-Requested-With") != "XMLHttpRequest":
                messages.success(request, f"Invitation sent to {email}")
                return redirect("organisation:dashboard", org_id=org.id)

            return JsonResponse(
                {
                    "success": True,
                    "invitation_id": str(invitation.id),
                    "message": f"Invitation sent to {email}",
                }
            )

        except ValidationError as e:
            # Rate limit errors from InvitationService should return 429
            error_msg = str(e.message if hasattr(e, "message") else e)
            if "rate limit" in error_msg.lower():
                return JsonResponse({"error": error_msg}, status=429)
            if request.headers.get("X-Requested-With") != "XMLHttpRequest":
                messages.error(request, error_msg)
                return redirect("organisation:dashboard", org_id=org.id)
            return JsonResponse({"error": error_msg}, status=400)
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)
        except (DatabaseError, SMTPException, OSError):
            logger.exception("Unexpected error creating invitation for org %s", org_id)
            return JsonResponse({"error": "Failed to create invitation"}, status=500)


class AcceptInvitationView(View):
    """
    Accept an organisation invitation via magic link.

    Public view - no login required (but user must exist).
    """

    def get(self, request, token):
        """Display invitation acceptance page."""
        # Find invitation
        invitation = get_object_or_404(OrganisationInvitation, token=token)

        # Check if valid
        if not invitation.is_valid():
            context = {
                "error": f"Invitation {invitation.status.lower()}",
                "invitation": invitation,
            }
            return render(request, "organisation/invitation_invalid.html", context)

        context = {
            "invitation": invitation,
        }
        return render(request, "organisation/invitation_accept.html", context)

    def post(self, request, token):
        """Process invitation acceptance."""
        if not request.user.is_authenticated:
            # Redirect to login with next parameter
            return redirect(f"/accounts/login/?next=/organisation/invitation/{token}/")

        # Accept invitation using service
        invitation_service = InvitationService()
        success, error = invitation_service.accept_invitation(token, request.user)

        if success:
            # Redirect to organisation dashboard or home
            return redirect("/")  # Will be updated to org dashboard in Phase 2
        else:
            context = {
                "error": error,
            }
            return render(request, "organisation/invitation_error.html", context)


class OrganisationMetricsAPIView(LoginRequiredMixin, View):
    """
    API endpoint for organisation metrics (JSON).

    Used by dashboard for real-time updates.
    """

    def get(self, request, org_id):
        """Return organisation metrics as JSON."""
        org = get_object_or_404(Organisation, id=org_id)

        # Get metrics using service
        org_service = OrganisationService()
        metrics = org_service.get_org_metrics(org)

        return JsonResponse(metrics)


class CreateOrganisationView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    """Create a new organisation.

    Any authenticated user can create an organisation. The creator becomes
    the INFORMATION_SPECIALIST (owner) with full management permissions.
    """

    form_class = CreateOrganisationForm
    template_name = "organisation/create.html"
    success_message = "Organisation '%(name)s' created successfully!"

    def get_success_url(self) -> str:
        return reverse_lazy("accounts:profile")

    def form_valid(self, form):
        response = super().form_valid(form)
        # Create membership with IS role for the creator
        OrganisationMembership.objects.create(
            organisation=self.object,
            user=self.request.user,
            role=OrganisationMembership.ROLE_INFORMATION_SPECIALIST,
            is_active=True,
        )
        logger.info(
            "User %s created organisation '%s'",
            self.request.user.username,
            self.object.name,
        )
        return response
