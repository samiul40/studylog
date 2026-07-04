import json

from django import template
from django.utils.safestring import mark_safe

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
def ring_offset(pct, circumference):
    """SVG stroke-dashoffset for a given circumference and percentage."""
    c = float(circumference)
    offset = c * (1 - (int(pct) if pct else 0) / 100)
    return f"{offset:.1f}"


@register.filter
def ring_offset_pct(done, total):
    """Return a 0-100 integer percentage given done/total minute values."""
    try:
        t = int(total or 0)
        d = int(done or 0)
        return min(100, round(d / t * 100)) if t else 0
    except (TypeError, ValueError, ZeroDivisionError):
        return 0


@register.filter
def tojson(value):
    """Serialize a Python value to a JSON literal, safe for inline <script>."""
    return mark_safe(json.dumps(value, ensure_ascii=False))
