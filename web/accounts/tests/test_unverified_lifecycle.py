from datetime import timedelta
from io import StringIO

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from model_bakery import baker

from accounts.management.commands.purge_unverified_accounts import (
    UNVERIFIED_RETENTION_DAYS,
)
from accounts.models import UserProfile

pytestmark = pytest.mark.django_db

User = get_user_model()


def make_account(username, *, days_ago, verified, **user_kwargs):
    user = baker.make(
        User,
        username=username,
        email=f"{username}@example.com",
        date_joined=timezone.now() - timedelta(days=days_ago),
        **user_kwargs,
    )
    EmailAddress.objects.create(
        user=user,
        email=user.email,
        verified=verified,
        primary=verified,
    )
    return user


def purge(**options):
    out = StringIO()
    call_command("purge_unverified_accounts", stdout=out, **options)
    return out.getvalue()


def test_a_bare_run_deletes_nothing(account_past_cutoff):
    """Dry-run by default: this command picks accounts by inactivity, so a
    bare run must never destroy anything."""
    output = purge()

    assert "Would permanently delete" in output
    assert User.objects.filter(pk=account_past_cutoff.pk).exists()


@pytest.fixture
def account_past_cutoff():
    return make_account("stale", days_ago=UNVERIFIED_RETENTION_DAYS + 1, verified=False)


def test_delete_removes_an_expired_unverified_account(account_past_cutoff):
    purge(delete=True)

    assert not User.objects.filter(pk=account_past_cutoff.pk).exists()


def test_a_recent_unverified_account_is_left_alone():
    recent = make_account("recent", days_ago=1, verified=False)

    purge(delete=True)

    assert User.objects.filter(pk=recent.pk).exists()


def test_a_verified_account_is_never_touched():
    verified = make_account(
        "verified", days_ago=UNVERIFIED_RETENTION_DAYS + 10, verified=True
    )

    purge(delete=True)

    assert User.objects.filter(pk=verified.pk).exists()


@pytest.mark.parametrize("flag", ["is_superuser", "is_staff"])
def test_admin_accounts_are_skipped(flag):
    """A stuck admin account should never be swept away silently."""
    admin = make_account(
        f"admin_{flag}",
        days_ago=UNVERIFIED_RETENTION_DAYS + 5,
        verified=False,
        **{flag: True},
    )

    purge(delete=True)

    assert User.objects.filter(pk=admin.pk).exists()


def test_accounts_awaiting_the_other_purge_are_skipped():
    """purge_deleted_accounts owns anything already asked to be removed."""
    leaving = make_account(
        "leaving", days_ago=UNVERIFIED_RETENTION_DAYS + 5, verified=False
    )
    UserProfile.objects.filter(user=leaving).update(
        deletion_requested_at=timezone.now()
    )

    purge(delete=True)

    assert User.objects.filter(pk=leaving.pk).exists()


def test_deleting_takes_the_profile_with_it(account_past_cutoff):
    purge(delete=True)

    assert not UserProfile.objects.filter(user_id=account_past_cutoff.pk).exists()


def test_nothing_to_do_is_reported_clearly():
    make_account("fine", days_ago=1, verified=False)

    assert "No unverified accounts to purge." in purge()


def test_the_deletion_log_does_not_contain_the_email(account_past_cutoff):
    """cron appends this output to a log file. Writing the address of someone
    whose data we just erased would quietly undo part of that erasure."""
    output = purge(delete=True)

    assert account_past_cutoff.email not in output
    assert f"id={account_past_cutoff.pk}" in output
