import datetime
import json

import pytest
from django.urls import reverse
from model_bakery import baker

from learning.models import LearningResource, LearningUnit, StudySession
from learning.services.sessions import upsert_resource_session

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TODAY = datetime.date.today()
YESTERDAY = TODAY - datetime.timedelta(days=1)
TOMORROW = TODAY + datetime.timedelta(days=1)


def make_session(user, **kwargs):
    kwargs.setdefault("date", TODAY)
    kwargs.setdefault("activity_type", StudySession.ActivityType.FLASHCARDS)
    kwargs.setdefault("duration_minutes", 30)
    kwargs.setdefault("status", StudySession.Status.LOGGED)
    return baker.make(StudySession, user=user, **kwargs)


def patch_unit(client, resource, unit, payload):
    """POST a JSON patch to the inline-update endpoint for a unit."""
    url = reverse(
        "learning:unit_inline_update",
        kwargs={"resource_pk": resource.pk, "unit_pk": unit.pk},
    )
    return client.post(url, data=json.dumps(payload), content_type="application/json")


def complete_reading(client, unit, duration):
    """POST to the reading-completion endpoint."""
    url = reverse("learning:unit_complete_reading", kwargs={"pk": unit.pk})
    return client.post(
        url,
        data=json.dumps({"duration_minutes": duration}),
        content_type="application/json",
    )


# ---------------------------------------------------------------------------
# Model / queryset
# ---------------------------------------------------------------------------


class TestStudySessionModel:
    def test_str_with_topic(self, user):
        session = make_session(user, topic="Glycolysis", date=TODAY)

        assert "Glycolysis" in str(session)
        assert str(TODAY) in str(session)

    def test_str_no_topic_fallback(self, user):
        session = make_session(user, topic="")

        assert "(no topic)" in str(session)

    def test_ordering_newest_date_first(self, user):
        s1 = make_session(user, date=YESTERDAY)
        s2 = make_session(user, date=TODAY)
        sessions = list(StudySession.objects.for_user(user))

        assert sessions[0].pk == s2.pk
        assert sessions[1].pk == s1.pk

    def test_for_user_excludes_other_users(self, user):
        other = baker.make("auth.User")
        make_session(user)
        make_session(other)

        assert StudySession.objects.for_user(user).count() == 1

    def test_for_month_filters_correctly(self, user):
        make_session(user, date=datetime.date(TODAY.year, TODAY.month, 1))
        make_session(user, date=datetime.date(TODAY.year - 1, TODAY.month, 1))
        qs = StudySession.objects.for_user(user).for_month(TODAY.year, TODAY.month)

        assert qs.count() == 1

    def test_to_dict_with_resource(self, user):
        resource = baker.make(LearningResource, user=user, title="Physics")
        session = make_session(user, resource=resource)
        d = session.to_dict()

        assert d["resource_id"] == resource.pk
        assert d["resource_title"] == "Physics"
        assert d["status"] in (StudySession.Status.LOGGED, StudySession.Status.PLANNED)

    def test_to_dict_without_resource(self, user):
        session = make_session(user, resource=None)
        d = session.to_dict()

        assert d["resource_id"] is None
        assert d["resource_title"] is None


# ---------------------------------------------------------------------------
# Service: upsert_resource_session
# ---------------------------------------------------------------------------


