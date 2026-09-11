import pytest
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.auth import get_user_model
from django.urls import reverse
from model_bakery import baker

from accounts.forms import StudyLogSocialSignupForm

pytestmark = pytest.mark.django_db

User = get_user_model()

CANCEL_URL = reverse("cancel_social_signup")


def make_sociallogin(email="samiul@example.com", first_name="Samiul"):
    user = User(email=email, first_name=first_name, last_name="Amin", username="")
    account = SocialAccount(
        provider="google",
        uid="google-uid-1",
        extra_data={"email": email, "given_name": first_name},
    )
    return SocialLogin(user=user, account=account)


def build_form(**overrides):
    data = {
        "email": "samiul@example.com",
        "username": "",
        "age_confirmed": "on",
        "accept_terms": "on",
    }
    data.update(overrides)
    return StudyLogSocialSignupForm(data, sociallogin=make_sociallogin())


def test_username_is_prefilled_from_the_google_account():
    form = StudyLogSocialSignupForm(sociallogin=make_sociallogin())

    assert form.suggested_username == "samiul"
    assert form.initial["username"] == "samiul"


def test_blank_username_is_allowed():
    form = build_form(username="")

    assert form.is_valid(), form.errors


@pytest.mark.parametrize(
    "username",
    ["ab", "x" * 21, "has-a-dash", "has a space", "hasa.dot", "emoji🎉"],
)
def test_badly_formatted_usernames_are_rejected(username):
    form = build_form(username=username)

    assert not form.is_valid()
    assert form.errors["username"] == ["Use 3–20 letters, numbers or underscores."]


@pytest.mark.parametrize("username", ["sam_123", "ABC", "x" * 20])
def test_well_formatted_usernames_are_accepted(username):
    form = build_form(username=username)

    assert form.is_valid(), form.errors


def test_taken_usernames_are_rejected():
    baker.make(User, username="taken_name")

    form = build_form(username="taken_name")

    assert not form.is_valid()
    assert form.errors["username"] == ["That username is already taken."]


def test_taken_usernames_are_rejected_regardless_of_case():
    baker.make(User, username="TakenName")

    form = build_form(username="takenname")

    assert not form.is_valid()
    assert "username" in form.errors


@pytest.mark.parametrize("missing", ["age_confirmed", "accept_terms"])
def test_consent_is_required(missing):
    form = build_form(**{missing: ""})

    assert not form.is_valid()
    assert missing in form.errors


def test_a_disabled_button_is_not_trusted():
    """The submit button is gated client side; the server must gate too."""
    form = build_form(age_confirmed="", accept_terms="", username="bad-name")

    assert not form.is_valid()
    assert set(form.errors) == {"age_confirmed", "accept_terms", "username"}


def test_cancel_clears_the_pending_google_identity(client):
    session = client.session
    session["socialaccount_sociallogin"] = {"some": "payload"}
    session.save()

    response = client.post(CANCEL_URL)

    assert response.status_code == 302
    assert response.url == reverse("account_login")
    assert "socialaccount_sociallogin" not in client.session


def test_cancel_is_harmless_when_nothing_is_pending(client):
    response = client.post(CANCEL_URL)

    assert response.status_code == 302


def test_cancel_rejects_get(client):
    """POST only, so a link prefetch can't drop a legitimate pending signup."""
    response = client.get(CANCEL_URL)

    assert response.status_code == 405
