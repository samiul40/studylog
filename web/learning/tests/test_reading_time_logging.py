"""
Tests for the reading-time logging feature:
  - LearningUnit.reading_minutes field and to_inline_dict
  - StudySession.unit FK and to_dict
  - upsert_resource_session with unit param (per-unit session keying)
  - LearningUnitCompleteReadingView
  - LearningUnitInlinePatchView reading-uncheck path
  - Video slider → 0 session cleanup
  - StudySessionForm unit field validation
  - get_resource_progress reading-specific stats
  - Session create view with unit linked
"""

import datetime
import json

import pytest
from django.urls import reverse
from model_bakery import baker

from learning.models import Activity, LearningResource, LearningUnit, StudySession
from learning.services.progress import get_resource_progress
from learning.services.sessions import upsert_resource_session

pytestmark = pytest.mark.django_db

TODAY = datetime.date.today()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_activity(slug):
    return Activity.objects.get(slug=slug, is_system=True)


def make_reading_resource(user):
    rt = baker.make("learning.ResourceType", content_kind="reading")
    return baker.make(LearningResource, user=user, resource_type=rt)


def make_video_resource(user):
    rt = baker.make("learning.ResourceType", content_kind="video")
    return baker.make(LearningResource, user=user, resource_type=rt)


def make_chapter(resource, **kwargs):
    kwargs.setdefault("status", LearningUnit.StatusChoices.NOT_STARTED)
    return baker.make(LearningUnit, resource=resource, **kwargs)


def complete_reading(client, unit, duration):
    url = reverse("learning:unit_complete_reading", kwargs={"pk": unit.pk})
    return client.post(
        url,
        data=json.dumps({"duration_minutes": duration}),
        content_type="application/json",
    )


def patch_unit(client, resource, unit, payload):
    url = reverse(
        "learning:unit_inline_update",
        kwargs={"resource_pk": resource.pk, "unit_pk": unit.pk},
    )
    return client.post(url, data=json.dumps(payload), content_type="application/json")


# ---------------------------------------------------------------------------
# LearningUnit.reading_minutes field
# ---------------------------------------------------------------------------


class TestReadingMinutesField:
    def test_field_defaults_to_null(self, user):
        resource = make_reading_resource(user)
        unit = make_chapter(resource)

        assert unit.reading_minutes is None

    def test_field_stores_positive_value(self, user):
        resource = make_reading_resource(user)
        unit = make_chapter(resource, reading_minutes=45)

        unit.refresh_from_db()
        assert unit.reading_minutes == 45

    def test_to_inline_dict_includes_reading_minutes(self, user):
        resource = make_reading_resource(user)
        unit = make_chapter(resource, reading_minutes=30)
        d = unit.to_inline_dict()

        assert "reading_minutes" in d
        assert d["reading_minutes"] == 30

    def test_to_inline_dict_reading_minutes_null_when_unset(self, user):
        resource = make_reading_resource(user)
        unit = make_chapter(resource)
        d = unit.to_inline_dict()

        assert d["reading_minutes"] is None


# ---------------------------------------------------------------------------
# StudySession.unit FK
# ---------------------------------------------------------------------------


class TestStudySessionUnitFK:
    def test_to_dict_includes_unit_id_and_title(self, user):
        resource = make_reading_resource(user)
        unit = make_chapter(resource, title="Chapter 1")
        session = baker.make(
            StudySession,
            user=user,
            resource=resource,
            unit=unit,
            activity=get_activity("read"),
            date=TODAY,
            duration_minutes=30,
        )
        d = session.to_dict()

        assert d["unit_id"] == unit.pk
        assert d["unit_title"] == "Chapter 1"

    def test_to_dict_unit_null_when_not_set(self, user):
        resource = make_reading_resource(user)
        session = baker.make(
            StudySession,
            user=user,
            resource=resource,
            unit=None,
            activity=get_activity("flashcards"),
            date=TODAY,
            duration_minutes=30,
        )
        d = session.to_dict()

        assert d["unit_id"] is None
        assert d["unit_title"] is None

    def test_deleting_unit_sets_fk_to_null(self, user):
        resource = make_reading_resource(user)
        unit = make_chapter(resource)
        session = baker.make(
            StudySession,
            user=user,
            resource=resource,
            unit=unit,
            activity=get_activity("read"),
            date=TODAY,
            duration_minutes=20,
        )
        unit.delete()
        session.refresh_from_db()

        assert session.unit_id is None


