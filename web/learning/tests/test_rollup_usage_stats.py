from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone
from model_bakery import baker

from learning.models import Activity, DailyUsageStat, LearningResource, StudySession

pytestmark = pytest.mark.django_db


def _days_ago(n):
    return timezone.localdate() - timedelta(days=n)


def _log_session(user, days_ago, minutes=30, **kwargs):
    return baker.make(
        StudySession,
        user=user,
        activity=Activity.objects.get(slug="flashcards", is_system=True),
        date=_days_ago(days_ago),
        duration_minutes=minutes,
        status=kwargs.pop("status", StudySession.Status.LOGGED),
        **kwargs,
    )


def _rollup(*args):
    out = StringIO()
    call_command("rollup_usage_stats", *args, stdout=out)
    return out.getvalue()


def test_backfills_from_earliest_session_through_yesterday(user):
    _log_session(user, days_ago=3, minutes=45)

    _rollup()

    dates = list(DailyUsageStat.objects.values_list("date", flat=True))
    assert dates == [_days_ago(1), _days_ago(2), _days_ago(3)]

    stat = DailyUsageStat.objects.get(date=_days_ago(3))
    assert stat.sessions_logged == 1
    assert stat.minutes_logged == 45
    assert stat.active_users == 1


def test_records_zero_rows_for_quiet_days(user):
    _log_session(user, days_ago=3)

    _rollup()

    quiet = DailyUsageStat.objects.get(date=_days_ago(2))
    assert quiet.sessions_logged == 0
    assert quiet.minutes_logged == 0
    assert quiet.active_users == 0


def test_today_is_not_rolled_up_while_still_partial(user):
    _log_session(user, days_ago=0)
    _log_session(user, days_ago=1)

    _rollup()

    assert not DailyUsageStat.objects.filter(date=_days_ago(0)).exists()
    assert DailyUsageStat.objects.filter(date=_days_ago(1)).exists()


def test_planned_sessions_are_not_counted(user):
    _log_session(user, days_ago=2, minutes=60, status=StudySession.Status.PLANNED)

    _rollup()

    stat = DailyUsageStat.objects.get(date=_days_ago(2))
    assert stat.sessions_logged == 0
    assert stat.minutes_logged == 0


def test_active_users_counts_each_user_once(user):
    other = baker.make("auth.User", is_superuser=False)
    _log_session(user, days_ago=2)
    _log_session(user, days_ago=2)
    _log_session(other, days_ago=2)

    _rollup()

    stat = DailyUsageStat.objects.get(date=_days_ago(2))
    assert stat.sessions_logged == 3
    assert stat.active_users == 2


def test_counts_resources_created_that_day(user):
    resource = baker.make(LearningResource, user=user)
    LearningResource.objects.filter(pk=resource.pk).update(
        created_at=timezone.now() - timedelta(days=2)
    )
    _log_session(user, days_ago=2)

    _rollup()

    assert DailyUsageStat.objects.get(date=_days_ago(2)).resources_created == 1


def test_rerunning_changes_nothing(user):
    _log_session(user, days_ago=2)
    _rollup()

    _log_session(user, days_ago=2)
    output = _rollup()

    assert DailyUsageStat.objects.get(date=_days_ago(2)).sessions_logged == 1
    assert "already up to date" in output


def test_recorded_days_survive_deletion_of_the_user_who_earned_them(user):
    _log_session(user, days_ago=2, minutes=90)
    _rollup()

    user.delete()
    _rollup()

    stat = DailyUsageStat.objects.get(date=_days_ago(2))
    assert stat.sessions_logged == 1
    assert stat.minutes_logged == 90
    assert stat.active_users == 1


def test_fills_a_day_the_cron_missed(user):
    _log_session(user, days_ago=2)
    _rollup()
    DailyUsageStat.objects.filter(date=_days_ago(1)).delete()

    _rollup()

    assert DailyUsageStat.objects.filter(date=_days_ago(1)).exists()


def test_reports_nothing_to_do_when_there_are_no_sessions():
    output = _rollup()

    assert "No sessions to roll up." in output
    assert not DailyUsageStat.objects.exists()
