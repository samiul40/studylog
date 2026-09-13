from datetime import date, datetime, time, timedelta
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from model_bakery import baker

from learning.management.commands.rollup_retention_cohorts import week_start
from learning.models import Activity, StudySession, UserRetentionCohort

pytestmark = pytest.mark.django_db

User = get_user_model()

# A Monday. Which checkpoints have come due is decided by where today falls in
# the week — a cohort three weeks back is due on a Sunday but not on a Monday —
# so it is pinned rather than left to the day the suite happens to run.
TODAY = date(2026, 9, 14)


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    monkeypatch.setattr(timezone, "localdate", lambda: TODAY)


def _cohort(weeks_ago):
    """The Monday that opened the signup week `weeks_ago` weeks back."""
    return week_start(TODAY) - timedelta(weeks=weeks_ago)


def _signup(cohort_start, day=0):
    """A user who registered `day` days into the week starting cohort_start.

    date_joined has a default, so it has to be overwritten after the fact.
    Midday keeps the signup away from a timezone boundary.
    """
    user = baker.make("auth.User", is_superuser=False)
    joined = timezone.make_aware(
        datetime.combine(cohort_start + timedelta(days=day), time(12, 0))
    )
    User.objects.filter(pk=user.pk).update(date_joined=joined)
    user.date_joined = joined
    user.signup_date = joined.date()
    return user


def _study(user, day, status=StudySession.Status.LOGGED):
    """Log a session `day` days after the user registered."""
    return baker.make(
        StudySession,
        user=user,
        activity=Activity.objects.get(slug="flashcards", is_system=True),
        date=user.signup_date + timedelta(days=day),
        duration_minutes=30,
        status=status,
    )


def _recorded(weeks_ago):
    """The cohort row for the week `weeks_ago` weeks back."""
    return UserRetentionCohort.objects.get(cohort_start=_cohort(weeks_ago))


def _rollup(*args):
    out = StringIO()
    call_command("rollup_retention_cohorts", *args, stdout=out)
    return out.getvalue()


# Weeks back far enough that the named checkpoint has closed for every member
# of the cohort: the Sunday joiner's window ends 6 + 7n + 6 days after the
# Monday it opened.
W1_DUE = 3
W2_DUE = 4
W4_DUE = 6
W8_DUE = 10


def test_creates_a_row_for_each_completed_signup_week():
    _signup(_cohort(3))
    _signup(_cohort(1))

    _rollup()

    starts = list(UserRetentionCohort.objects.values_list("cohort_start", flat=True))
    assert starts == [_cohort(1), _cohort(3)]


def test_the_current_week_is_not_recorded_while_still_taking_signups():
    _signup(_cohort(1))

    _rollup()

    assert not UserRetentionCohort.objects.filter(cohort_start=_cohort(0)).exists()


def test_a_week_nobody_joined_in_gets_no_row():
    _signup(_cohort(3))

    _rollup()

    assert not UserRetentionCohort.objects.filter(cohort_start=_cohort(2)).exists()


def test_cohort_size_counts_everyone_who_registered_that_week():
    for day in (0, 3, 6):
        _signup(_cohort(2), day=day)
    _signup(_cohort(1))

    _rollup()

    assert _recorded(2).cohort_size == 3
    assert _recorded(1).cohort_size == 1


def test_weeks_break_on_monday():
    """Sunday closes a cohort; the Monday after opens the next one."""
    _signup(_cohort(3), day=6)
    _signup(_cohort(2), day=0)

    _rollup()

    assert _recorded(3).cohort_size == 1
    assert _recorded(2).cohort_size == 1


def test_a_user_with_no_sessions_is_not_retained():
    _signup(_cohort(W1_DUE))

    _rollup()

    cohort = _recorded(W1_DUE)
    assert cohort.cohort_size == 1
    assert cohort.week_1_retained == 0


@pytest.mark.parametrize("day", [7, 10, 13])
def test_a_session_inside_the_week_1_window_counts(day):
    _study(_signup(_cohort(W1_DUE)), day)

    _rollup()

    assert _recorded(W1_DUE).week_1_retained == 1


@pytest.mark.parametrize("day", [0, 6])
def test_studying_before_the_window_opens_is_not_week_1_retention(day):
    _study(_signup(_cohort(W1_DUE)), day)

    _rollup()

    assert _recorded(W1_DUE).week_1_retained == 0


