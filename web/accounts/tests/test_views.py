# Django
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile

User = get_user_model()

pytestmark = pytest.mark.django_db


def test_settings_view_requires_login(client):
    url = reverse("settings")
    res = client.get(url)

    assert res.status_code == 302
    assert reverse("account_login") in res.url


def test_settings_view_logged_in(client_logged_in):
    url = reverse("settings")
    res = client_logged_in.get(url)

    assert res.status_code == 200
    assert b"Settings" in res.content or b"settings" in res.content.lower()


def test_settings_profile_update(client_logged_in, user):
    url = reverse("settings")
    res = client_logged_in.post(
        url,
        {
            "form_type": "profile",
            "first_name": "Alice",
            "last_name": "Smith",
            "email": "alice@example.com",
        },
    )

    assert res.status_code == 302
    assert res.url == url
    user.refresh_from_db()
    assert user.first_name == "Alice"
    assert user.last_name == "Smith"
    assert user.email == "alice@example.com"


def test_settings_profile_update_duplicate_email(client_logged_in, user):
    other = User.objects.create_user(
        username="other", email="taken@example.com", password="pass"
    )
    url = reverse("settings")
    res = client_logged_in.post(
        url,
        {
            "form_type": "profile",
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": other.email,
        },
    )

    assert res.status_code == 200
    assert b"already in use" in res.content


def test_settings_password_change(client_logged_in, user):
    url = reverse("settings")
    res = client_logged_in.post(
        url,
        {
            "form_type": "password",
            "old_password": "12345",
            "new_password1": "NewPass!99",
            "new_password2": "NewPass!99",
        },
    )

    assert res.status_code == 302
    assert res.url == url
    user.refresh_from_db()
    assert user.check_password("NewPass!99")


def test_settings_password_change_wrong_old(client_logged_in):
    url = reverse("settings")
    res = client_logged_in.post(
        url,
        {
            "form_type": "password",
            "old_password": "wrongpassword",
            "new_password1": "NewPass!99",
            "new_password2": "NewPass!99",
        },
    )

    assert res.status_code == 200
    content = res.content.lower()
    assert b"old_password" in res.content or b"incorrect" in content


def test_delete_account_requires_login(client):
    url = reverse("delete_account")
    res = client.post(url)

    assert res.status_code == 302
    assert reverse("account_login") in res.url


def test_delete_account_deactivates_user(client_logged_in, user):
    url = reverse("delete_account")
    res = client_logged_in.post(url)

    assert res.status_code == 302
    assert res.url == reverse("account_login")

    user.refresh_from_db()
    assert user.is_active is False
    assert user.profile.deletion_requested_at is not None


def test_delete_account_logs_user_out(client_logged_in):
    url = reverse("delete_account")
    client_logged_in.post(url)

    res = client_logged_in.get(reverse("settings"))
    assert res.status_code == 302
    assert reverse("account_login") in res.url


def test_reactivate_get_renders_form(client):
    url = reverse("reactivate_account")
    res = client.get(url)

    assert res.status_code == 200
    assert b"Reactivate" in res.content


def test_reactivate_unknown_email(client):
    url = reverse("reactivate_account")
    res = client.post(url, {"email": "nobody@example.com", "password": "whatever"})

    assert res.status_code == 200
    assert b"No account found" in res.content


def test_reactivate_wrong_password(client, user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.deletion_requested_at = timezone.now()
    profile.save(update_fields=["deletion_requested_at"])

    url = reverse("reactivate_account")
    res = client.post(url, {"email": user.email, "password": "wrongpassword"})

    assert res.status_code == 200
    assert b"Incorrect password" in res.content


def test_reactivate_not_scheduled_for_deletion(client, user):
    url = reverse("reactivate_account")
    res = client.post(url, {"email": user.email, "password": "12345"})

    assert res.status_code == 200
    assert b"not scheduled for deletion" in res.content


def test_reactivate_success_within_window(client, user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.deletion_requested_at = timezone.now() - timedelta(days=5)
    profile.save(update_fields=["deletion_requested_at"])
    user.is_active = False
    user.save(update_fields=["is_active"])

    url = reverse("reactivate_account")
    res = client.post(url, {"email": user.email, "password": "12345"})

    assert res.status_code == 302
    assert res.url == reverse("learning:dashboard")

    user.refresh_from_db()
    profile.refresh_from_db()
    assert user.is_active is True
    assert profile.deletion_requested_at is None


def test_reactivate_expired_window(client, user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.deletion_requested_at = timezone.now() - timedelta(days=31)
    profile.save(update_fields=["deletion_requested_at"])
    user.is_active = False
    user.save(update_fields=["is_active"])

    url = reverse("reactivate_account")
    res = client.post(url, {"email": user.email, "password": "12345"})

    assert res.status_code == 200
    assert b"permanently deleted" in res.content

    user.refresh_from_db()
    assert user.is_active is False