# ---------------------------------------------------------------------------
# upsert_resource_session with unit param
# ---------------------------------------------------------------------------


class TestUpsertResourceSessionWithUnit:
    def test_creates_separate_rows_for_different_units(self, user):
        resource = make_video_resource(user)
        unit_a = make_chapter(resource)
        unit_b = make_chapter(resource)
        watch = get_activity("watch")

        upsert_resource_session(user, resource, TODAY, watch, 10, unit=unit_a)
        upsert_resource_session(user, resource, TODAY, watch, 15, unit=unit_b)

        qs = StudySession.objects.filter(user=user, resource=resource)
        assert qs.count() == 2
        assert StudySession.objects.get(unit=unit_a).duration_minutes == 10
        assert StudySession.objects.get(unit=unit_b).duration_minutes == 15

    def test_accumulates_on_same_unit_same_day(self, user):
        resource = make_video_resource(user)
        unit = make_chapter(resource)
        watch = get_activity("watch")

        upsert_resource_session(user, resource, TODAY, watch, 5, unit=unit)
        upsert_resource_session(user, resource, TODAY, watch, 10, unit=unit)

        assert StudySession.objects.get(unit=unit).duration_minutes == 15

    def test_decrement_on_same_unit_stays_isolated(self, user):
        resource = make_video_resource(user)
        unit_a = make_chapter(resource)
        unit_b = make_chapter(resource)
        watch = get_activity("watch")

        upsert_resource_session(user, resource, TODAY, watch, 20, unit=unit_a)
        upsert_resource_session(user, resource, TODAY, watch, 30, unit=unit_b)
        # Rewind unit_a — must not affect unit_b
        upsert_resource_session(user, resource, TODAY, watch, -10, unit=unit_a)

        assert StudySession.objects.get(unit=unit_a).duration_minutes == 10
        assert StudySession.objects.get(unit=unit_b).duration_minutes == 30


# ---------------------------------------------------------------------------
# LearningUnitCompleteReadingView
# ---------------------------------------------------------------------------


class TestCompleteReadingViewExtended:
    def test_session_has_unit_fk(self, client_logged_in, user):
        resource = make_reading_resource(user)
        unit = make_chapter(resource)
        complete_reading(client_logged_in, unit, 45)

        session = StudySession.objects.get(user=user, activity=get_activity("read"))
        assert session.unit == unit

    def test_reading_minutes_stored_on_unit(self, client_logged_in, user):
        resource = make_reading_resource(user)
        unit = make_chapter(resource)
        complete_reading(client_logged_in, unit, 30)

        unit.refresh_from_db()
        assert unit.reading_minutes == 30

    def test_zero_duration_sets_reading_minutes_to_null(self, client_logged_in, user):
        resource = make_reading_resource(user)
        unit = make_chapter(resource)
        complete_reading(client_logged_in, unit, 0)

        unit.refresh_from_db()
        assert unit.reading_minutes is None

    def test_re_logging_updates_existing_session(self, client_logged_in, user):
        resource = make_reading_resource(user)
        unit = make_chapter(resource)
        complete_reading(client_logged_in, unit, 20)
        complete_reading(client_logged_in, unit, 40)

        # Must stay at exactly one session for this unit
        sessions = StudySession.objects.filter(
            user=user,
            unit=unit,
            activity=get_activity("read"),
        )
        assert sessions.count() == 1
        assert sessions.first().duration_minutes == 40

    def test_two_chapters_get_separate_sessions(self, client_logged_in, user):
        resource = make_reading_resource(user)
        ch1 = make_chapter(resource)
        ch2 = make_chapter(resource)
        complete_reading(client_logged_in, ch1, 25)
        complete_reading(client_logged_in, ch2, 35)

        assert (
            StudySession.objects.filter(
                user=user, activity=get_activity("read")
            ).count()
            == 2
        )
        assert StudySession.objects.get(unit=ch1).duration_minutes == 25
        assert StudySession.objects.get(unit=ch2).duration_minutes == 35


# ---------------------------------------------------------------------------
# LearningUnitInlinePatchView — reading uncheck
# ---------------------------------------------------------------------------