class TestUpsertResourceSession:
    def setup_method(self):
        self.activity = StudySession.ActivityType.VIDEO_WATCH

    def test_creates_new_session(self, user):
        resource = baker.make(LearningResource, user=user)
        session = upsert_resource_session(user, resource, TODAY, self.activity, 10)

        assert session is not None
        assert session.duration_minutes == 10

    def test_increments_same_day(self, user):
        resource = baker.make(LearningResource, user=user)
        upsert_resource_session(user, resource, TODAY, self.activity, 5)
        upsert_resource_session(user, resource, TODAY, self.activity, 15)
        session = StudySession.objects.get(user=user, resource=resource, date=TODAY)

        assert session.duration_minutes == 20

    def test_creates_new_record_different_day(self, user):
        resource = baker.make(LearningResource, user=user)
        upsert_resource_session(user, resource, YESTERDAY, self.activity, 20)
        upsert_resource_session(user, resource, TODAY, self.activity, 10)

        assert StudySession.objects.filter(user=user, resource=resource).count() == 2

    def test_negative_delta_decrements_session(self, user):
        resource = baker.make(LearningResource, user=user)
        upsert_resource_session(user, resource, TODAY, self.activity, 20)
        upsert_resource_session(user, resource, TODAY, self.activity, -10)
        session = StudySession.objects.get(user=user, resource=resource, date=TODAY)

        assert session.duration_minutes == 10

    def test_negative_delta_floored_at_zero(self, user):
        resource = baker.make(LearningResource, user=user)
        upsert_resource_session(user, resource, TODAY, self.activity, 5)
        upsert_resource_session(user, resource, TODAY, self.activity, -20)
        session = StudySession.objects.get(user=user, resource=resource, date=TODAY)

        assert session.duration_minutes == 0

    def test_negative_delta_no_session_is_noop(self, user):
        resource = baker.make(LearningResource, user=user)
        result = upsert_resource_session(user, resource, TODAY, self.activity, -10)

        assert result is None
        assert not StudySession.objects.filter(user=user, resource=resource).exists()

    def test_zero_duration_creates_session(self, user):
        resource = baker.make(LearningResource, user=user)
        session = upsert_resource_session(
            user, resource, TODAY, StudySession.ActivityType.READING, 0
        )

        assert session is not None
        assert session.duration_minutes == 0

    def test_none_skipped(self, user):
        resource = baker.make(LearningResource, user=user)
        result = upsert_resource_session(user, resource, TODAY, self.activity, None)

        assert result is None
        assert not StudySession.objects.filter(user=user, resource=resource).exists()


# ---------------------------------------------------------------------------
# Form
# ---------------------------------------------------------------------------


class TestStudySessionForm:
    def test_valid_minimal(self, user):
        from learning.forms import StudySessionForm

        form = StudySessionForm(
            data={
                "activity_type": StudySession.ActivityType.FLASHCARDS,
                "date": str(TODAY),
                "duration_minutes": 30,
                "status": StudySession.Status.LOGGED,
            },
            user=user,
        )

        assert form.is_valid(), form.errors

    def test_future_date_invalid_for_logged(self, user):
        from learning.forms import StudySessionForm

        form = StudySessionForm(
            data={
                "activity_type": StudySession.ActivityType.FLASHCARDS,
                "date": str(TOMORROW),
                "duration_minutes": 30,
                "status": StudySession.Status.LOGGED,
            },
            user=user,
        )

        assert not form.is_valid()
        assert "date" in form.errors

    def test_future_date_valid_for_planned(self, user):
        from learning.forms import StudySessionForm

        form = StudySessionForm(
            data={
                "activity_type": StudySession.ActivityType.FLASHCARDS,
                "date": str(TOMORROW),
                "duration_minutes": 30,
                "status": StudySession.Status.PLANNED,
            },
            user=user,
        )

        assert form.is_valid(), form.errors

    def test_zero_duration_invalid(self, user):
        from learning.forms import StudySessionForm

        form = StudySessionForm(
            data={
                "activity_type": StudySession.ActivityType.FLASHCARDS,
                "date": str(TODAY),
                "duration_minutes": 0,
                "status": StudySession.Status.LOGGED,
            },
            user=user,
        )

        assert not form.is_valid()
        assert "duration_minutes" in form.errors

    def test_resource_queryset_scoped_to_user(self, user):
        from learning.forms import StudySessionForm

        other = baker.make("auth.User")
        my_resource = baker.make(LearningResource, user=user)
        baker.make(LearningResource, user=other)
        form = StudySessionForm(user=user)
        qs = form.fields["resource"].queryset

        assert my_resource in qs
        assert qs.count() == 1


