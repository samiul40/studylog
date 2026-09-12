import datetime

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from model_bakery import baker

from learning.models import Activity, LearningResource, LearningUnit, StudySession

pytestmark = pytest.mark.django_db

CHANGELIST = reverse("admin:learning_studysession_changelist")
TODAY = timezone.localdate()


def make_session(user, **kwargs):
    kwargs.setdefault("date", TODAY)
    kwargs.setdefault(
        "activity", Activity.objects.get(slug="flashcards", is_system=True)
    )
    kwargs.setdefault("duration_minutes", 30)
    kwargs.setdefault("status", StudySession.Status.LOGGED)
    return baker.make(StudySession, user=user, **kwargs)


def rows(client, params=None):
    response = client.get(CHANGELIST, params or {})
    return list(response.context["cl"].queryset)


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------


def test_the_context_column_pairs_the_resource_with_the_unit(client_logged_in, user):
    resource = baker.make(LearningResource, user=user, title="Algebra")
    unit = baker.make(LearningUnit, resource=resource, title="Vectors", order=1)
    make_session(user, resource=resource, unit=unit)

    content = client_logged_in.get(CHANGELIST).content.decode()

    assert "Algebra · Vectors" in content


def test_the_context_column_falls_back_to_a_dash(client_logged_in, user):
    make_session(user)

    content = client_logged_in.get(CHANGELIST).content.decode()

    assert "Resource / unit" in content
    assert "—" in content


def test_activity_and_status_render_as_coloured_labels(client_logged_in, user):
    make_session(
        user,
        activity=Activity.objects.get(slug="watch", is_system=True),
        status=StudySession.Status.PLANNED,
    )

    content = client_logged_in.get(CHANGELIST).content.decode()

    # "watch" is an info-coloured activity; "planned" an info-coloured status.
    assert "bg-blue-100" in content
    assert "Watched" in content
    assert "Planned" in content


def test_a_custom_activity_gets_the_neutral_label(client_logged_in, user):
    """Users invent their own activities, so colours cannot be exhaustive."""
    custom = baker.make(Activity, name="Lab work", is_system=False, user=user)
    make_session(user, activity=custom)

    content = client_logged_in.get(CHANGELIST).content.decode()

    assert "Lab work" in content


# ---------------------------------------------------------------------------
# Data quality filter
# ---------------------------------------------------------------------------


def test_the_filter_finds_sessions_with_no_resource(client_logged_in, user):
    resource = baker.make(LearningResource, user=user, title="Algebra")
    linked = make_session(user, resource=resource, title="linked")
    loose = make_session(user, title="loose")

    found = rows(client_logged_in, {"quality": "no_resource"})

    assert loose in found
    assert linked not in found


def test_the_filter_finds_implausibly_long_sessions(client_logged_in, user):
    long_one = make_session(user, duration_minutes=241)
    normal = make_session(user, duration_minutes=240)

    found = rows(client_logged_in, {"quality": "long"})

    assert long_one in found
    assert normal not in found


def test_the_filter_finds_sessions_with_no_title(client_logged_in, user):
    untitled = make_session(user, title="")
    titled = make_session(user, title="Revision")

    found = rows(client_logged_in, {"quality": "no_title"})

    assert untitled in found
    assert titled not in found


def test_an_unknown_quality_value_does_not_narrow_the_list(client_logged_in, user):
    make_session(user)

    assert len(rows(client_logged_in, {"quality": "nonsense"})) == 1


def test_the_quality_filter_renders_as_a_dropdown(client_logged_in, user):
    make_session(user)

    content = client_logged_in.get(CHANGELIST).content.decode()

    assert "data quality" in content.lower()
    assert 'name="quality"' in content


def test_the_activity_filter_is_a_dropdown_not_a_list(client_logged_in, user):
    """Users create their own activities, so the option list has no ceiling —
    as a right-rail list of links it would grow taller than the page."""
    for i in range(30):
        custom = baker.make(Activity, name=f"Custom {i}", is_system=False, user=user)
        make_session(user, activity=custom)

    content = client_logged_in.get(CHANGELIST).content.decode()

    assert 'name="activity__id__exact"' in content
    # One <select>, not one <a> per activity.
    assert content.count('name="activity__id__exact"') == 1


def test_filtering_by_a_single_activity_still_works(client_logged_in, user):
    watching = make_session(
        user, activity=Activity.objects.get(slug="watch", is_system=True)
    )
    reading = make_session(
        user, activity=Activity.objects.get(slug="read", is_system=True)
    )

    found = rows(client_logged_in, {"activity__id__exact": watching.activity_id})

    assert watching in found
    assert reading not in found


# ---------------------------------------------------------------------------
# Query count
# ---------------------------------------------------------------------------


def test_the_changelist_does_not_query_per_row(client_logged_in, user):
    resource = baker.make(LearningResource, user=user, title="Algebra")
    unit = baker.make(LearningUnit, resource=resource, title="Vectors", order=1)
    for offset in range(20):
        make_session(
            user,
            resource=resource,
            unit=unit,
            date=TODAY - datetime.timedelta(days=offset),
        )
    client_logged_in.get(CHANGELIST)

    with CaptureQueriesContext(connection) as few:
        client_logged_in.get(CHANGELIST)

    for offset in range(20, 40):
        make_session(
            user,
            resource=resource,
            unit=unit,
            date=TODAY - datetime.timedelta(days=offset),
        )

    with CaptureQueriesContext(connection) as many:
        client_logged_in.get(CHANGELIST)

    assert len(many) == len(few)