class TestReadingUncheck:
    def test_uncheck_deletes_only_that_chapters_session(self, client_logged_in, user):
        resource = make_reading_resource(user)
        ch1 = make_chapter(resource, status=LearningUnit.StatusChoices.COMPLETED)
        ch2 = make_chapter(resource, status=LearningUnit.StatusChoices.COMPLETED)
        read = get_activity("read")

        # Create a session for each chapter
        baker.make(
            StudySession,
            user=user,
            resource=resource,
            unit=ch1,
            activity=read,
            date=TODAY,
            duration_minutes=20,
        )
        baker.make(
            StudySession,
            user=user,
            resource=resource,
            unit=ch2,
            activity=read,
            date=TODAY,
            duration_minutes=15,
        )

        # Uncheck ch2
        patch_unit(
            client_logged_in,
            resource,
            ch2,
            {"status": LearningUnit.StatusChoices.NOT_STARTED},
        )

        # ch1's session must survive
        assert StudySession.objects.filter(unit=ch1).exists()
        # ch2's session must be gone
        assert not StudySession.objects.filter(unit=ch2).exists()

    def test_uncheck_clears_reading_minutes(self, client_logged_in, user):
        resource = make_reading_resource(user)
        ch = make_chapter(
            resource,
            status=LearningUnit.StatusChoices.COMPLETED,
            reading_minutes=30,
        )
        patch_unit(
            client_logged_in,
            resource,
            ch,
            {"status": LearningUnit.StatusChoices.NOT_STARTED},
        )

        ch.refresh_from_db()
        assert ch.reading_minutes is None

    def test_uncheck_sets_status_to_not_started(self, client_logged_in, user):
        resource = make_reading_resource(user)
        ch = make_chapter(resource, status=LearningUnit.StatusChoices.COMPLETED)
        patch_unit(
            client_logged_in,
            resource,
            ch,
            {"status": LearningUnit.StatusChoices.NOT_STARTED},
        )

        ch.refresh_from_db()
        assert ch.status == LearningUnit.StatusChoices.NOT_STARTED


# ---------------------------------------------------------------------------
# Video slider → 0 session cleanup
# ---------------------------------------------------------------------------


class TestVideoSliderToZeroCleanup:
    def test_slider_to_zero_deletes_session(self, client_logged_in, user):
        resource = make_video_resource(user)
        unit = baker.make(
            LearningUnit,
            resource=resource,
            duration_minutes=60,
            video_progress_minutes=0,
        )
        # Move slider to 20
        patch_unit(client_logged_in, resource, unit, {"video_progress_minutes": 20})
        assert StudySession.objects.filter(
            user=user, unit=unit, activity=get_activity("watch")
        ).exists()

        # Rewind to 0
        unit.refresh_from_db()
        patch_unit(client_logged_in, resource, unit, {"video_progress_minutes": 0})

        assert not StudySession.objects.filter(
            user=user, unit=unit, activity=get_activity("watch")
        ).exists()

    def test_slider_to_zero_does_not_touch_other_units_session(
        self, client_logged_in, user
    ):
        resource = make_video_resource(user)
        unit_a = baker.make(
            LearningUnit,
            resource=resource,
            duration_minutes=60,
            video_progress_minutes=0,
        )
        unit_b = baker.make(
            LearningUnit,
            resource=resource,
            duration_minutes=60,
            video_progress_minutes=0,
        )
        patch_unit(client_logged_in, resource, unit_a, {"video_progress_minutes": 15})
        patch_unit(client_logged_in, resource, unit_b, {"video_progress_minutes": 10})

        # Rewind unit_a to 0
        unit_a.refresh_from_db()
        patch_unit(client_logged_in, resource, unit_a, {"video_progress_minutes": 0})

        # unit_b session must be untouched
        assert StudySession.objects.filter(
            user=user, unit=unit_b, activity=get_activity("watch")
        ).exists()


# ---------------------------------------------------------------------------
# StudySessionForm — unit field
# ---------------------------------------------------------------------------


