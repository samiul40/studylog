import datetime

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from model_bakery import baker

from learning.models import Activity, LearningResource, LearningUnit, StudySession

pytestmark = pytest.mark.django_db

CHANGELIST = reverse("admin:learning_learningresource_changelist")
TODAY = timezone.localdate()


def make_resource(user, **kwargs):
    return baker.make(LearningResource, user=user, **kwargs)


def make_units(resource, total, completed=0):
    for i in range(total):
        baker.make(
            LearningUnit,
            resource=resource,
            order=i + 1,
            status="completed" if i < completed else "not_started",
        )


def make_session(user, resource, days_ago=0, minutes=30):
    return baker.make(
        StudySession,
        user=user,
        resource=resource,
        date=TODAY - datetime.timedelta(days=days_ago),
        activity=Activity.objects.get(slug="flashcards", is_system=True),
        duration_minutes=minutes,
        status=StudySession.Status.LOGGED,
    )


def row_for(client, resource):
    response = client.get(CHANGELIST)
    return response.context["cl"].queryset.get(pk=resource.pk)


def rows(client, params=None):
    return list(client.get(CHANGELIST, params or {}).context["cl"].queryset)


# ---------------------------------------------------------------------------
# Annotated columns
# ---------------------------------------------------------------------------


def test_progress_comes_from_the_annotation(client_logged_in, user):
    resource = make_resource(user, title="Algebra")
    make_units(resource, total=4, completed=1)

    content = client_logged_in.get(CHANGELIST).content.decode()

    assert "1/4" in content


def test_a_resource_with_no_units_reads_as_zero(client_logged_in, user):
    make_resource(user, title="Empty")

    content = client_logged_in.get(CHANGELIST).content.decode()

    assert "0%" in content


def test_the_session_columns_are_annotated(client_logged_in, user):
    resource = make_resource(user, title="Algebra")
    make_session(user, resource, days_ago=1, minutes=90)
    make_session(user, resource, days_ago=3, minutes=30)

    row = row_for(client_logged_in, resource)

    assert row.session_count == 2
    assert row.session_minutes == 120
    assert row.last_activity == TODAY - datetime.timedelta(days=1)


def test_a_resource_nobody_studied_reads_as_empty(client_logged_in, user):
    resource = make_resource(user, title="Untouched")

    row = row_for(client_logged_in, resource)

    assert row.session_count == 0
    assert row.session_minutes == 0
    assert row.last_activity is None


def test_units_do_not_inflate_the_logged_minutes(client_logged_in, user):
    """Joining units and sessions at once multiplies one by the other."""
    resource = make_resource(user, title="Algebra")
    make_units(resource, total=5, completed=2)
    make_session(user, resource, minutes=60)
    make_session(user, resource, days_ago=1, minutes=60)

    row = row_for(client_logged_in, resource)

    assert row.session_count == 2
    assert row.session_minutes == 120
    assert row.total_units == 5
    assert row.completed_units == 2


def test_sessions_do_not_inflate_the_unit_totals(client_logged_in, user):
    """The same fan-out in the other direction."""
    resource = make_resource(user, title="Algebra")
    make_units(resource, total=3, completed=3)
    for offset in range(4):
        make_session(user, resource, days_ago=offset)

    row = row_for(client_logged_in, resource)

    assert row.total_units == 3
    assert row.completed_units == 3
    assert row.percentage == 100


# ---------------------------------------------------------------------------
# Traction filter
# ---------------------------------------------------------------------------


def test_traction_finds_resources_studied_this_week(client_logged_in, user):
    recent = make_resource(user, title="Recent")
    make_session(user, recent, days_ago=2)
    old = make_resource(user, title="Old")
    make_session(user, old, days_ago=20)

    found = rows(client_logged_in, {"traction": "this_week"})

    assert recent in found
    assert old not in found


def test_traction_finds_stale_resources(client_logged_in, user):
    stale = make_resource(user, title="Stale")
    make_session(user, stale, days_ago=31)
    warm = make_resource(user, title="Warm")
    make_session(user, warm, days_ago=29)

    found = rows(client_logged_in, {"traction": "stale"})

    assert stale in found
    assert warm not in found


def test_stale_does_not_swallow_never_studied(client_logged_in, user):
    """A resource nobody opened is a different problem from an abandoned one."""
    never = make_resource(user, title="Never")
    stale = make_resource(user, title="Stale")
    make_session(user, stale, days_ago=60)

    assert never not in rows(client_logged_in, {"traction": "stale"})
    assert never in rows(client_logged_in, {"traction": "never"})


def test_traction_finds_never_studied_resources(client_logged_in, user):
    never = make_resource(user, title="Never")
    studied = make_resource(user, title="Studied")
    make_session(user, studied)

    found = rows(client_logged_in, {"traction": "never"})

    assert never in found
    assert studied not in found


def test_traction_finds_completed_resources(client_logged_in, user):
    done = make_resource(user, title="Done")
    make_units(done, total=3, completed=3)
    partial = make_resource(user, title="Partial")
    make_units(partial, total=3, completed=2)

    found = rows(client_logged_in, {"traction": "completed"})

    assert done in found
    assert partial not in found


def test_an_empty_resource_does_not_count_as_completed(client_logged_in, user):
    """Nothing to finish is not the same as having finished it."""
    empty = make_resource(user, title="Empty")

    assert empty not in rows(client_logged_in, {"traction": "completed"})


# ---------------------------------------------------------------------------
# Query count
# ---------------------------------------------------------------------------


def test_the_changelist_does_not_query_per_row(client_logged_in, user):
    for i in range(10):
        resource = make_resource(user, title=f"Resource {i}")
        make_units(resource, total=3, completed=1)
        make_session(user, resource)
    client_logged_in.get(CHANGELIST)

    with CaptureQueriesContext(connection) as few:
        client_logged_in.get(CHANGELIST)

    for i in range(10, 30):
        resource = make_resource(user, title=f"Resource {i}")
        make_units(resource, total=3, completed=1)
        make_session(user, resource)

    with CaptureQueriesContext(connection) as many:
        client_logged_in.get(CHANGELIST)

    assert len(many) == len(few)
