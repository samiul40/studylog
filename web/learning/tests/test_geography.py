import pytest
from allauth.account.models import EmailAddress
from django.utils import timezone
from model_bakery import baker

from accounts.models import UserProfile
from learning.services.geography import COUNTRY_NAME, ZONE_COUNTRY, get_user_countries

pytestmark = pytest.mark.django_db


def _member(tz, verified=True, **profile):
    user = baker.make("auth.User")
    EmailAddress.objects.create(
        user=user, email=f"{user.username}@example.com", verified=verified
    )
    UserProfile.objects.filter(user=user).update(timezone=tz, **profile)
    return user


# ---------------------------------------------------------------------------
# ZONE_COUNTRY
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tz, code",
    [
        ("Asia/Dhaka", "BD"),
        ("Europe/London", "GB"),
        ("America/Argentina/Buenos_Aires", "AR"),
    ],
)
def test_a_current_zone_maps_to_its_country(tz, code):
    assert ZONE_COUNTRY.get(tz) == code


@pytest.mark.parametrize(
    "tz, code",
    [("Asia/Calcutta", "IN"), ("Europe/Kiev", "UA"), ("America/Buenos_Aires", "AR")],
)
def test_a_legacy_browser_zone_maps_to_its_country(tz, code):
    assert ZONE_COUNTRY.get(tz) == code


@pytest.mark.parametrize("tz", ["UTC", "Etc/GMT+5", "Not/AZone", ""])
def test_a_zone_with_no_country_maps_to_none(tz):
    assert ZONE_COUNTRY.get(tz) is None


def test_country_names_come_from_iso3166():
    assert COUNTRY_NAME["BD"] == "Bangladesh"


# ---------------------------------------------------------------------------
# get_user_countries
# ---------------------------------------------------------------------------


def test_users_are_counted_per_country_most_first():
    _member("Asia/Dhaka")
    _member("America/New_York")
    _member("America/Chicago")

    rows, unknown = get_user_countries()

    assert rows == [
        {"code": "US", "name": "United States", "users": 2},
        {"code": "BD", "name": "Bangladesh", "users": 1},
    ]
    assert unknown == 0


def test_users_without_a_country_zone_are_counted_as_unknown():
    _member("UTC")
    _member("Asia/Dhaka")

    rows, unknown = get_user_countries()

    assert [r["code"] for r in rows] == ["BD"]
    assert unknown == 1


def test_unverified_accounts_are_not_counted():
    _member("Asia/Dhaka", verified=False)
    baker.make("auth.User")  # no email address at all

    assert get_user_countries() == ([], 0)


def test_accounts_pending_deletion_are_not_counted():
    _member("Asia/Dhaka", deletion_requested_at=timezone.now())

    assert get_user_countries() == ([], 0)


def test_a_user_with_two_verified_addresses_is_counted_once():
    user = _member("Asia/Dhaka")
    EmailAddress.objects.create(user=user, email="second@example.com", verified=True)

    rows, _ = get_user_countries()

    assert rows[0]["users"] == 1