class TestStudySessionFormUnitField:
    def test_unit_is_optional(self, user):
        from learning.forms import StudySessionForm

        form = StudySessionForm(
            data={
                "activity": get_activity("flashcards").pk,
                "date": str(TODAY),
                "duration_minutes": 30,
                "status": StudySession.Status.LOGGED,
            },
            user=user,
        )

        assert form.is_valid(), form.errors

    def test_unit_from_own_resource_is_valid(self, user):
        from learning.forms import StudySessionForm

        resource = make_reading_resource(user)
        unit = make_chapter(resource)

        form = StudySessionForm(
            data={
                "activity": get_activity("read").pk,
                "date": str(TODAY),
                "duration_minutes": 20,
                "status": StudySession.Status.LOGGED,
                "resource": resource.pk,
                "unit": unit.pk,
            },
            user=user,
        )

        assert form.is_valid(), form.errors

    def test_unit_from_wrong_resource_is_invalid(self, user):
        from learning.forms import StudySessionForm

        resource_a = make_reading_resource(user)
        resource_b = make_reading_resource(user)
        unit_b = make_chapter(resource_b)

        form = StudySessionForm(
            data={
                "activity": get_activity("read").pk,
                "date": str(TODAY),
                "duration_minutes": 20,
                "status": StudySession.Status.LOGGED,
                "resource": resource_a.pk,
                "unit": unit_b.pk,
            },
            user=user,
        )

        assert not form.is_valid()
        assert "unit" in form.errors

    def test_unit_queryset_scoped_to_user(self, user):
        from learning.forms import StudySessionForm

        other = baker.make("auth.User")
        my_resource = make_reading_resource(user)
        other_resource = make_reading_resource(other)
        my_unit = make_chapter(my_resource)
        other_unit = make_chapter(other_resource)

        form = StudySessionForm(user=user)
        unit_qs = form.fields["unit"].queryset

        assert my_unit in unit_qs
        assert other_unit not in unit_qs


# ---------------------------------------------------------------------------
# Session create view — unit saved on session
# ---------------------------------------------------------------------------


class TestSessionCreateWithUnit:
    def test_unit_saved_when_provided(self, client_logged_in, user):
        resource = make_reading_resource(user)
        unit = make_chapter(resource)
        url = reverse("learning:session_create")
        client_logged_in.post(
            url,
            {
                "activity": get_activity("read").pk,
                "date": str(TODAY),
                "duration_minutes": 30,
                "status": StudySession.Status.LOGGED,
                "resource": resource.pk,
                "unit": unit.pk,
            },
        )

        session = StudySession.objects.get(user=user)
        assert session.unit == unit

    def test_session_created_without_unit(self, client_logged_in, user):
        url = reverse("learning:session_create")
        client_logged_in.post(
            url,
            {
                "activity": get_activity("flashcards").pk,
                "date": str(TODAY),
                "duration_minutes": 30,
                "status": StudySession.Status.LOGGED,
            },
        )

        session = StudySession.objects.get(user=user)
        assert session.unit is None


# ---------------------------------------------------------------------------
# get_resource_progress — reading stats
# ---------------------------------------------------------------------------


class TestReadingProgressStats:
    def test_is_reading_true_for_reading_resource(self, user):
        resource = make_reading_resource(user)
        result = get_resource_progress(resource)

        assert result["is_reading"] is True

    def test_is_reading_false_for_video_resource(self, user):
        resource = make_video_resource(user)
        result = get_resource_progress(resource)

        assert result["is_reading"] is False

    def test_time_read_total_sums_reading_minutes(self, user):
        resource = make_reading_resource(user)
        make_chapter(resource, status="completed", reading_minutes=30)
        make_chapter(resource, status="completed", reading_minutes=45)
        result = get_resource_progress(resource)

        assert result["time_read_total"] == 75

    def test_time_read_total_excludes_not_started(self, user):
        resource = make_reading_resource(user)
        make_chapter(resource, status="completed", reading_minutes=20)
        make_chapter(resource, status="not_started", reading_minutes=None)
        result = get_resource_progress(resource)

        assert result["time_read_total"] == 20

    def test_time_read_total_ignores_null_reading_minutes(self, user):
        resource = make_reading_resource(user)
        # Completed without logged time (e.g. "Log without time")
        make_chapter(resource, status="completed", reading_minutes=None)
        result = get_resource_progress(resource)

        assert result["time_read_total"] == 0

    def test_chapters_with_read_counts_nonzero_reading_minutes(self, user):
        resource = make_reading_resource(user)
        make_chapter(resource, status="completed", reading_minutes=30)
        make_chapter(resource, status="completed", reading_minutes=None)
        make_chapter(resource, status="completed", reading_minutes=0)
        result = get_resource_progress(resource)

        # Only the one with reading_minutes > 0 counts
        assert result["chapters_with_read"] == 1

    def test_reading_stats_absent_for_video_resource(self, user):
        resource = make_video_resource(user)
        result = get_resource_progress(resource)

        assert result["time_read_total"] == 0
        assert result["chapters_with_read"] == 0