def test_studying_after_the_window_closes_is_not_week_1_retention():
    _study(_signup(_cohort(W2_DUE)), 14)

    _rollup()

    cohort = _recorded(W2_DUE)
    assert cohort.week_1_retained == 0
    assert cohort.week_2_retained == 1


@pytest.mark.parametrize(
    ("week", "weeks_ago", "day"),
    [(2, W2_DUE, 14), (2, W2_DUE, 20), (4, W4_DUE, 28), (8, W8_DUE, 62)],
)
def test_the_later_checkpoints_use_their_own_windows(week, weeks_ago, day):
    _study(_signup(_cohort(weeks_ago)), day)

    _rollup()

    cohort = _recorded(weeks_ago)
    assert cohort.retained(week) == 1
    assert cohort.week_1_retained == 0


def test_a_user_who_studied_all_week_counts_once():
    user = _signup(_cohort(W1_DUE))
    for day in range(7, 14):
        _study(user, day)

    _rollup()

    assert _recorded(W1_DUE).week_1_retained == 1


def test_the_window_follows_each_user_not_the_cohort_start():
    """A Sunday joiner's week 1 runs 6 days later than a Monday joiner's."""
    monday = _signup(_cohort(W1_DUE), day=0)
    sunday = _signup(_cohort(W1_DUE), day=6)
    _study(monday, 7)
    _study(sunday, 7)

    _rollup()

    assert _recorded(W1_DUE).week_1_retained == 2


def test_planned_sessions_are_not_coming_back():
    _study(_signup(_cohort(W1_DUE)), 7, status=StudySession.Status.PLANNED)

    _rollup()

    assert _recorded(W1_DUE).week_1_retained == 0


def test_checkpoints_that_have_not_elapsed_stay_null():
    _signup(_cohort(2))

    _rollup()

    cohort = _recorded(2)
    assert cohort.week_1_retained is None
    assert cohort.week_2_retained is None
    assert cohort.week_4_retained is None
    assert cohort.week_8_retained is None


def test_a_checkpoint_waits_for_the_last_member_of_the_cohort():
    """Two weeks back, week 1 has closed for the Monday joiner but not for a
    Sunday one, so nothing is recorded yet."""
    _signup(_cohort(2), day=0)

    _rollup()

    assert _recorded(2).week_1_retained is None


def test_checkpoints_fill_in_as_they_come_due():
    _study(_signup(_cohort(W2_DUE)), 14)
    _rollup()

    cohort = _recorded(W2_DUE)
    assert cohort.week_2_retained == 1
    assert cohort.week_4_retained is None
    assert cohort.week_8_retained is None


def test_rerunning_changes_nothing():
    _study(_signup(_cohort(W1_DUE)), 7)
    _rollup()

    _study(_signup(_cohort(W1_DUE)), 7)
    output = _rollup()

    cohort = _recorded(W1_DUE)
    assert cohort.cohort_size == 1
    assert cohort.week_1_retained == 1
    assert "already up to date" in output


def test_a_recorded_checkpoint_survives_deletion_of_the_user_behind_it():
    user = _study(_signup(_cohort(W1_DUE)), 7).user
    _rollup()

    user.delete()
    _rollup()

    cohort = _recorded(W1_DUE)
    assert cohort.cohort_size == 1
    assert cohort.week_1_retained == 1


def test_a_missed_run_is_caught_up():
    _study(_signup(_cohort(W4_DUE)), 28)
    _rollup()
    UserRetentionCohort.objects.all().delete()

    _rollup()

    cohort = _recorded(W4_DUE)
    assert cohort.week_4_retained == 1


def test_reports_nothing_to_do_without_any_accounts():
    output = _rollup()

    assert "already up to date" in output
    assert not UserRetentionCohort.objects.exists()


def test_reports_nothing_to_do_before_the_first_week_ends():
    _signup(_cohort(0))

    output = _rollup()

    assert "already up to date" in output
    assert not UserRetentionCohort.objects.exists()


def test_the_query_count_does_not_grow_with_the_number_of_users(
    django_assert_max_num_queries,
):
    """A cohort of 14 costs the same as a cohort of one: the size and each
    checkpoint are one grouped query over the whole range."""
    for day in range(7):
        for _ in range(2):
            _study(_signup(_cohort(W8_DUE), day=day), 7)

    with django_assert_max_num_queries(12):
        _rollup()
