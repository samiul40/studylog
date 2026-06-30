import json
import zoneinfo
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model, login, update_session_auth_hash
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone as dj_timezone
from django.views import View
from django.views.decorators.http import require_POST

from .forms import ChangePasswordForm, ProfileUpdateForm, TimezoneForm
from .models import UserProfile

User = get_user_model()

ACCOUNT_RETENTION_DAYS = 30


class Settings(LoginRequiredMixin, View):
    def _get_profile(self, user):
        profile, _ = UserProfile.objects.get_or_create(user=user)
        return profile

    def get(self, request):
        profile = self._get_profile(request.user)
        return render(
            request,
            "accounts/settings.html",
            {
                "profile_form": ProfileUpdateForm(instance=request.user),
                "timezone_form": TimezoneForm(instance=profile),
                "password_form": ChangePasswordForm(request.user),
            },
        )

    def post(self, request):
        profile = self._get_profile(request.user)
        form_type = request.POST.get("form_type")

        if form_type == "profile":
            profile_form = ProfileUpdateForm(request.POST, instance=request.user)
            timezone_form = TimezoneForm(instance=profile)
            password_form = ChangePasswordForm(request.user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Profile updated successfully.")
                return redirect("settings")

        elif form_type == "timezone":
            profile_form = ProfileUpdateForm(instance=request.user)
            timezone_form = TimezoneForm(request.POST, instance=profile)
            password_form = ChangePasswordForm(request.user)
            if timezone_form.is_valid():
                timezone_form.save()
                messages.success(request, "Timezone updated successfully.")
                return redirect("settings")

        elif form_type == "password":
            profile_form = ProfileUpdateForm(instance=request.user)
            timezone_form = TimezoneForm(instance=profile)
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
                "timezone_form": timezone_form,
                "password_form": password_form,
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
