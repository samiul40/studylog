import json
from unittest.mock import patch

import pytest
from django.urls import reverse

from learning.models import LearningResource, LearningUnit, ResourceType

pytestmark = pytest.mark.django_db

URL = reverse("learning:youtube_preview")


class TestYouTubePreviewView:
    def test_requires_login(self, client):
        response = client.post(
            URL,
            content_type="application/json",
            data=json.dumps({"url": "https://youtube.com/watch?v=abc"}),
        )

        assert response.status_code == 302

    def test_returns_metadata(self, client_logged_in):
        mock_data = {
            "title": "My Course",
            "is_playlist": True,
            "units": [{"title": "Intro", "duration_minutes": 5}],
        }

        with patch(
            "learning.views.youtube.fetch_youtube_metadata",
            return_value=mock_data,
        ):
            response = client_logged_in.post(
                URL,
                content_type="application/json",
                data=json.dumps({"url": "https://youtube.com/playlist?list=abc"}),
            )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "My Course"
        assert data["is_playlist"] is True
        assert len(data["units"]) == 1

    def test_missing_url_returns_400(self, client_logged_in):
        response = client_logged_in.post(
            URL,
            content_type="application/json",
            data=json.dumps({}),
        )

        assert response.status_code == 400
        assert "error" in response.json()

    def test_invalid_json_returns_400(self, client_logged_in):
        response = client_logged_in.post(
            URL,
            content_type="application/json",
            data="not-json",
        )

        assert response.status_code == 400
        assert "error" in response.json()

    def test_service_error_returns_400(self, client_logged_in):
        with patch(
            "learning.views.youtube.fetch_youtube_metadata",
            side_effect=Exception("Video unavailable"),
        ):
            response = client_logged_in.post(
                URL,
                content_type="application/json",
                data=json.dumps({"url": "https://youtube.com/watch?v=private"}),
            )

        assert response.status_code == 400
        assert response.json()["error"] == "Video unavailable"


class TestResourceCreateWithYouTubeUnits:
    def test_creates_units_from_youtube_data(self, client_logged_in, user):
        rt = ResourceType.objects.get(slug="udemy")
        units_data = [
            {"title": "Intro", "duration_minutes": 5},
            {"title": "Chapter 1", "duration_minutes": 12},
            {"title": "Chapter 2", "duration_minutes": None},
        ]

        response = client_logged_in.post(
            reverse("learning:resource_create"),
            {
                "title": "My YouTube Course",
                "resource_type": rt.pk,
                "description": "",
                "youtube_units": json.dumps(units_data),
            },
        )

        assert response.status_code == 302

        resource = LearningResource.objects.get(title="My YouTube Course", user=user)
        units = LearningUnit.objects.filter(resource=resource).order_by("order")

        assert units.count() == 3
        assert units[0].title == "Intro"
        assert units[0].duration_minutes == 5
        assert units[0].order == 1
        assert units[1].title == "Chapter 1"
        assert units[1].duration_minutes == 12
        assert units[2].title == "Chapter 2"
        assert units[2].duration_minutes is None

    def test_youtube_units_take_priority_over_unit_count(self, client_logged_in, user):
        rt = ResourceType.objects.get(slug="udemy")
        units_data = [{"title": "Only Unit", "duration_minutes": 10}]

        client_logged_in.post(
            reverse("learning:resource_create"),
            {
                "title": "Priority Test",
                "resource_type": rt.pk,
                "description": "",
                "unit_count": 5,
                "youtube_units": json.dumps(units_data),
            },
        )

        resource = LearningResource.objects.get(title="Priority Test", user=user)
        assert LearningUnit.objects.filter(resource=resource).count() == 1
