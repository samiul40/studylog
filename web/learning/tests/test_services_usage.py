from datetime import date

import pytest
from model_bakery import baker

from learning.models import DailyUsageStat
from learning.services.usage import get_usage_breakdown

pytestmark = pytest.mark.django_db


def _stat(day, **counters):
    return baker.make(DailyUsageStat, date=day, **counters)


def test_sums_each_month_separately():
    _stat(date(2026, 3, 1), sessions_logged=2, minutes_logged=60)
    _stat(date(2026, 3, 2), sessions_logged=3, minutes_logged=45)
    _stat(date(2026, 4, 1), sessions_logged=1, minutes_logged=30)

    rows = get_usage_breakdown()

    assert [r["label"] for r in rows] == ["Apr 2026", "Mar 2026"]
    assert rows[1]["sessions"] == 5
    assert rows[1]["minutes"] == 105


def test_weeks_are_labelled_from_the_monday():
    # 2026-03-04 is a Wednesday; its week starts Monday 2026-03-02.
    _stat(date(2026, 3, 4), sessions_logged=2)

    rows = get_usage_breakdown("week")

    assert rows[0]["label"] == "2 Mar 2026"


def test_active_users_takes_the_highest_rolling_count_not_the_sum():
    _stat(date(2026, 3, 1), active_users_28d=4)
    _stat(date(2026, 3, 2), active_users_28d=7)
    _stat(date(2026, 3, 3), active_users_28d=2)

    rows = get_usage_breakdown()

    assert rows[0]["active_users"] == 7


def test_each_period_reports_its_own_window():
    _stat(date(2026, 3, 4), active_users_7d=3, active_users_28d=9)

    weekly = get_usage_breakdown("week")
    monthly = get_usage_breakdown("month")

    assert weekly[0]["active_users"] == 3
    assert weekly[0]["window_days"] == 7
    assert monthly[0]["active_users"] == 9
    assert monthly[0]["window_days"] == 28


def test_reports_accounts_alongside_active_users():
    _stat(date(2026, 3, 1), active_users_28d=2, total_accounts=8)
    _stat(date(2026, 3, 2), active_users_28d=3, total_accounts=10)

    rows = get_usage_breakdown()

    assert rows[0]["active_users"] == 3
    assert rows[0]["total_accounts"] == 10


def test_weeks_split_a_month_that_months_would_merge():
    _stat(date(2026, 3, 2), sessions_logged=2)
    _stat(date(2026, 3, 10), sessions_logged=3)

    weekly = get_usage_breakdown("week")
    monthly = get_usage_breakdown("month")

    assert [r["sessions"] for r in weekly] == [3, 2]
    assert [r["sessions"] for r in monthly] == [5]


def test_formats_minutes_for_display():
    _stat(date(2026, 3, 1), minutes_logged=655)

    rows = get_usage_breakdown()

    assert rows[0]["minutes_display"] == "10h 55m"


def test_returns_newest_first_limited_to_n():
    for month in range(1, 6):
        _stat(date(2026, month, 1))

    rows = get_usage_breakdown(n=3)

    assert [r["label"] for r in rows] == ["May 2026", "Apr 2026", "Mar 2026"]


def test_an_unknown_period_falls_back_to_months():
    _stat(date(2026, 3, 1), sessions_logged=2)
    _stat(date(2026, 3, 10), sessions_logged=3)

    rows = get_usage_breakdown("fortnight")

    assert [r["label"] for r in rows] == ["Mar 2026"]


def test_returns_empty_when_nothing_recorded():
    assert get_usage_breakdown() == []
