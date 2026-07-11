"""
Tests for the v3 dashboard analytics features.

Covers: forecast methodology, study streak, month stats,
stale-resource detection, and the completed_at backfill migration.
"""

import datetime

import pytest
from django.utils import timezone
from model_bakery import baker

from learning.models import (
    Activity,
    LearningResource,
    LearningUnit,
    ResourceType,
    StudySession,
)
from learning.services.dashboard import (
    _build_greeting_headline,
    _get_backlog,
    _get_heatmap_by_session_minutes,
    _get_momentum_v2,
    _get_month_stats,
    _get_stale_resources,
    _get_study_streak_unified,
    _get_video_time_invested,
    _get_weekly_activity,
)
from learning.services.utils import fmt_duration as _fmt_duration

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def video_rt():
    rt, _ = ResourceType.objects.get_or_create(
        slug="youtube",
        defaults={"name": "YouTube", "content_kind": "video"},
    )
    return rt


@pytest.fixture
def reading_rt():
    rt, _ = ResourceType.objects.get_or_create(
        slug="book",
        defaults={"name": "Book", "content_kind": "reading"},
    )
    return rt


@pytest.fixture
def resource(user, video_rt):
    return baker.make(
        LearningResource, user=user, resource_type=video_rt, is_archived=False
    )


def _user_unit_qs(user):
    return LearningUnit.objects.filter(
        resource__is_archived=False,
        resource__user=user,
    )


def _user_resource_qs(user):
    return LearningResource.objects.filter(user=user, is_archived=False)


def _completed(resource, completed_at, duration_minutes=None):
    """Create a completed unit with explicit completed_at."""
    unit = baker.make(
        LearningUnit,
        resource=resource,
        status="completed",
        duration_minutes=duration_minutes,
    )
    LearningUnit.objects.filter(pk=unit.pk).update(completed_at=completed_at)
    return unit


def _days_ago(n):
    return timezone.now() - datetime.timedelta(days=n)


def _weeks_ago(n):
    return timezone.now() - datetime.timedelta(weeks=n)


# ---------------------------------------------------------------------------
# _fmt_duration
# ---------------------------------------------------------------------------


class TestFmtDuration:
    def test_zero_returns_dash(self):
        assert _fmt_duration(0) == "—"

    def test_none_returns_dash(self):
        assert _fmt_duration(None) == "—"

    def test_minutes_only(self):
        assert _fmt_duration(45) == "45m"

    def test_hours_only(self):
        assert _fmt_duration(120) == "2h"

    def test_hours_and_minutes(self):
        assert _fmt_duration(130) == "2h 10m"


# ---------------------------------------------------------------------------
# _get_study_streak
# ---------------------------------------------------------------------------


