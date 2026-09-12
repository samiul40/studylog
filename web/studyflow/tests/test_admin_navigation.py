"""The Unfold sidebar is hand-written, so nothing keeps it in step with the
admin registry on its own. These tests are that link: register a model and
forget the nav entry and the model becomes unreachable except by typing its
URL, which is how an admin page quietly stops existing."""

from collections import Counter

import pytest
from django.conf import settings
from django.contrib import admin
from django.urls import reverse

pytestmark = pytest.mark.django_db

SIDEBAR_GROUPS = settings.UNFOLD["SIDEBAR"]["navigation"]


def sidebar_links():
    """Every link in the sidebar, in order, as resolved URL strings."""
    return [str(item["link"]) for group in SIDEBAR_GROUPS for item in group["items"]]


def registered_changelists():
    """Changelist URL -> model, for everything in the admin registry."""
    return {
        reverse(
            f"admin:{model._meta.app_label}_{model._meta.model_name}_changelist"
        ): model
        for model in admin.site._registry
    }


def test_every_registered_model_is_in_the_sidebar():
    links = set(sidebar_links())

    missing = [
        f"{model._meta.app_label}.{model._meta.model_name} ({url})"
        for url, model in registered_changelists().items()
        if url not in links
    ]

    assert not missing, f"registered but not in the sidebar: {missing}"


def test_no_model_is_listed_twice():
    counts = Counter(sidebar_links())

    duplicates = [link for link, count in counts.items() if count > 1]

    assert not duplicates, f"listed more than once in the sidebar: {duplicates}"


def test_every_sidebar_link_goes_somewhere_real():
    """A link to an unregistered model would 404 for whoever clicked it."""
    known = set(registered_changelists()) | {reverse("admin:index")}

    unknown = [link for link in sidebar_links() if link not in known]

    assert not unknown, f"sidebar links to nothing registered: {unknown}"


def test_the_system_group_is_last_and_collapsed():
    system = SIDEBAR_GROUPS[-1]

    assert system["title"] == "System"
    assert system["collapsible"] is True


def test_access_attempts_stays_out_of_the_system_group():
    """It is the one axes model worth seeing daily, so it lives under People."""
    attempts = reverse("admin:axes_accessattempt_changelist")
    groups = {
        group["title"]: [str(item["link"]) for item in group["items"]]
        for group in SIDEBAR_GROUPS
    }

    assert attempts in groups["People"]
    assert attempts not in groups["System"]


def test_the_sidebar_renders_for_a_staff_user(client_logged_in):
    content = client_logged_in.get(reverse("admin:index")).content.decode()

    for group in SIDEBAR_GROUPS:
        assert group["title"] in content
