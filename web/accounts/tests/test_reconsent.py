import pytest
from django.urls import reverse
from model_bakery import baker

from accounts.models import UserProfile

pytestmark = pytest.mark.django_db

ACCEPT_URL = reverse("accept_terms")
GATED_URL = reverse("learning:dashboard")


@pytest.fixture
def unconsented(client):
    """A user from before consent was captured: no version, no age tick."""
    user = baker.make("auth.User", is_superuser=True, is_staff=True)
    client.force_login(user)
    return user


def test_gated_page_redirects_to_the_consent_screen(client, unconsented):
    response = client.get(GATED_URL)

    assert response.status_code == 302
    assert response.url.startswith(ACCEPT_URL)


def test_the_original_destination_is_preserved(client, unconsented):
    response = client.get(GATED_URL)

    assert f"next={GATED_URL}" in response.url.replace("%2F", "/")


def test_a_consented_user_passes_straight_through(client_logged_in):
    response = client_logged_in.get(GATED_URL)

    assert response.status_code == 200


def test_a_stale_version_is_gated_again(client_logged_in, user, settings):
    settings.TERMS_VERSION = "9.9"

    response = client_logged_in.get(GATED_URL)

    assert response.status_code == 302
    assert response.url.startswith(ACCEPT_URL)


def test_anonymous_users_are_untouched(client):
    response = client.get(GATED_URL)

    assert ACCEPT_URL not in response.url


@pytest.mark.parametrize(
    "url_name",
    ["terms", "privacy", "accept_terms", "settings", "account_logout"],
)
def test_exempt_pages_stay_reachable_while_gated(client, unconsented, url_name):
    """Chiefly terms and privacy: gating the documents a user must read in
    order to consent would trap them with no way out."""
    response = client.get(reverse(url_name))

    assert response.status_code == 200


def test_the_consent_page_does_not_redirect_to_itself(client, unconsented):
    response = client.get(ACCEPT_URL)

    assert response.status_code == 200


def test_accepting_records_consent_and_returns_the_user(client, unconsented):
    response = client.post(
        ACCEPT_URL,
        {"age_confirmed": "on", "accept_terms": "on", "next": GATED_URL},
    )

    assert response.status_code == 302
    assert response.url == GATED_URL

    profile = UserProfile.objects.get(user=unconsented)
    assert profile.terms_accepted is True
    assert profile.terms_accepted_at is not None
    assert profile.terms_version == "1.0"
    assert profile.privacy_accepted is True
    assert profile.privacy_version == "1.0"
    assert profile.age_confirmed is True
    assert profile.age_confirmed_at is not None


def test_the_app_is_usable_once_accepted(client, unconsented):
    client.post(ACCEPT_URL, {"age_confirmed": "on", "accept_terms": "on"})

    response = client.get(GATED_URL)

    assert response.status_code == 200


@pytest.mark.parametrize("missing", ["age_confirmed", "accept_terms"])
def test_both_boxes_are_required(client, unconsented, missing):
    data = {"age_confirmed": "on", "accept_terms": "on", "next": GATED_URL}
    del data[missing]

    response = client.post(ACCEPT_URL, data)

    assert response.status_code == 200
    assert missing in response.context["form"].errors
    assert UserProfile.objects.get(user=unconsented).terms_accepted is False


def test_an_external_next_is_ignored(client, unconsented):
    response = client.post(
        ACCEPT_URL,
        {
            "age_confirmed": "on",
            "accept_terms": "on",
            "next": "https://evil.example.com/steal",
        },
    )

    assert response.url == GATED_URL


def test_age_is_not_asked_again_once_confirmed(client, user, settings):
    """A version-only bump should ask about the terms, not the user's age."""
    client.force_login(user)
    settings.TERMS_VERSION = "2.0"

    response = client.get(ACCEPT_URL)

    assert "age_confirmed" not in response.context["form"].fields
    assert "accept_terms" in response.context["form"].fields


def test_reaccepting_keeps_the_original_age_timestamp(client, user, settings):
    client.force_login(user)
    original = user.profile.age_confirmed_at
    settings.TERMS_VERSION = "2.0"

    client.post(ACCEPT_URL, {"accept_terms": "on"})

    profile = UserProfile.objects.get(user=user)
    assert profile.age_confirmed_at == original
    assert profile.terms_version == "2.0"


def test_a_user_with_no_profile_does_not_error(client):
    """createsuperuser and fixtures can produce users with no profile row."""
    user = baker.make("auth.User")
    UserProfile.objects.filter(user=user).delete()
    client.force_login(user)

    response = client.get(GATED_URL)

    assert response.status_code == 302
    assert response.url.startswith(ACCEPT_URL)