class TestStudyStreak:
    def test_no_activity_returns_zero(self, user, resource):
        assert _get_study_streak_unified(_user_unit_qs(user), user) == 0

    def test_single_today_is_streak_of_1(self, user, resource):
        _completed(resource, timezone.now())
        assert _get_study_streak_unified(_user_unit_qs(user), user) == 1

    def test_consecutive_days_counted(self, user, resource):
        for n in range(4):
            _completed(resource, _days_ago(n))
        assert _get_study_streak_unified(_user_unit_qs(user), user) == 4

    def test_gap_breaks_streak(self, user, resource):
        # Day 0, 1, then skip 2, day 3 — streak from today = 2
        _completed(resource, _days_ago(0))
        _completed(resource, _days_ago(1))
        _completed(resource, _days_ago(3))
        assert _get_study_streak_unified(_user_unit_qs(user), user) == 2

    def test_streak_starts_yesterday_when_today_empty(self, user, resource):
        # Yesterday and two days ago active, but not today
        _completed(resource, _days_ago(1))
        _completed(resource, _days_ago(2))
        assert _get_study_streak_unified(_user_unit_qs(user), user) == 2

    def test_multiple_units_same_day_count_once(self, user, resource):
        now = timezone.now()
        _completed(resource, now)
        _completed(resource, now)
        assert _get_study_streak_unified(_user_unit_qs(user), user) == 1

    def test_future_completed_at_not_counted(self, user, resource):
        future = timezone.now() + datetime.timedelta(days=2)
        _completed(resource, future)
        assert _get_study_streak_unified(_user_unit_qs(user), user) == 0

    def test_video_progress_today_counts_as_active(self, user, resource):
        unit = baker.make(
            LearningUnit,
            resource=resource,
            status="in_progress",
            duration_minutes=60,
        )
        LearningUnit.objects.filter(pk=unit.pk).update(
            video_progress_minutes=5, updated_at=timezone.now()
        )
        assert _get_study_streak_unified(_user_unit_qs(user), user) == 1

    def test_video_progress_consecutive_days_builds_streak(self, user, resource):
        for n in range(3):
            unit = baker.make(
                LearningUnit,
                resource=resource,
                status="in_progress",
                duration_minutes=60,
            )
            LearningUnit.objects.filter(pk=unit.pk).update(
                video_progress_minutes=10, updated_at=_days_ago(n)
            )
        assert _get_study_streak_unified(_user_unit_qs(user), user) == 3

    def test_zero_progress_not_counted(self, user, resource):
        unit = baker.make(
            LearningUnit,
            resource=resource,
            status="not_started",
            duration_minutes=60,
        )
        LearningUnit.objects.filter(pk=unit.pk).update(
            video_progress_minutes=0, updated_at=timezone.now()
        )
        assert _get_study_streak_unified(_user_unit_qs(user), user) == 0

    def test_progress_and_completion_on_different_days_union(self, user, resource):
        # Completion 2 days ago, video progress yesterday — should give streak of 2
        _completed(resource, _days_ago(2))
        unit = baker.make(
            LearningUnit,
            resource=resource,
            status="in_progress",
            duration_minutes=60,
        )
        LearningUnit.objects.filter(pk=unit.pk).update(
            video_progress_minutes=15, updated_at=_days_ago(1)
        )
        assert _get_study_streak_unified(_user_unit_qs(user), user) == 2

    def test_logged_session_today_builds_streak(self, user, resource):
        """A logged session alone (no unit activity) counts toward the streak."""
        act, _ = Activity.objects.get_or_create(
            slug="flashcards",
            defaults={"name": "Flashcards / Anki", "is_system": True},
        )
        baker.make(
            StudySession,
            user=user,
            activity=act,
            status="logged",
            date=datetime.date.today(),
            duration_minutes=30,
        )
        assert _get_study_streak_unified(_user_unit_qs(user), user) == 1


# ---------------------------------------------------------------------------
# _get_month_stats — started vs finished
# ---------------------------------------------------------------------------


class TestMonthStats:
    def test_no_activity_returns_zeros(self, user):
        s, f = _get_month_stats(_user_resource_qs(user))
        assert s == 0 and f == 0

    def test_resource_created_this_month_is_started(self, user, video_rt):
        baker.make(
            LearningResource, user=user, resource_type=video_rt, is_archived=False
        )
        s, _ = _get_month_stats(_user_resource_qs(user))
        assert s == 1

    def test_resource_created_last_month_not_started(self, user, video_rt):
        now = timezone.localtime()
        last_month = now.replace(day=1) - datetime.timedelta(days=1)
        r = baker.make(
            LearningResource, user=user, resource_type=video_rt, is_archived=False
        )
        LearningResource.objects.filter(pk=r.pk).update(created_at=last_month)
        s, _ = _get_month_stats(_user_resource_qs(user))
        assert s == 0

    def test_resource_all_units_done_this_month_is_finished(self, user, video_rt):
        r = baker.make(
            LearningResource, user=user, resource_type=video_rt, is_archived=False
        )
        unit = baker.make(LearningUnit, resource=r, status="completed")
        LearningUnit.objects.filter(pk=unit.pk).update(completed_at=timezone.now())
        _, f = _get_month_stats(_user_resource_qs(user))
        assert f == 1

    def test_partially_done_resource_not_finished(self, user, video_rt):
        r = baker.make(
            LearningResource, user=user, resource_type=video_rt, is_archived=False
        )
        _completed(r, timezone.now())
        baker.make(LearningUnit, resource=r, status="not_started")
        _, f = _get_month_stats(_user_resource_qs(user))
        assert f == 0

    def test_finished_last_month_not_counted(self, user, video_rt):
        r = baker.make(
            LearningResource, user=user, resource_type=video_rt, is_archived=False
        )
        unit = baker.make(LearningUnit, resource=r, status="completed")
        last_month = timezone.localtime().replace(day=1) - datetime.timedelta(days=1)
        LearningUnit.objects.filter(pk=unit.pk).update(completed_at=last_month)
        _, f = _get_month_stats(_user_resource_qs(user))
        assert f == 0


