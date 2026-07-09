import datetime

from django.utils import timezone


def calculate_percentage(part: int, total: int) -> int:
    """
    Calculate percentage safely.

    Returns 0 if total is 0.
    """
    if not total:
        return 0

    return round((part / total) * 100)


def when_label(date: datetime.date, today: datetime.date) -> str:
    """Relative date label: "Today", "Yesterday", "3 days ago", "Due Monday", etc."""
    delta = (date - today).days
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Tomorrow"
    if delta == -1:
        return "Yesterday"
    if -7 < delta < -1:
        return f"{abs(delta)} days ago"
    if 1 < delta < 7:
        return f"Due {date.strftime('%A')}"
    return date.strftime("%-d %b")


def current_week_start() -> datetime.datetime:
    """Return midnight Monday of the current local week."""
    now = timezone.localtime()
    return (now - datetime.timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def fmt_duration(minutes: int) -> str:
    """Format minutes as '2h 10m' / '45m' / '—' for zero."""
    if not minutes:
        return "—"
    h, m = divmod(int(minutes), 60)
    if h and m:
        return f"{h}h {m}m"
    if h:
        return f"{h}h"
    return f"{m}m"


def fmt_duration_html(minutes: int) -> str:
    """Format minutes as HTML with <small> unit suffixes for stat card values."""
    if not minutes:
        return "—"
    h, m = divmod(int(minutes), 60)
    if h and m:
        return f"{h}<small>h</small> {m}<small>m</small>"
    if h:
        return f"{h}<small>h</small>"
    return f"{m}<small>m</small>"
