from datetime import date

import pytest
from django.urls import reverse
from model_bakery import baker

from learning.models import DailyUsageStat

pytestmark = pytest.mark.django_db


def test_changelist_loads(client_logged_in):
    baker.make(DailyUsageStat, date=date(2026, 3, 1), sessions_logged=7)

    response = client_logged_in.get(
        reverse("admin:learning_dailyusagestat_changelist")
    )

    assert response.status_code == 200
    assert "1 Mar 2026" in response.content.decode()


def test_rows_cannot_be_added_by_hand(client_logged_in):
    response = client_logged_in.get(reverse("admin:learning_dailyusagestat_add"))

    assert response.status_code == 403


def test_a_row_opens_read_only(client_logged_in):
    stat = baker.make(DailyUsageStat, date=date(2026, 3, 1))

    response = client_logged_in.get(
        reverse("admin:learning_dailyusagestat_change", args=[stat.pk])
    )

    assert response.status_code == 200
    assert response.context["has_change_permission"] is False


def test_index_shows_monthly_usage_by_default(client_logged_in):
    baker.make(
        DailyUsageStat,
        date=date(2026, 3, 1),
        sessions_logged=7,
        minutes_logged=655,
    )

    response = client_logged_in.get(reverse("admin:index"))
    content = response.content.decode()

    assert response.status_code == 200
    assert response.context["usage_period"] == "month"
    assert "Mar 2026" in content
    assert "10h 55m" in content


def test_index_switches_to_weeks(client_logged_in):
    baker.make(DailyUsageStat, date=date(2026, 3, 4), sessions_logged=7)

    response = client_logged_in.get(reverse("admin:index"), {"period": "week"})

    assert response.status_code == 200
    assert response.context["usage_period"] == "week"
    assert "2 Mar 2026" in response.content.decode()


def test_index_ignores_an_unknown_period(client_logged_in):
    response = client_logged_in.get(reverse("admin:index"), {"period": "fortnight"})

    assert response.status_code == 200
    assert response.context["usage_period"] == "month"


def test_index_prompts_to_run_the_command_when_empty(client_logged_in):
    response = client_logged_in.get(reverse("admin:index"))

    assert response.status_code == 200
    assert "rollup_usage_stats" in response.content.decode()
