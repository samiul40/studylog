import re
from urllib.parse import parse_qs, urlparse

import requests
from django.conf import settings

MAX_PLAYLIST_UNITS = 50
_YT_API = "https://www.googleapis.com/youtube/v3"


def fetch_youtube_metadata(url: str) -> dict:
    """
    Returns title and a list of units (title + duration_minutes) for a YouTube
    URL — either a playlist or a single video.
    Raises ValueError for bad URLs or missing config.
    Raises requests.HTTPError on API errors.
    """
    api_key = settings.YOUTUBE_API_KEY
    if not api_key:
        raise ValueError("YouTube API key is not configured.")

    video_id, playlist_id = _extract_ids(url)

    if playlist_id:
        return _fetch_playlist(playlist_id, api_key)
    elif video_id:
        return _fetch_video(video_id, api_key)
    else:
        raise ValueError("Could not find a video or playlist ID in that URL.")


def _fetch_playlist(playlist_id: str, api_key: str) -> dict:
    """
    Fetches metadata for a YouTube playlist.
    Makes three API calls: one for the playlist title, one for the list of
    videos (titles + IDs), and one to batch-fetch durations for all videos.
    Returns the standard metadata dict with is_playlist=True.
    """
    playlist_response = requests.get(
        f"{_YT_API}/playlists",
        params={"part": "snippet", "id": playlist_id, "key": api_key},
        timeout=10,
    )
    playlist_response.raise_for_status()
    playlist_items = playlist_response.json().get("items", [])
    if not playlist_items:
        raise ValueError("Playlist not found.")

    playlist_title = playlist_items[0]["snippet"]["title"]

    playlist_videos_response = requests.get(
        f"{_YT_API}/playlistItems",
        params={
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": MAX_PLAYLIST_UNITS,
            "key": api_key,
        },
        timeout=10,
    )
    playlist_videos_response.raise_for_status()

    video_ids = []
    titles_by_id = {}
    for item in playlist_videos_response.json().get("items", []):
        snippet = item.get("snippet", {})
        vid_id = snippet.get("resourceId", {}).get("videoId")
        if vid_id:
            video_ids.append(vid_id)
            titles_by_id[vid_id] = snippet.get("title") or ""

    durations_by_id = _fetch_durations(video_ids, api_key)

    units = []
    for i, vid_id in enumerate(video_ids):
        units.append(
            {
                "title": titles_by_id.get(vid_id) or f"Video {i + 1}",
                "duration_minutes": durations_by_id.get(vid_id),
            }
        )

    return {
        "title": playlist_title,
        "is_playlist": True,
        "units": units,
    }


def _fetch_video(video_id: str, api_key: str) -> dict:
    """
    Fetches metadata for a single YouTube video.
    Makes one API call to retrieve the title and duration.
    Returns the standard metadata dict with is_playlist=False and one unit.
    """
    video_response = requests.get(
        f"{_YT_API}/videos",
        params={
            "part": "snippet,contentDetails",
            "id": video_id,
            "key": api_key,
        },
        timeout=10,
    )
    video_response.raise_for_status()
    items = video_response.json().get("items", [])
    if not items:
        raise ValueError("Video not found or is private.")

    item = items[0]
    title = item["snippet"]["title"]
    duration = _parse_iso_duration(item["contentDetails"]["duration"])

    return {
        "title": title,
        "is_playlist": False,
        "units": [{"title": title, "duration_minutes": duration}],
    }


def _fetch_durations(video_ids: list, api_key: str) -> dict:
    """
    Fetches durations for a list of video IDs in a single API call.
    Returns a dict of {video_id: duration_minutes}.
    """
    if not video_ids:
        return {}

    durations_response = requests.get(
        f"{_YT_API}/videos",
        params={
            "part": "contentDetails",
            "id": ",".join(video_ids),
            "key": api_key,
        },
        timeout=10,
    )
    durations_response.raise_for_status()

    result = {}
    for item in durations_response.json().get("items", []):
        vid_id = item["id"]
        result[vid_id] = _parse_iso_duration(item["contentDetails"]["duration"])
    return result


def _extract_ids(url: str) -> tuple:
    """Returns (video_id, playlist_id) parsed from a YouTube URL."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)

    if parsed.netloc in ("youtu.be",):
        video_id = parsed.path.lstrip("/") or None
    else:
        video_id = (qs.get("v") or [None])[0]

    playlist_id = (qs.get("list") or [None])[0]

    return video_id, playlist_id


def _parse_iso_duration(duration: str) -> int | None:
    """Converts ISO 8601 duration (e.g. 'PT4M13S') to whole minutes."""
    if not duration:
        return None
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    total_seconds = hours * 3600 + minutes * 60 + seconds
    if not total_seconds:
        return None
    return max(1, round(total_seconds / 60))
