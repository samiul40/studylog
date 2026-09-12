from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from model_bakery import baker

from accounts.admin import ENGAGEMENT_BUCKETS, engagement_bucket, engagement_cutoffs
from learning.models import Activity, LearningResource, StudySession

pytestmark = pytest.mark.django_db

CHANGELIST = reverse("admin:auth_user_changelist")
TODAY = timezone.localdate()


def make_user(username, joined_days_ago=400):
    return baker.make(
        "auth.User",
        username=username,
        date_joined=timezone.now() - timedelta(days=joined_days_ago),
    )


def make_session(user, days_ago, minutes=30):
    return baker.make(
        StudySession,
        user=user,
        date=TODAY - timedelta(days=days_ago),
        activity=Activity.objects.get(slug="flashcards", is_system=True),
        duration_minutes=minutes,
        status=StudySession.Status.LOGGED,
    )


def bucket_of(username, client):
    """The bucket the changelist itself computed for one row."""
    response = client.get(CHANGELIST)
    row = response.context["cl"].queryset.get(username=username)
    return engagement_bucket(row, engagement_cutoffs())


# ---------------------------------------------------------------------------
# Buckets
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("days_ago", "expected"),
    [
        (0, "active"),
        (7, "active"),
        (8, "idle"),
        (30, "idle"),
        (31, "dormant"),
    ],
)
def test_recency_decides_the_bucket(client_logged_in, days_ago, expected):
    user = make_user("someone")
    # Three sessions, so an old join date is not what keeps them out of "new".
    for offset in (days_ago, days_ago + 100, days_ago + 200):
        make_session(user, offset)

    assert bucket_of("someone", client_logged_in) == expected


def test_a_user_who_never_logged_a_session_is_never_logged(client_logged_in):
    make_user("empty")

    assert bucket_of("empty", client_logged_in) == "never"


def test_a_recent_signup_with_few_sessions_is_new(client_logged_in):
    user = make_user("fresh", joined_days_ago=3)
    make_session(user, 1)
    make_session(user, 0)

    assert bucket_of("fresh", client_logged_in) == "new"


def test_a_recent_signup_who_is_already_busy_is_active(client_logged_in):
    """Three sessions is the point where "new" stops explaining the row."""
    user = make_user("busy", joined_days_ago=3)
    for offset in (0, 1, 2):
        make_session(user, offset)

    assert bucket_of("busy", client_logged_in) == "active"


def test_a_deletion_request_outranks_every_other_bucket(client_logged_in):
    user = make_user("leaving", joined_days_ago=2)
    make_session(user, 0)
    user.profile.deletion_requested_at = timezone.now()
    user.profile.save()

    assert bucket_of("leaving", client_logged_in) == "deletion"


def test_a_user_with_no_profile_still_gets_a_bucket(client_logged_in):
    """The profile is a nullable join, so the column must not blow up on it."""
    user = make_user("profileless")
    user.profile.delete()

    assert bucket_of("profileless", client_logged_in) == "never"


# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------


def test_the_filter_agrees_with_the_column(client_logged_in):
    active = make_user("active_user")
    make_session(active, 1)
    make_session(active, 2)
    make_session(active, 3)
    idle = make_user("idle_user")
    for offset in (10, 110, 210):
        make_session(idle, offset)
    dormant = make_user("dormant_user")
    for offset in (90, 190, 290):
        make_session(dormant, offset)
    make_user("never_user")
    make_user("new_user", joined_days_ago=1)

    for bucket, username in [
        ("active", "active_user"),
        ("idle", "idle_user"),
        ("dormant", "dormant_user"),
        ("never", "never_user"),
        ("new", "new_user"),
    ]:
        response = client_logged_in.get(CHANGELIST, {"engagement": bucket})
        usernames = [u.username for u in response.context["cl"].queryset]

        assert username in usernames, f"{username} missing from {bucket}"
        assert bucket_of(username, client_logged_in) == bucket


def test_the_buckets_partition_the_table(client_logged_in):
    """Every user lands in exactly one bucket, or filter and column diverge."""
    busy = make_user("busy")
    for offset in (1, 40, 200):
        make_session(busy, offset)
    quiet = make_user("quiet")
    make_session(quiet, 60)
    make_user("blank")
    make_user("newbie", joined_days_ago=2)

    total = client_logged_in.get(CHANGELIST).context["cl"].queryset.count()
    counted = sum(
        client_logged_in.get(CHANGELIST, {"engagement": bucket})
        .context["cl"]
        .queryset.count()
        for bucket in ENGAGEMENT_BUCKETS
    )

    assert counted == total


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------


def test_the_activity_column_counts_only_the_28_day_window(client_logged_in):
    user = make_user("windowed")
    make_session(user, 1, minutes=60)
    make_session(user, 27, minutes=60)
    make_session(user, 40, minutes=600)

    row = client_logged_in.get(CHANGELIST).context["cl"].queryset.get(pk=user.pk)

    assert row.sessions_28d == 2
    assert row.minutes_28d == 120


def test_resources_do_not_inflate_the_logged_minutes(client_logged_in):
    """Two multi-valued joins in one query would multiply the Sum out."""
    user = make_user("owner")
    make_session(user, 1, minutes=45)
    make_session(user, 2, minutes=45)
    baker.make(LearningResource, user=user, _quantity=3)

    row = client_logged_in.get(CHANGELIST).context["cl"].queryset.get(pk=user.pk)

    assert row.sessions_28d == 2
    assert row.minutes_28d == 90
    assert row.resource_count == 3


def test_the_changelist_renders_the_engagement_labels(client_logged_in):
    user = make_user("labelled")
    for offset in (0, 1, 2):
        make_session(user, offset)

    content = client_logged_in.get(CHANGELIST).content.decode()

    assert "Active" in content
    assert "Engagement" in content