# ---------------------------------------------------------------------------
# Unit view hooks
# ---------------------------------------------------------------------------


class TestVideoSessionAutoLog:
    def _make_video_unit(self, user):
        resource = baker.make(LearningResource, user=user)
        unit = baker.make(
            LearningUnit,
            resource=resource,
            duration_minutes=60,
            video_progress_minutes=0,
        )
        return resource, unit

    def test_slider_increase_creates_session(self, client_logged_in, user):
        resource, unit = self._make_video_unit(user)
        patch_unit(client_logged_in, resource, unit, {"video_progress_minutes": 15})

        assert StudySession.objects.filter(
            user=user,
            resource=resource,
            activity_type=StudySession.ActivityType.VIDEO_WATCH,
        ).exists()
        session = StudySession.objects.get(user=user, resource=resource)
        assert session.duration_minutes == 15

    def test_slider_second_move_same_day_accumulates(self, client_logged_in, user):
        resource, unit = self._make_video_unit(user)
        patch_unit(client_logged_in, resource, unit, {"video_progress_minutes": 10})
        unit.refresh_from_db()
        patch_unit(client_logged_in, resource, unit, {"video_progress_minutes": 25})
        session = StudySession.objects.get(user=user, resource=resource)

        assert session.duration_minutes == 25  # 10 + 15

    def test_slider_backward_decrements_session(self, client_logged_in, user):
        resource, unit = self._make_video_unit(user)
        patch_unit(client_logged_in, resource, unit, {"video_progress_minutes": 20})
        unit.refresh_from_db()
        patch_unit(client_logged_in, resource, unit, {"video_progress_minutes": 10})
        session = StudySession.objects.get(user=user, resource=resource)

        assert session.duration_minutes == 10


class TestCompleteReadingView:
    def test_marks_unit_complete_and_logs_session(self, client_logged_in, user):
        resource = baker.make(LearningResource, user=user)
        unit = baker.make(
            LearningUnit,
            resource=resource,
            status=LearningUnit.StatusChoices.NOT_STARTED,
        )
        resp = complete_reading(client_logged_in, unit, 45)

        assert resp.status_code == 200
        unit.refresh_from_db()
        assert unit.status == LearningUnit.StatusChoices.COMPLETED
        session = StudySession.objects.get(user=user, resource=resource)
        assert session.duration_minutes == 45
        assert session.activity_type == StudySession.ActivityType.READING

    def test_zero_duration_still_creates_session(self, client_logged_in, user):
        resource = baker.make(LearningResource, user=user)
        unit = baker.make(LearningUnit, resource=resource)
        complete_reading(client_logged_in, unit, 0)

        assert StudySession.objects.filter(user=user, resource=resource).exists()

    def test_other_user_gets_404(self, client_logged_in, user):
        other = baker.make("auth.User")
        resource = baker.make(LearningResource, user=other)
        unit = baker.make(LearningUnit, resource=resource)
        resp = complete_reading(client_logged_in, unit, 20)

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Session CRUD views
# ---------------------------------------------------------------------------


class TestStudySessionCreateView:
    def test_creates_session_for_current_user(self, client_logged_in, user):
        url = reverse("learning:session_create")
        resp = client_logged_in.post(
            url,
            {
                "activity_type": StudySession.ActivityType.FLASHCARDS,
                "date": str(TODAY),
                "duration_minutes": 30,
                "status": StudySession.Status.LOGGED,
            },
        )

        assert resp.status_code == 302
        session = StudySession.objects.get()
        assert session.user == user

    def test_unauthenticated_redirects(self, client):
        url = reverse("learning:session_create")
        resp = client.post(url, {})

        assert resp.status_code == 302
        assert "login" in resp["Location"].lower() or resp["Location"].startswith("/")

    def test_invalid_form_does_not_create(self, client_logged_in, user):
        url = reverse("learning:session_create")
        # Templates aren't built yet; suppress render exception to isolate the
        # behaviour we care about: form_invalid must not create a DB record.
        client_logged_in.raise_request_exception = False
        client_logged_in.post(url, {"duration_minutes": 0})

        assert not StudySession.objects.exists()


