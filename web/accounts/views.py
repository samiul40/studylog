import json
import zoneinfo
from datetime import timedelta

from allauth.account.internal.flows.email_verification import (
    send_verification_email_to_address,
)
from allauth.account.models import EmailAddress
from django.contrib import messages
from django.contrib.auth import get_user_model, login, update_session_auth_hash
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone as dj_timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.decorators.http import require_POST

from .forms import (
    AcceptTermsForm,
    ChangeEmailForm,
    ChangePasswordForm,
    ProfileUpdateForm,
    TimezoneForm,
)
from .models import UserProfile

User = get_user_model()

ACCOUNT_RETENTION_DAYS = 30


class Settings(LoginRequiredMixin, View):
    def _get_profile(self, user):
        profile, _ = UserProfile.objects.get_or_create(user=user)
        return profile

    def _pending_email(self, user):
        """An address the user has asked for but not yet confirmed."""
        return (
            EmailAddress.objects.filter(user=user, verified=False)
            .exclude(email__iexact=user.email or "")
            .first()
        )

    def get(self, request):
        profile = self._get_profile(request.user)
        return render(
            request,
            "accounts/settings.html",
            {
                "profile_form": ProfileUpdateForm(instance=request.user),
                "email_form": ChangeEmailForm(user=request.user),
                "timezone_form": TimezoneForm(instance=profile),
                "password_form": ChangePasswordForm(request.user),
                "pending_email": self._pending_email(request.user),
            },
        )

    def post(self, request):
        profile = self._get_profile(request.user)
        form_type = request.POST.get("form_type")

        profile_form = ProfileUpdateForm(instance=request.user)
        email_form = ChangeEmailForm(user=request.user)
        timezone_form = TimezoneForm(instance=profile)
        password_form = ChangePasswordForm(request.user)

        if form_type == "profile":
            profile_form = ProfileUpdateForm(request.POST, instance=request.user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Profile updated successfully.")
                return redirect("settings")

        elif form_type == "email":
            email_form = ChangeEmailForm(data=request.POST, user=request.user)
            if email_form.is_valid():
                # Stores the address as unverified and emails a confirmation.
                # User.email is untouched until allauth promotes it on confirm.
                email_form.save(request)
                messages.success(
                    request,
                    "Check your inbox — we've sent a link to confirm your new "
                    "email address. Your current address stays active until "
                    "you confirm.",
                )
                return redirect("settings")

        elif form_type == "email_resend":
            pending = self._pending_email(request.user)
            if pending:
                # allauth's own helper, so the resend is rate limited the same
                # way its email page is. Internal API, pinned allauth version.
                # It returns False when throttled — don't claim we sent one.
                if send_verification_email_to_address(request, pending):
                    messages.success(
                        request, f"We've sent another link to {pending.email}."
                    )
                else:
                    messages.warning(
                        request,
                        "We sent a link moments ago — check your inbox, or try "
                        "again shortly.",
                    )
            return redirect("settings")

        elif form_type == "email_cancel":
            pending = self._pending_email(request.user)
            if pending:
                # Safe to drop outright: it is neither verified nor primary, so
                # removing it just abandons the pending change.
                address = pending.email
                pending.delete()
                messages.success(request, f"Cancelled the change to {address}.")
            return redirect("settings")

        elif form_type == "timezone":
            timezone_form = TimezoneForm(request.POST, instance=profile)
            if timezone_form.is_valid():
                timezone_form.save()
                messages.success(request, "Timezone updated successfully.")
                return redirect("settings")

        elif form_type == "password":
            password_form = ChangePasswordForm(request.user, request.POST)
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash(request, password_form.user)
                messages.success(request, "Password changed successfully.")
                return redirect("settings")

        else:
            return redirect("settings")

        return render(
            request,
            "accounts/settings.html",
            {
                "profile_form": profile_form,
                "email_form": email_form,
                "timezone_form": timezone_form,
                "password_form": password_form,
                "pending_email": self._pending_email(request.user),
            },
        )


class DeleteAccountView(LoginRequiredMixin, View):
    def post(self, request):
        user = request.user
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.deletion_requested_at = dj_timezone.now()
        profile.save(update_fields=["deletion_requested_at"])
        user.is_active = False
        user.save(update_fields=["is_active"])
        auth_logout(request)
        messages.success(
            request,
            "Your account has been scheduled for deletion. "
            f"Your data will be retained for {ACCOUNT_RETENTION_DAYS} days "
            "in case you change your mind.",
        )
        return redirect("account_login")


class ReactivateAccountView(View):
    template = "accounts/reactivate.html"

    def get(self, request):
        return render(request, self.template)

    def post(self, request):
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return render(
                request,
                self.template,
                {"error": "No account found with that email address."},
            )

        if not user.check_password(password):
            return render(
                request,
                self.template,
                {"error": "Incorrect password."},
            )

        try:
            profile = user.profile
        except UserProfile.DoesNotExist:
            return render(
                request,
                self.template,
                {"error": "Account cannot be reactivated."},
            )

        if not profile.deletion_requested_at:
            return render(
                request,
                self.template,
                {"error": "This account is not scheduled for deletion."},
            )

        cutoff = profile.deletion_requested_at + timedelta(days=ACCOUNT_RETENTION_DAYS)
        if dj_timezone.now() > cutoff:
            return render(
                request,
                self.template,
                {"error": "expired"},
            )

        profile.deletion_requested_at = None
        profile.save(update_fields=["deletion_requested_at"])
        user.is_active = True
        user.save(update_fields=["is_active"])
        login(
            request,
            user,
            backend="allauth.account.auth_backends.AuthenticationBackend",
        )
        messages.success(request, "Welcome back! Your account has been reactivated.")
        return redirect("learning:dashboard")


@login_required
@require_POST
def set_timezone(request):
    try:
        data = json.loads(request.body)
        tz_name = data.get("timezone", "")
        zoneinfo.ZoneInfo(tz_name)  # raises if invalid
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        profile.timezone = tz_name
        profile.save(update_fields=["timezone"])
        return JsonResponse({"ok": True})
    except Exception:
        return JsonResponse({"ok": False}, status=400)


@require_POST
def cancel_social_signup(request):
    """
    Abandon a half-finished Google sign-up.

    Without this the pending identity stays in the session and is resurrected
    the next time the user visits the social signup page.
    """
    request.session.pop("socialaccount_sociallogin", None)
    return redirect("account_login")


class AcceptTermsView(LoginRequiredMixin, View):
    """
    Re-consent gate. TermsAcceptanceMiddleware sends users here when the terms
    they accepted no longer match the published version.
    """

    template = "account/accept_terms.html"

    def get_profile(self):
        profile, _ = UserProfile.objects.get_or_create(user=self.request.user)
        return profile

    def get_redirect_target(self):
        target = self.request.GET.get("next") or self.request.POST.get("next", "")
        if target and url_has_allowed_host_and_scheme(
            target, allowed_hosts={self.request.get_host()}
        ):
            return target
        return reverse("learning:dashboard")

    def get(self, request):
        profile = self.get_profile()
        return render(
            request,
            self.template,
            {
                "form": AcceptTermsForm(age_already_confirmed=profile.age_confirmed),
                "next": self.get_redirect_target(),
                "is_update": bool(profile.terms_version),
            },
        )

    def post(self, request):
        profile = self.get_profile()
        form = AcceptTermsForm(
            request.POST, age_already_confirmed=profile.age_confirmed
        )

        if not form.is_valid():
            return render(
                request,
                self.template,
                {
                    "form": form,
                    "next": self.get_redirect_target(),
                    "is_update": bool(profile.terms_version),
                },
            )

        form.record_acceptance(request.user)
        messages.success(request, "Thanks — you're all set.")
        return redirect(self.get_redirect_target())
