import re
from datetime import date

import pytest
from django.contrib import admin
from django.urls import reverse
from model_bakery import baker

from learning.models import DailyUsageStat, LearningResource, LearningUnit

pytestmark = pytest.mark.django_db

INDEX = reverse("admin:index")


def test_the_stat_cards_carry_the_site_totals(client_logged_in, user):
    resource = baker.make(LearningResource, user=user, title="Algebra")
    baker.make(LearningUnit, resource=resource, order=1, status="completed")
    baker.make(LearningUnit, resource=resource, order=2, status="not_started")

    response = client_logged_in.get(INDEX)
    labels = [card["label"] for card in response.context["stat_cards"]]

    assert labels == ["Resources", "Units", "Completed units", "Completion rate"]
    assert response.context["total_units"] == 2
    assert response.context["completed_units"] == 1
    assert "50%" in response.content.decode()


def test_the_course_progress_table_is_gone(client_logged_in, user):
    """It duplicated the resources changelist once that grew a progress column."""
    baker.make(LearningResource, user=user, title="Uniquely Named Course")

    content = client_logged_in.get(INDEX).content.decode()

    assert "Course Progress" not in content
    assert "Uniquely Named Course" not in content


def test_the_page_carries_no_inline_styles(client_logged_in):
    """The point of re-templating it was to stop hand-styling the admin."""
    content = client_logged_in.get(INDEX).content.decode()

    body = content.split("</head>", 1)[-1]
    inline = re.findall(r'<[^>]+\sstyle="[^"]*"', body)

    assert not inline, f"inline styles left on the index: {inline[:3]}"


def test_the_app_list_still_renders(client_logged_in):
    content = client_logged_in.get(INDEX).content.decode()

    assert reverse("admin:learning_studysession_changelist") in content


def test_the_index_view_is_unfolds_own(client_logged_in):
    """The old code replaced admin.site.index; the callback leaves it alone."""
    assert admin.site.index.__self__ is admin.site
    assert type(admin.site).__module__.startswith("unfold")


def test_the_usage_table_reports_active_users_as_a_share(client_logged_in):
    baker.make(
        DailyUsageStat,
        date=date(2026, 3, 1),
        sessions_logged=7,
        minutes_logged=655,
        active_users_28d=3,
        total_accounts=12,
    )

    response = client_logged_in.get(INDEX)
    row = response.context["usage_table"]["rows"][0]

    assert "3 (25%)" in row
    assert "10h 55m" in row


def test_a_period_with_no_accounts_shows_a_bare_count(client_logged_in):
    """Dividing by zero accounts would blow up the page."""
    baker.make(
        DailyUsageStat,
        date=date(2026, 3, 1),
        active_users_28d=0,
        total_accounts=0,
    )

    response = client_logged_in.get(INDEX)

    assert response.status_code == 200
    assert 0 in response.context["usage_table"]["rows"][0]
