import zoneinfo
from urllib.parse import urlencode

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile


class TimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            try:
                timezone.activate(zoneinfo.ZoneInfo(profile.timezone or "UTC"))
            except (zoneinfo.ZoneInfoNotFoundError, KeyError):
                timezone.deactivate()
        else:
            timezone.deactivate()

        return self.get_response(request)


def _exempt_prefixes():
    """
    Paths a user must still reach before they have accepted.

    "/accounts/" is deliberately broad: it covers every allauth route (login,
    logout, signup, password reset, email confirmation), this app's settings,
    account deletion and reactivation, and set_timezone — which base.html
    fetches on every page load. It also holds the consent page itself, so a
    redirect loop is impossible by construction rather than by special case.
    """
    return (
        "/accounts/",
        "/" + settings.ADMIN_URL,
        reverse("terms"),
        reverse("privacy"),
        settings.STATIC_URL,
        settings.MEDIA_URL,
        "/robots.txt",
        "/sitemap.xml",
        "/__debug__/",
    )


class TermsAcceptanceMiddleware:
    """
    Hold signed-in users at the consent page until the terms they accepted
    match the published version. Bumping settings.TERMS_VERSION re-prompts
    everyone.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._needs_consent(request):
            url = reverse("accept_terms")
            query = urlencode({"next": request.get_full_path()})
            return redirect(f"{url}?{query}")

        return self.get_response(request)

    def _needs_consent(self, request):
        if not request.user.is_authenticated:
            return False

        if request.path.startswith(_exempt_prefixes()):
            return False

        # get_or_create, not user.profile — superusers made by createsuperuser
        # and users built in fixtures may have no profile row.
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        return profile.terms_version != settings.TERMS_VERSION
