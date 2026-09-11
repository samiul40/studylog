"""Flash messages used to render inline inside <main>, so any page with a
custom layout suppressed them and the message was silently swallowed — then
reappeared later, stacked, on the next page that did render them."""

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

pytestmark = pytest.mark.django_db

DASHBOARD = reverse("learning:dashboard")


def add_message_then_get(client, url):
    """Trigger a real message, then load `url` and see whether it rendered."""
    client.post(
        reverse("settings"),
        {"form_type": "profile", "first_name": "Sam", "last_name": "Amin"},
    )
    return client.get(url)


def test_a_message_renders_on_the_dashboard(client_logged_in, user):
    """The dashboard suppressed the alerts block, so this never showed."""
    response = add_message_then_get(client_logged_in, DASHBOARD)

    assert "Profile updated successfully." in response.content.decode()


@pytest.mark.parametrize(
    "url_name",
    [
        "learning:dashboard",
        "learning:resource_list",
        "learning:session_list",
        "feature_request",
        "settings",
    ],
)
def test_messages_render_across_differently_laid_out_pages(
    client_logged_in, user, url_name
):
    response = add_message_then_get(client_logged_in, reverse(url_name))

    assert "toast-msg" in response.content.decode()


def test_a_message_is_consumed_and_does_not_reappear(client_logged_in, user):
    """Messages persist until rendered. When pages swallowed them they queued
    up and appeared later in duplicate."""
    add_message_then_get(client_logged_in, DASHBOARD)

    second = client_logged_in.get(DASHBOARD)

    assert "Profile updated successfully." not in second.content.decode()
    assert list(get_messages(second.wsgi_request)) == []


def test_no_toast_markup_when_there_are_no_messages(client_logged_in):
    response = client_logged_in.get(DASHBOARD)

    assert "toast-msg" not in response.content.decode()