# ---------------------------------------------------------------------------
# _get_stale_resources — 14-day idle threshold
# ---------------------------------------------------------------------------


class TestStaleResources:
    def test_no_stale_resources_when_all_recent(self, user, resource):
        _completed(resource, _days_ago(3))
        baker.make(LearningUnit, resource=resource, status="not_started")
        result = _get_stale_resources(_user_resource_qs(user))
        assert result == []

    def test_exactly_14_days_is_stale(self, user, resource):
        # Must have an unfinished unit so the resource counts as "in progress"
        _completed(resource, _days_ago(14))
        baker.make(LearningUnit, resource=resource, status="not_started")
        result = _get_stale_resources(_user_resource_qs(user))
        assert len(result) == 1
        assert result[0]["idle_days"] == 14

    def test_13_days_is_not_stale(self, user, resource):
        _completed(resource, _days_ago(13))
        baker.make(LearningUnit, resource=resource, status="not_started")
        result = _get_stale_resources(_user_resource_qs(user))
        assert result == []

    def test_completed_resource_not_included(self, user, resource):
        # All units done — resource is complete, not stale
        unit = baker.make(LearningUnit, resource=resource, status="completed")
        LearningUnit.objects.filter(pk=unit.pk).update(completed_at=_days_ago(30))
        result = _get_stale_resources(_user_resource_qs(user))
        assert result == []

    def test_max_3_returned(self, user, video_rt):
        for _ in range(5):
            r = baker.make(
                LearningResource,
                user=user,
                resource_type=video_rt,
                is_archived=False,
            )
            _completed(r, _days_ago(20))
            baker.make(LearningUnit, resource=r, status="not_started")
        result = _get_stale_resources(_user_resource_qs(user))
        assert len(result) <= 3

    def test_most_idle_first(self, user, video_rt):
        r1 = baker.make(
            LearningResource,
            user=user,
            resource_type=video_rt,
            is_archived=False,
        )
        r2 = baker.make(
            LearningResource,
            user=user,
            resource_type=video_rt,
            is_archived=False,
        )
        _completed(r1, _days_ago(30))
        baker.make(LearningUnit, resource=r1, status="not_started")
        _completed(r2, _days_ago(20))
        baker.make(LearningUnit, resource=r2, status="not_started")

        result = _get_stale_resources(_user_resource_qs(user))

        assert result[0]["idle_days"] >= result[1]["idle_days"]


# ---------------------------------------------------------------------------
# _get_backlog
# ---------------------------------------------------------------------------


class TestBacklog:
    def test_empty_returns_zeros(self, user):
        b = _get_backlog(_user_unit_qs(user))
        assert b["total"] == 0
        assert b["pct"] == 0

    def test_correct_counts(self, user, resource):
        baker.make(LearningUnit, resource=resource, status="completed", _quantity=3)
        baker.make(LearningUnit, resource=resource, status="in_progress", _quantity=2)
        baker.make(LearningUnit, resource=resource, status="not_started", _quantity=5)
        b = _get_backlog(_user_unit_qs(user))
        assert b["total"] == 10
        assert b["completed"] == 3
        assert b["in_progress"] == 2
        assert b["not_started"] == 5
        assert b["pct"] == 30


