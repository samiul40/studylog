from unittest.mock import MagicMock, patch

from learning.services.youtube import (
    MAX_PLAYLIST_UNITS,
    fetch_youtube_metadata,
)


def make_ydl(info):
    instance = MagicMock()
    instance.extract_info.return_value = info

    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=instance)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


class TestFetchYoutubeMetadataSingleVideo:
    @patch("learning.services.youtube.yt_dlp.YoutubeDL")
    def test_returns_one_unit(self, mock_class):
        mock_class.return_value = make_ydl({"title": "My Video", "duration": 360})

        result = fetch_youtube_metadata("https://youtube.com/watch?v=abc")

        assert result["is_playlist"] is False
        assert len(result["units"]) == 1

    @patch("learning.services.youtube.yt_dlp.YoutubeDL")
    def test_title_and_duration_are_correct(self, mock_class):
        mock_class.return_value = make_ydl({"title": "My Video", "duration": 360})

        result = fetch_youtube_metadata("https://youtube.com/watch?v=abc")

        assert result["title"] == "My Video"
        assert result["units"][0]["title"] == "My Video"
        assert result["units"][0]["duration_minutes"] == 6

    @patch("learning.services.youtube.yt_dlp.YoutubeDL")
    def test_duration_rounds_to_nearest_minute(self, mock_class):
        mock_class.return_value = make_ydl({"title": "Video", "duration": 95})

        result = fetch_youtube_metadata("https://youtube.com/watch?v=abc")

        assert result["units"][0]["duration_minutes"] == 2

    @patch("learning.services.youtube.yt_dlp.YoutubeDL")
    def test_duration_floors_at_one_minute(self, mock_class):
        mock_class.return_value = make_ydl({"title": "Short", "duration": 10})

        result = fetch_youtube_metadata("https://youtube.com/watch?v=abc")

        assert result["units"][0]["duration_minutes"] == 1

    @patch("learning.services.youtube.yt_dlp.YoutubeDL")
    def test_missing_duration_returns_none(self, mock_class):
        mock_class.return_value = make_ydl({"title": "Video", "duration": None})

        result = fetch_youtube_metadata("https://youtube.com/watch?v=abc")

        assert result["units"][0]["duration_minutes"] is None


class TestFetchYoutubeMetadataPlaylist:
    @patch("learning.services.youtube.yt_dlp.YoutubeDL")
    def test_returns_all_entries(self, mock_class):
        mock_class.return_value = make_ydl(
            {
                "_type": "playlist",
                "title": "My Playlist",
                "entries": [
                    {"title": "Video 1", "duration": 120},
                    {"title": "Video 2", "duration": 180},
                    {"title": "Video 3", "duration": 60},
                ],
            }
        )

        result = fetch_youtube_metadata("https://youtube.com/playlist?list=abc")

        assert result["is_playlist"] is True
        assert result["title"] == "My Playlist"
        assert len(result["units"]) == 3

    @patch("learning.services.youtube.yt_dlp.YoutubeDL")
    def test_capped_at_max_playlist_units(self, mock_class):
        entries = [
            {"title": f"Video {i}", "duration": 60}
            for i in range(MAX_PLAYLIST_UNITS + 10)
        ]
        mock_class.return_value = make_ydl(
            {
                "_type": "playlist",
                "title": "Big Playlist",
                "entries": entries,
            }
        )

        result = fetch_youtube_metadata("https://youtube.com/playlist?list=abc")

        assert len(result["units"]) == MAX_PLAYLIST_UNITS

    @patch("learning.services.youtube.yt_dlp.YoutubeDL")
    def test_none_entries_are_skipped(self, mock_class):
        mock_class.return_value = make_ydl(
            {
                "_type": "playlist",
                "title": "Playlist",
                "entries": [
                    {"title": "Video 1", "duration": 120},
                    None,
                    {"title": "Video 3", "duration": 60},
                ],
            }
        )

        result = fetch_youtube_metadata("https://youtube.com/playlist?list=abc")

        assert len(result["units"]) == 2

    @patch("learning.services.youtube.yt_dlp.YoutubeDL")
    def test_missing_title_falls_back_to_video_number(self, mock_class):
        mock_class.return_value = make_ydl(
            {
                "_type": "playlist",
                "title": "Playlist",
                "entries": [{"title": None, "duration": 60}],
            }
        )

        result = fetch_youtube_metadata("https://youtube.com/playlist?list=abc")

        assert result["units"][0]["title"] == "Video 1"

    @patch("learning.services.youtube.yt_dlp.YoutubeDL")
    def test_missing_duration_returns_none(self, mock_class):
        mock_class.return_value = make_ydl(
            {
                "_type": "playlist",
                "title": "Playlist",
                "entries": [{"title": "Video 1", "duration": None}],
            }
        )

        result = fetch_youtube_metadata("https://youtube.com/playlist?list=abc")

        assert result["units"][0]["duration_minutes"] is None
