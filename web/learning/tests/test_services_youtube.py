from unittest.mock import MagicMock, patch

import pytest

from learning.services.youtube import (
    MAX_PLAYLIST_UNITS,
    _parse_iso_duration,
    fetch_youtube_metadata,
)


def mock_get(*responses):
    """Returns a side_effect list of mock responses for requests.get."""
    mocks = []
    for data in responses:
        m = MagicMock()
        m.json.return_value = data
        m.raise_for_status = MagicMock()
        mocks.append(m)
    return mocks


SINGLE_VIDEO_RESP = {
    "items": [
        {
            "id": "abc",
            "snippet": {"title": "My Video"},
            "contentDetails": {"duration": "PT6M0S"},
        }
    ]
}

PLAYLIST_RESP = {"items": [{"snippet": {"title": "My Playlist"}}]}

PLAYLIST_ITEMS_RESP = {
    "items": [
        {"snippet": {"title": "Video 1", "resourceId": {"videoId": "v1"}}},
        {"snippet": {"title": "Video 2", "resourceId": {"videoId": "v2"}}},
        {"snippet": {"title": "Video 3", "resourceId": {"videoId": "v3"}}},
    ]
}

DURATIONS_RESP = {
    "items": [
        {"id": "v1", "contentDetails": {"duration": "PT2M0S"}},
        {"id": "v2", "contentDetails": {"duration": "PT3M0S"}},
        {"id": "v3", "contentDetails": {"duration": "PT1M0S"}},
    ]
}


@pytest.mark.django_db
class TestFetchYoutubeMetadataSingleVideo:
    @patch("learning.services.youtube.requests.get")
    def test_returns_one_unit(self, mock_get_fn, settings):
        settings.YOUTUBE_API_KEY = "test-key"
        mock_get_fn.side_effect = mock_get(SINGLE_VIDEO_RESP)

        result = fetch_youtube_metadata("https://youtube.com/watch?v=abc")

        assert result["is_playlist"] is False
        assert len(result["units"]) == 1

    @patch("learning.services.youtube.requests.get")
    def test_title_and_duration_are_correct(self, mock_get_fn, settings):
        settings.YOUTUBE_API_KEY = "test-key"
        mock_get_fn.side_effect = mock_get(SINGLE_VIDEO_RESP)

        result = fetch_youtube_metadata("https://youtube.com/watch?v=abc")

        assert result["title"] == "My Video"
        assert result["units"][0]["title"] == "My Video"
        assert result["units"][0]["duration_minutes"] == 6

    @patch("learning.services.youtube.requests.get")
    def test_missing_api_key_raises(self, mock_get_fn, settings):
        settings.YOUTUBE_API_KEY = ""

        with pytest.raises(ValueError, match="not configured"):
            fetch_youtube_metadata("https://youtube.com/watch?v=abc")

    @patch("learning.services.youtube.requests.get")
    def test_video_not_found_raises(self, mock_get_fn, settings):
        settings.YOUTUBE_API_KEY = "test-key"
        mock_get_fn.side_effect = mock_get({"items": []})

        with pytest.raises(ValueError, match="not found"):
            fetch_youtube_metadata("https://youtube.com/watch?v=abc")

    def test_unrecognised_url_raises(self, settings):
        settings.YOUTUBE_API_KEY = "test-key"

        with pytest.raises(ValueError, match="Could not find"):
            fetch_youtube_metadata("https://example.com/not-youtube")


@pytest.mark.django_db
class TestFetchYoutubeMetadataPlaylist:
    @patch("learning.services.youtube.requests.get")
    def test_returns_all_entries(self, mock_get_fn, settings):
        settings.YOUTUBE_API_KEY = "test-key"
        mock_get_fn.side_effect = mock_get(
            PLAYLIST_RESP, PLAYLIST_ITEMS_RESP, DURATIONS_RESP
        )

        result = fetch_youtube_metadata("https://youtube.com/playlist?list=PLabc")

        assert result["is_playlist"] is True
        assert result["title"] == "My Playlist"
        assert len(result["units"]) == 3

    @patch("learning.services.youtube.requests.get")
    def test_titles_and_durations_are_correct(self, mock_get_fn, settings):
        settings.YOUTUBE_API_KEY = "test-key"
        mock_get_fn.side_effect = mock_get(
            PLAYLIST_RESP, PLAYLIST_ITEMS_RESP, DURATIONS_RESP
        )

        result = fetch_youtube_metadata("https://youtube.com/playlist?list=PLabc")

        assert result["units"][0]["title"] == "Video 1"
        assert result["units"][0]["duration_minutes"] == 2
        assert result["units"][1]["duration_minutes"] == 3

    @patch("learning.services.youtube.requests.get")
    def test_playlist_not_found_raises(self, mock_get_fn, settings):
        settings.YOUTUBE_API_KEY = "test-key"
        mock_get_fn.side_effect = mock_get({"items": []})

        with pytest.raises(ValueError, match="not found"):
            fetch_youtube_metadata("https://youtube.com/playlist?list=PLabc")

    @patch("learning.services.youtube.requests.get")
    def test_capped_at_max_playlist_units(self, mock_get_fn, settings):
        settings.YOUTUBE_API_KEY = "test-key"
        items = [
            {
                "snippet": {
                    "title": f"Video {i}",
                    "resourceId": {"videoId": f"v{i}"},
                }
            }
            for i in range(MAX_PLAYLIST_UNITS)
        ]
        durations = {
            "items": [
                {"id": f"v{i}", "contentDetails": {"duration": "PT1M0S"}}
                for i in range(MAX_PLAYLIST_UNITS)
            ]
        }
        mock_get_fn.side_effect = mock_get(PLAYLIST_RESP, {"items": items}, durations)

        result = fetch_youtube_metadata("https://youtube.com/playlist?list=PLabc")

        assert len(result["units"]) == MAX_PLAYLIST_UNITS


class TestParseIsoDuration:
    def test_minutes_only(self):
        assert _parse_iso_duration("PT4M") == 4

    def test_hours_and_minutes(self):
        assert _parse_iso_duration("PT1H30M") == 90

    def test_seconds_round_up(self):
        assert _parse_iso_duration("PT1M35S") == 2

    def test_seconds_only_floors_at_one(self):
        assert _parse_iso_duration("PT30S") == 1

    def test_zero_duration_returns_none(self):
        assert _parse_iso_duration("PT0S") is None

    def test_empty_string_returns_none(self):
        assert _parse_iso_duration("") is None

    def test_full_format(self):
        assert _parse_iso_duration("PT1H2M3S") == 62
