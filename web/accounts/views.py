import json
import zoneinfo

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views import View
from django.views.decorators.http import require_POST

from .forms import ChangePasswordForm, ProfileUpdateForm, TimezoneForm
from .models import UserProfile


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
