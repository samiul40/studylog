from datetime import date

import pytest
from django.urls import reverse
from model_bakery import baker

from learning.models import UserRetentionCohort

pytestmark = pytest.mark.django_db

MONDAY = date(2026, 8, 31)


def _changelist(client):
    return client.get(reverse("admin:learning_userretentioncohort_changelist"))


def test_changelist_loads(client_logged_in):
    baker.make(UserRetentionCohort, cohort_start=MONDAY, cohort_size=20)

    response = _changelist(client_logged_in)

    assert response.status_code == 200
    assert "31 Aug 2026" in response.content.decode()


def test_the_table_shows_counts_beside_their_percentages(client_logged_in):
    baker.make(
        UserRetentionCohort,
        cohort_start=MONDAY,
        cohort_size=20,
        week_1_retained=12,
        week_2_retained=10,
        week_4_retained=8,
    )

    content = _changelist(client_logged_in).content.decode()

    for value in ("20", "12", "60.0%", "10", "50.0%", "8", "40.0%"):
        assert value in content


def test_an_unelapsed_checkpoint_shows_a_dash_not_a_zero(client_logged_in):
    # 11/20 rather than 12/20, so the real rate doesn't contain "0.0%" as a
    # substring and the assertion below means what it says.
    baker.make(
        UserRetentionCohort,
        cohort_start=MONDAY,
        cohort_size=20,
        week_1_retained=11,
        week_8_retained=None,
    )

    content = _changelist(client_logged_in).content.decode()

    assert "55.0%" in content
    assert "—" in content
    assert "0.0%" not in content


def test_an_empty_cohort_shows_a_dash_rather_than_erroring(client_logged_in):
    baker.make(
        UserRetentionCohort, cohort_start=MONDAY, cohort_size=0, week_1_retained=0
    )

    response = _changelist(client_logged_in)

    assert response.status_code == 200
    assert "—" in response.content.decode()


def test_rows_cannot_be_added_by_hand(client_logged_in):
    response = client_logged_in.get(reverse("admin:learning_userretentioncohort_add"))

    assert response.status_code == 403


def test_a_row_opens_read_only(client_logged_in):
    cohort = baker.make(UserRetentionCohort, cohort_start=MONDAY)

    response = client_logged_in.get(
        reverse("admin:learning_userretentioncohort_change", args=[cohort.pk])
    )

    assert response.status_code == 200
    assert response.context["has_change_permission"] is False
