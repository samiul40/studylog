from datetime import date

import pytest
from django.db import IntegrityError
from model_bakery import baker

from learning.models import UserRetentionCohort

pytestmark = pytest.mark.django_db

MONDAY = date(2026, 8, 31)


def test_user_retention_cohort_str():
    cohort = baker.make(UserRetentionCohort, cohort_start=MONDAY, cohort_size=30)

    assert str(cohort) == "Week of 2026-08-31: 30 signups"


def test_checkpoints_start_unrecorded():
    cohort = UserRetentionCohort.objects.create(cohort_start=MONDAY)

    assert cohort.cohort_size == 0
    assert cohort.week_1_retained is None
    assert cohort.week_8_retained is None


def test_only_one_row_per_cohort():
    UserRetentionCohort.objects.create(cohort_start=MONDAY)

    with pytest.raises(IntegrityError):
        UserRetentionCohort.objects.create(cohort_start=MONDAY)


def test_ordering_is_newest_first():
    for day in (24, 10, 17):
        baker.make(UserRetentionCohort, cohort_start=date(2026, 8, day))

    days = [c.cohort_start.day for c in UserRetentionCohort.objects.all()]
    assert days == [24, 17, 10]


def test_retained_reads_the_checkpoint_for_a_week():
    cohort = baker.make(
        UserRetentionCohort,
        cohort_start=MONDAY,
        week_1_retained=19,
        week_8_retained=None,
    )

    assert cohort.retained(1) == 19
    assert cohort.retained(8) is None


@pytest.mark.parametrize(
    ("retained", "expected"),
    [(19, 63.3), (15, 50.0), (12, 40.0), (0, 0.0), (30, 100.0)],
)
def test_retention_rate_is_a_percentage_of_the_cohort(retained, expected):
    cohort = baker.make(
        UserRetentionCohort,
        cohort_start=MONDAY,
        cohort_size=30,
        week_1_retained=retained,
    )

    assert cohort.retention_rate(1) == expected


def test_an_unrecorded_checkpoint_has_no_rate():
    """None, not 0.0 — nobody has come back yet is a different claim from the
    window not having happened."""
    cohort = baker.make(
        UserRetentionCohort, cohort_start=MONDAY, cohort_size=30, week_4_retained=None
    )

    assert cohort.retention_rate(4) is None


def test_an_empty_cohort_has_no_rate_rather_than_dividing_by_zero():
    cohort = baker.make(
        UserRetentionCohort, cohort_start=MONDAY, cohort_size=0, week_1_retained=0
    )

    assert cohort.retention_rate(1) is None


def test_cohorts_survive_user_deletion(user):
    baker.make(
        UserRetentionCohort, cohort_start=MONDAY, cohort_size=4, week_1_retained=3
    )

    user.delete()

    cohort = UserRetentionCohort.objects.get(cohort_start=MONDAY)
    assert cohort.cohort_size == 4
    assert cohort.week_1_retained == 3
