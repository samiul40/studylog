import pytest
from model_bakery import baker

from learning.models import LearningResource, LearningUnit
from learning.services.progress import get_resource_progress

pytestmark = pytest.mark.django_db


@pytest.fixture
def resource(user):
    return baker.make(LearningResource, user=user)


class TestGetResourceProgress:
    def test_no_units(self, resource):
        result = get_resource_progress(resource)

        assert result["total_units"] == 0
        assert result["completed_units"] == 0
        assert result["remaining_units"] == 0
        assert result["completion_percentage"] == 0
        assert result["total_duration"] == 0
        assert result["completed_duration"] == 0
        assert result["remaining_duration"] == 0

    def test_all_completed(self, resource):
        baker.make(
            LearningUnit,
            resource=resource,
            status="completed",
            duration_minutes=30,
            _quantity=3,
        )

        result = get_resource_progress(resource)

        assert result["total_units"] == 3
        assert result["completed_units"] == 3
        assert result["remaining_units"] == 0
        assert result["completion_percentage"] == 100
        assert result["total_duration"] == 90
        assert result["completed_duration"] == 90
        assert result["remaining_duration"] == 0

    def test_partial_completion(self, resource):
        baker.make(
            LearningUnit, resource=resource, status="completed", duration_minutes=20
        )
        baker.make(
            LearningUnit, resource=resource, status="not_started", duration_minutes=40
        )

        result = get_resource_progress(resource)

        assert result["total_units"] == 2
        assert result["completed_units"] == 1
        assert result["remaining_units"] == 1
        assert result["completion_percentage"] == 33  # time-based: 20min / 60min
        assert result["total_duration"] == 60
        assert result["completed_duration"] == 20
        assert result["remaining_duration"] == 40

    def test_none_completed(self, resource):
        baker.make(
            LearningUnit,
            resource=resource,
            status="not_started",
            duration_minutes=10,
            _quantity=2,
        )

        result = get_resource_progress(resource)

        assert result["completed_units"] == 0
        assert result["completion_percentage"] == 0

    def test_units_ordered_by_order_field(self, resource):
        u2 = baker.make(LearningUnit, resource=resource, order=2, title="Second")
        u1 = baker.make(LearningUnit, resource=resource, order=1, title="First")

        result = get_resource_progress(resource)

        assert list(result["units"]) == [u1, u2]

    def test_units_with_null_duration_excluded_from_duration_totals(self, resource):
        baker.make(
            LearningUnit, resource=resource, status="completed", duration_minutes=None
        )

        result = get_resource_progress(resource)

        assert result["total_duration"] == 0
        assert result["completed_duration"] == 0

    def test_in_progress_video_minutes_counted_in_time_done(self, resource):
        baker.make(
            LearningUnit, resource=resource, status="completed", duration_minutes=10
        )
        baker.make(
            LearningUnit,
            resource=resource,
            duration_minutes=5,
            video_progress_minutes=2,
        )

        result = get_resource_progress(resource)

        assert result["total_duration"] == 15
        assert result["completed_duration"] == 12  # 10 (completed) + 2 (in-progress)
        assert result["remaining_duration"] == 3
