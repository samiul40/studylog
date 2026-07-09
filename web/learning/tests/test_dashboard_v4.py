"""Tests for v4 dashboard additions: completed_resources_count, resume_resource,
and the area chart coordinate builder."""

import pytest
from django.utils import timezone
from model_bakery import baker

from learning.models import LearningResource, LearningUnit
from learning.services.dashboard import (
    _get_completed_resources_count,
    _get_resume_resource,
)
from learning.views.dashboard import _build_sessions_area_chart

pytestmark = pytest.mark.django_db


@pytest.fixture
def resource(user):
    return baker.make(LearningResource, user=user, is_archived=False)


def _resource_qs(user):
    return LearningResource.objects.active().filter(user=user)


def _make_completed_unit(resource, completed_at=None):
    unit = baker.make(LearningUnit, resource=resource, status="completed")
    ts = completed_at or timezone.now()
    LearningUnit.objects.filter(pk=unit.pk).update(completed_at=ts)
    return unit


# ---------------------------------------------------------------------------
# _get_completed_resources_count
# ---------------------------------------------------------------------------


class TestGetCompletedResourcesCount:
    def test_zero_when_no_resources(self, user):
        assert _get_completed_resources_count(_resource_qs(user)) == 0

    def test_counts_resource_where_all_units_complete(self, user, resource):
        baker.make(LearningUnit, resource=resource, status="completed", _quantity=3)

        assert _get_completed_resources_count(_resource_qs(user)) == 1

    def test_excludes_resource_with_no_units(self, user, resource):
        # resource exists but has no units — not "completed"
        assert _get_completed_resources_count(_resource_qs(user)) == 0

    def test_excludes_partially_complete_resource(self, user, resource):
        baker.make(LearningUnit, resource=resource, status="completed")
        baker.make(LearningUnit, resource=resource, status="not_started")

        assert _get_completed_resources_count(_resource_qs(user)) == 0

    def test_excludes_resource_with_only_not_started_units(self, user, resource):
        baker.make(LearningUnit, resource=resource, status="not_started", _quantity=2)

        assert _get_completed_resources_count(_resource_qs(user)) == 0

    def test_counts_multiple_completed_resources(self, user):
        r1 = baker.make(LearningResource, user=user, is_archived=False)
        r2 = baker.make(LearningResource, user=user, is_archived=False)
        baker.make(LearningUnit, resource=r1, status="completed")
        baker.make(LearningUnit, resource=r2, status="completed")

        assert _get_completed_resources_count(_resource_qs(user)) == 2

    def test_mixed_resources_counts_only_finished_ones(self, user):
        r_done = baker.make(LearningResource, user=user, is_archived=False)
        r_partial = baker.make(LearningResource, user=user, is_archived=False)
        baker.make(LearningUnit, resource=r_done, status="completed")
        baker.make(LearningUnit, resource=r_partial, status="completed")
        baker.make(LearningUnit, resource=r_partial, status="not_started")

        assert _get_completed_resources_count(_resource_qs(user)) == 1


# ---------------------------------------------------------------------------
# _get_resume_resource
# ---------------------------------------------------------------------------


class TestGetResumeResource:
    def test_none_when_no_resources(self, user):
        assert _get_resume_resource(_resource_qs(user)) is None

    def test_none_when_no_units(self, user, resource):
        assert _get_resume_resource(_resource_qs(user)) is None

    def test_none_when_only_not_started_units(self, user, resource):
        baker.make(LearningUnit, resource=resource, status="not_started")
        assert _get_resume_resource(_resource_qs(user)) is None

    def test_none_when_all_resources_fully_complete(self, user, resource):
        baker.make(LearningUnit, resource=resource, status="completed", _quantity=2)
        assert _get_resume_resource(_resource_qs(user)) is None

    def test_returns_in_progress_resource(self, user, resource):
        _make_completed_unit(resource)
        baker.make(LearningUnit, resource=resource, status="not_started")

        result = _get_resume_resource(_resource_qs(user))

        assert result is not None
        assert result["title"] == resource.title

    def test_returns_expected_fields(self, user, resource):
        _make_completed_unit(resource)
        baker.make(LearningUnit, resource=resource, status="not_started")

        result = _get_resume_resource(_resource_qs(user))

        for field in (
            "title",
            "type_name",
            "type_slug",
            "content_kind",
            "pct",
            "completed_units",
            "total_units",
            "url",
        ):
            assert field in result, f"missing field: {field}"

    def test_pct_calculated_correctly(self, user, resource):
        _make_completed_unit(resource)
        _make_completed_unit(resource)
        baker.make(LearningUnit, resource=resource, status="not_started", _quantity=2)

        result = _get_resume_resource(_resource_qs(user))

        assert result["pct"] == 50
        assert result["completed_units"] == 2
        assert result["total_units"] == 4

    def test_returns_most_recently_active_resource(self, user):
        older = baker.make(LearningResource, user=user, is_archived=False)
        newer = baker.make(LearningResource, user=user, is_archived=False)

        now = timezone.now()
        import datetime

        yesterday = now - datetime.timedelta(days=1)

        _make_completed_unit(older, completed_at=yesterday)
        baker.make(LearningUnit, resource=older, status="not_started")
        _make_completed_unit(newer, completed_at=now)
        baker.make(LearningUnit, resource=newer, status="not_started")

        result = _get_resume_resource(_resource_qs(user))

        assert result["title"] == newer.title

    def test_ignores_fully_completed_resource_alongside_in_progress(self, user):
        done = baker.make(LearningResource, user=user, is_archived=False)
        partial = baker.make(LearningResource, user=user, is_archived=False)
        baker.make(LearningUnit, resource=done, status="completed")
        _make_completed_unit(partial)
        baker.make(LearningUnit, resource=partial, status="not_started")

        result = _get_resume_resource(_resource_qs(user))

        assert result["title"] == partial.title


