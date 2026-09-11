import pytest
from allauth.socialaccount.models import SocialApp
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.urls import reverse

from accounts.forms import StudyLogSignupForm

pytestmark = pytest.mark.django_db

URL = reverse("account_signup")


@pytest.fixture(autouse=True)
def google_social_app():
    """The signup template calls {% provider_login_url 'google' %}, which raises
    SocialApp.DoesNotExist unless a provider row exists, so the page cannot
    render at all without one."""
    app = SocialApp.objects.create(
        provider="google", name="Google", client_id="test-id", secret="test-secret"
    )
    app.sites.add(Site.objects.get_current())
    return app


VALID = {
    "username": "newbie",
    "email": "newbie@example.com",
    "password1": "sup3rSecret!23",
    "password2": "sup3rSecret!23",
    "age_confirmed": "on",
    "accept_terms": "on",
}

User = get_user_model()


def test_signup_records_acceptance_on_the_profile(client):
    response = client.post(URL, VALID)

    assert response.status_code == 302

    profile = User.objects.get(username="newbie").profile

    assert profile.terms_accepted is True
    assert profile.terms_accepted_at is not None
    assert profile.terms_version == "1.0"

    assert profile.privacy_accepted is True
    assert profile.privacy_accepted_at is not None
    assert profile.privacy_version == "1.0"

    assert profile.age_confirmed is True
    assert profile.age_confirmed_at is not None


def test_acceptance_records_the_configured_versions(client, settings):
    settings.TERMS_VERSION = "2.0"
    settings.PRIVACY_VERSION = "3.1"

    client.post(URL, VALID)

    profile = User.objects.get(username="newbie").profile

    assert profile.terms_version == "2.0"
    assert profile.privacy_version == "3.1"


@pytest.mark.parametrize("missing", ["age_confirmed", "accept_terms"])
def test_signup_is_rejected_without_each_checkbox(client, missing):
    data = {key: value for key, value in VALID.items() if key != missing}

    response = client.post(URL, data)

    assert response.status_code == 200
    assert missing in response.context["form"].errors
    assert not User.objects.filter(username="newbie").exists()


def test_rejected_signup_keeps_what_the_user_typed(client):
    data = {key: value for key, value in VALID.items() if key != "accept_terms"}

    response = client.post(URL, data)

    form = response.context["form"]

    assert form["username"].value() == "newbie"
    assert form["email"].value() == "newbie@example.com"


def test_both_checkboxes_are_required_on_the_form():
    form = StudyLogSignupForm()

    assert form.fields["age_confirmed"].required is True
    assert form.fields["accept_terms"].required is True


def test_signup_page_renders_both_checkboxes(client):
    content = client.get(URL).content.decode()

    assert 'name="age_confirmed"' in content
    assert 'name="accept_terms"' in content
