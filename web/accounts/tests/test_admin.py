from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from model_bakery import baker

from accounts.models import UserProfile

pytestmark = pytest.mark.django_db

CHANGELIST = reverse("admin:auth_user_changelist")


def make_user(username, terms_version):
    user = baker.make("auth.User", username=username)
    UserProfile.objects.filter(user=user).update(terms_version=terms_version)
    return user


def test_changelist_shows_the_terms_column(client_logged_in):
    make_user("current_user", "1.0")

    content = client_logged_in.get(CHANGELIST).content.decode()

    assert "Terms" in content
    assert "✓ 1.0" in content


def test_an_outdated_version_is_called_out(client_logged_in):
    make_user("old_user", "0.9")

    content = client_logged_in.get(CHANGELIST).content.decode()

    assert "Outdated (0.9)" in content


def test_a_user_who_never_accepted_is_called_out(client_logged_in):
    make_user("never_user", "")

    content = client_logged_in.get(CHANGELIST).content.decode()

    assert "— Never" in content


@pytest.mark.parametrize(
    ("status", "expected", "unexpected"),
    [
        ("current", "current_user", "never_user"),
        ("outdated", "old_user", "current_user"),
        ("never", "never_user", "current_user"),
    ],
)
def test_the_terms_filter_narrows_the_list(
    client_logged_in, status, expected, unexpected
):
    make_user("current_user", "1.0")
    make_user("old_user", "0.9")
    make_user("never_user", "")

    response = client_logged_in.get(CHANGELIST, {"terms_status": status})

    usernames = [u.username for u in response.context["cl"].queryset]

    assert expected in usernames
    assert unexpected not in usernames


def test_a_user_with_no_profile_counts_as_never(client_logged_in):
    user = baker.make("auth.User", username="profileless")
    UserProfile.objects.filter(user=user).delete()

    response = client_logged_in.get(CHANGELIST, {"terms_status": "never"})

    assert "profileless" in [u.username for u in response.context["cl"].queryset]


def test_consent_fields_are_read_only_on_the_user_page(client_logged_in, user):
    """Consent records what the user did — editing it here would fabricate it."""
    url = reverse("admin:auth_user_change", args=[user.pk])

    content = client_logged_in.get(url).content.decode()

    assert 'name="profile-0-terms_version"' not in content
    assert 'name="profile-0-terms_accepted"' not in content
    assert 'name="profile-0-timezone"' in content


def test_users_are_listed_newest_first(client_logged_in):
    # Names chosen so alphabetical order (the Django default) disagrees with
    # newest-first, otherwise this passes without the ordering being applied.
    baker.make(
        "auth.User", username="aaa_old", date_joined=timezone.now() - timedelta(days=5)
    )
    baker.make("auth.User", username="zzz_new", date_joined=timezone.now())

    response = client_logged_in.get(CHANGELIST)

    usernames = [u.username for u in response.context["cl"].queryset]
    assert usernames.index("zzz_new") < usernames.index("aaa_old")