# ---------------------------------------------------------------------------
# _get_video_time_invested
# ---------------------------------------------------------------------------


class TestTimeInvested:
    def test_none_user_returns_dashes(self):
        t = _get_video_time_invested(None)
        assert t["this_week"] == "—"
        assert t["this_month"] == "—"
        assert t["all_time"] == "—"

    def test_this_week_sums_video_units(self, user, resource):
        unit = baker.make(
            LearningUnit,
            resource=resource,
            status="completed",
            duration_minutes=90,
        )
        LearningUnit.objects.filter(pk=unit.pk).update(completed_at=timezone.now())
        t = _get_video_time_invested(user)
        assert t["resource_this_week"] == 90
        assert t["this_week"] == "1h 30m"

    def test_excludes_reading_type(self, user, reading_rt):
        r = baker.make(
            LearningResource, user=user, resource_type=reading_rt, is_archived=False
        )
        unit = baker.make(
            LearningUnit, resource=r, status="completed", duration_minutes=60
        )
        LearningUnit.objects.filter(pk=unit.pk).update(completed_at=timezone.now())
        t = _get_video_time_invested(user)
        assert t["resource_this_week"] == 0


# ---------------------------------------------------------------------------
# _get_weekly_activity — height proportions
# ---------------------------------------------------------------------------


class TestWeeklyActivity:
    def test_returns_8_entries(self, user, resource):
        result = _get_weekly_activity(_user_unit_qs(user))
        assert len(result) == 8

    def test_current_week_flagged(self, user, resource):
        result = _get_weekly_activity(_user_unit_qs(user))
        current = [w for w in result if w["is_current"]]
        assert len(current) == 1

    def test_max_week_has_100_height(self, user, resource):
        _completed(resource, timezone.now())
        result = _get_weekly_activity(_user_unit_qs(user))
        # the week with count=1 should have height_pct=100 (it's the max)
        assert result[-1]["height_pct"] == 100

    def test_empty_weeks_have_zero_height(self, user, resource):
        result = _get_weekly_activity(_user_unit_qs(user))
        assert all(w["height_pct"] == 0 for w in result)


# ---------------------------------------------------------------------------
# _get_heatmap — structure
# ---------------------------------------------------------------------------


def _make_session(user, date, duration_minutes=60):
    """Helper: create a logged StudySession for heatmap/streak tests."""
    act, _ = Activity.objects.get_or_create(
        slug="flashcards",
        defaults={"name": "Flashcards / Anki", "is_system": True},
    )
    return baker.make(
        StudySession,
        user=user,
        activity=act,
        status="logged",
        date=date,
        duration_minutes=duration_minutes,
    )


class TestHeatmap:
    def test_has_correct_year(self, user):
        h = _get_heatmap_by_session_minutes(user)
        assert h["year"] == timezone.localdate().year

    def test_has_12_month_labels(self, user):
        h = _get_heatmap_by_session_minutes(user)
        assert len(h["month_labels"]) == 12

    def test_each_week_has_7_days(self, user):
        h = _get_heatmap_by_session_minutes(user)
        assert all(len(week) == 7 for week in h["weeks"])

    def test_session_today_increments_active_days(self, user):
        _make_session(user, datetime.date.today(), duration_minutes=45)
        h = _get_heatmap_by_session_minutes(user)
        assert h["active_days"] == 1

    def test_level_thresholds(self, user):
        today = datetime.date.today()
        # 45m < 90 → level 2
        _make_session(user, today, duration_minutes=45)
        h = _get_heatmap_by_session_minutes(user)
        todays_cell = next(
            cell
            for week in h["weeks"]
            for cell in week
            if cell["date"] == today.isoformat()
        )
        assert todays_cell["level"] == 2

    def test_future_cells_are_level_zero(self, user):
        future = datetime.date.today() + datetime.timedelta(days=5)
        h = _get_heatmap_by_session_minutes(user)
        for week in h["weeks"]:
            for cell in week:
                if cell.get("date") == future.isoformat():
                    assert cell["level"] == 0


