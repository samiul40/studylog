import datetime

import pytest
from django.utils import timezone
from model_bakery import baker

from learning.models import Activity, LearningResource, StudySession
from learning.services.user_activity import calculate_streaks, get_user_activity

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


def days_ago(*offsets):
    return [TODAY - datetime.timedelta(days=n) for n in offsets]


def make_session(user, offset, minutes=30, **kwargs):
    kwargs.setdefault(
        "activity", Activity.objects.get(slug="flashcards", is_system=True)
    )
    return baker.make(
        StudySession,
        user=user,
        date=TODAY - datetime.timedelta(days=offset),
        duration_minutes=minutes,
        status=kwargs.pop("status", StudySession.Status.LOGGED),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# calculate_streaks
# ---------------------------------------------------------------------------


def test_no_dates_is_no_streak():
    assert calculate_streaks([]) == (0, 0)


def test_a_run_ending_today_is_current():
    assert calculate_streaks(days_ago(0, 1, 2)) == (3, 3)


def test_a_run_ending_yesterday_still_counts():
    """Not having studied yet today shouldn't read as a broken streak."""
    assert calculate_streaks(days_ago(1, 2, 3)) == (3, 3)


def test_a_run_that_stopped_before_yesterday_is_broken():
    assert calculate_streaks(days_ago(2, 3, 4)) == (0, 3)


def test_the_best_streak_survives_the_current_one_breaking():
    # A five-day run last month, then a single day today.
    assert calculate_streaks(days_ago(0, 40, 41, 42, 43, 44)) == (1, 5)


def test_a_gap_splits_a_run():
    assert calculate_streaks(days_ago(0, 1, 3, 4, 5)) == (2, 3)


def test_duplicate_dates_count_once():
    """Several sessions in one day are still one day of the streak."""
    assert calculate_streaks(days_ago(0, 0, 0, 1, 1)) == (2, 2)


def test_order_does_not_matter():
    assert calculate_streaks(days_ago(2, 0, 1)) == calculate_streaks(days_ago(0, 1, 2))


def test_a_single_day_today_is_a_streak_of_one():
    assert calculate_streaks(days_ago(0)) == (1, 1)


def test_a_single_old_day_is_a_best_of_one_and_no_current():
    assert calculate_streaks(days_ago(100)) == (0, 1)


# ---------------------------------------------------------------------------
# get_user_activity
# ---------------------------------------------------------------------------


def test_a_user_with_no_sessions_reads_as_zero(user):
    activity = get_user_activity(user)

    assert activity["sessions_total"] == 0
    assert activity["minutes_total"] == 0
    assert activity["average_minutes"] == 0
    assert activity["current_streak"] == 0
    assert activity["last_session"] is None


def test_totals_split_the_28_day_window_from_the_lifetime(user):
    make_session(user, 1, minutes=60)
    make_session(user, 27, minutes=60)
    make_session(user, 40, minutes=120)

    activity = get_user_activity(user)

    assert activity["sessions_28d"] == 2
    assert activity["minutes_28d"] == 120
    assert activity["sessions_total"] == 3
    assert activity["minutes_total"] == 240


def test_the_average_is_over_every_logged_session(user):
    make_session(user, 0, minutes=30)
    make_session(user, 1, minutes=90)

    assert get_user_activity(user)["average_minutes"] == 60


def test_planned_sessions_are_not_counted(user):
    """A planned session is an intention, not a record of studying."""
    make_session(user, 0, minutes=60, status=StudySession.Status.PLANNED)

    activity = get_user_activity(user)

    assert activity["sessions_total"] == 0
    assert activity["current_streak"] == 0


def test_another_users_sessions_are_not_counted(user):
    stranger = baker.make("auth.User", username="stranger")
    make_session(stranger, 0)

    assert get_user_activity(user)["sessions_total"] == 0


def test_the_last_session_carries_its_activity_and_resource(user):
    resource = baker.make(LearningResource, user=user, title="Linear Algebra")
    make_session(user, 3)
    make_session(user, 0, resource=resource)

    last = get_user_activity(user)["last_session"]

    assert last.date == TODAY
    assert last.resource.title == "Linear Algebra"
