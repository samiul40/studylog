import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from accounts.forms import TimezoneForm
from accounts.middleware import TimezoneMiddleware
from accounts.models import UserProfile

User = get_user_model()

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_middleware():
    return TimezoneMiddleware(get_response=lambda r: None)


def _request_for(user, path="/"):
    req = RequestFactory().get(path)
    req.user = user
    return req


# ---------------------------------------------------------------------------
# TimezoneMiddleware
# ---------------------------------------------------------------------------


class TestTimezoneMiddleware:
    def test_authenticated_user_activates_their_timezone(self, user):
        UserProfile.objects.filter(user=user).update(timezone="Europe/London")
        _make_middleware()(_request_for(user))
        assert timezone.get_current_timezone_name() == "Europe/London"

    def test_authenticated_user_no_profile_creates_one_and_uses_utc(self, user):
        UserProfile.objects.filter(user=user).delete()
        _make_middleware()(_request_for(user))
        profile = UserProfile.objects.get(user=user)
        assert profile.timezone == "UTC"
        assert timezone.get_current_timezone_name() == "UTC"

    def test_unauthenticated_user_deactivates_timezone(self):
        timezone.activate("Europe/London")
        req = RequestFactory().get("/")
        req.user = AnonymousUser()
        _make_middleware()(req)
        assert timezone.get_current_timezone_name() == "UTC"

    def test_invalid_timezone_in_profile_deactivates_gracefully(self, user):
        UserProfile.objects.filter(user=user).update(timezone="Not/ATimezone")
        _make_middleware()(_request_for(user))
        assert timezone.get_current_timezone_name() == "UTC"

    @pytest.mark.parametrize(
        "tz_name",
        [
            "America/New_York",
            "Asia/Tokyo",
            "Australia/Sydney",
            "Europe/Paris",
            "UTC",
        ],
    )
    def test_activates_timezone_correctly(self, user, tz_name):
        UserProfile.objects.filter(user=user).update(timezone=tz_name)
        _make_middleware()(_request_for(user))
        assert timezone.get_current_timezone_name() == tz_name


# ---------------------------------------------------------------------------
# set_timezone view
# ---------------------------------------------------------------------------


class TestSetTimezoneView:
    def _post(self, client, tz_name):
        return client.post(
            reverse("set_timezone"),
            data=json.dumps({"timezone": tz_name}),
            content_type="application/json",
        )

    def test_valid_timezone_saves_and_returns_ok(self, client_logged_in, user):
        res = self._post(client_logged_in, "Europe/London")
        assert res.status_code == 200
        assert res.json() == {"ok": True}
        assert UserProfile.objects.get(user=user).timezone == "Europe/London"

    def test_invalid_timezone_returns_400(self, client_logged_in):
        res = self._post(client_logged_in, "Not/ATimezone")
        assert res.status_code == 400
        assert res.json() == {"ok": False}

    def test_unauthenticated_redirects_to_login(self, client):
        res = self._post(client, "Europe/London")
        assert res.status_code == 302
        assert reverse("account_login") in res.url

    def test_get_request_not_allowed(self, client_logged_in):
        res = client_logged_in.get(reverse("set_timezone"))
        assert res.status_code == 405

    def test_creates_profile_if_missing(self, client_logged_in, user):
        UserProfile.objects.filter(user=user).delete()
        res = self._post(client_logged_in, "Asia/Tokyo")
        assert res.status_code == 200
        assert UserProfile.objects.get(user=user).timezone == "Asia/Tokyo"


# ---------------------------------------------------------------------------
# UserProfile signal
# ---------------------------------------------------------------------------


class TestUserProfileSignal:
    def test_new_user_gets_profile_with_utc(self):
        user = User.objects.create_user(username="newuser", password="pass")
        profile = UserProfile.objects.get(user=user)
        assert profile.timezone == "UTC"

    def test_saving_existing_user_does_not_duplicate_profile(self, user):
        user.first_name = "Updated"
        user.save()
        assert UserProfile.objects.filter(user=user).count() == 1


# ---------------------------------------------------------------------------
# TimezoneForm
# ---------------------------------------------------------------------------


class TestTimezoneForm:
    @pytest.mark.parametrize(
        "tz_name",
        [
            "Europe/London",
            "America/New_York",
            "Asia/Tokyo",
            "UTC",
        ],
    )
    def test_valid_timezone_is_accepted(self, tz_name):
        assert TimezoneForm(data={"timezone": tz_name}).is_valid()

    @pytest.mark.parametrize(
        "tz_name",
        [
            "Not/ATimezone",
            "random",
            "",
        ],
    )
    def test_invalid_timezone_is_rejected(self, tz_name):
        assert not TimezoneForm(data={"timezone": tz_name}).is_valid()


# ---------------------------------------------------------------------------
# Settings page — timezone form_type
# ---------------------------------------------------------------------------


class TestSettingsTimezoneForm:
    def test_timezone_update_saves_and_redirects(self, client_logged_in, user):
        url = reverse("settings")
        res = client_logged_in.post(
            url, {"form_type": "timezone", "timezone": "America/New_York"}
        )
        assert res.status_code == 302
        assert res.url == url
        assert UserProfile.objects.get(user=user).timezone == "America/New_York"

    def test_invalid_timezone_rerenders_form(self, client_logged_in):
        url = reverse("settings")
        res = client_logged_in.post(
            url, {"form_type": "timezone", "timezone": "Bad/Zone"}
        )
        assert res.status_code == 200
