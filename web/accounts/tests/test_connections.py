import pytest
from allauth.socialaccount.models import SocialAccount, SocialApp
from django.contrib.sites.models import Site
from django.urls import reverse

pytestmark = pytest.mark.django_db

URL = reverse("socialaccount_connections")


@pytest.fixture(autouse=True)
def google_app():
    app = SocialApp.objects.create(
        provider="google", name="Google", client_id="x", secret="y"
    )
    app.sites.add(Site.objects.get_current())
    return app


def test_the_add_card_shows_when_nothing_is_linked(client_logged_in):
    content = client_logged_in.get(URL).content.decode()

    assert "Add a connection" in content
    assert "Nothing linked" in content


def test_the_add_card_is_hidden_once_google_is_linked(client_logged_in, user):
    """Google is the only provider, so once it's connected there is nothing
    left to add and the card is just noise."""
    SocialAccount.objects.create(
        provider="google", uid="1", user=user, extra_data={"email": "a@b.com"}
    )

    content = client_logged_in.get(URL).content.decode()

    assert "Add a connection" not in content
    assert "Disconnect" in content


def test_the_page_uses_the_app_layout(client_logged_in):
    content = client_logged_in.get(URL).content.decode()

    assert "settings-wrap" in content
    assert "Connected accounts" in content


def test_no_unrendered_template_syntax_leaks_into_the_page(client_logged_in, user):
    """Django's {# #} comments cannot span lines — a wrapped one silently
    renders as visible text rather than being stripped."""
    SocialAccount.objects.create(
        provider="google", uid="2", user=user, extra_data={"email": "a@b.com"}
    )

    content = client_logged_in.get(URL).content.decode()

    assert "{#" not in content
    assert "{%" not in content
