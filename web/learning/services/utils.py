import datetime


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
