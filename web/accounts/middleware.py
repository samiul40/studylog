import zoneinfo

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
