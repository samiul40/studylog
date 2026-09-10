from unittest.mock import patch

import pytest
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.urls import reverse
from model_bakery import baker

from learning.models import FeatureRequest

pytestmark = pytest.mark.django_db

URL = reverse("feature_request")


@pytest.fixture(autouse=True)
def reset_rate_limit():
    """Rate-limit counters live in the process-wide cache and user PKs are
    reused after each rollback, so without this one test's POSTs eat into the
    next test's allowance."""
    cache.clear()


def test_get_renders_form(client_logged_in):
    response = client_logged_in.get(URL)

    assert response.status_code == 200
    assert "form" in response.context


def test_create_feature_request(client_logged_in, user):
    data = {
        "idea": "Remind me if I haven't logged a session in a few days",
        "why": "I lose momentum without a nudge",
    }

    response = client_logged_in.post(URL, data)

    assert response.status_code == 302
    assert response.url == f"{URL}?submitted=1"

    request = FeatureRequest.objects.get(user=user)
    assert request.idea == data["idea"]
    assert request.why == data["why"]
    assert request.status == FeatureRequest.StatusChoices.NEW


def test_create_feature_request_without_why(client_logged_in, user):
    response = client_logged_in.post(URL, {"idea": "Add a weekly summary email"})

    assert response.status_code == 302
    assert FeatureRequest.objects.get(user=user).why == ""


def test_idea_is_trimmed(client_logged_in, user):
    client_logged_in.post(URL, {"idea": "   Add a streak counter   ", "why": "  "})

    request = FeatureRequest.objects.get(user=user)
    assert request.idea == "Add a streak counter"
    assert request.why == ""


def test_missing_idea_is_rejected(client_logged_in):
    response = client_logged_in.post(URL, {"idea": "", "why": "No idea given"})

    assert response.status_code == 200
    assert "idea" in response.context["form"].errors
    assert not FeatureRequest.objects.exists()


def test_too_short_idea_is_rejected(client_logged_in):
    response = client_logged_in.post(URL, {"idea": "abc"})

    assert response.status_code == 200
    assert "idea" in response.context["form"].errors
    assert not FeatureRequest.objects.exists()


@pytest.mark.parametrize("field", ["idea", "why"])
def test_too_long_input_is_rejected(client_logged_in, field):
    data = {"idea": "A perfectly reasonable idea", field: "x" * 2001}

    response = client_logged_in.post(URL, data)

    assert response.status_code == 200
    assert field in response.context["form"].errors
    assert not FeatureRequest.objects.exists()


def test_submitted_input_is_preserved_on_error(client_logged_in):
    response = client_logged_in.post(URL, {"idea": "abc", "why": "Keep this text"})

    form = response.context["form"]
    assert form["idea"].value() == "abc"
    assert form["why"].value() == "Keep this text"


def test_unauthenticated_post_is_rejected(client):
    response = client.post(URL, {"idea": "Let me post without logging in"})

    assert response.status_code == 302
    assert "/login/" in response.url
    assert not FeatureRequest.objects.exists()


def test_unauthenticated_get_redirects_to_login(client):
    response = client.get(URL)

    assert response.status_code == 302
    assert "/login/" in response.url


def test_learning_user_group_can_submit(client):
    """The group permissions migration covers FeatureRequest, so an ordinary
    signed-up user can reach the page without being redirected to index."""
    user = baker.make("auth.User", is_superuser=False, is_staff=False)
    user.groups.add(Group.objects.get(name="Learning User"))
    client.force_login(user)

    response = client.post(URL, {"idea": "Ideas from a non-superuser account"})

    assert response.status_code == 302
    assert FeatureRequest.objects.filter(user=user).exists()


def test_user_without_permission_redirects_to_index(client):
    user = baker.make("auth.User", is_superuser=False, is_staff=False)
    client.force_login(user)

    response = client.get(URL)

    assert response.status_code == 302
    assert response.url == reverse("index")


def test_rate_limited_post_is_not_saved(client_logged_in):
    with patch("django_ratelimit.decorators.is_ratelimited", return_value=True):
        response = client_logged_in.post(URL, {"idea": "Spamming the same idea"})

    assert response.status_code == 302
    assert response.url == URL
    assert not FeatureRequest.objects.exists()
