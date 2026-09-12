from datetime import date

import pytest
from django.db import IntegrityError
from model_bakery import baker

from learning.models import DailyUsageStat

pytestmark = pytest.mark.django_db


def test_daily_usage_stat_str():
    stat = baker.make(DailyUsageStat, date=date(2026, 3, 1), sessions_logged=7)

    assert str(stat) == "2026-03-01: 7 sessions"


def test_counters_default_to_zero():
    stat = DailyUsageStat.objects.create(date=date(2026, 3, 1))

    assert stat.sessions_logged == 0
    assert stat.minutes_logged == 0
    assert stat.active_users == 0
    assert stat.resources_created == 0


def test_only_one_row_per_date():
    DailyUsageStat.objects.create(date=date(2026, 3, 1))

    with pytest.raises(IntegrityError):
        DailyUsageStat.objects.create(date=date(2026, 3, 1))


def test_ordering_is_newest_first():
    baker.make(DailyUsageStat, date=date(2026, 3, 1))
    baker.make(DailyUsageStat, date=date(2026, 3, 3))
    baker.make(DailyUsageStat, date=date(2026, 3, 2))

    assert [s.date.day for s in DailyUsageStat.objects.all()] == [3, 2, 1]


def test_stats_survive_user_deletion(user):
    baker.make(DailyUsageStat, date=date(2026, 3, 1), sessions_logged=4, active_users=1)

    user.delete()

    stat = DailyUsageStat.objects.get(date=date(2026, 3, 1))
    assert stat.sessions_logged == 4
    assert stat.active_users == 1
