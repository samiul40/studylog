import yt_dlp

MAX_PLAYLIST_UNITS = 50


def fetch_youtube_metadata(url: str) -> dict:
    """
    Returns title and a list of units (title + duration_minutes) for a YouTube
    URL — either a playlist or a single video.
    Raises yt_dlp.utils.DownloadError on invalid/private/unreachable URLs.
    """
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if info.get("_type") == "playlist":
        all_entries = info.get("entries") or []

        entries = []
        for entry in all_entries:
            if entry:
                entries.append(entry)
            if len(entries) == MAX_PLAYLIST_UNITS:
                break

        units = []
        for i, entry in enumerate(entries):
            units.append(
                {
                    "title": entry.get("title") or f"Video {i + 1}",
                    "duration_minutes": _to_minutes(entry.get("duration")),
                }
            )

        return {
            "title": info.get("title") or "",
            "is_playlist": True,
            "units": units,
        }

    return {
        "title": info.get("title") or "",
        "is_playlist": False,
        "units": [
            {
                "title": info.get("title") or "Video",
                "duration_minutes": _to_minutes(info.get("duration")),
            }
        ],
    }


def _to_minutes(seconds) -> int | None:
    if not seconds:
        return None
    return max(1, round(int(seconds) / 60))
