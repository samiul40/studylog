import math

from django import template

register = template.Library()


@register.filter
def format_duration(minutes):
    """Convert a total-minutes integer to a human-readable string.

    Examples: 0 → "0m", 45 → "45m", 90 → "1h 30m", 120 → "2h"
    """
    if not minutes:
        return "0m"
    hours, mins = divmod(int(minutes), 60)
    if hours and mins:
        return f"{hours}h {mins}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


@register.filter
def hours_from_minutes(minutes):
    """Whole-hours component of a minutes value. Returns 0 for falsy input."""
    if not minutes:
        return 0
    return int(minutes) // 60


@register.filter
def remaining_mins(minutes):
    """Sub-hour minutes component. Returns 0 for falsy input."""
    if not minutes:
        return 0
    return int(minutes) % 60


@register.filter
def ring_dashoffset(pct):
    """SVG stroke-dashoffset for a stroked ring with r=43 (C≈270.2)."""
    r = 43
    circumference = 2 * math.pi * r
    offset = circumference * (1 - (int(pct) if pct else 0) / 100)
    return f"{offset:.1f}"
