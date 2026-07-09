import datetime

import pytest
from django.utils import timezone
from model_bakery import baker

from learning.models import LearningResource, LearningUnit, ResourceType
from learning.services.dashboard import (
    _get_resource_types_with_counts,
    _get_weekly_summary,
    get_dashboard_stats,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def resource(user):
    return baker.make(LearningResource, user=user, is_archived=False)


def _user_unit_qs(user):
    return LearningUnit.objects.filter(
        resource__is_archived=False,
        resource__user=user,
    )


def _make_completed(resource, completed_at=None):
    """Create a completed unit with a controlled completed_at timestamp."""
    unit = baker.make(LearningUnit, resource=resource, status="completed")
    ts = completed_at or timezone.now()
    LearningUnit.objects.filter(pk=unit.pk).update(completed_at=ts)
    return unit


# ---------------------------------------------------------------------------
# get_dashboard_stats — top-level
# ---------------------------------------------------------------------------


class TestGetDashboardStatsReturnShape:
    def test_returns_all_required_keys(self, user, resource):
        result = get_dashboard_stats(user=user)

        expected_keys = {
            "total_resources",
            "total_units",
            "completed_units",
            "incomplete_units",
            "completion_rate",
            "resource_progress",
            "most_progress",
            "least_progress",
            "recent_resources",
            "active_filter",
            "resource_types_with_counts",
            "weekly_summary",
            "in_progress_count",
            "study_streak",
            "month_started",
            "month_finished",
            "weekly_activity",
            "backlog",
            "time_invested",
            "stale_resources",
            "momentum",
            "resources_table",
            "completed_resources_count",
            "resume_resource",
            # v6 session-driven keys
            "session_week_stats",
            "session_weekly_chart",
            "recent_sessions",
            "heatmap_sessions",
            "greeting_headline",
            "greeting_units",
            "greeting_sessions",
            "combined_study_time_this_week",
            "combined_study_time_this_week_html",
            "session_time_this_week",
            "resource_time_this_week",
        }
        assert expected_keys == set(result.keys())

    def test_empty_user_has_zero_counts(self, user):
        result = get_dashboard_stats(user=user)

        assert result["total_resources"] == 0
        assert result["total_units"] == 0
        assert result["completed_units"] == 0
        assert result["incomplete_units"] == 0
        assert result["completion_rate"] == 0

    def test_active_filter_reflects_passed_value(self, user):
        result = get_dashboard_stats(user=user, resource_type="video")
        assert result["active_filter"] == "video"

    def test_active_filter_none_by_default(self, user):
        result = get_dashboard_stats(user=user)
        assert result["active_filter"] is None


class TestGetDashboardStatsCounts:
    def test_counts_units_correctly(self, user, resource):
        baker.make(LearningUnit, resource=resource, status="completed", _quantity=2)
        baker.make(LearningUnit, resource=resource, status="not_started", _quantity=1)

        result = get_dashboard_stats(user=user)

        assert result["total_units"] == 3
        assert result["completed_units"] == 2
        assert result["incomplete_units"] == 1

    def test_excludes_archived_resource_units(self, user):
        archived = baker.make(LearningResource, user=user, is_archived=True)
        baker.make(LearningUnit, resource=archived, status="completed")

        result = get_dashboard_stats(user=user)

        assert result["total_units"] == 0

    def test_excludes_other_users_data(self, user):
        other = baker.make("auth.User")
        other_resource = baker.make(LearningResource, user=other, is_archived=False)
        baker.make(LearningUnit, resource=other_resource, status="completed")

        result = get_dashboard_stats(user=user)

        assert result["total_resources"] == 0
        assert result["total_units"] == 0

    def test_site_wide_stats_when_user_is_none(self, user):
        other = baker.make("auth.User")
        r1 = baker.make(LearningResource, user=user, is_archived=False)
        r2 = baker.make(LearningResource, user=other, is_archived=False)
        baker.make(LearningUnit, resource=r1, status="completed")
        baker.make(LearningUnit, resource=r2, status="completed")

        result = get_dashboard_stats(user=None)

        assert result["total_resources"] >= 2
        assert result["total_units"] >= 2


class TestGetDashboardStatsFiltering:
    def test_resource_type_filter_restricts_resources(self, user):
        rt_video, _ = ResourceType.objects.get_or_create(
            slug="youtube", defaults={"name": "YouTube", "content_kind": "video"}
        )
        rt_book, _ = ResourceType.objects.get_or_create(
            slug="book", defaults={"name": "Book", "content_kind": "reading"}
        )
        baker.make(
            LearningResource,
            user=user,
            resource_type=rt_video,
            is_archived=False,
        )
        baker.make(
            LearningResource,
            user=user,
            resource_type=rt_book,
            is_archived=False,
        )

        result = get_dashboard_stats(user=user, resource_type="youtube")

        assert result["total_resources"] == 1

    def test_resource_type_filter_restricts_units(self, user):
        rt_video, _ = ResourceType.objects.get_or_create(
            slug="youtube", defaults={"name": "YouTube", "content_kind": "video"}
        )
        rt_book, _ = ResourceType.objects.get_or_create(
            slug="book", defaults={"name": "Book", "content_kind": "reading"}
        )
        r_video = baker.make(
            LearningResource,
            user=user,
            resource_type=rt_video,
            is_archived=False,
        )
        r_book = baker.make(
            LearningResource,
            user=user,
            resource_type=rt_book,
            is_archived=False,
        )
        baker.make(LearningUnit, resource=r_video, status="completed")
        baker.make(LearningUnit, resource=r_book, status="completed")

        result = get_dashboard_stats(user=user, resource_type="youtube")

        assert result["total_units"] == 1


class TestGetDashboardStatsMostLeastProgress:
    def test_most_and_least_progress_none_when_no_resources(self, user):
        result = get_dashboard_stats(user=user)

        assert result["most_progress"] is None
        assert result["least_progress"] is None

    def test_most_progress_is_highest_percent(self, user):
        r1 = baker.make(LearningResource, user=user, is_archived=False)
        r2 = baker.make(LearningResource, user=user, is_archived=False)
        baker.make(LearningUnit, resource=r1, status="completed", _quantity=4)
        baker.make(LearningUnit, resource=r2, status="completed", _quantity=1)
        baker.make(LearningUnit, resource=r2, status="not_started", _quantity=3)

        result = get_dashboard_stats(user=user)

        assert result["most_progress"]["id"] == r1.id
        assert result["most_progress"]["percent"] == 100

    def test_least_progress_is_lowest_percent(self, user):
        r1 = baker.make(LearningResource, user=user, is_archived=False)
        r2 = baker.make(LearningResource, user=user, is_archived=False)
        baker.make(LearningUnit, resource=r1, status="completed", _quantity=4)
        baker.make(LearningUnit, resource=r2, status="not_started", _quantity=4)

        result = get_dashboard_stats(user=user)

        assert result["least_progress"]["id"] == r2.id
        assert result["least_progress"]["percent"] == 0


# ---------------------------------------------------------------------------
# _get_resource_types_with_counts
# ---------------------------------------------------------------------------


class TestGetResourceTypesWithCounts:
    def test_returns_empty_when_user_is_none(self):
        result = _get_resource_types_with_counts(user=None)
        assert result == []

    def test_returns_types_with_counts(self, user):
        rt = baker.make(ResourceType)
        baker.make(
            LearningResource,
            user=user,
            resource_type=rt,
            is_archived=False,
            _quantity=3,
        )

        result = _get_resource_types_with_counts(user=user)

        assert len(result) == 1
        assert result[0]["count"] == 3
        assert result[0]["type"] == rt

    def test_excludes_archived_resources_from_count(self, user):
        rt = baker.make(ResourceType)
        baker.make(LearningResource, user=user, resource_type=rt, is_archived=False)
        baker.make(LearningResource, user=user, resource_type=rt, is_archived=True)

        result = _get_resource_types_with_counts(user=user)

        assert result[0]["count"] == 1

    def test_excludes_other_users_resources(self, user):
        other = baker.make("auth.User")
        rt = baker.make(ResourceType)
        baker.make(LearningResource, user=other, resource_type=rt, is_archived=False)

        result = _get_resource_types_with_counts(user=user)

        assert result == []


# ---------------------------------------------------------------------------
# _get_weekly_summary
# ---------------------------------------------------------------------------


class TestGetWeeklySummary:
    def test_returns_zero_counts_with_no_data(self, user, resource):
        result = _get_weekly_summary(_user_unit_qs(user))

        assert result["units_completed"] == 0
        assert result["learning_time_minutes"] == 0
        assert result["resources_worked_on"] == 0

    def test_returns_7_daily_completions(self, user, resource):
        result = _get_weekly_summary(_user_unit_qs(user))
        assert len(result["daily_completions"]) == 7

    def test_daily_labels_are_mon_to_sun(self, user, resource):
        result = _get_weekly_summary(_user_unit_qs(user))
        labels = [d["label"] for d in result["daily_completions"]]
        assert labels == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    def test_counts_units_completed_this_week(self, user, resource):
        unit = baker.make(
            LearningUnit,
            resource=resource,
            status="completed",
            duration_minutes=30,
        )
        LearningUnit.objects.filter(pk=unit.pk).update(completed_at=timezone.now())

        result = _get_weekly_summary(_user_unit_qs(user))

        assert result["units_completed"] == 1
        assert result["learning_time_minutes"] == 30
        assert result["resources_worked_on"] == 1

    def test_excludes_completions_from_last_week(self, user, resource):
        now = timezone.localtime()
        current_week_start = (now - datetime.timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        last_week = current_week_start - datetime.timedelta(days=1)
        _make_completed(resource, completed_at=last_week)

        result = _get_weekly_summary(_user_unit_qs(user))

        assert result["units_completed"] == 0

    def test_resources_worked_on_counts_distinct_resources(self, user):
        r1 = baker.make(LearningResource, user=user, is_archived=False)
        r2 = baker.make(LearningResource, user=user, is_archived=False)
        now = timezone.now()
        _make_completed(r1, completed_at=now)
        _make_completed(r1, completed_at=now)
        _make_completed(r2, completed_at=now)

        result = _get_weekly_summary(_user_unit_qs(user))

        assert result["resources_worked_on"] == 2

    def test_learning_time_sums_duration_of_completed_units(self, user, resource):
        now = timezone.now()
        u1 = baker.make(
            LearningUnit, resource=resource, status="completed", duration_minutes=45
        )
        u2 = baker.make(
            LearningUnit, resource=resource, status="completed", duration_minutes=15
        )
        LearningUnit.objects.filter(pk__in=[u1.pk, u2.pk]).update(completed_at=now)

        result = _get_weekly_summary(_user_unit_qs(user))

        assert result["learning_time_minutes"] == 60