# ---------------------------------------------------------------------------
# _get_momentum
# ---------------------------------------------------------------------------


class TestMomentum:
    """Tests for _get_momentum_v2 (sessions-based momentum card)."""

    def _stats(self, this_count, last_count, this_mins=0, last_mins=0):
        return {
            "this_week_count": this_count,
            "last_week_count": last_count,
            "this_week_mins": this_mins,
            "last_week_mins": last_mins,
        }

    def test_zero_last_week_gives_new(self):
        m = _get_momentum_v2(self._stats(3, 0))
        assert m["sess_delta_dir"] == "new"

    def test_improvement_gives_up(self):
        m = _get_momentum_v2(self._stats(5, 3))
        assert m["sess_delta_dir"] == "up"
        assert m["sess_this_week"] == 5
        assert m["sess_last_week"] == 3

    def test_regression_gives_down(self):
        m = _get_momentum_v2(self._stats(1, 4))
        assert m["sess_delta_dir"] == "down"

    def test_time_comes_from_sessions(self):
        m = _get_momentum_v2(self._stats(2, 2, this_mins=30, last_mins=20))
        assert m["time_this_week"] == 30
        assert m["time_last_week"] == 20

    def test_bar_widths_proportional(self):
        m = _get_momentum_v2(self._stats(4, 2))
        assert m["sess_this_pct"] == 100
        assert m["sess_last_pct"] == 50


# ---------------------------------------------------------------------------
# _get_greeting_headline
# ---------------------------------------------------------------------------


class TestGreetingHeadline:
    def test_zero_zero_shows_plural(self):
        h = _build_greeting_headline(0, 0)
        assert "0 units" in h
        assert "0 sessions" in h

    def test_singular_unit(self):
        h = _build_greeting_headline(1, 3)
        assert "1 unit" in h
        assert "3 sessions" in h

    def test_singular_session(self):
        h = _build_greeting_headline(2, 1)
        assert "2 units" in h
        assert "1 session" in h

    def test_plural_both(self):
        h = _build_greeting_headline(5, 7)
        assert "5 units" in h
        assert "7 sessions" in h

    def test_includes_this_week(self):
        h = _build_greeting_headline(1, 1)
        assert "this week" in h


# ---------------------------------------------------------------------------
# Migration: completed_at backfill
# ---------------------------------------------------------------------------


class TestCompletedAtBackfill:
    def test_backfill_sets_completed_at_from_updated_at(self, user, resource):
        """
        The 0019 migration sets completed_at = updated_at for completed units
        that had a null completed_at (i.e. pre-migration records).
        """
        unit = baker.make(LearningUnit, resource=resource, status="completed")
        past = _days_ago(30)
        # Simulate a pre-migration row: null completed_at, old updated_at
        LearningUnit.objects.filter(pk=unit.pk).update(
            completed_at=None,
            updated_at=past,
        )
        unit.refresh_from_db()
        assert unit.completed_at is None

        # Run the backfill logic directly (mirrors the migration)
        from django.db.models import F as DjangoF

        LearningUnit.objects.filter(
            status="completed",
            completed_at__isnull=True,
        ).update(completed_at=DjangoF("updated_at"))

        unit.refresh_from_db()
        assert unit.completed_at is not None
        assert unit.completed_at.date() == past.date()

    def test_backfill_does_not_overwrite_existing_completed_at(self, user, resource):
        """Rows that already have completed_at are left untouched."""
        specific_time = _days_ago(10)
        unit = baker.make(LearningUnit, resource=resource, status="completed")
        LearningUnit.objects.filter(pk=unit.pk).update(
            completed_at=specific_time,
        )

        from django.db.models import F as DjangoF

        LearningUnit.objects.filter(
            status="completed",
            completed_at__isnull=True,
        ).update(completed_at=DjangoF("updated_at"))

        unit.refresh_from_db()
        assert unit.completed_at.date() == specific_time.date()