class TestStudySessionUpdateView:
    def test_can_edit_own_session(self, client_logged_in, user):
        session = make_session(user, duration_minutes=20)
        url = reverse("learning:session_update", kwargs={"pk": session.pk})
        resp = client_logged_in.post(
            url,
            {
                "activity_type": session.activity_type,
                "date": str(session.date),
                "duration_minutes": 45,
                "status": session.status,
            },
        )

        assert resp.status_code == 302
        session.refresh_from_db()
        assert session.duration_minutes == 45

    def test_other_users_session_returns_404(self, client_logged_in, user):
        other = baker.make("auth.User")
        session = make_session(other)
        url = reverse("learning:session_update", kwargs={"pk": session.pk})
        resp = client_logged_in.post(url, {"duration_minutes": 99})

        assert resp.status_code == 404


class TestStudySessionDeleteView:
    def test_can_delete_own_session(self, client_logged_in, user):
        session = make_session(user)
        url = reverse("learning:session_delete", kwargs={"pk": session.pk})
        resp = client_logged_in.post(url)

        assert resp.status_code == 302
        assert not StudySession.objects.filter(pk=session.pk).exists()

    def test_other_users_session_returns_404(self, client_logged_in, user):
        other = baker.make("auth.User")
        session = make_session(other)
        url = reverse("learning:session_delete", kwargs={"pk": session.pk})
        resp = client_logged_in.post(url)

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Calendar / day AJAX views
# ---------------------------------------------------------------------------


class TestStudySessionCalendarView:
    def test_missing_params_returns_400(self, client_logged_in):
        url = reverse("learning:session_calendar")
        resp = client_logged_in.get(url)

        assert resp.status_code == 400

    def test_returns_correct_per_day_totals(self, client_logged_in, user):
        make_session(user, date=TODAY, duration_minutes=30)
        make_session(user, date=TODAY, duration_minutes=20)
        url = reverse("learning:session_calendar")
        resp = client_logged_in.get(url, {"year": TODAY.year, "month": TODAY.month})
        data = resp.json()
        today_cell = next(
            day for day in data["days"] if day["date"] == TODAY.isoformat()
        )

        assert resp.status_code == 200
        assert today_cell["done_minutes"] == 50

    def test_other_users_sessions_excluded(self, client_logged_in, user):
        other = baker.make("auth.User")
        make_session(other, date=TODAY, duration_minutes=999)
        url = reverse("learning:session_calendar")
        resp = client_logged_in.get(url, {"year": TODAY.year, "month": TODAY.month})
        data = resp.json()

        assert data["total_minutes"] == 0


class TestStudySessionDayView:
    def test_bad_date_returns_400(self, client_logged_in):
        url = reverse("learning:session_day")
        resp = client_logged_in.get(url, {"date": "not-a-date"})

        assert resp.status_code == 400

    def test_returns_sessions_for_date(self, client_logged_in, user):
        make_session(user, date=TODAY, duration_minutes=25)
        url = reverse("learning:session_day")
        resp = client_logged_in.get(url, {"date": TODAY.isoformat()})
        data = resp.json()

        assert resp.status_code == 200
        assert data["day_done_count"] == 1
        assert data["day_total_minutes"] == 25

    def test_empty_when_no_sessions(self, client_logged_in, user):
        url = reverse("learning:session_day")
        resp = client_logged_in.get(url, {"date": TODAY.isoformat()})
        data = resp.json()

        assert data["day_done_count"] == 0

    def test_other_users_sessions_excluded(self, client_logged_in, user):
        other = baker.make("auth.User")
        make_session(other, date=TODAY, duration_minutes=60)
        url = reverse("learning:session_day")
        resp = client_logged_in.get(url, {"date": TODAY.isoformat()})
        data = resp.json()

        assert data["day_done_count"] == 0