# ---------------------------------------------------------------------------
# _build_sessions_area_chart
# ---------------------------------------------------------------------------


class TestBuildAreaChart:
    def _make_activity(self, counts):
        return [
            {"count": c, "label": f"Week {i + 1}", "is_current": i == len(counts) - 1}
            for i, c in enumerate(counts)
        ]

    def test_returns_none_for_empty_list(self):
        assert _build_sessions_area_chart([]) is None

    def test_returns_none_for_none(self):
        assert _build_sessions_area_chart(None) is None

    def test_has_data_false_when_all_zero(self):
        activity = self._make_activity([0, 0, 0, 0, 0, 0, 0, 0])
        result = _build_sessions_area_chart(activity)
        assert result["has_data"] is False

    def test_has_data_true_when_any_nonzero(self):
        activity = self._make_activity([0, 0, 0, 0, 0, 11, 5, 1])
        result = _build_sessions_area_chart(activity)
        assert result["has_data"] is True

    def test_returns_required_keys(self):
        activity = self._make_activity([0, 0, 0, 0, 0, 11, 5, 1])
        result = _build_sessions_area_chart(activity)
        for key in ("line_d", "area_d", "points", "y_base", "has_data"):
            assert key in result, f"missing key: {key}"

    def test_points_length_matches_input(self):
        activity = self._make_activity([0, 0, 0, 0, 0, 11, 5, 1])
        result = _build_sessions_area_chart(activity)
        assert len(result["points"]) == 8

    def test_first_point_x_is_20(self):
        activity = self._make_activity([1, 2, 3, 4, 5, 6, 7, 8])
        result = _build_sessions_area_chart(activity)
        assert result["points"][0]["x"] == 20.0

    def test_last_point_x_is_780(self):
        activity = self._make_activity([1, 2, 3, 4, 5, 6, 7, 8])
        result = _build_sessions_area_chart(activity)
        assert result["points"][-1]["x"] == 780.0

    def test_max_value_point_reaches_y_top(self):
        # The highest count should map to Y=20 (top of chart)
        activity = self._make_activity([0, 0, 0, 0, 0, 11, 0, 0])
        result = _build_sessions_area_chart(activity)
        peak = next(p for p in result["points"] if p["count"] == 11)
        assert peak["y"] == 20.0

    def test_zero_count_points_at_baseline(self):
        activity = self._make_activity([0, 0, 0, 0, 0, 11, 0, 0])
        result = _build_sessions_area_chart(activity)
        baseline = result["y_base"]
        zero_points = [p for p in result["points"] if p["count"] == 0]
        for p in zero_points:
            assert p["y"] == baseline

    def test_line_d_starts_with_M(self):
        activity = self._make_activity([0, 0, 0, 0, 0, 11, 5, 1])
        result = _build_sessions_area_chart(activity)
        assert result["line_d"].startswith("M")

    def test_area_d_ends_with_Z(self):
        activity = self._make_activity([0, 0, 0, 0, 0, 11, 5, 1])
        result = _build_sessions_area_chart(activity)
        assert result["area_d"].endswith("Z")

    def test_point_labels_match_input(self):
        activity = self._make_activity([1, 2, 3])
        result = _build_sessions_area_chart(activity)
        assert result["points"][0]["label"] == "Week 1"
        assert result["points"][2]["label"] == "Week 3"
