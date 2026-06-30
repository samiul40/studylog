from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone

from accounts.models import UserProfile

User = get_user_model()

pytestmark = pytest.mark.django_db


def _make_deleted_user(username, days_ago):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass"
    )
    user.is_active = False
    user.save(update_fields=["is_active"])
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.deletion_requested_at = timezone.now() - timedelta(days=days_ago)
    profile.save(update_fields=["deletion_requested_at"])
    return user


def test_purge_deletes_accounts_past_retention_window():
    expired = _make_deleted_user("expired", days_ago=31)

    call_command("purge_deleted_accounts", stdout=StringIO())

    assert not User.objects.filter(pk=expired.pk).exists()


def test_purge_keeps_accounts_within_retention_window():
    recent = _make_deleted_user("recent", days_ago=5)

    call_command("purge_deleted_accounts", stdout=StringIO())

    assert User.objects.filter(pk=recent.pk).exists()


def test_purge_ignores_accounts_without_deletion_request(user):
    call_command("purge_deleted_accounts", stdout=StringIO())

    assert User.objects.filter(pk=user.pk).exists()


def test_purge_dry_run_deletes_nothing():
    expired = _make_deleted_user("expired", days_ago=31)

    call_command("purge_deleted_accounts", "--dry-run", stdout=StringIO())

    assert User.objects.filter(pk=expired.pk).exists()
